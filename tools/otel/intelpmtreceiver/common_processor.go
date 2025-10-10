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
	"encoding/base64"
	"encoding/binary"
	"strings"

	"go.uber.org/zap"
)

// processAggregatorData contains the common logic for processing telemetry data
// shared between local and redfish aggregators.
func processAggregatorData(
	data string,
	aggregator Aggregator,
	aggregatorInterface AggregatorInterface,
	dataTypeMap map[string]DataType,
	logger *zap.Logger,
) map[string]MetricValue {
	values := make(map[string]MetricValue)
	rawValues := make(map[string]uint64)

	telemBytes, err := base64.StdEncoding.DecodeString(data)
	if err != nil {
		logger.Warn("Failed to decode telemetry data", zap.Error(err))
		return values
	}

	// Extract raw values from binary data
	for _, sampleGroup := range aggregator.SampleGroup {
		for _, sample := range sampleGroup.Sample {
			if uint64(len(telemBytes)) < sample.CalculatedByteOffset+sampleSizeBytes {
				logger.Warn("Insufficient telemetry data",
					zap.String("sample_id", sample.SampleID),
					zap.Int("data_length", len(telemBytes)),
					zap.Uint64("required_offset", sample.CalculatedByteOffset+sampleSizeBytes))
				break
			}
			container := binary.LittleEndian.Uint64(
				telemBytes[sample.CalculatedByteOffset : sample.CalculatedByteOffset+sampleSizeBytes],
			)
			rawValues[sample.SampleID] = (container & sample.CalculatedMask) >> sample.Lsb
		}
	}

	// Process formulas and calculate metrics
	for _, sampleParam := range aggregatorInterface.AggregatorSamples.AggregatorSample {
		if ReservedRegex.MatchString(sampleParam.SampleName) {
			continue
		}

		params := make(map[string]interface{})
		allInputsFound := true

		for _, input := range sampleParam.TransformInputs.TransformInput {
			if _, ok := rawValues[input.SampleIDREF]; !ok {
				logger.Warn("Sample ID not found",
					zap.String("sample_id", input.SampleIDREF),
					zap.String("sample_name", sampleParam.SampleName))
				allInputsFound = false
				break
			}
			params[input.VarName] = rawValues[input.SampleIDREF]
		}

		if !allInputsFound {
			continue
		}

		var result interface{}
		if result, err = eval(sampleParam.TransformFormula, params); err != nil {
			logger.Warn("Error during evaluation of sample",
				zap.String("sample_name", sampleParam.SampleName),
				zap.Error(err))
			continue
		}

		name := sampleParam.SampleGroup + "." + sampleParam.SampleName
		metricType := "gauge"

		if sampleParam.SampleType == "Counter" {
			metricType = "counter"
			// use SampleName only for counter
			name = sampleParam.SampleName
		}

		// replace array index with dot notation
		name = strings.ReplaceAll(name, "[", ".")
		name = strings.ReplaceAll(name, "]", "")

		unit := ""
		if dataType, ok := dataTypeMap[sampleParam.DatatypeIDRef]; ok {
			unit = dataType.Unit.Name
		}

		values[name] = MetricValue{
			Name:        name,
			Type:        metricType,
			Description: sampleParam.Description,
			Unit:        unit,
			Value:       result,
		}
	}

	return values
}
