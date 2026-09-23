# Private assessment (not for the proposal)

**Time.** 1 to 3 hours of actual work once he can see their workflow, same-day turnaround.
The build itself is a pattern he already knows cold. The variable is reading their existing
canvas and finding the real bottleneck they mentioned but did not describe.

**Likelihood.** High that it lands. The one unknown is what their APIs actually are.
Everything risky here happens in their account: whether the failing call is a rate limit, a
timeout, an auth expiry, or bad data upstream changes what the retry policy should be, and
that is not knowable until he sees the workflow and one failed execution. Second risk is
access. If they will not export the workflow JSON or share a screen, the job stalls before
it starts. Third, "connects multiple systems through an API" can quietly mean five systems,
not two, and the fix multiplies. Cap the scope at the one workflow they show him.

**Standard pricing.** Market for a scoped n8n hardening pass on one small workflow is
roughly $150 to $400 fixed, or $75 to $125 an hour. This post is $20 fixed, entry level,
with an average bid of $43.73 against a $700 high. So $20 is well under market and he knows
it. It is worth taking as a foot in the door on a client who clearly has more workflows
behind this one, not as a rate. Do not anchor future work to it. No recurring software cost
to quote unless they want the run log and alerting on something they do not already pay for
(Google Sheets and Slack are free at this volume).

**Ask before quoting anything beyond this one workflow.**
- Which two or more systems are being connected, and which API is the one that fails?
- Can they export the workflow JSON, or is this screen share only?
- n8n cloud or self hosted, and what version?
- What is the current issue in their words: an error, a wrong result, or just slowness?
- Is there a Slack channel and a sheet he can log to, or should it stay inside n8n?
- Roughly how many executions a day, so the retry and backoff numbers are sized right?
