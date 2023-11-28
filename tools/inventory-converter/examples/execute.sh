#!/bin/sh

../inventory_converter.py \
  -s ../schemas/AggregatorSchemaVer0.avsc \
  -i ../../../xml/SPR/PM/spr_aggregator_interface.xml \
  -t ./SPR_PM_metadata.yaml \
  -o /tmp/spr_egs_PM.avro  \
  -v 0 --debug