# Intel PMT Inventory Converter

Tool intended to convert official Intel PMT XMLs into flattened Avro binary
file. The Avro file contains minimal subset of information stored in these XMLs.

## How to use it?

### Version
Inventory-converter is versioned and currently support
2 versions: 0 and 1.
- Version 0 enables user to specify which
metrics publish using Redfish sensor.
- Version 1 extends user specifications to data sources selection and
  streaming through Kafka for specific metric.

Keep in mind that version distinguishes dependencies and each platform supports
one version. Versioning is not backwards compatible from the platform point of view.


### Dependencies

- Given - already provided
  - Intel PMT Telemetry Semantic Space XMLs
    - Available at [Intel-PMT](https://github.com/intel/Intel-PMT/tree/master/xml/)
    - Choose subdirectory containing ${name}_aggregator_interface.xml suitable for
      device you want to be observed
  - Intel PMT Aggregator Avro Schema avsc
    - Available at `schemas/`
    - Choose between `AggregatorSchemaVer0.avsc` and `AggregatorSchemaVer1.avsc` according to the version

- User defined - should be created by you
  - YAML with Metric metadata
    - User specified. Example file included in `./examples`.
      Described in detail [here](#yaml-with-metric-metadata)

Following graph shows conversion flow:

```
      ┌─────── Conversion input ─────────┐
      │                                  │
      ▼                                  ▼
┌────►
│
      ┌───┐                            ---------------------
P     │XML│                            |Describes available|
r     ├───┴──────────────────────────┐ |metrics            |
o     │ - *_aggregator_interface.xml │ ---------------------
v     │ - *_aggregator.xml           │
i     │ - *_common.xml               ├─────────────────────────────┐
d     └──────────────────────────────┘                             │
e                                                                  │
d     ┌────┐                  -----------------                    │
      │AVSC│                  |Describes .avro|                    │
b     ├────┴────────────────┐ |file format    |                    │
y     │ - .avsc schema file │ -----------------                    │
      └──────────────────┬──┘                                      │
I                        │                                         │
n                        └──────────────────────────────────────<input>
t                                                                  │
e                                                                  │
l                                                       ┌──────┐   │
                                                        │Python│   │
│                                                       ├──────┴───▼──────────┐
│              ┌─────────<user input>──────────────────►│ Inventory Converter │
│              │                                        └──────────┬──────────┘
└────►         │                                                   │
               │                                                   │
┌────►         │                                                   │
│              │                                               <creates>
      ┌────┐   │   ---------------------------                     │
U     │YAML│   │   |Describes desired metrics|                     │
s     ├────┴───┴─┐ |and monitoring params    |            ┌────┐   │
e     │ - *.yaml │ ---------------------------            │avro│   │
r     └──────────┘                                        ├────┴───▼─┐
                                                          │ - *.avro │
│                                                         └──────────┘
└────►                                        --------------------------------
                                              |Subset of XML filtered by YAML|
                                              |structured according to AVSC  |
                                              --------------------------------
```

### YAML with Metric metadata

This file contains list of metrics to be extracted from XML and extra metadata
not originally present in XMLs. It can be used by external software utilizing
generated Avro file to obtain extra information about metrics which controls
how it should handle them. It is recommended to not select metrics that are reserved.
Inventory-converter is versioned and currently support 2 versions of yaml.
Version 1 is an extension of the version 0.

#### YAML format for version 0
Currently supported extensions inform Avro file consumer about:

- Sensor type mapping (see enum `SensorTypes` in
  `schemas/AggregatorSchema.avsc`)
- Whether given metric should be available as Redfish sensor

Example of correct YAML metadata for version 0 looks like this:
```yaml
# (...)
2304: "Temperature" # Maps to one of available Sensor types
2305: "Power" # This metric will be published using Redfish sensor
# (...)
```
#### YAML format for version 1

Version 1 extends information from version 0 with:
- Whether given metric should be available through push model (over Kafka stream)
- Whether data source of this metric is Streaming watcher/Threshold watcher for Kafka stream and
  Streaming watcher/Threshold watcher/Aggregator for Redfish sensor

Keep in mind that there are some limitations for this yaml:
- Watcher is ignored for all destinations and shouldn't be used
- Kafka stream doesn't support Aggregator source
- If you provide in list more than one data source then only one data source will be streamed.
Data source will be chosen according to priority list:
  1. ThresholdWatcher,
  2. StreamingWatcher,
  3. Aggregator

Format of YAML metadata file in Version 1 is as following:

```yaml
# (...)
386: # Identifies sampleID attribute from $(name)_aggregator_interface.xml
    type: Count # Maps to one of available Sensor types
    kafkaStream:
      - StreamingWatcher # Configures whether metric should be published using push model
    redfishSensor:
      - Aggregator # Configures whether metric should be published using Redfish sensor
389:
    type: Count
    kafkaStream: # Empty list means that this metric won't be published using Kafka stream
    redfishSensor: # This metric won't be published using Redfish sensor
474:
    type: Count
    kafkaStream: # Metric will be published using Kafka Stream and
      - ThresholdWatcher # data source of this metric will be Threshold Watcher
    redfishSensor: # Metric will be published using Redfish Sensor and
      - StreamingWatcher  # data source of this metric will be Streaming Watcher
475:
    type: Count
    kafkaStream:
      - StreamingWatcher  # Data source of this metric will
      - ThresholdWatcher  # be Threshold Watcher
    redfishSensor:
      - StreamingWatcher  # Data source of this metric will
      - ThresholdWatcher  # be Threshold Watcher
      - Aggregator

# (...)
```

Example of WRONG YAML metadata for Version 1 is as following:
```yaml
# (...)
474: #WRONG YAML metadata !
    type: Count
    kafkaStream: # As aggregator cannot be data source of Kafka streaming
        - Aggregator # this config won't work
    redfishSensor: # Data source of Redfish sensor can be empty and it just means that
                   # this metric won't be published using Redfish sensor
# (...)
```

### Installing package

Inventory converter is delivered as Python package compatible with pip.
You can install it and its dependencies in your environment to use freely
in the system.

```bash
pip3 install .
```

## Running inventory converter

```bash
inventory-converter -i $(path_to_aggregator_interface).xml \
                    -s $(path_to_avro_schema).avsc \
                    -t $(path_to_metadata).yaml \
                    -o $(output_file).avro \
                    -v $(version)
# Where each $(name) shall be replaced with proper path to input file and
# for version with two possibles: 1 or 0.
```

### [Alternative] Run inventory converter in batch based on config

If you need to generate multiple files, you may find the below configuration
helpful.
`schema-generator` accepts input in following format:

```yaml
# (...)

- avroSchema: "path/to/schema.avsc"
  telemetryInterfaceXml: "path/to/telemetry_interface.xml"
  sensorTypeYaml: "path/to/sensorTypes.yaml"
  output: "path/to/output.avro"
  version: "inventory_converter_version"

- avroSchema: "path/to/schema.avsc"
  telemetryInterfaceXml: "path/to/telemetry_interface.xml"
  sensorTypeYaml: "path/to/sensorTypes.yaml"
  output: "path/to/output.avro"
  version: "inventory_converter_version"

# (...)
```

You can provide the required options here and then call once:

```bash
# example input
schema-generator -c examples/schema-generator-example.yaml
```
