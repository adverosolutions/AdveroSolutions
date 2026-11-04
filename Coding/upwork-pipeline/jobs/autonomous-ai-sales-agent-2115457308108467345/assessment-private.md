# Private assessment: autonomous-ai-sales-agent-2115457308108467345

Job: AI Agent Engineer Needed to Build an Autonomous AI Sales Agent
URL: https://www.upwork.com/jobs/~022115457308108467345
Batch: 2026-10-28 saved-jobs, pick 4, U1 opener B. Legacy sales-deck template.

## Scene map
| # | Scene | Surface | Purpose | New fact the viewer learns | Evidence on screen | Seconds |
|---|---|---|---|---|---|---|
| 0 | Cover | template cover | Frame the system | Find and score, approve and send, book and report | 3-step overview | 10 |
| 1 | research-and-score (required) | n8n native editor, ai_agent | Discovery, research, scoring | Agent reads company sources, checks CRM and opt-outs, scores 86/100 with reasons and recommended service, holds for approval | Node inspector: Halvorsen Freight signals, score, tier | 30 |
| 2 | outreach-and-reply (required) | workbench messages | Approval gate, personalized outreach, follow-up, reply handling | Nothing sends without the sales lead's yes; follow-up cancels on reply; reply sorted as wants a meeting | 6-message thread, 40/day limit, sequence status | 35 |
| 3 | meeting-booked (required) | workbench outcome | Result and reporting | Meeting EVT-5512 booked, team briefed, dashboard counts, activity log incl. calendar retry | Metrics (illustrative), stage bar, booking card | 25 |
| 4 | booking-run (optional, Detailed only) | n8n native execution | Reliability | Calendar create timed out, retried, booked once; CRM patched, sequence paused | Execution 4127, 7.8s, tool output attempt 1 timeout / attempt 2 created | 25 |
| 5 | Close | template close | Measurement and CTA | Qualified meetings, positive reply rate, team time per meeting | Directional goals, 15-minute call CTA | 10 |

Standard (2 min) = 0,1,2,3,5. Detailed (3 min) adds 4.

## Flags
- Client: AI-services company (Pakistan), likely white-label. 3 posted, 0 hires, 0 reviews; 4 invites, 1 interviewing.
- Post has 8 evaluation questions in the body; Q1, Q7, Q8 need Lorenzo's facts (see proposal notes).
- B opener preview 104 chars (below 133); B claim "just built ... last week" leans on the approved "similar build last week" fact for AI agents on client databases.
- All data invented: Halvorsen Freight, Rosalind Achterberg, PRS-2041, RUN-1102-07, EVT-5512, execution 4127.
- Similarity (U-021): word-trigram Jaccard on titles, captions and labels vs 59 other P/jobs specs; max 0.117 (openai-n8n-production-agents); exact overlaps only locked template copy and generic node names.
- QA nav note: under Playwright's fake clock the nav appeared to lag one step; in real time Next/Previous/arrows/dots all move correctly. Test artifact, not a runtime bug.
