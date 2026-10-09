# Assessment (private) - PI law firm, demand package agent (part 4 fed by part 3)

## Time
- This piece (the canvas, made real on their files): 45 to 70 hours, 3 to 4
  calendar weeks. Breakdown: case-system webhook and Drive folder conventions
  6-10 h; page-by-page pull plus an OCR path for scanned faxes 8-14 h;
  extraction prompt and schema tuned on 2-3 real closed cases 10-15 h; totals,
  gap and missing-record checks 4-6 h; template tags, Docs fill, exhibit index
  5-8 h; approval loop and Word/PDF export 4-6 h; error path, test runs,
  attorney walkthrough 8-11 h. The long pole is tuning extraction on their real
  records, not the wiring.
- Full post (6 parts: trilingual 24/7 voice receptionist, intake with e-sign and
  conflict screening, records requests and follow-up, demand packages, case
  management dashboards, trilingual client comms): a multi-month program, 4 to
  6+ months in phases. Do not scope it in the proposal.

## Likelihood
- Wiring (webhook, Drive, Docs, Gmail send-and-wait, export): high. Standard
  n8n and Google APIs. Gmail "send and wait" with a custom form and the
  `data.Decision` field shape are unverified in Lorenzo's instance; check on
  first compile.
- Scanned records: the real risk. Many medical records and bills arrive as
  faxed image PDFs with no text layer. The canvas flags those pages
  (unreadable_pages) instead of skipping them, but a production build needs an
  OCR pass (Google Document AI, or sending the PDF pages to Claude's native PDF
  reading) with page numbers kept. Decide on their real files. This risk is
  on the canvas (overview setup line, node 2 note) and in beat 7.
- Code node dependency: pdfjs-dist must be allowed on a self-hosted n8n
  (NODE_FUNCTION_ALLOW_EXTERNAL). n8n Cloud does not allow external modules;
  there it becomes n8n's Extract From File node with pages kept separate, or an
  OCR service call.
- Volume: a big case can run hundreds of pages. Extraction runs one document
  per call, so context is fine; cost and run time scale with pages.
- Traceability: page citations are as good as the page markers and the parser.
  Must spot-check extracted charges against the ledgers on test cases.
- Their case management system is unnamed. If it has no outbound webhook on
  status change, the trigger becomes a poll of its API (more hours).
- Confidentiality: medical records are PHI. They need a BAA with Google
  Workspace (available on paid plans) and an appropriate agreement with the
  model provider before real records flow; confirm Anthropic's current terms
  for their plan. Unverified for Lorenzo: how Anthropic BAAs are offered today.
- Lorenzo has no personal injury, legal or medical records experience. Nothing
  on the build or in the beats claims it. Framing: the canvas is the example
  they asked for (Q1, Q3, Q4); the attorney keeps liability, the demand figure
  and approval.

## Standard pricing
- This piece: market $6,000 to $12,000 for a tested, attorney-reviewed demand
  drafting pipeline on their files (legal and PHI work carries a premium over
  generic automation).
- Full 6-part program: $40,000 to $120,000+ over phases, plus a monthly
  support retainer ($1,500 to $4,000).
- Recurring software: n8n self-hosted $20-50/mo server (or n8n Cloud from about
  $50/mo, but see the module limit above); Claude API usage per case (low
  single to low double dollars per case at a few hundred pages, to confirm on
  real volumes); OCR if used (Document AI is priced per page); Google
  Workspace they likely already pay.
- Post rate: hourly, "rate not given", budget "open". Recorded bids avg $38.72
  (range $7-$300) are far below market for this scope.

## Ask before quoting
1. Which case management system, and can it fire a webhook when a case moves
   to "ready for demand"?
2. Where do records and bills live today (the case system's documents, Drive,
   SharePoint, a records vendor portal)?
3. Roughly how many demands a month, and pages per case?
4. What share of records arrive as scanned faxes?
5. Their firm-approved demand letter and settlement brochure templates; are
   they the same document or two?
6. Who approves: the handling attorney only, or case manager first?
7. Their treatment-gap threshold in days (the canvas asks for it as a setting).
8. Do they have BAAs in place with Google and their other vendors?
9. Which phase they want first; the post asks for assessment, roadmap, then
   phased builds.

## Flags
- US client (Florida). Lorenzo confirms eligibility; copy asserts no location.
- The post asks for PI firm experience, multilingual voice demos and "examples
  of your work". Lorenzo has no PI or legal work to show; the build answers
  Q3 and Q4 directly, and nothing claims past legal work.
- Trilingual (English, Spanish, Haitian Creole) applies to client-facing parts;
  the demand letter goes to insurers, so this piece is English. Worth one line
  on the call, not on the canvas.
- Hiring history (hospitality research, EA, Notion, Wix, "Nosh team" in
  reviews) does not match a law firm. Possibly an operator or assistant hiring
  for the firm. Private; never mentioned.
- No stated restriction on contact outside Upwork.
