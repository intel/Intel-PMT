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
	"context"
	"errors"
	"net/http"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/receiver"
)

const (
	defaultInterval = 5 * time.Second
)

func createDefaultConfig() component.Config {
	return &Config{
		Interval: defaultInterval.String(),
	}
}

func createMetricReceiver(
	_ context.Context,
	params receiver.Settings,
	baseCfg component.Config,
	consumer consumer.Metrics,
) (receiver.Metrics, error) {
	logger := params.Logger
	receiverConfig, ok := baseCfg.(*Config)
	if !ok {
		return nil, errors.New("failed to cast base config to *Config")
	}
	pmtReceiver := &intelpmtreceiver{
		logger:      logger,
		consumer:    consumer,
		config:      receiverConfig,
		httpClients: make(map[string]*http.Client),
		cache:       newPMTCache(),
	}
	return pmtReceiver, nil
}

func NewFactory() receiver.Factory {
	return receiver.NewFactory(
		component.MustNewType("intelpmtreceiver"),
		createDefaultConfig,
		receiver.WithMetrics(createMetricReceiver, component.StabilityLevelAlpha))
}
