// Copyright 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package intelpmtreceiver

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"path"
	"reflect"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/pmetric"
	"go.uber.org/zap"
)

// pmtCache contains all cached PMT metadata.
type pmtCache struct {
	commonCache              map[string]DataTypes
	aggregatorCache          map[string]Aggregator
	aggregatorInterfaceCache map[string]AggregatorInterface
}

func newPMTCache() *pmtCache {
	return &pmtCache{
		commonCache:              make(map[string]DataTypes),
		aggregatorCache:          make(map[string]Aggregator),
		aggregatorInterfaceCache: make(map[string]AggregatorInterface),
	}
}

type intelpmtreceiver struct {
	host        component.Host
	cancel      context.CancelFunc
	ctx         context.Context
	logger      *zap.Logger
	consumer    consumer.Metrics
	config      *Config
	httpClients map[string]*http.Client // Per-instance HTTP clients for different endpoints
	cache       *pmtCache
	lookupMap   PMTLookupMap
}

// commonAggregatorSetup contains the shared data setup for both local and redfish aggregators.
type commonAggregatorSetup struct {
	Common              DataTypes
	DataTypeMap         map[string]DataType
	Aggregator          Aggregator
	AggregatorInterface AggregatorInterface
}

// setMetricValue sets the appropriate numeric value on a datapoint based on the actual type of the value.
// Returns true if the value was successfully set, false if the type was unsupported.
func (ipr *intelpmtreceiver) setMetricValue(
	dataPoint pmetric.NumberDataPoint,
	value interface{},
	metricName string,
) bool {
	switch typedValue := value.(type) {
	case int64:
		dataPoint.SetIntValue(typedValue)
	case uint64:
		if typedValue > math.MaxInt64 {
			// Cannot represent exactly as int64; store as double to retain magnitude.
			dataPoint.SetDoubleValue(float64(typedValue))
		} else {
			dataPoint.SetIntValue(int64(typedValue))
		}
	case float64:
		dataPoint.SetDoubleValue(typedValue)
	case int:
		dataPoint.SetIntValue(int64(typedValue))
	case uint:
		safeVal := uint64(typedValue)
		if safeVal > math.MaxInt64 {
			// Cannot represent exactly as int64; store as double to retain magnitude.
			dataPoint.SetDoubleValue(float64(safeVal))
		} else {
			dataPoint.SetIntValue(int64(safeVal))
		}
	default:
		ipr.logger.Warn("Unsupported metric value type",
			zap.Any("type", reflect.TypeOf(value)),
			zap.String("metric", metricName))
		return false
	}
	return true
}

func (ipr *intelpmtreceiver) scrapeMetrics() pmetric.Metrics {
	var endpointAggregatorsMap map[string][]MetricAggregator
	metrics := pmetric.NewMetrics()

	switch ipr.config.Mode {
	case "redfish":
		endpointAggregatorsMap = ipr.getPMTRedfish()
	case "local":
		endpointAggregatorsMap = ipr.getPMTLocal()
	default:
		ipr.logger.Error("Unsupported mode in configuration", zap.String("mode", ipr.config.Mode))
		return metrics // Return empty metrics on error
	}

	// Create a separate resource for each endpoint
	for _, dataAggregators := range endpointAggregatorsMap {
		if len(dataAggregators) == 0 {
			continue // Skip endpoints with no aggregators
		}

		// Create resource/scope metrics for this endpoint
		scopeMetrics := metrics.ResourceMetrics().AppendEmpty().ScopeMetrics().AppendEmpty()

		// Process all aggregators for this endpoint
		for _, dataAggregator := range dataAggregators {
			collectionTimestamp, err := dataAggregator.GetCollectionTimestamp()
			if err != nil {
				ipr.logger.Warn("Failed to get collection timestamp", zap.Error(err))
				continue
			}

			var timestamp pcommon.Timestamp
			if collectionTimestamp > uint64(math.MaxInt64) {
				ipr.logger.Warn(
					"Clamping collection timestamp (seconds overflow)",
					zap.Uint64("collection_seconds", collectionTimestamp),
				)
				timestamp = pcommon.NewTimestampFromTime(time.Unix(math.MaxInt64, 0))
			} else {
				timestamp = pcommon.NewTimestampFromTime(time.Unix(int64(collectionTimestamp), 0))
			}

			processedValues := dataAggregator.Process(ipr.logger)
			for _, metricValue := range processedValues {
				metric := pmetric.NewMetric()
				metric.SetName(strings.ToLower(metricValue.Name))
				metric.SetDescription(metricValue.Description)
				metric.SetUnit(metricValue.Unit)
				var dataPoint pmetric.NumberDataPoint
				if metricValue.Type == "gauge" {
					dataPoint = metric.SetEmptyGauge().DataPoints().AppendEmpty()
					dataPoint.SetTimestamp(timestamp)
				} else {
					dataPoint = metric.SetEmptySum().DataPoints().AppendEmpty()
					metric.Sum().SetIsMonotonic(true)
					metric.Sum().SetAggregationTemporality(pmetric.AggregationTemporalityCumulative)
					dataPoint.SetStartTimestamp(timestamp)
					dataPoint.SetTimestamp(timestamp)
				}

				if !ipr.setMetricValue(dataPoint, metricValue.Value, metricValue.Name) {
					continue // Skip this metric if value type is unsupported
				}

				attributeMap := pcommon.NewMap()
				if err = attributeMap.FromRaw(dataAggregator.GetAttributes()); err != nil {
					ipr.logger.Warn("Failed to set attributes", zap.Error(err))
					continue
				}
				attributeMap.CopyTo(dataPoint.Attributes())

				newMetric := scopeMetrics.Metrics().AppendEmpty()
				metric.CopyTo(newMetric)
			}
		}
	}
	return metrics
}

func (ipr *intelpmtreceiver) initPMT() error {
	// init lookup map from metadata file
	metadataFile := ipr.config.Metadata
	if _, err := os.Stat(metadataFile); err != nil {
		return err
	}

	var metadata PMTMetadata
	err := GetPMTMetadata(metadataFile, &metadata)
	if err != nil {
		return err
	}
	// build lookup map
	ipr.lookupMap, err = BuildLookupMap(metadata, ipr.logger)

	return err
}

func (ipr *intelpmtreceiver) scrapeCycle() {
	startTime := time.Now()
	metrics := ipr.scrapeMetrics()
	scrapeDuration := time.Since(startTime)
	ipr.logger.Debug("Metrics scraped successfully",
		zap.Duration("scrape_time", scrapeDuration),
		zap.Int("metric_count", metrics.MetricCount()))
	if err := ipr.consumer.ConsumeMetrics(ipr.ctx, metrics); err != nil {
		ipr.logger.Error("Failed to consume metrics", zap.Error(err))
	}
}

func (ipr *intelpmtreceiver) Start(ctx context.Context, host component.Host) error {
	// initialization
	err := ipr.initPMT()
	if err != nil {
		ipr.logger.Error("Failed to initialize PMT metadata", zap.Error(err))
		return err
	}

	ipr.host = host
	ipr.ctx, ipr.cancel = context.WithCancel(ctx)
	interval, err := time.ParseDuration(ipr.config.Interval)
	if err != nil {
		return fmt.Errorf("invalid interval duration '%s': %w", ipr.config.Interval, err)
	}
	go func() {
		// Perform an initial scrape immediately
		ipr.scrapeCycle()

		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				ipr.scrapeCycle()
			case <-ipr.ctx.Done():
				return
			}
		}
	}()

	return nil
}
func (ipr *intelpmtreceiver) Shutdown(_ context.Context) error {
	// Cancel the context to stop the scraping goroutine
	if ipr.cancel != nil {
		ipr.cancel()
	}

	// Close all HTTP clients
	for _, client := range ipr.httpClients {
		if client != nil {
			client.CloseIdleConnections()
		}
	}

	return nil
}

// setupAggregatorComponents loads and caches the common XML components needed by aggregators.
func (ipr *intelpmtreceiver) setupAggregatorComponents(xmlSet XMLSet) (*commonAggregatorSetup, error) {
	setup := &commonAggregatorSetup{}

	// Load common datatypes
	common, ok := ipr.cache.commonCache[xmlSet.Basedir]
	if !ok {
		common = DataTypes{}
		err := GetPMTCommonDatatypes(path.Join(xmlSet.Basedir, xmlSet.Common), &common)
		if err != nil {
			return nil, fmt.Errorf("failed to load common datatypes: %w", err)
		}
		ipr.cache.commonCache[xmlSet.Basedir] = common
	}
	setup.Common = common
	setup.DataTypeMap = make(map[string]DataType)
	for _, dataType := range common.DataTypes {
		setup.DataTypeMap[dataType.Name] = dataType
	}

	// Load aggregator
	aggregator, ok := ipr.cache.aggregatorCache[xmlSet.Basedir]
	if !ok {
		aggregator = Aggregator{}
		err := GetPMTAggregator(path.Join(xmlSet.Basedir, xmlSet.Aggregator), &aggregator)
		if err != nil {
			return nil, fmt.Errorf("failed to load aggregator: %w", err)
		}
		ipr.cache.aggregatorCache[xmlSet.Basedir] = aggregator
	}
	setup.Aggregator = aggregator

	// Load aggregator interface
	aggregatorInterface, ok := ipr.cache.aggregatorInterfaceCache[xmlSet.Basedir]
	if !ok {
		aggregatorInterface = AggregatorInterface{}
		err := GetPMTAggregatorInterface(path.Join(xmlSet.Basedir, xmlSet.AggregatorInterface), &aggregatorInterface)
		if err != nil {
			return nil, fmt.Errorf("failed to load aggregator interface: %w", err)
		}
		ipr.cache.aggregatorInterfaceCache[xmlSet.Basedir] = aggregatorInterface
	}
	setup.AggregatorInterface = aggregatorInterface

	return setup, nil
}

func (ipr *intelpmtreceiver) getPMTLocal() map[string][]MetricAggregator {
	// build a map of local aggregators, one resource per telemetry device
	decodableAggregatorsMap := make(map[string][]MetricAggregator)
	aggregatorMap, err := discoverLocalAggregator(ipr.config.Path)
	if err != nil {
		ipr.logger.Error("Failed to discover local aggregators",
			zap.Error(err))
		return map[string][]MetricAggregator{}
	}

	for deviceName, aggregatorInfo := range aggregatorMap {
		guid := aggregatorInfo.GUID
		size := aggregatorInfo.Size
		var xmlSet XMLSet
		xmlSet, err = FindXMLSetForGUIDSize(ipr.lookupMap, guid, size)
		if err != nil {
			ipr.logger.Warn("Failed to find XML set for aggregator",
				zap.String("device", deviceName),
				zap.Error(err))
			continue
		}
		var setup *commonAggregatorSetup
		if setup, err = ipr.setupAggregatorComponents(xmlSet); err != nil {
			ipr.logger.Warn("Failed to setup aggregator components",
				zap.String("guid", guid),
				zap.Uint64("size", size),
				zap.String("device", deviceName),
				zap.Error(err))
			continue
		}

		dataAggregator := LocalMetricAggregator{
			Common:              setup.Common,
			DataTypeMap:         setup.DataTypeMap,
			Aggregator:          setup.Aggregator,
			AggregatorInterface: setup.AggregatorInterface,
			GUID:                guid,
			CollectionTimestamp: aggregatorInfo.CollectionTimestamp,
			Path:                aggregatorInfo.Path,
			Size:                size,
			Data:                aggregatorInfo.Data,
			Attributes:          make(map[string]interface{}),
		}

		// add attributes
		dataAggregator.Attributes["telem"] = aggregatorInfo.Path
		dataAggregator.Attributes["device"] = deviceName
		for attributeKey, attributeValue := range aggregatorInfo.Attributes {
			if intValue, ok := attributeValue.(int64); ok {
				dataAggregator.Attributes[attributeKey] = intValue
			} else {
				dataAggregator.Attributes[attributeKey] = fmt.Sprintf("%+v", attributeValue)
			}
		}

		// Create a resource per device (e.g., "local.telem0", "local.telem1", etc.)
		resourceKey := fmt.Sprintf("local.%s", deviceName)
		decodableAggregatorsMap[resourceKey] = []MetricAggregator{dataAggregator}
	}

	return decodableAggregatorsMap
}

func discoverLocalAggregator(telemPath string) (map[string]LocalMetricAggregator, error) {
	aggregators := make(map[string]LocalMetricAggregator)

	entries, err := os.ReadDir(telemPath)
	if err != nil {
		return map[string]LocalMetricAggregator{}, err
	}

	// attributes
	attributes := make(map[string]interface{})
	hostname, err := os.Hostname()
	if err != nil {
		hostname = "unknown"
	}
	attributes["hostname"] = hostname

	for _, fileEntry := range entries {
		if !strings.HasPrefix(fileEntry.Name(), "telem") {
			continue
		}
		timestamp := time.Now().Unix()
		guidPath := path.Join(telemPath, fileEntry.Name(), "guid")
		var guidBytes []byte
		if guidBytes, err = os.ReadFile(guidPath); err != nil {
			continue
		}
		if len(guidBytes) == 0 {
			continue
		}
		stringGUID := string(guidBytes)
		// Remove trailing newline if present
		stringGUID = strings.TrimSuffix(stringGUID, "\n")
		// Ensure GUID has proper format (0x prefix)
		if !strings.HasPrefix(stringGUID, "0x") {
			continue
		}
		if len(stringGUID) < minGUIDLength {
			continue
		}
		var intGUID uint64
		if intGUID, err = strconv.ParseUint(stringGUID[2:], 16, 64); err == nil {
			stringGUID = fmt.Sprintf("0x%08x", intGUID)
		} else {
			continue
		}
		sizePath := path.Join(telemPath, fileEntry.Name(), "size")
		var sizeBytes []byte
		if sizeBytes, err = os.ReadFile(sizePath); err != nil {
			continue
		}
		if len(sizeBytes) == 0 {
			continue
		}
		sizeString := strings.TrimSuffix(string(sizeBytes), "\n")
		var sizeInt uint64
		if sizeInt, err = strconv.ParseUint(sizeString, 0, 64); err != nil {
			continue
		}
		telemFilePath := path.Join(telemPath, fileEntry.Name(), "telem")
		var binaryData []byte
		if binaryData, err = os.ReadFile(telemFilePath); err != nil {
			continue
		}
		localAggregator := LocalMetricAggregator{
			GUID:                stringGUID,
			CollectionTimestamp: strconv.FormatInt(timestamp, 10),
			Path:                telemFilePath,
			Size:                sizeInt,
			Attributes:          attributes,
			Data:                base64.StdEncoding.EncodeToString(binaryData),
		}
		aggregators[fileEntry.Name()] = localAggregator
	}

	return aggregators, nil
}

func (ipr *intelpmtreceiver) getPMTRedfish() map[string][]MetricAggregator {
	// Build a map of endpoint<->aggregators
	decodableAggregatorsMap := make(map[string][]MetricAggregator)

	for endpointLabel, remoteConfig := range ipr.config.RemoteConfig {
		aggregatorMap, err := ipr.discoverRedfishAggregator(endpointLabel, remoteConfig)
		if err != nil {
			ipr.logger.Error("Failed to discover aggregators for Redfish endpoint",
				zap.String("endpoint", endpointLabel),
				zap.Error(err))
			continue // Continue processing other endpoints
		}

		endpointAggregators := make([]MetricAggregator, 0)

		for _, aggregatorInfo := range aggregatorMap {
			guid := aggregatorInfo.GUID
			size := aggregatorInfo.Size
			var xmlSet XMLSet
			if xmlSet, err = FindXMLSetForGUIDSize(ipr.lookupMap, guid, size); err != nil {
				ipr.logger.Warn("Failed to find XML set for aggregator",
					zap.String("endpoint", endpointLabel),
					zap.Error(err))
				continue
			}
			var setup *commonAggregatorSetup
			if setup, err = ipr.setupAggregatorComponents(xmlSet); err != nil {
				ipr.logger.Warn("Failed to setup aggregator components",
					zap.String("guid", guid),
					zap.Uint64("size", size),
					zap.String("endpoint", endpointLabel),
					zap.Error(err))
				continue
			}

			dataAggregator := RedfishMetricAggregator{
				XMLSet:              xmlSet,
				Common:              setup.Common,
				DataTypeMap:         setup.DataTypeMap,
				Aggregator:          setup.Aggregator,
				AggregatorInterface: setup.AggregatorInterface,
				Attributes:          make(map[string]interface{}),
				Data:                aggregatorInfo.Data,
				CollectionTimestamp: aggregatorInfo.CollectionTimestamp,
				GUID:                aggregatorInfo.GUID,
				Size:                aggregatorInfo.Size,
			}

			// add attributes
			dataAggregator.Attributes["RedfishEndpoint"] = endpointLabel
			for attributeKey, attributeValue := range aggregatorInfo.Attributes {
				if intValue, ok := attributeValue.(int64); ok {
					dataAggregator.Attributes[attributeKey] = intValue
				} else {
					dataAggregator.Attributes[attributeKey] = fmt.Sprintf("%+v", attributeValue)
				}
			}
			endpointAggregators = append(endpointAggregators, dataAggregator)
		}

		// Only add to map if we have aggregators for this label
		if len(endpointAggregators) > 0 {
			decodableAggregatorsMap[endpointLabel] = endpointAggregators
		}
	}
	return decodableAggregatorsMap
}

// getHTTPClient returns or creates an HTTP client for the given endpoint label.
func (ipr *intelpmtreceiver) getHTTPClient(
	endpointLabel string,
	clientConfig RedfishEndpointConfig,
) (*http.Client, error) {
	if existingClient, exists := ipr.httpClients[endpointLabel]; exists {
		return existingClient, nil
	}

	telemetrySettings := component.TelemetrySettings{}
	newClient, err := clientConfig.ToClient(context.Background(), nil, telemetrySettings)
	if err != nil {
		return nil, err
	}

	ipr.httpClients[endpointLabel] = newClient
	return newClient, nil
}

func (ipr *intelpmtreceiver) discoverRedfishAggregator(
	endpointLabel string,
	clientConfig RedfishEndpointConfig,
) (map[string]RedfishMetricAggregator, error) {
	client, err := ipr.getHTTPClient(endpointLabel, clientConfig)
	if err != nil {
		return map[string]RedfishMetricAggregator{}, err
	}

	var collectActionParam map[string]string

	if clientConfig.TriggerParameter != "" {
		triggerParam := map[string]string{}
		err = json.Unmarshal([]byte(clientConfig.TriggerParameter), &triggerParam)
		if err == nil {
			collectActionParam = triggerParam
		} else {
			return map[string]RedfishMetricAggregator{}, err
		}
	} else {
		collectActionParam = map[string]string{
			"TelemetryDataType":    "OEM",
			"OEMTelemetryDataType": "BulkTelemetrySnapshot",
		}
	}

	// perform triggeraction before collection
	if clientConfig.TriggerAction != "" {
		var payload []byte
		if payload, err = json.Marshal(collectActionParam); err != nil {
			return map[string]RedfishMetricAggregator{}, err
		}
		var postResponse *http.Response
		var postReq *http.Request
		if postReq, err = http.NewRequestWithContext(
			ipr.ctx,
			http.MethodPost,
			clientConfig.TriggerAction,
			bytes.NewBuffer(payload),
		); err != nil {
			return map[string]RedfishMetricAggregator{}, err
		}
		postReq.Header.Set("Content-Type", "application/json")
		if postResponse, err = client.Do(postReq); err != nil {
			return map[string]RedfishMetricAggregator{}, err
		}
		defer postResponse.Body.Close()

		// Check response status code
		if postResponse.StatusCode < 200 || postResponse.StatusCode >= 300 {
			return map[string]RedfishMetricAggregator{}, fmt.Errorf(
				"unexpected status code: %d, endpoint: %s",
				postResponse.StatusCode,
				endpointLabel,
			)
		}
	}

	// perform collection
	var response *http.Response
	getReq, err := http.NewRequestWithContext(ipr.ctx, http.MethodGet, clientConfig.Endpoint, nil)
	if err != nil {
		return map[string]RedfishMetricAggregator{}, err
	}
	if response, err = client.Do(getReq); err != nil {
		return map[string]RedfishMetricAggregator{}, err
	}
	defer response.Body.Close()

	// Check HTTP status code
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return map[string]RedfishMetricAggregator{}, fmt.Errorf(
			"unexpected status code: %d, endpoint: %s",
			response.StatusCode,
			endpointLabel,
		)
	}

	responseBytes, err := io.ReadAll(response.Body)
	if err != nil {
		return map[string]RedfishMetricAggregator{}, err
	}
	// grab the telemetry data
	var telemetryData RedfishTelemetryData
	if err = json.Unmarshal(responseBytes, &telemetryData); err != nil {
		return map[string]RedfishMetricAggregator{}, fmt.Errorf("error: %w, response: %s", err, string(responseBytes))
	}

	aggregators := make(map[string]RedfishMetricAggregator)

	for index, redfishAggregator := range telemetryData.TelemetryData {
		aggregatorData := RedfishMetricAggregator{
			GUID:                strings.ToLower(redfishAggregator.GUID),
			Size:                redfishAggregator.Size,
			Attributes:          redfishAggregator.Attributes,
			Data:                redfishAggregator.Data,
			CollectionTimestamp: redfishAggregator.CollectionTimestamp,
		}
		indexKey := fmt.Sprintf("telem%d", index)
		aggregators[indexKey] = aggregatorData
	}

	return aggregators, nil
}
