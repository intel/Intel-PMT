# Intel PMT Receiver

This repository contains Intel PMT Receiver and an example of custom OpenTelemetry Collector.

## Required Go version

This package was developed and tested with Go 1.24.4
https://go.dev/dl/

For Linux installation:
[How to install Go on Linux](https://golangdocs.com/install-go-linux)

## How to build

Download the OpenTelemetry Collector Builder from [opentelemetry-collector-releases repository](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/). Currently this code is tested with ocb v0.134.0 [OCB on Windows x86_64](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/cmd%2Fbuilder%2Fv0.134.0/ocb_0.134.0_windows_amd64.exe) and [OCB for Linux x86_64](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/cmd%2Fbuilder%2Fv0.134.0/ocb_0.134.0_linux_amd64)

If you want to run it with a different version of ocb you might need to change versions of dependencies in *build-config.yaml*.
When building on Windows, add the .exe suffix to the output file name in build-config.yaml (under dist->name)

Note: If it requires a proxy to connect to the internet, please set the http and https proxy environment variables accordingly.

Run the following command in the folder that contains the file *build-config.yaml* (tools/otel):

```bash
cd tools/otel
/path_to_ocb/ocb_exec --config build-config.yaml
```

Compilation process can take a few minutes. If you want to make it faster, remove unused dependencies from *build-config.yaml*

It will create a folder named *build* with some generated Go files. It then pulls the required dependencies and compiles an executable named *otelcol-pmt*.

## How to run custom OpenTelemetry Collector with PMT support

There are 2 configuration files in the *tools/otel/config* folder.

**config-example-pmt-redfish.yaml** is for collecting telemetry remotely through BMC.

**config-example-pmt-local.yaml** is for running the collector in local mode which requires access to the telemetry binary blobs.
These are provided by *intel_pmt* driver and on Linux they're visible under */sys/class/intel_pmt/*

Find **config-example-pmt-redfish.yaml** in *tools/otel/config* folder. Adjust the settings for the receiver:
- Set desired scraping interval
- You can rename *endpoint1* to label it accordingly or add more endpoints
- Set BMC IP and Base64 encoded credentials (replace bmc_ip and Somebase64encodedCredential)
- If needed you can choose to skip TLS certificate verification by adding:
```yaml
endpoint: ...
headers:
  Authorization: ...
tls:
  insecure_skip_verify: true
```

A simple trick to get Base64 credentials is to use curl in verbose mode to access BMC.

```bash
curl -v -k -u username:password https://bmc_ip/
```

This will show the HTTP headers sent by curl that include the Authorization header.

The Intel PMT XML files are included in the **xml** folder of this repository. Point the *metadata* property to the correct path of *pmt.xml*.

Note: If using a relative path to *pmt.xml* be careful where you're running the collector from.

Go to the *build* folder and run *otelcol-pmt* with your adjusted configuration.

```bash
cd build
otelcol-pmt --config ../config-example-pmt-redfish.yaml
```

We should see some debug logs printed out with the number of metrics being processed.
To disable these logs remove the debug exporter from the pipeline in the config.

```bash
2025-02-12T16:42:52.648-0700    info    service@v0.123.0/service.go:186 Setting up own telemetry...
2025-02-12T16:42:52.648-0700    info    builders/builders.go:26 Development component. May change in the future.       {"kind": "exporter", "data_type": "metrics", "name": "debug"}
2025-02-12T16:42:52.649-0700    info    service@v0.123.0/service.go:252 Starting otelcol-pmt.exe...     {"Version": "0.123.0-pmt", "NumCPU": 20}
2025-02-12T16:42:52.649-0700    info    extensions/extensions.go:39     Starting extensions...
2025-02-12T16:42:52.649-0700    info    otlpreceiver@v0.123.0/otlp.go:112       Starting GRPC server    {"kind": "receiver", "name": "otlp", "data_type": "metrics", "endpoint": "0.0.0.0:4317"}
2025-02-12T16:42:52.651-0700    info    service@v0.123.0/service.go:275 Everything is ready. Begin running and processing data.
2025-02-12T16:43:07.308-0700    info    Metrics {"kind": "exporter", "data_type": "metrics", "name": "debug", "resource metrics": 32098, "metrics": 32098, "data points": 32098}
```

To see the metrics reported by this agent, we can access the Prometheus exporter.

```bash
curl http://localhost:8889/metrics
```

It will produce lines of Prometheus/OpenMetrics report like the following snippet.

```bash
# HELP agg_data_loss_count_agg_data_loss_count Running count of processing cycles when the telemetry aggregator was unable to update all samples. Estimated maximum rate of change is 10000 per second. If the actual rate of change is zero, there is no data loss. Otherwise, other samples in this aggregator may report incorrect values for the duration of the data loss.
# TYPE agg_data_loss_count_agg_data_loss_count gauge
agg_data_loss_count_agg_data_loss_count{AccessId="248",AccessType="MCTP over PCIe",DeviceId="1",DeviceType="CPU",RedfishEndpoint="poland",SourceId="2",SourceType="Aggregator"} 0
agg_data_loss_count_agg_data_loss_count{AccessId="249",AccessType="MCTP over PCIe",DeviceId="1",DeviceType="CPU",RedfishEndpoint="poland",SourceId="2",SourceType="Aggregator"} 0
agg_data_loss_count_agg_data_loss_count{AccessId="25",AccessType="MCTP over PCIe",DeviceId="0",DeviceType="CPU",RedfishEndpoint="poland",SourceId="2",SourceType="Aggregator"} 0
agg_data_loss_count_agg_data_loss_count{AccessId="250",AccessType="MCTP over PCIe",DeviceId="1",DeviceType="CPU",RedfishEndpoint="poland",SourceId="2",SourceType="Aggregator"} 0
agg_data_loss_count_agg_data_loss_count{AccessId="26",AccessType="MCTP over PCIe",DeviceId="0",DeviceType="CPU",RedfishEndpoint="poland",SourceId="2",SourceType="Aggregator"} 0
agg_data_loss_count_agg_data_loss_count{AccessId="27",AccessType="MCTP over PCIe",DeviceId="0",DeviceType="CPU",RedfishEndpoint="poland",SourceId="2",SourceType="Aggregator"} 0
# HELP agg_data_loss_timestamp_agg_data_loss_timestamp Timestamp of last processing cycle when the telemetry aggregator was unable to update all samples. Reported in crystal clock TSC ticks (25MHz).
```
