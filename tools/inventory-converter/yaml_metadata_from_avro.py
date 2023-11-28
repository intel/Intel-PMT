#!/usr/bin/env python3

# Copyright (C) 2022-2023 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generates yaml file with metrics configuration from avro file"""

import re
import sys
import yaml
import argparse
import logging
from pathlib import Path
from textwrap import dedent
from avro.datafile import DataFileReader, DataFileWriter
from avro.io import DatumReader, DatumWriter
from avro.errors import AvroException

logger = logging.getLogger()
versions = {"EGS": 0, "BHS": 1}

def load_avro_file(avro_file):
    """Loads avro file with additional data"""
    logger.info("Loading AVRO file: %s", avro_file)

    if Path(avro_file).is_symlink():
        logger.exception("Symlinks are not allowed for input files")
        sys.exit(1)
    try:
        avro_file_reader = DataFileReader(open(Path(avro_file), "rb"), DatumReader())
    except IOError:
        logger.exception("Cannot open input avro file")
        sys.exit(1)
    except AvroException:
        logger.exception("Cannot load input avro file")
        sys.exit(2)
    logger.info("Avro file loaded and parsed successfully.")
    return avro_file_reader

def read_metrics(avro_file, version):
    """Parse avro file"""
    aggregator = [aggregator for aggregator in avro_file][0]
    metrics = aggregator['metrics']
    metric_map = {}
    description_map = {}
    header_map = {}
    header_map['name'] = aggregator['name']
    header_map['description'] = aggregator['description']
    header_map['uniqueId'] = aggregator['uniqueId']
    for metric_id, metric in metrics.items():
        if version == versions["BHS"]:
            if metric['sensorType'] or metric['kafkaStream'] or metric["redfishSensor"]:
                sensorType = dict()
                sensorType['type'] = metric['sensorType']
                sensorType['kafkaStream'] = metric['kafkaStream']
                sensorType["redfishSensor"] = metric["redfishSensor"]
                metric_map[int(metric_id)] = sensorType
                description_map[int(metric_id)] = metric['description']
        else:
            if metric['sensorType']:
                sensorType =  metric['sensorType']
                metric_map[int(metric_id)] = sensorType
                description_map[int(metric_id)] = metric['description']
    avro_file.close()
    return(metric_map, description_map, header_map)

def write_yaml_file(yaml, yaml_file_path):
    """Writes metrics to yaml file"""
    logger.info("Writing to YAML file: %s", yaml_file_path)

    try:
        with open(yaml_file_path, 'w') as yaml_file:
            yaml_file.write(yaml)
    except IOError:
        logger.exception("Cannot open output file")
        sys.exit(1)
    except TypeError:
        logger.exception("Cannot save output file")
        sys.exit(2)
    logger.info("Yaml file written successfully.")

def metrics_to_yaml(metric_list):
    """Writes metrics to yaml string"""
    logger.info("Writing metrics to string")

    return yaml.dump(metric_list, indent=4, default_flow_style=False)

def add_description_comments(description_map, header_map, yaml):
    """Writes description of metrics to yaml file"""
    header = f'''
        # Metedata generated for following Telemetry Aggregator:
        
        # name : {header_map['name']}
        # description : {header_map['description']}
        # uniqueId : {hex(header_map['uniqueId'] & (2**32-1))}

    '''
    result = dedent(header)

    is_sample_id = re.compile(r'^(?P<sample_id>\d+):')

    def preprocess(line):
        match_result = is_sample_id.match(line)
        if match_result:
            sample_id = int(match_result.groupdict()['sample_id'])
            return f'{line} # {description_map[sample_id]}'
        else:
            return line

    for line in yaml.splitlines():
        line = preprocess(line)
        result += f'{line}\n'
    return result


def main():
    """Runs inventory_converter for many instances from config"""
    args = parse_cmdline()
    avro_file_reader = load_avro_file(args.avro)
    metric_map, description_map, header_map = read_metrics(avro_file_reader, args.version)

    if Path(args.yaml).is_symlink():
        logger.exception("Symlinks are not allowed for output files")
        sys.exit(1)
    yaml_string = metrics_to_yaml(metric_map)
    yaml_string = add_description_comments(description_map, header_map, yaml_string)

    write_yaml_file(yaml_string, args.yaml)


def validate_path(path):
    """Checks if input path is valid"""
    try:
        output = Path(path).resolve()
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Provided path is invalid: {e}")
    return output


def parse_cmdline():
    """Parse command line"""
    parser = argparse.ArgumentParser(
        description='Convert Avro binary file to Yaml file with configuration of metrics.')
    parser.add_argument('-a', '--avro', metavar='AVRO', required=True,
                        type=validate_path, help='Path to avro from which yaml file should generated')
    parser.add_argument('-y', '--yaml', metavar='YAML', required=True,
                        type=validate_path, help='Path to output yaml file')
    parser.add_argument('-v', '--version', metavar='VERSION', help='Version of Avro', required=True, type=int,
                        choices=list(versions.values()))
    return parser.parse_args()

if __name__ == "__main__":
    main()
