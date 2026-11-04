# $20K 90 Day Sprint — Daily Log source map (12 metric columns)
Sheet: https://docs.google.com/spreadsheets/d/1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0/edit#gid=22421784 · tab "Daily Log"
Row 1 headers; data rows 2-91 = Days 1-90 (2026-10-20 to 2027-01-17); **row = Day + 1**.
C Logged = =IF(COUNTA(Dn:Nn)>0,1,0) and O $ Toward $20K = running sum of N (formulas, never overwrite). P Notes stays blank.
**2026-10-21 16:15 CT: column L 'Community Engagement' inserted (Lorenzo via COO). Old L/M/N/O shifted to M/N/O/P; formulas auto-adjusted and verified. Backup: ~/advero/state/backups/sprint_daily_log_formulas_20261021-1614.txt. Target columns by header name.**
Every count uses the CT calendar day (America/Chicago; UTC-5 until 2026-11-01, UTC-6 after). Convert Z timestamps first. Never estimate; no or ambiguous source = blank.
Written 2026-10-20 ~8:28pm CT by Community Manager.

| Col | Metric | Status | Source and method |
|---|---|---|---|
| D | Upwork Proposals | SOURCE OK | Upwork MCP `list_freelancer_proposals` action=list, status=Accepted (= submitted), sort CREATEDDATETIME DESC; page until createdDateTime is before the CT day; count those inside it. Check status=Pending too (normally empty). |
| E | Upwork Replies | SOURCE OK | Upwork MCP `get_messages` list_rooms room_type=INTERVIEW (most-recently-active first). Count rooms with a client-side message created in the CT day; confirm with list_messages when the latest message's side is missing. Proposal rooms only, not active-contract chats. 10-20: newest INTERVIEW activity was 2026-10-07 → 0. |
| F | Cold Emails Sent | SOURCE OK | Instantly API `GET /api/v2/campaigns/analytics/overview?start_date=D&end_date=D` → emails_sent_count (key loaded by ~/advero/bin/_load_box_secrets.py; helper ~/advero/state/reports/pull_instantly_northstar.py). Pull late evening or next morning for the final count. |
| G | Email Replies | SOURCE OK | Same Instantly call → reply_count_unique (excludes automatic replies). Cross-check: human replies in ~/advero/state/handled.jsonl for the CT day (5 on 10-20). |
| H | LinkedIn Requests Sent | NO SOURCE YET (partial) | Agent-sent batches are logged in ~/advero/state/linkedin_approvals.jsonl and grok_updates (10-20: batch revoked, "0 of 8 sent"), but Lorenzo's own requests are not logged. Needs the LinkedIn "Sent invitations" count read daily, or a self-report. |
| I | LinkedIn Replies (= replies and DMs from prospects on LinkedIn) | NO SOURCE YET | linkedin_tracker.csv `reply` column is empty and there is no inbox read. Needs a daily LinkedIn/Sales Nav inbox check or a self-report. |
| J | Community Posts | posts_log.jsonl entries with posted_at on the CT date (Lorenzo confirmed or verified on page; logged by the 6 PM community routine); 0 if the log has none | Advero agents post nothing; Lorenzo's own posts aren't logged. Needs a "posted" log or self-report. (Engagement digest drafts are not posts.) |
| K | New Communities | SOURCE OK | ~/advero/state/communities/joins.jsonl: groups whose latest record has status "approved" with date = CT day. 10-20: The Official BookingKoala Community, Construction Contractors Hub = 2. Pending (5 on 10-20) not counted. |
| L | Community Engagement | SOURCE: Community Manager / Engagement Bot | Comments Lorenzo himself posted in communities that CT day (confirmed by Lorenzo or seen on page; conversation_tracker.csv / posts_log tracking). Drafts don't count. Added 2026-10-21; Day 1 blank (no source). |
| M | Calls Booked | NO SOURCE YET (partial) | Google Calendar primary ([REDACTED]) events created in the CT day + Gmail booking emails + Instantly total_meeting_booked (unreliable, always 0). 10-20: calendar has no events Oct 13–Nov 20, no booking emails. Left blank by convention when nothing is found; needs a booking log (lead, channel, booked_at) to count reliably. |
| N | $ Closed | NO SOURCE YET | Needs a won-deal log with Won Date and amount (Upwork contract start/amount or Lorenzo's confirmation). finance/business/receipts.jsonl is expenses, not revenue. |
| O | $ Toward $20K | FORMULA | =IF(COUNT(N$2:Nn)=0,"",SUM(N$2:Nn)) |
| C | Logged | FORMULA | =IF(COUNTA(Dn:Nn)>0,1,0) |
| P | Notes | BLANK | Lorenzo's standing rule: always blank. |
