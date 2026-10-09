# Dossier - Apollo Cold Email Setup & Email Verification Expert Needed

url: https://www.upwork.com/jobs/~022104652503902335866

## Who they are
- First name: unknown (not signed, no `client first name:` line)
- Company: unknown
- Industry: unknown. The post says only that they are about to launch a cold email campaign in Apollo.
- Location / timezone: Germany (CET/CEST)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel ("Client record not pulled").

## Tools they named
1. Apollo

## Every number in the post
- "Fixed $20" (budget)
- "1 invite" (metadata)
- Nothing else: no list size, no mailbox or domain count, no launch date, no sequence length.

## Their requirements, verbatim, in their order
1. "set up and verify a cold email campaign using Apollo"
2. "configuring the campaign"
3. "reviewing and refining the email flow"
4. "ensuring the setup is ready for launch"
5. "identify issues, improve clarity, and confirm everything is functioning correctly before sending"
6. "strong experience in cold email workflows and verification"

6 parts in the post, 4 scenes in the prototype:
- Parts 1 and 2 share scene 1, "Campaign configured" (the Apollo sequence, mailboxes, window, limits, stop rules).
- Part 3 and the "improve clarity" half of part 5 share scene 2, "Email flow refined".
- Part 5 ("identify issues ... confirm everything is functioning correctly before sending") and the "verification" in parts 1 and 6 are scene 3, "Verification" (DNS, mailboxes, list and email verification, test sends, one issue caught and fixed).
- Part 4 is scene 4, "Ready to launch".
- Part 6 (experience) is answered in the beats: 100k+ cold emails a month.

## The odd ask only they would recognize
"confirm everything is functioning correctly before sending": they want proof before the first email goes out, not after. On screen: the preflight counter (24 of 24) and a missing DMARC record caught before any send. Named in beat 4.

## What their hiring history implies
Client record not pulled. From the post alone: a $20 fixed, short-term job with one invite, Germany. They have a campaign drafted in Apollo and want an expert pass before pressing launch. They will judge on whether the checks are concrete and whether the fix list is specific, not on strategy.

## Their likely data
One Apollo contact and one sequence step. Sample only, not theirs.

```json
{
  "contact": {"first_name": "Jonas", "last_name": "Keller", "title": "Head of Operations", "company": "Brightline Freight", "email": "jonas@brightline-freight.com", "email_status": "verified"},
  "sequence": {"name": "Q4 Outbound, Ops leaders", "steps": 4, "step_days": [1, 3, 7, 12], "mailboxes": ["mara@tryhalden.com", "mara@gethalden.com", "mara@haldenhq.com"]},
  "step_1": {"subject": "Brightline's weekly reporting", "words": 38, "variables": ["first_name", "company"]}
}
```

## Sizing (setup / infrastructure / method jobs only)
The post gives no list size, mailbox count or launch date, so every figure is their input:
- Daily new contacts = your mailboxes x the per-mailbox daily limit you set in Apollo.
- Days to reach the whole list = your list size / daily new contacts, plus the length of the sequence (last step's day) before the last follow-up lands.
- Sample on screen (illustrative): 3 mailboxes x 40 a day = 120 a day; 1,240 contacts take about 11 sending days for step 1.
Insight for the screen: the daily cap is the ceiling for step 1 AND every follow-up together, so follow-ups eat into new-contact volume from day 3. Shown on the launch chart (stacked by step under the 120 cap line).

## Three things they would recognize on screen
1. Apollo named in the scene eyebrows ("Apollo · sequence setup", "Apollo · 4-step sequence") and the description cards.
2. "Before sending": the preflight counter going 0 to 24 and a missing DMARC record caught and fixed before any send (scene 3).
3. "Reviewing and refining the email flow" / "improve clarity": step 1 marked up line by line, then rewritten, with words, asks and spam flags counted down (scene 2).

## Beat 1 draft
"This is a working prototype of your Apollo cold email campaign."
