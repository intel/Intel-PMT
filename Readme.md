# Intel Platform Monitoring Technology Telemetry (Intel PMT)

## What is Intel PMT

Intel PMT is a standardized way of exposing telemetry through host-based and out-of-band access across client, server and companion products.
It consists of five key components:
* Discovery: A common discovery mechanism
* Aggregator: Responsible for collecting the information
* Watcher: Provides a control to take action on telemetry (e.g. stream)
* Schema: Describes the telemetry and provides a standardized approach to transforming telemetry
* Access: A standardized driver model and standardized OOB API

Each Intel PMT provider is identified by unique ID and each unique ID is associated with a set of XML specification files.

## What is specified in Intel PMT XML files?

Each set of Intel PMT XML files define:
* Common data types
* Low level samples specification (container index, offset, LSB, MSB)
* High level samples specification (derivation of samples and counters value through application of transformation on one or more low level samples)

## Intel PMT Linux kernel modules

Intel PMT support on Linux has been added to mainline Linux kernel under platform driver (_drivers/platform/x86/intel/pmt_). This driver exposes Intel PMT telemetry space as _sysfs_ entry under folder _/sys/class/intel_pmt/_. This driver will expose each discovered Intel PMT telemetry aggregator under a folder with prefix _telem_. Inside this folder, there will be files named:
- guid: the unique id of the Intel PMT space
- size: the size of the Intel PMT space
- telem: the Intel PMT space

Using _guid_ and _size_ information, the associated Intel PMT XML files set can be identified using repository metadata at _xml/pmt.xml_.

## How is Intel PMT XML to be used in a telemetry agent

Intel PMT kernel driver is typically loaded to discover and manage Intel PMT providers on a platform. Once the kernel driver is loaded, telemetry agent shall scan the discovered PMT unique IDs. For every known unique ID, telemetry agent shall load the matching set of XML files. Using the specification in the XML files, telemetry agent then reads low level samples/counters followed up by evaluation of high level samples/counters as defined by each high level transformation formula. Telemetry agent may also furnish the result of the evaluation with appropriate unit. Telemetry agent then can report out the collected data to designated data collectors for further processing (i.e. observability visualization, machine learning, inference).