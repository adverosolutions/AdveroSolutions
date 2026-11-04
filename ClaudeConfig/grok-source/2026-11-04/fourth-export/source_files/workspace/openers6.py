import json,re
def cnt(t): return len(t)-6+59
L="Batch C (2026-10-22 10:45 CT, aware-audience brief)"
R=[
("[THEIR STACK], [THEIR GAP]. Built and running: [LOOM]",
 "GHL pipeline, Calendly bookings, no-show follow-up missing. Built and running: [LOOM]",
 "Stack + gap in one line. Proof = the working build itself.",""),
("[THEIR WORKFLOW]. I built the intake system for a PI law firm. [LOOM]",
 "After-hours calls, paper intake. I built the intake system for a PI law firm. [LOOM]",
 "Workflow + section 7 fact (PI intake). PI or legal posts only.",""),
("[THEIR WORKFLOW]. I've built systems for several other lenders. [LOOM]",
 "Applications stuck in email. I've built systems for several other lenders. [LOOM]",
 "Workflow + section 7 fact (lenders). Lender posts only.",""),
("[THEIR STACK], [MANUAL STEP]. I send 100k+ cold emails a month on Instantly. [LOOM]",
 "Apify lists, replies sorted by hand. I send 100k+ cold emails a month on Instantly. [LOOM]",
 "Stack + section 7 fact (100k+ a month on Instantly). Cold email posts only.",""),
("An agent on your [THEIR DATA]. I've built agents on client databases for numerous companies. [LOOM]",
 "An agent on your help docs. I've built agents on client databases for numerous companies. [LOOM]",
 "Use case + section 7 fact (agents on existing client databases).",""),
("An agent reading your [THEIR DATA]. Just finished a similar build last week. [LOOM]",
 "An agent reading your Shopify orders. Just finished a similar build last week. [LOOM]",
 "Use case + approved line 'Just finished a similar build last week' (AI agents on existing data only).",""),
("[THEIR WORKFLOW]. Scaled my own AI agency to $10,000 a month. [LOOM]",
 "GHL lead follow-up. Scaled my own AI agency to $10,000 a month. [LOOM]",
 "Workflow + P.S. bullet A (short form, per section 6 agency tail rule).","FLAG: P.S. fact, needs Lorenzo's OK outside the P.S."),
("[THEIR TOOL] [PROBLEM FROM THE POST]. I work in n8n and Make daily. Fixed: [LOOM]",
 "Make scenario stops on blank form fields. I work in n8n and Make daily. Fixed: [LOOM]",
 "Specific failure from their post + section 7 fact (n8n and Make daily).",""),
("[THEIR WORKFLOW]. I've worked with dental practices. Running version: [LOOM]",
 "Recall texts and review requests. I've worked with dental practices. Running version: [LOOM]",
 "Workflow + section 7 fact (dental). Dental posts only, no PMS claims.",""),
("[THEIR WORKFLOW]. I've worked with construction companies. [LOOM]",
 "Estimate requests in an inbox nobody owns. I've worked with construction companies. [LOOM]",
 "Workflow + section 7 fact (outdoor living / construction). Those posts only.",""),
]
bad=re.compile(r'quick|game.changer|hope this|I noticed|streamline|seamless|leverage|elevate|day job|[\u2013\u2014!?]',re.I)
rows=[['',L,'','','','',''],]
for i,(t,e,a,f) in enumerate(R,1):
    for s in (t,e): assert not bad.search(s),(i,s); assert '[LOOM]' in s
    c=cnt(e); print(i,c); assert c<150,(i,c)
    rows.append([f'C{i}','C (10:45 CT)',t,e,c,(a+(' '+f if f else '')),''])
rows.append(['','','Batch C notes: one line on their stack or workflow, then one proof point, then [LOOM]. Proof = section 7 confirmed facts (UPWORK_PROCESS.md) or the build itself; each section 7 fact only for the matching kind of post. No emojis. [LOOM] counted as 59 chars; counts are for the example fill.','','','',''])
json.dump(rows,open('openers_rows6.json','w'),ensure_ascii=False)
