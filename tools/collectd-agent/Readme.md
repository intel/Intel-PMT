# Intel PMT Open Telemetry Python Reference Agent

## Dependencies

```
pip install lxml
pip install requests
pip install urllib3
```

## General Usage

```
usage: pmt.py [-h] -s URL [-i INTERVAL] [-r] [-a] [-w ALLOWLIST]
              [-o OUTPUT_LOG_FILE]

PMT agent, reporting telemetry to stdout.

options:
  -h, --help          show this help message and exit
  -s URL              PMT repository XML metadata
  -i INTERVAL         Interval between reads (in seconds).
  -r                  Read metrics and exit
  -a                  Append sampleID to sample identifier
  -w ALLOWLIST        Path to file containing allowed metrics in form of list
                      of regular expressions split by new line
  -o OUTPUT_LOG_FILE  Output log file. If file is not defined, logging is
                      redirected to stdout
```

## Collection telemetry data via command line interface

```
sudo python pmt.py -s file:///home/user/Intel-PMT/xml/pmt.xml
```
