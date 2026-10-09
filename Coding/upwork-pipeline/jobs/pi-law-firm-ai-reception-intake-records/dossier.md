# Dossier - AI Automation Expert - Personal Injury Law Firm Reception, Intake, Medical Records & Case Management

url: https://www.upwork.com/jobs/~022103549670129109428

## Who they are
- First name: unknown (reviews name Hannah and Shane, "the Nosh team"; which one posted this is unclear, and the post is unsigned)
- Company: unknown (the post says "a personal injury law firm" and never names it)
- Industry: personal injury law firm ("automobile accidents, slip-and-fall incidents, premises liability, and other injury-related matters")
- Location / timezone: Florida, US (Eastern)
- Website read: none named

## Client
no client intel

## Tools they named
In order: n8n, Make, Zapier, OpenAI ("or similar technologies", as examples, not their stack); "the firm's case management system" (not named); "legal practice management software and CRM"; "electronic signature" (tool not named); "text and email"; "Word and PDF"; "document management platforms" (not named).
Commit on the chart: their own case management system as the hub, labelled as their input ("Your Case Management System"), since they asked for integration with existing software, not a replacement. No vendor named on the chart.

## Every number in the post
- "three languages: English, Spanish, and Haitian Creole" (all client-facing, including voice)
- "24/7" call answering
- Six scope areas (1 to 6), 7 applicant questions
- "Word and PDF" export formats
- Phases asked for pricing: "initial assessment, first implementation phase, and full-office automation"
- Metadata: hourly, rate not given, part time, long-term; client record 105 contracts, $27,714.76 spent, 4.88 over 38 reviews, 48% hire rate; bids avg $38.72 (range $7-$300); 26 connects
- Missing numbers they obviously have: calls per day, new cases per month, open caseload, share of Spanish and Haitian Creole callers, staff count, which case management and document systems. All go to "Ask before quoting" and appear only as labelled inputs.

## Their requirements, verbatim, in their order
1. "AI Receptionist & Front Desk"
2. "AI Client Intake & New Case Onboarding"
3. "Medical Records & Medical Billing Automation"
4. "AI Settlement Brochure & Demand Package Preparation"
5. "AI Case Management & Workflow Automation"
6. "AI Client Communication & Follow-Up"

Six parts in your post, five bands on the canvas: parts 5 and 6 share band 5 ("Your parts 5 and 6: case management and client communication"), since both are the same case file talking to staff and to the client.

Cross-cutting asks quoted: "The system must not invent medical findings, treatment details, expenses, legal arguments, or other case information. Drafts should be traceable to the underlying case records and supporting documentation." / "Allow attorneys and case managers to review, edit, and approve all AI-generated materials." / "Track important case dates and deadlines, with staff verification of legally significant deadlines." / "We want to eliminate the need for staff to manually enter the same information into multiple systems." / "Escalate legal questions, settlement discussions, complaints, and sensitive matters to the appropriate staff member."

## The odd ask only they would recognize
Haitian Creole, by voice, alongside English and Spanish, on every client-facing piece. Second: "Drafts should be traceable to the underlying case records" - every line of a demand letter tied to the page it came from. Both on screen (steps 1, 6, 8, 12) and in beats.

## What their hiring history implies
105 contracts and 1,812 hours across hospitality research, consultations, an executive assistant, a Notion expert, a Wix shop and brand designers: an operator who hires often and in pieces, with no legal-tech hires on record. They asked for a roadmap and phases, so they will judge a clear, staged plan with attorney control over anything clever. The bid average ($38.72) suggests hourly-minded pricing expectations against an expert-level scope.

## Their likely data
One intake record (illustrative):

```json
{
  "caller_language": "Haitian Creole",
  "caller_type": "new prospective client",
  "claim_type": "automobile accident",
  "incident_date": "2026-09-12",
  "incident_location": "NW 7th Ave and 62nd St, Miami",
  "injuries": "neck and lower back pain, seen at ER same day",
  "treatment": "hospital ER, then chiropractor twice a week",
  "insurance": "own PIP carrier and the other driver's carrier, claim numbers pending",
  "police_report": "requested",
  "urgent": false,
  "next_step": "consultation booked, agreement sent for e-signature"
}
```

## Sizing (method job)
No volumes in the post, so no arithmetic. The sizing is by risk, from their own asks:
- Haitian Creole voice is the least proven piece of the stack (far fewer voice models and far less test data than English or Spanish). It gets tested with their own bilingual staff (or a Haitian Creole speaker they trust) on real-style calls before any phone line goes live; text in Haitian Creole is the fallback if voice is not good enough yet.
- The demand package is only as good as the records behind it: traceability (every visit, diagnosis and bill logged with the page it came from) is built in band 3, before any drafting in band 4.
- Their case management system is the hub; which one it is decides how much of band 5 is a direct connection versus workarounds. Carried as their input.
Sharpest insight for chart and beat: test Haitian Creole voice with their own staff first; every demand-letter line links back to a record page.

## Three things they would recognize on screen
1. English, Spanish or Haitian Creole on step 1 and step 12, and in the title ("in Three Languages").
2. "Each Line Tied to a Record" on the draft step, and the attorney gate "Attorney Approves Before Anything Leaves the Firm?" (their traceability and approval asks).
3. Their caller types "New Client, Current Client, Medical Provider or Insurance Rep" on step 2, and "Word and PDF Package With the Exhibit Index" on step 10.

## Beat 1 draft
"This is first call to settlement, three languages, for your injury firm."
