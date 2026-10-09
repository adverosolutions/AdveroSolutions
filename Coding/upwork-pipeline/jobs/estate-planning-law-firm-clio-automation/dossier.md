# Dossier - AI & Automation Consultant for Small Estate Planning Law Firm (Google Workspace + Clio)

url: https://www.upwork.com/jobs/~022104564284809129550

## Who they are
- First name: unknown (post is unsigned; writer is "the managing attorney")
- Company: unknown (no firm name in the post)
- Industry: "a 4-person estate planning and probate firm" (wills, trusts, POAs)
- Location / timezone: Florida, United States (US-only applicants required); Eastern time for most of Florida
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
Claude, ChatGPT, Clio (Clio Manage), Google Sheet, Word templates, Google Workspace (Gmail, Drive, Docs, Calendar), Lawmatics (intake forms), Claude Pro, Zapier, Make, n8n, Apps Script.
Build commits to n8n (they are "open to Zapier, Make, n8n or Apps Script, whatever you would actually recommend"), Clio and Lawmatics over their REST APIs, Claude as the AI step, Gmail, Google Docs, Google Sheets.

## Every number in the post
- "4-person" firm: "me, an associate, a paralegal, and a part-time intake coordinator"
- "about a year" using Claude and ChatGPT informally
- "a paid scoping call (1 hour)"
- Metadata: hourly $50-$150, expert, part time; 81 contracts, 61% hire rate, $147.6k spent, 4.99 feedback; avg bid $81.98; 0 invites, 0 interviewing, 0 hired
- Not given (their inputs, never stated as fact): new clients per month, matters open at once, days of silence before a reminder, emails a day in the attorney's inbox, their Clio matter stage names, their template list.

## Their requirements, verbatim, in their order
1. "New client intake - leads come in from the website form, phone, and referrals. The same info gets re-typed into Clio and a Google Sheet, and the welcome email and engagement letter go out whenever someone remembers."
2. "Document drafting - wills, trusts, POAs are built from Word templates. I'd like a first draft generated from the intake questionnaire so the paralegal is editing, not typing."
3. "Follow-ups - clients go quiet mid-matter (signing appointments, missing documents, unpaid retainers). Nothing reminds us. I find out when the client calls annoyed."
4. "Email - I'm the bottleneck. Too much sits in my inbox that the paralegal could handle if it were routed to her with a short summary."

Standing conditions: "as long as my paralegal can run it without me in the loop"; "Client information is confidential"; "build it, document it, and show my team how to use it"; start with "a paid scoping call (1 hour) ... you tell me what you would fix first".

4 parts in your post, 4 sections on the canvas (plus a failure alert section after theirs).

## The odd ask only they would recognize
"as long as my paralegal can run it without me in the loop" - on screen: the overview sticky, the paralegal getting the Clio review task, the routed mail and the failure alert ("Alert Your Paralegal, Not You"). Second: "so the paralegal is editing, not typing" - on the drafting section note.

## What their hiring history implies
81 contracts and $147.6k spent: a frequent, experienced hirer who knows how to judge freelancers. The metadata says that history is for a different kind of business, so it is not used on screen. They explicitly reject tool lists ("I'm not looking for a list of AI tools to buy") and want something built, documented and taught. A paid scoping call first means they judge judgment: what to fix first and roughly what it takes.

## Their likely data
One Lawmatics intake for a married couple's estate plan in Florida (illustrative):

```json
{
  "prospect_id": "8841207",
  "first_name": "Margaret",
  "last_name": "Delgado",
  "email": "margaret.delgado@gmail.com",
  "phone": "(941) 555-0187",
  "source": "Referral",
  "referred_by": "Their CPA",
  "matter_type": "Estate Plan - Married Couple",
  "county": "Sarasota",
  "spouse": "Robert Delgado",
  "children": "Elena Delgado (38), Marcus Delgado (35)",
  "documents_requested": "Revocable trust, pour-over wills, durable POA, health care surrogate",
  "personal_representative": "Elena Delgado",
  "successor_trustee": "Elena Delgado, then Marcus Delgado"
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job. No volume numbers in the post; lead volume, open matters and inbox volume are asked on the scoping call.

## Three things they would recognize on screen
1. Their three quiet-client cases, in their words: "signing appointments, missing documents, unpaid retainers" - node 13 label and section 3 note.
2. Lawmatics form -> Clio contact and matter -> their Google Sheet -> welcome email and engagement letter, the exact retyping they described - section 1 node labels.
3. "Paralegal can run it without me in the loop" and "editing, not typing" - overview sticky, section 2 note, node 20 "Alert Your Paralegal, Not You".

## Beat 1 draft
"This is intake to first draft for your estate planning firm, paralegal-run."
