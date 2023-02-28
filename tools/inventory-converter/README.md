# Intel PMT Inventory Converter

Tool intended to convert official Intel PMT XMLs into flattened Avro binary
file. The Avro file contains minimal subset of information stored in these XMLs.

## How to use it?

### Dependencies

- Given - already provided
  - Intel PMT Telemetry Semantic Space XMLs
    - Available at [Intel-PMT](https://github.com/intel/Intel-PMT/tree/master/xml/)
    - Choose subdirectory containing ${name}_aggregator_interface.xml suitable for
      device you want to be observed
  - Intel PMT Aggregator Avro Schema
    - Available at `schemas/AggregatorSchema.avsc`
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
how it should handle them.

Currently supported extensions inform Avro file consumer about:

- Sensor type mapping (see enum `SensorTypes` in 
  `schemas/AggregatorSchema.avsc`)
- Whether given metric should be available through push model (over stream)

Format of such YAML metadata file is the following:

```yaml
# (...)
2304: # Identifies sampleID attribute from $(name)_aggregator_interface.xml
    type: "Temperature" # Maps to one of available Sensor types
    stream: True # Configures wether metric should be published using push model 
2305:
    type: "Power"
    stream: False
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
                    -o $(output_file).avro

# Where each $(name) shall be replaced with proper path to input file
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

- avroSchema: "path/to/schema.avsc"
  telemetryInterfaceXml: "path/to/telemetry_interface.xml"
  sensorTypeYaml: "path/to/sensorTypes.yaml"
  output: "path/to/output.avro"

# (...)
```

You can provide the required options here and then call once:

```bash
# example input
schema-generator -c examples/schema-generator-example.yaml
```
