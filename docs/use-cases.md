# Use Cases

## Local Validation
Run Python agent in read-once mode to quickly retireve telemetry.
```bash
sudo python tools/collectd-agent/pmt.py -s file:///path_to_repo_root/xml/pmt.xml -r
```

## Continuous Metrics Streaming
Use OpenTelemetry collector with Prometheus exporter for dashboard integration.
```bash
./otelcol-pmt --config tools/otel/configs/config-example-pmt-local.yaml
```

## Remote Metrics Streaming
Use OpenTelemetry collector in remote configuration.
```bash
./otelcol-pmt --config tools/otel/configs/config-example-pmt-redfish.yaml
```
