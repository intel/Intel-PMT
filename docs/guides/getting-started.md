# Getting Started

## 1. Clone Repository
```bash
git clone https://github.com/intel/Intel-PMT.git
cd Intel-PMT
```

## 2. Identify Telemetry Sources
Local: Check `/sys/class/intel_pmt/` for `telem*` directories.
Remote (BMC): Ensure Redfish endpoint is reachable and credentials valid.

## 3. Run Python Agent
```bash
sudo python tools/collectd-agent/pmt.py -s file://$(pwd)/xml/pmt.xml -r
```
Add interval streaming:
```bash
sudo python tools/collectd-agent/pmt.py -s file://$(pwd)/xml/pmt.xml -i 10
```
Follow `tools/collectd-agent/Readme.md` for usage details.

## 4. Build OpenTelemetry Collector
Follow `tools/otel/Readme.md` to build `otelcol-pmt`.

## 5. Run Collector (Local Mode)
```bash
cd tools/otel/build
./otelcol-pmt --config ../configs/config-example-pmt-local.yaml
```

## 6. Verify Metrics
```bash
curl http://localhost:8889/metrics | head
```
