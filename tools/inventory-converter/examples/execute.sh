#!/bin/sh

../inventory_converter.py \
  -s ../schemas/AggregatorSchema.avsc \
  -i ../../../xml/SPR/PM/spr_aggregator_interface.xml \
  -t ./SPR_PM_metadata.yaml \
  -o /tmp/spr_oobcore_bhs_60_newest.avro --debug
