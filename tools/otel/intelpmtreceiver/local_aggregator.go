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
	"strconv"

	"go.uber.org/zap"
)

type LocalMetricAggregator struct {
	GUID                string
	CollectionTimestamp string
	Size                uint64
	Path                string
	Attributes          map[string]interface{}
	Data                string
	// PMT specification associated with this aggregator
	XMLSet              XMLSet
	Common              DataTypes
	DataTypeMap         map[string]DataType
	Aggregator          Aggregator
	AggregatorInterface AggregatorInterface
}

type LocalTelemetryData struct {
	TelemetryData []LocalMetricAggregator `json:"TelemetryData"`
}

func (lma LocalMetricAggregator) Process(logger *zap.Logger) map[string]MetricValue {
	return processAggregatorData(
		lma.Data,
		lma.Aggregator,
		lma.AggregatorInterface,
		lma.DataTypeMap,
		logger,
	)
}

func (lma LocalMetricAggregator) GetAttributes() map[string]interface{} {
	return lma.Attributes
}

func (lma LocalMetricAggregator) GetCollectionTimestamp() (uint64, error) {
	return strconv.ParseUint(lma.CollectionTimestamp, 10, 64)
}
