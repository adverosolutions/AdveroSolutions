# Screening answers draft (Lorenzo pastes these himself; not part of proposal.md)
Job: https://www.upwork.com/jobs/~022112931725830057478
No required opening word in the post.

1. How would you populate an existing Excel template from QuickBooks data while preserving formulas and verifying accuracy?
I'd connect QuickBooks and the workbook through n8n, pull the month's cash flow report, and write the values only into the template's input cells. The formula cells never get written to, so they keep calculating. After the write, the run reads the totals back and compares ending cash with QuickBooks. If they don't match, the file gets flagged for review instead of marked ready. The video in my proposal shows this on a sample month.

2. Can you help identify and build additional AI automations for our CPA firm? Please give one example and explain how you train nontechnical staff to use your solutions.
Yes. One example is meeting prep: before a client call, an assistant pulls that client's latest numbers and open items into a one page brief, so whoever runs the meeting starts with everything in front of them. For training, [LORENZO: confirm or replace with how you actually train staff, e.g. a short walkthrough video per task plus sitting in on the first few runs].

3. Describe your recent experience with similar projects
I work daily in n8n, Make and Claude Code, with MCP tools on live APIs, and I have AI agents deployed in my own agency and for numerous client companies. I've also built systems for several lenders. My work samples are on my Upwork profile, and the video in my proposal shows your build.

## Lorenzo must confirm before sending
- Q2 training method: not in the approved facts, left as a placeholder.
- Any QuickBooks or Excel specific past build: not in the approved facts, so not claimed anywhere.
- QuickBooks Online vs Desktop: the post doesn't say. The demo uses the QuickBooks Online Reports API; Desktop would need a different connector. Worth asking on the call.
