#!/usr/bin/env python3

# Copyright (C) 2021-2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runs inventory converter for multiple schemas"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

from inventory_converter import inventory_converter, assert_is_not_symlink

logger = logging.getLogger()


class ValidationException(Exception):
    """Schema generator input exception"""

    def __init__(self, errors):
        self.errors = errors


def main():
    """Runs inventory_converter for many instances from config"""
    args = parse_cmdline()
    config = Path(args.config)

    try:
        for avro_schema, aggregator, sensor_types, output in generate_input(config):
            inventory_converter(avro_schema, aggregator, sensor_types, output)
    except ValidationException as exception:
        for error in exception.errors:
            logger.error(error.msg)
    except yaml.parser.ParserError:
        logger.exception("Yaml Parsing error found")


def validate_path(path):
    """Checks if input path is valid"""
    try:
        output = Path(path).resolve()
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Provided path is invalid: {e}")
    return output


def generate_input(config_path: Path):
    """Generates input"""
    assert_is_not_symlink(config_path)
    try:
        with config_path.open("r") as config_file:
            config = yaml.load(config_file, Loader=yaml.SafeLoader)
            validate_config(config)
    except IOError:
        logger.error(f'File {repr(config_path)} cannot be loaded.')
        sys.exit()

    for config_element in config:
        yield (config_element["avroSchema"], config_element["telemetryInterfaceXml"],
               config_element["sensorTypeYaml"], config_element["output"])


def validate_config(config):
    """Validates config"""
    errors = list(generate_config_validation_errors(config))
    if errors:
        raise ValidationException(errors)


def generate_config_validation_errors(config):
    """Find errors from validation"""
    fields = ["avroSchema", "telemetryInterfaceXml",
              "sensorTypeYaml", "output"]
    if not isinstance(config, list):
        yield "Config file is not a list."
        return
    for i, config_element in enumerate(config):
        if not isinstance(config_element, dict):
            yield f"{i} element is not a dict."
            continue
        for field in fields:
            try:
                if not isinstance(config_element[field], str):
                    yield f"'{field}' value is not a string in {i} element."
            except KeyError:
                yield f"Missing '{field}' field in {i} element."


def parse_cmdline():
    """Parse command line"""
    parser = argparse.ArgumentParser(
        description='Convert XML Telemetry Aggregator data to Avro binary file with schema.')
    required = parser.add_argument_group('required arguments')
    required.add_argument('-c', '--config', metavar='CONFIG',
                          type=validate_path, help='Path to yaml with config. If not provided '
                                                   'looks for schema-generator.yaml in execution directory',
                          default='schema-generator.yaml')

    return parser.parse_args()


if __name__ == "__main__":
    main()
