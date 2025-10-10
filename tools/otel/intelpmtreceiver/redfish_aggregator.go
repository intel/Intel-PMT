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
	"errors"
	"strconv"

	"github.com/PaesslerAG/gval"
	"go.uber.org/zap"
)

type RedfishMetricAggregator struct {
	GUID                string                 `json:"Guid"`
	CollectionTimestamp string                 `json:"CollectionTimestamp"`
	Size                uint64                 `json:"Size"`
	Attributes          map[string]interface{} `json:"attributes"`
	Data                string                 `json:"Data"`

	// PMT specification associated with this aggregator
	XMLSet              XMLSet              `json:"-"`
	Common              DataTypes           `json:"-"`
	DataTypeMap         map[string]DataType `json:"-"`
	Aggregator          Aggregator          `json:"-"`
	AggregatorInterface AggregatorInterface `json:"-"`
}

type RedfishTelemetryData struct {
	TelemetryData []RedfishMetricAggregator `json:"TelemetryData"`
}

func hexToDec(hexStr string) string {
	dec, err := strconv.ParseUint(hexStr[2:], 16, 64)
	if err != nil {
		// Return original string if conversion fails - let caller handle the error
		return hexStr
	}
	ret := strconv.FormatUint(dec, 10)
	return ret
}

func eval(equation string, params map[string]interface{}) (interface{}, error) {
	if equation == "" {
		return nil, errors.New("no transformation equation found")
	}
	// gval doesn't support hexadecimals
	equation = HexToDecRegex.ReplaceAllStringFunc(equation, hexToDec)
	if equation == "" {
		return nil, errors.New("error during hex to decimal conversion")
	}
	result, err := gval.Evaluate(equation, params)
	if err != nil {
		return nil, err
	}
	return result, nil
}

func (rma RedfishMetricAggregator) Process(logger *zap.Logger) map[string]MetricValue {
	return processAggregatorData(
		rma.Data,
		rma.Aggregator,
		rma.AggregatorInterface,
		rma.DataTypeMap,
		logger,
	)
}

func (rma RedfishMetricAggregator) GetAttributes() map[string]interface{} {
	return rma.Attributes
}

func (rma RedfishMetricAggregator) GetCollectionTimestamp() (uint64, error) {
	return strconv.ParseUint(rma.CollectionTimestamp, 10, 64)
}
