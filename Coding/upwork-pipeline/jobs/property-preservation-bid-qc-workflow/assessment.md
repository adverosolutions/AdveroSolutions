# Private assessment, not for the proposal

**Time.** Discovery phase: 12 to 20 hours over 1 to 2 weeks (what PPW exposes, what historical bid data exists and in what shape, which client pricing schedules they hold, architecture memo and phased plan). Phase 1 pilot as built in the spec: 45 to 70 hours over 3 to 5 weeks, and that assumes discovery came back with a usable data path. If PPW turns out to be browser-automation only, add 20 to 40 hours for the RPA layer and expect it to break on their UI changes forever after. Phases 2 to 7 in the post (after-photo verification, ready-for-office, contractor pricing assignment) are each their own build.

**Likelihood / what actually breaks.**
- **Computer vision on photos is not verified experience.** Lorenzo has the Anthropic API and n8n daily; he has not shipped a photo-verification system. Claude's vision is the honest path here and it is genuinely good at "describe this condition, does it match these instructions" on field photos. A custom CV model is not on the table and should not be implied. Say vision-via-Claude on camera, not "computer vision".
- **A pricing model on historical bid data is also not verified experience.** What is buildable now is a lookup plus benchmarking layer (median by county, work order type, client, last N months) that the model reasons over. That is not a trained pricing model and the post may want one eventually. Do not promise regression or ML pricing.
- **PPW integration is unknown until discovery.** API, scheduled export, middleware, or RPA are all still live options. The spec makes the trigger and the two PPW calls swappable on purpose. Never quote the pilot as a fixed price before that answer exists.
- **Their historical data is the real risk.** Bid history that lives in PDFs, in PPW screens, or in one processor's spreadsheet turns the pricing layer into a data project first. Ask to see a sample export before quoting phase 1.
- **Photo volume drives API cost.** At roughly 8 to 15 before-photos per order, Claude vision runs a few cents per work order; at high volume that is a real monthly line item and they should hear the number, not discover it.
- **US-only post.** Lorenzo confirms his own eligibility. Do not assert a location anywhere in the copy.
- Human-in-the-loop is a selling point, not a limitation. Bids reaching a client without a person tapping approve is the failure mode that loses them the client relationship, so the checkpoint stays in phase 1 regardless.

**Standard pricing.** Discovery/scoping phase for an ambiguous ops process like this: $2,500 to $6,000 fixed, or 15 to 25 hours at $90 to $150/hr. Phase 1 pilot: $9,000 to $18,000 fixed, or hourly at the same band. Post is $19 to $40/hr, well under US market for AI plus portal-integration work; the top of their band is roughly half the floor of the specialist rate. Bid the two phases separately, always. Recurring: Claude API on photo volume, n8n cloud or self-host, plus whatever PPW charges for API access if it exists.

**Ask before quoting.**
1. Does PPW expose an API to vendors, and can they get credentials? If not, is a scheduled export available?
2. How many work orders a month, and how many photos per order?
3. How much historical bid data exists, and in what format? Can they send one sample export?
4. Which client pricing schedules do they hold (MCS, Freddie, Guardian, Altisource, NFR)? Are the allowables documented anywhere?
5. Which work order type do they want the pilot on? Initial secures and winterizations are the cleanest candidates.
6. Who is the approver, and where do they live day to day (Slack, Teams, email)?
7. Do they already run n8n or anything similar, or is hosting part of the job?
