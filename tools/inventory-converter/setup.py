#!/usr/bin/env python3

# Copyright (C) 2021-2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from distutils.core import setup

setup(name='inventory-converter',
      python_requires='>3.6.5',
      version='1.0',
      description='Convert XML Telemetry Aggregator data to Avro binary file with schema.',
      py_modules=['inventory_converter', 'schema_generator', 'yaml_metadata_from_avro'],
      entry_points={
          'console_scripts': ['inventory-converter=inventory_converter:main', 
                              'schema-generator=schema_generator:main',
                              'yaml-metadata-from-avro=yaml_metadata_from_avro:main'],
      },
      install_requires=[
          'avro==1.11.3',
          'lxml==4.9.2',
          'PyYAML==6.0'
      ]
      )
