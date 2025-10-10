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
	"time"

	"go.opentelemetry.io/collector/config/confighttp"
)

type RedfishEndpointConfig struct {
	// Location of Telemetry Data to collect.
	confighttp.ClientConfig `mapstructure:",squash"`

	// Action to trigger data collection.
	TriggerAction string `mapstructure:"trigger_action"`
	// Parameter to include in trigger action.
	TriggerParameter string `mapstructure:"trigger_param"`
}

type Config struct {
	Interval     string                           `mapstructure:"interval"`
	Metadata     string                           `mapstructure:"metadata"`
	Mode         string                           `mapstructure:"mode"`
	Path         string                           `mapstructure:"path"`
	RemoteConfig map[string]RedfishEndpointConfig `mapstructure:"endpoints"`
}

// Validate checks if the receiver configuration is valid.
func (cfg *Config) Validate() error {
	interval, _ := time.ParseDuration(cfg.Interval)
	if interval.Seconds() < minIntervalSeconds {
		return errors.New("when defined, the interval has to be set to at least 5 seconds (5s)")
	}
	if cfg.Mode != modeLocal && cfg.Mode != modeRedfish {
		return errors.New("must be either local or redfish")
	}
	if cfg.Mode == modeLocal && cfg.Path == "" {
		cfg.Path = "/sys/class/intel_pmt"
	}
	return nil
}
