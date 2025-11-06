# FAQ

## General
**Q: What is Intel PMT?**
A standardized telemetry exposure framework across Intel platforms combining discovery, aggregation, schema-driven transformation, and access.

**Q: Where do I start?**
See `docs/guides/getting-started.md` for a quick setup.

**Q: How do I know which XML files to use?**
XMLs work in a hierarchy with pmt.xml as root that allows to match aggregators by GUID and size.
All tools should only use pmt.xml as root XML.

## Telemetry & Schemas
**Q: Can I modify XMLs?/Can I add my own telemetry into XMLs?**
No - XMLs are defined by platform architects and should not be modified.

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

**Q: I cannot connect to the BMC platform**
Check if BMC IP is valid and make sure you use proper base64 encoded credentials.

## Licensing & Security
**Q: License?**
Apache 2.0—see `License`.

**Q: How do I report a security vulnerability?**
Follow `Security.md` instructions.
