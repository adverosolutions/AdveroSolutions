# Loom beat sheet - Your Monday.com to PandaDoc Contract Engine

- you want Monday to PandaDoc contracts, reliable, with real error handling
- item hits Ready for Contract, we fetch columns and download the PDF
- Extract Text From PDF first, then the Text Found gate catches scans
- one extraction step, fixed JSON schema, party, value, term, start date
- nothing reaches PandaDoc until required fields present and amounts parse
- PandaDoc builds the draft async, so we wait, then Send For Signature
- any step fails, Slack gets it and Monday flips to Contract Failed
- can start [START], working demo by [DRAFT]
