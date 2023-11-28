#!/bin/bash
/usr/src/app/otelcol-contrib --config=/usr/src/app/config/config.yml &
# just make sure otelcol-contrib has fully started
sleep 2 
# start piping in pmt data to otelcol-contrib carbon port 10000/tcp
python3 -u /usr/src/app/pmt.py -s file:///usr/src/app/xml/pmt.xml -w /usr/src/app/config/allowlist.txt | /usr/bin/nc 127.0.0.1 10000 
