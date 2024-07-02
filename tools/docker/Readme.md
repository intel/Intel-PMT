# Docker image for Intel PMT Telemetry data collection with OpenTelemetry Collector Contrib

## Scope of this document

This document explains how to build and to run a container image using Docker which will allow Intel PMT Telemetry collection using reference Python script, piping the data to carbon receiver of OpenTelemetry Collector Contrib and then exposing it over Prometheus. End user implementation could then expand from this reference sample fitting their observability requirements.

## Building container image

### Assumption

This requires a fully working Docker installation on Linux-based system. Please refer to <https://docs.docker.com/engine/install/>

### Pre-requisite

This process requires a binary copy of **otelcol-contrib** from OpenTelemetry Collector Contrib Release (<https://github.com/open-telemetry/opentelemetry-collector-releases/releases>). Please download **otelcol-contrib_xxxx_linux_amd64.tar.gz**, uncompress the file and copy **otelcol-contrib** into folder tools/docker (the folder of this Readme.md).

### Build process

Go to the top of this repository and execute:

```bash
chmod a+x tools/docker/entrypoint.sh
docker build -f tools/docker/Dockerfile -t pmt .
```

This will build a container image named **pmt** in your local Docker image library

## Running pmt container image

This container requires exposure of host **/sys** folder to container under **/hostfs/sys** mount point. Here is an example of how to run it.

```bash
docker run -d -h container-hostname -p 9100:9100 -v /sys:/hostfs/sys --name pmt-container pmt
```

To verify if the container is running and collecting data, a simple Prometheus metrics pull can be done to verify it.

```bash
curl http://localhost:9100/metrics

```
