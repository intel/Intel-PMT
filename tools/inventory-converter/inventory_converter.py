#!/usr/bin/env python3

# Copyright (C) 2021-2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
This module is an Avro payload generator for PMT sensors inventory.
Generated binary can be uploaded to the BMC.
"""
import os
import sys
import json
import struct
import argparse
import logging
import tokenize
from io import BytesIO
from pathlib import Path
from lxml import etree

import yaml

import avro.schema

from avro.io import DatumWriter
from avro.datafile import DataFileWriter
from avro.errors import AvroException

logger = logging.getLogger()


def opener(path, flags):
    return os.open(path, flags, 0o600)


def assert_is_not_symlink(path):
    if Path(path).is_symlink():
        raise IOError(
            f'Unable to open file at path {path}. Per security policy usage of symbolic links shall be avoided.')


class LocalResolver(etree.Resolver):
    """For safety ensures that all resolved files comes from the same directory."""

    def __init__(self, initial_path):
        self._initial_path = LocalResolver.parent_dir(initial_path)

    @staticmethod
    def parent_dir(path):
        return os.path.dirname(os.path.abspath(path))

    def resolve(self, url, id, context):
        if (LocalResolver.parent_dir(url) != self._initial_path):
            logger.exception(
                f'XML contains url to external entity which is disabled for safety purposes. Received url: {url} Trusted directory: {self._initial_path}')
            raise ValueError()
        return self.resolve_filename(url, context)


def try_load_aggregator_interface(interface_file):
    """Load XML file, parse and include external entities."""

    # Safety checks
    assert_is_not_symlink(interface_file)
    safeResolver = LocalResolver(interface_file)
    parserParams = {
        "no_network": True,
        "load_dtd": False,
        "resolve_entities": False
    }

    parser = etree.XMLParser(**parserParams)
    parser.resolvers.add(safeResolver)
    ag_iface = etree.parse(interface_file, parser)
    # Explicitly include other XML files.
    ag_iface.xinclude()
    return ag_iface.getroot()


def try_load_yaml_config(yaml_file_path):
    """Load YAML file."""
    assert_is_not_symlink(yaml_file_path)
    with yaml_file_path.open("r") as yaml_file:
        return yaml.load(yaml_file, Loader=yaml.SafeLoader)


def extract_namespaces(xml_data):
    """Extract XML namespaces, used for XPath traversal."""
    nsmap = {k if k is not None else 'default': v for k, v in xml_data.nsmap.items()}
    # Iterate over top-level elements, as some namespaces are included from other files.
    for top_element in xml_data:
        for key, value in top_element.nsmap.items():
            if key not in nsmap and key is not None:
                nsmap[key] = value
    return nsmap


def get_child_value(name, element, namespace, default=None):
    """Get value from named child of the element."""
    found = element.xpath(name, namespaces=namespace)
    if found is not None and len(found) > 0 and hasattr(found[0], "text"):
        return found[0].text
    return default


class InfixToPostfixTransformator:
    """Transform from infix to postfix format"""

    @staticmethod
    def is_token_valid(token):
        """Checks if token is valid"""
        if token['type'] in ('ENCODING', 'NEWLINE', 'ENDMARKER', 'INDENT', 'DEDENT'):
            return False
        if (token['type'] == 'ERRORTOKEN' and
                token['string'] == "$" or token['string'] == " "):
            return False
        return True

    def __init__(self, infix_form):
        logger.debug("Converting transformation: %s", infix_form)
        self.infix_form = infix_form
        tokenized_infix_form = tokenize.tokenize(
            BytesIO(infix_form.encode("utf-8")).readline)
        tokens = []
        for tok in tokenized_infix_form:
            tok_d = {'type': tokenize.tok_name[tok.type], 'string': tok.string}
            tokens.append(tok_d)

        for idx, val in enumerate(tokens):
            if val['string'] == "$" and idx < len(tokens) - 1:
                tokens[idx + 1]['string'] = '$' + tokens[idx + 1]['string']
                continue

        self.sanitized_tokens = [
            (tok['type'], tok['string']) for tok in tokens if self.is_token_valid(tok)
        ]

    def transform(self):
        """Transform from infix to postfix format"""
        t_output = []
        t_stack = []
        precedence = {
            "^": 0,
            "|": 0,
            "&": 1,
            ">>": 2,
            "<<": 3,
            "+": 4,
            "-": 4,
            "*": 5,
            "/": 5,
            "**": 6,
        }
        for token_type, token_value in self.sanitized_tokens:
            if token_type in ("NUMBER", "NAME"):
                t_output.append(token_value)
            elif token_value == ")":
                if not t_stack:
                    raise SyntaxError("Cannot parse transformation to RPN(unbalanced parens): "
                                      f"{self.infix_form}")
                while t_stack and t_stack[-1] != "(":
                    t_output.append(t_stack.pop())
                if t_stack[-1] != "(":
                    raise SyntaxError(
                        "Cannot parse transformation to RPN (unbalanced parens): "
                        f"{self.infix_form}")
                t_stack.pop()
            elif token_value == "(":
                t_stack.append(token_value)
            elif token_type == "OP" and token_value != ")":
                while (t_stack and
                       t_stack[-1] != "(" and
                       precedence[t_stack[-1]] >= precedence[token_value]):
                    t_output.append(t_stack.pop())
                t_stack.append(token_value)
            else:
                raise SyntaxError(
                    "Cannot parse transformation to RPN: "
                    f"{self.infix_form}. Token {token_type} = {token_value}")
        while t_stack:
            token = t_stack.pop()
            t_output.append(token)
        rpn = " ".join(t_output)
        logger.debug("RPN notation: %s", rpn)
        return rpn


def extract_sample_group(elem, agg_nsmap):
    """Extracts sample group from given element"""
    sample_group = {}
    sample_group["name"] = elem.get("name")
    sample_group["sampleId"] = int(elem.get("sampleID"))
    sample_group["sampleGroupId"] = elem.get("sampleGroupID")
    sample_group["description"] = get_child_value(
        "TELC:description", elem, agg_nsmap)
    sample_group["length"] = int(
        get_child_value("TELC:length", elem, agg_nsmap))
    sample_group["samples"] = {}
    for sample in elem.xpath("TELC:sample", namespaces=agg_nsmap):
        sample_dtc = {}
        sample_dtc["name"] = sample.get("name")
        sample_dtc["datatypeIDREF"] = sample.get("datatypeIDREF")
        sample_dtc["sampleId"] = sample.get("sampleID")
        sample_dtc["description"] = get_child_value(
            "TELC:description", sample, agg_nsmap)
        sample_dtc["sampleSubGroup"] = get_child_value(
            "TELC:sampleSubGroup", sample, agg_nsmap)
        sample_dtc["sampleType"] = get_child_value(
            "TELC:sampleType", sample, agg_nsmap)
        sample_dtc["size"] = int(get_child_value(
            "TELC:size", sample, agg_nsmap))
        sample_dtc["lsb"] = int(get_child_value(
            "TELC:lsb", sample, agg_nsmap))
        sample_dtc["msb"] = int(get_child_value(
            "TELC:msb", sample, agg_nsmap))
        if sample_dtc["sampleId"] in sample_group["samples"]:
            raise NameError(
                f"Duplicated sample ID {sample_dtc['sampleId']} "
                f"in group {sample_group['sampleGroupId']}.")
        sample_group["samples"][sample_dtc["sampleId"]] = sample_dtc
    return sample_group


def extract_metric(elem, agg_nsmap, sensor_types):
    """Extracts metric from given element"""
    sample_id = int(elem.get("sampleID"))
    metric = {}
    metric["name"] = elem.get("sampleName")
    metric["sampleGroup"] = elem.get("sampleGroup")
    metric["datatypeIDREF"] = elem.get("datatypeIDREF")
    metric["sampleId"] = sample_id
    metric["description"] = get_child_value(
        "TELI:description", elem, agg_nsmap)
    metric["sampleType"] = get_child_value(
        "TELI:SampleType", elem, agg_nsmap)
    if sample_id in sensor_types:
        metric["sensorType"] = sensor_types[sample_id]["type"]
        if bool(sensor_types[sample_id]["stream"]):
            metric["streamed"] = bool(sensor_types[sample_id]["stream"])
    metric["redfishURL"] = get_child_value(
        "TELI:redfish_url", elem, agg_nsmap)
    metric["transformation"] = get_child_value(
        "TELI:transformREF", elem, agg_nsmap)
    metric["inputs"] = {}
    for inp in elem.xpath("TELC:TransFormInputs/TELC:TransFormInput", namespaces=agg_nsmap):
        sample_input = {}
        sample_input["groupIDREF"] = get_child_value(
            "TELC:sampleGroupIDREF", inp, agg_nsmap)
        sample_input["sampleIDREF"] = get_child_value(
            "TELC:sampleIDREF", inp, agg_nsmap)
        metric["inputs"][inp.get("varName")] = sample_input
    return metric


def extract_aggregator(aggregator_interface, sensor_types):
    """Extract aggregator data and pack it into python structures."""
    agg_nsmap = extract_namespaces(aggregator_interface)
    aggregator = {}
    aggregator["name"] = get_child_value(
        "TELI:name", aggregator_interface, agg_nsmap)
    aggregator["description"] = get_child_value(
        "TELI:description", aggregator_interface, agg_nsmap)
    aggregator["uniqueId"] = struct.unpack('i', struct.pack('I', int(get_child_value(
        "TELI:uniqueid", aggregator_interface, agg_nsmap), 16)))[0]
    aggregator["NDA"] = get_child_value(
        "TELI:NDA", aggregator_interface, agg_nsmap)
    aggregator["samplePeriod"] = int(get_child_value(
        "TELI:samplePeriod", aggregator_interface, agg_nsmap))
    aggregator["metrics"] = {}
    aggregator["groups"] = {}
    logger.info(
        "Parsing Aggregator: %s[%x]", aggregator['name'], aggregator['uniqueId'])

    logger.debug(aggregator)

    # Iterate over SampleGroups and their Samples (low level mapping):
    direct_samples = 0
    for elem in aggregator_interface.xpath("TELEM:Aggregator/TELEM:SampleGroup",
                                           namespaces=agg_nsmap):
        sample_group = extract_sample_group(elem, agg_nsmap)
        direct_samples += 1
        if str(sample_group["sampleGroupId"]) in aggregator["groups"]:
            raise NameError(
                f"Duplicated SampleGroup ID: {sample_group['sampleGroupId']}")
        aggregator["groups"][str(sample_group["sampleGroupId"])] = sample_group
    logger.info("Processed Subgroups: %d", len(aggregator["groups"]))
    logger.info("Processed Samples: %d", direct_samples)

    # Iterate over Metrics (high level data, exported outside):
    for elem in aggregator_interface.xpath(
            "TELI:AggregatorSamples/TELI:T_AggregatorSample", namespaces=agg_nsmap):
        metric = extract_metric(elem, agg_nsmap, sensor_types)
        if str(metric["sampleId"]) in aggregator["metrics"]:
            raise NameError(f"Duplicated Metric ID: {metric['sampleId']}")
        aggregator["metrics"][str(metric["sampleId"])] = metric

    logger.info("Processed Metrics: %d", len(aggregator["metrics"]))

    # Process transformations:
    aggregator["transformations"] = {}
    for elem in aggregator_interface.xpath(
            "TELC:TransFormations/TELC:TransFormation", namespaces=agg_nsmap):
        transformation = {}
        transformation["name"] = elem.get("name")
        transformation["transformId"] = elem.get("transformID")
        transformation["transform"] = InfixToPostfixTransformator(
            get_child_value("TELC:transform", elem, agg_nsmap)).transform()
        transformation["output_dataclass"] = get_child_value(
            "TELC:output_dataclass", elem, agg_nsmap)
        transformation["parameters"] = []
        for tra in elem.xpath("TELC:TransFormParameters/TELC:parameterName", namespaces=agg_nsmap):
            if hasattr(tra, "text") and len(tra.text) > 0:
                transformation["parameters"].append(tra.text)
        if transformation["name"] in aggregator["transformations"]:
            raise NameError(
                f"Duplicated transformation: {transformation['name']}")
        aggregator["transformations"][transformation["name"]] = transformation
    return aggregator


def parse_cmdline():
    """Parses command line arguments"""
    parser = argparse.ArgumentParser(
        description='Convert XML Telemetry Aggregator data to Avro binary file with schema.')
    optional = parser.add_argument_group('Optional arguments')
    required = parser.add_argument_group('Required arguments')
    required.add_argument('-s', '--avro-schema', metavar='SCHEMA_FILE',
                          type=validate_path, help='Avro schema file (.avsc)', required=True)
    required.add_argument('-i', '--aggregator', metavar='AGGREGATOR_FILE',
                          type=validate_path, help='Aggregator Interface XML file', required=True)
    required.add_argument('-o', '--output', metavar='AVRO_FILE', type=validate_path,
                          help='Avro payload file to be produced (.avro)', required=True)
    required.add_argument('-t', '--sensor-types', metavar='SENSOR_TYPES_FILE', type=validate_path,
                          help='YAML file with sensor types map', required=True)
    optional.add_argument('--metrics', metavar='METRICS_JSON',
                          type=validate_path, help='JSON file with metrics exported from XML')
    optional.add_argument('-j', '--toJson', metavar='AVRO_TO_JSON',
                          type=validate_path, help='Generate JSON with text representation of created .avro file')
    optional.add_argument('--xml-validator', metavar='XML_SCHEMA_FILE',
                          type=validate_path, help='XML Schema file to validate Aggregator (.xsd)')
    optional.add_argument('--debug', action="store_true",
                          help='Print debugging data (messy output)')
    optional.add_argument('--verbose', action="store_true",
                          help='Increase program verbosity')
    return parser.parse_args()


def open_avro_schema(avro_schema_path):
    """Opens avro schema file"""
    logger.info("Loading Avro schema: %s", repr(avro_schema_path))
    try:
        with open(avro_schema_path, "rb") as schema_file:
            avro_schema = avro.schema.parse(schema_file.read())
    except IOError:
        logger.exception("Cannot open schema file")
        sys.exit(1)
    except AvroException:
        logger.exception("Cannot load schema file")
        sys.exit(2)
    logger.info("Schema loaded successfully.")
    return avro_schema


def load_aggregator_interface(aggregator):
    """Loads XML aggregator data"""
    logger.info("Loading Aggregator data: %s", repr(aggregator))
    try:
        aggregator_xml = try_load_aggregator_interface(aggregator)
    except IOError:
        logger.exception("Cannot open data file")
        sys.exit(1)
    except etree.ParseError:
        logger.exception("Cannot load data file")
        sys.exit(2)
    logger.info("Aggregator data loaded and parsed successfully.")
    return aggregator_xml


def load_yaml_config(sensor_types):
    """Loads yaml file with additional data"""
    logger.info("Loading YAML with sensor types: %s", repr(sensor_types))
    try:
        sensor_types_map = try_load_yaml_config(Path(sensor_types))
    except IOError:
        logger.exception("Cannot open file with sensor types")
        sys.exit(1)
    except yaml.YAMLError:
        logger.exception("Cannot load file with sensor types")
        sys.exit(2)
    logger.info("File with sensor types loaded and parsed successfully.")
    return sensor_types_map


def dump_metrics(metrics, aggregator):
    """Dumps metrics if any"""
    if metrics:
        logger.info("Saving Metrics to file %s", repr(metrics))
        try:
            assert_is_not_symlink(metrics)
            with open(metrics, "w", encoding="utf-8", opener=opener) as met_dump:
                json.dump(aggregator["metrics"], met_dump, indent=4)
        except IOError:
            logger.exception("Cannot open output file")
            sys.exit(1)
        except TypeError:
            logger.exception("Cannot save output file")
            sys.exit(2)


def dump_aggregator(json_output, aggregator):
    """Dumps metrics if any"""
    if json_output:
        logger.info("Saving Aggregator to file %s", repr(json_output))
        try:
            with open(json_output, "w", encoding="utf-8") as agg_dump:
                json.dump(aggregator, agg_dump, indent=4)
        except IOError as e:
            logger.exception(
                f"Unable to create JSON file. Exception occurred: {str(e)}")
            sys.exit(1)
        except TypeError as e:
            logger.exception(
                f"Unable to convert aggregator metadata to JSON. Exception occurred: {str(e)}")
            sys.exit(2)


def inventory_converter(avro_schema_path, aggregator, yaml_config, output, metrics=None, json_output=None):
    """Generates avro file"""
    avro_schema = open_avro_schema(avro_schema_path)
    aggregator_xml = load_aggregator_interface(aggregator)
    sensor_types_map = load_yaml_config(yaml_config)
    # Load YAML file with sensor types data:

    try:
        aggregator = extract_aggregator(aggregator_xml, sensor_types_map)
    except NameError:
        logger.exception("Cannot process Aggregator")
        sys.exit(3)
    except TypeError:
        logger.exception("Cannot process Aggregator")
        sys.exit(4)

    try:
        avro.io.validate(avro_schema, aggregator, True)
    except AvroException:
        logger.exception(
            "Cannot validate data with schema. Use --debug option to gather more information.")
        sys.exit(5)
    logger.info("Data validated with schema.")

    logger.info("Saving avro data to file: %s", repr(output))
    try:
        assert_is_not_symlink(output)
        with open(output, "wb", opener=opener) as output_file:
            writer = DataFileWriter(output_file,
                                    DatumWriter(), avro_schema)
            writer.append(aggregator)
            writer.close()
    except IOError:
        logger.exception("Cannot open output file")
        sys.exit(1)
    except AvroException:
        logger.exception("Cannot save output file:")
        sys.exit(2)

    dump_metrics(metrics, aggregator)
    dump_aggregator(json_output, aggregator)

    logger.info("Conversion finished.")


def validate_path(path):
    """Checks if input path is valid"""
    try:
        output = Path(path).resolve()
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Provided path is invalid: {e}")
    return output


def main():
    """Parses arguments and runs inventory converter"""
    args = parse_cmdline()
    if args.debug:
        logging_level = logging.DEBUG
    elif args.verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.WARNING

    logging.basicConfig(level=logging_level)

    inventory_converter(args.avro_schema, args.aggregator,
                        args.sensor_types, args.output, args.metrics, args.toJson)


if __name__ == "__main__":
    main()
