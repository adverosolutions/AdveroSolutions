# Dossier - AI Automation Expert - Personal Injury Law Firm Reception, Intake, Medical Records & Case Management

url: https://www.upwork.com/jobs/~022103549670129109428

Prop scope (main session): ONE piece of the post, part 4 (settlement brochure
and demand package) with part 3's records extraction feeding it. n8n canvas.

## Who they are
- First name: unknown (the metadata says the reviews name two contacts and it
  is unclear which one posted; the post is unsigned)
- Company: unknown (the post names no firm)
- Industry: "a personal injury law firm" (their words); cases include
  "automobile accidents, slip-and-fall incidents, premises liability"
- Location / timezone: Florida, US (from the metadata paragraph); US Eastern
- Website read: none named

## Client (from `client.json`)
no client intel

## Tools they named
In order of appearance: "n8n, Make, Zapier, OpenAI" (as example platforms, "or
similar technologies"), "Word and PDF" (export formats), "the firm's case
management system" / "existing legal software and document management
platforms" (unnamed). No case management product, document store or chat tool
is named.
Committed for this prop: n8n (they list it first); Claude as the model (Lorenzo
uses the Anthropic API daily; the post says "OpenAI, or similar"); Google Drive
as the records store and Google Docs for the editable draft (main session's
call: "Google Drive folder is fine as the committed store"); Gmail for the
attorney approval gate and the error alert (stays inside the same Google
Workspace; the post names no chat tool). Their case management system stays in
their own words ("your case management system") and sends the webhook.

## Every number in the post
- "24/7" (AI receptionist answers calls)
- "three languages: English, Spanish, and Haitian Creole"
- Scope parts 1 to 6 (reception, intake, medical records, settlement
  brochure and demand package, case management, client communication)
- "Questions for Applicants": 7 questions
- Metadata (private, not for the build): hourly, rate not given; part time,
  long-term; 105 contracts, 70 jobs with hires, $27,714.76 spent, 4.88 over 38
  reviews; bids avg $38.72, range $7-$300; 26 connects.
No number about case volume, pages per case, providers per case, demands per
month or turnaround. Those are their inputs and go to "Ask before quoting".

## Their requirements, verbatim, in their order (part 4, fed by part 3)
Part 3 lines used by this prop:
- "Receive, download, classify, and organize medical records and bills."
- "Identify treatment dates, diagnoses, procedures, medical providers, and treatment history."
- "Organize medical expenses by provider and date."
- "Identify missing treatment records, incomplete billing statements, and gaps in documentation."
Part 4:
1. "Collect and organize relevant case information automatically."
2. "Review and summarize accident reports, medical records, medical bills, and supporting documentation."
3. "Generate chronological summaries of the client's medical treatment."
4. "Prepare structured summaries of injuries, diagnoses, procedures, and treatment history."
5. "Organize past medical expenses and other documented damages."
6. "Identify relevant information concerning liability, injuries, treatment, and the impact on the client's daily life."
7. "Generate draft settlement brochures and demand letters using firm-approved templates."
8. "Incorporate supporting medical documentation, photographs, accident reports, and other relevant exhibits."
9. "Automatically create an organized exhibit index."
10. "Identify missing information or documentation before a settlement package is finalized."
11. "Allow attorneys and case managers to review, edit, and approve all AI-generated materials."
12. "Export completed settlement brochures and demand packages into professional, editable formats, including Word and PDF."
Plus: "The system must not invent medical findings, treatment details, expenses,
legal arguments, or other case information. Drafts should be traceable to the
underlying case records and supporting documentation."

Grouping: 12 lines in part 4 plus the part 3 feed, grouped in their flow order
into 4 sections plus the error section:
- Section 1 (part 4 line 1): case marked ready, pull the records and bills.
- Section 2 (part 3 feed + part 4 lines 2-5, 10): extract every fact with its
  page, total by provider, flag missing records and gaps.
- Section 3 (part 4 lines 6-9): draft from the firm template, facts only,
  exhibit index, saved to Google Docs.
- Section 4 (part 4 lines 11-12): attorney review, edits back, Word and PDF.
- Section 5: error alert (after theirs).

## The odd ask only they would recognize
"The system must not invent medical findings, treatment details, expenses,
legal arguments, or other case information. Drafts should be traceable to the
underlying case records." On screen: node 3 ties every visit and charge to its
file and page; node 5's label says "From Extracted Facts Only" and its prompt
leaves liability argument and the demand figure to the attorney; the draft
cites an exhibit and page for every fact. Named in beat 3 and beat 5.

## What their hiring history implies
Private. A heavy, repeat Upwork buyer (105 contracts, 48% hire rate) whose past
hires are hospitality research, consultations, an executive assistant, Notion,
Wix and brand design; nothing legal. The posting account may belong to an
operator or assistant hiring for the firm, or a new venture. They judge by
concrete answers to their 7 questions and by what they can see; they asked for
examples and demonstrations, so a working canvas on one piece answers that
better than a roadmap. None of this appears on screen.

## Their likely data
One auto accident case marked ready for demand (fictional, illustrative):

```json
{
  "case_id": "PI-2026-0418",
  "client_name": "Marisol Pierre",
  "preferred_language": "Haitian Creole",
  "case_type": "Automobile accident",
  "incident_date": "2026-03-14",
  "incident_location": "I-95 northbound near Broward Blvd, Fort Lauderdale, FL",
  "status": "Ready for demand",
  "assigned_attorney_email": "attorney@yourfirm.com",
  "case_manager_email": "casemanager@yourfirm.com",
  "insurer": "Seaboard Mutual Auto",
  "claim_number": "SMA-7741-2209",
  "drive_folder_id": "1pQ-case-PI-2026-0418",
  "providers_on_file": [
    "Coral Coast Emergency Physicians",
    "Atlantic Imaging Center",
    "Sunshine Spine and Rehab",
    "Dr. Renee Castillo, Orthopedics"
  ]
}
```

Extracted result on that case: ER 2026-03-14 $4,812.00; MRI 2026-03-28
$2,350.00; physical therapy 24 visits $6,480.00; orthopedic consult
$1,150.00; total $14,792.00; treatment gap 2026-05-02 to 2026-06-19 (48 days)
in physical therapy; Atlantic Imaging bill on file but the MRI report is
missing.

## Sizing (setup / infrastructure / method jobs only)
Not a setup job. No volumes in the post; pages per case, demands per month and
the share of scanned faxes are their inputs (assessment asks).

## Three things they would recognize on screen
1. "Must not invent ... traceable to the underlying case records": node 3 label
   "Extracts Every Visit, Charge and Its Source Page", the parser sub-node
   "Each Fact With Its File and Page", node 5 "From Extracted Facts Only".
2. "Organize medical expenses by provider" and "Identify missing treatment
   records ... and gaps in documentation": node 4 label and the output sample's
   totals and gaps.
3. "Automatically create an organized exhibit index" and "editable formats,
   including Word and PDF": node 6 "Save the Draft With the Exhibit Index" and
   node 9 "Export the Demand Package as Word and PDF"; the attorney gate
   (node 7) answers "review, edit, and approve".

## Beat 1 draft
"This is your demand package agent for your personal injury firm."
