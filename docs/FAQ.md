# FAQ

## General
**Q: What is Intel PMT?**

A standardized telemetry exposure framework across Intel platforms combining discovery, aggregation, schema-driven transformation, and access.

**Q: Where do I start?**

See `docs/guides/getting-started.md` for a quick setup.

## Telemetry & Schemas
**Q: How do I know which XML files to use?**

XMLs work in a hierarchy with pmt.xml as root that allows to match aggregators by GUID and size.
All tools should only use pmt.xml as root XML.

**Q: Can I modify XMLs?/Can I add my own telemetry into XMLs?**

No - XMLs are defined by platform architects and should not be modified.

**Q: Can PMT support platform level monitoring through BMC's Bulk Telemetry?**

It can, but currently it doesn't.

For the telemetry to be gathered from the whole platform, each component would have to either
- implement PMT spec and expose its metrics in aggregator described by GUID or
- have its sensors aggregated directly by BMC

Bulk Telemetry supports only continuous metric gathering. Event-driven telemetry (like crashlog) is currently not supported, but might be in the future.

**Q: Is it possible to monitor thousands of servers simultaneously using Bulk Telemetry?**

Yes, Intel PMT Receiver can be configured to scrape any amount of BMCs per instance and Collector allows to easily create multiple instances of receivers.

Supporting large-scale telemetry gathering would probably need some enhancements on the receiver side and figuring out proper pipeline, but yes it's possible.

## Tools
**Q: Difference between Python agent and Go receiver?**

Python agent is a reference code for local telemetry gathering only; Go receiver integrates into OpenTelemetry pipelines and allows for local and remote gathering from BMC.

**Q: How do I request a feature?**

Open a GitHub issue using the feature request template or by email.

## Ownership & Governance
**Q: Who maintains this project?**

@jwasiuki (jedrzej.wasiukiewicz@intel.com)
See `MAINTAINERS.md`.

## Troubleshooting
**Q: GUID and/or size do not match**

Please make sure that you use valid FW components. Pre-release versions might not work properly.

**Q: Collector cannot connect to the BMC platform**

Check if BMC IP is valid and make sure you use proper base64 encoded credentials.

## Licensing & Security
**Q: License?**

Apache 2.0 - see `License`.

**Q: How do I report a security vulnerability?**

Follow `Security.md` instructions.
