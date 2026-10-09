PROVENANCE. Hey there 👋 here's your first milestone, one sale comp from a OneDrive PDF into an approved Excel row, 2-min video: https://www.loom.com/share/2a8545d82895493992bfdb95faf7a773

The video walks through that one comp end to end: the PDF picked up from the job folder, the comp extracted with page-level citations, staged in Supabase with the duplicate check, approved by an appraiser, written into the mapped input row of your Excel model, and every step in the audit trail, ending on the pipeline behind it.

Production systems: I built the intake system for a personal injury law firm, and I've built AI agents on existing databases for numerous companies.

Moving a sale-comp PDF into an approved Excel row without duplicates: Microsoft Graph delta queries watch the authorized folders, and every file is keyed by its drive item ID plus a content hash, so a re-read never creates a second record. Claude extracts into a Pydantic schema where every field carries its page number and source text, and a record missing a citation fails validation. Property and transaction are separate tables: the property matches on parcel number or a PostGIS distance check on the geocoded address, and the transaction matches on sale date, price and parties. Staging marks each record new property, new transaction on a known property, or duplicate, and a unique constraint on the transaction key backs that up in Postgres. Nothing reaches production until an appraiser approves it, inside one database transaction.

Proving no formulas changed: before any write, the runner hashes every formula cell (sheet, address and formula text), the defined names and the macro project. It writes only to the mapped input cells, recalculates in desktop Excel, and hashes again. The two manifests must match exactly or the write rolls back and a QC finding opens, and both manifests go into the audit trail.

What I'd defer from the first 16 weeks: semantic search over past jobs (pgvector), drafting Word narrative beyond the factual sections, and rent and expense comps until the sale-comp path is proven, since they reuse the same pipeline.

I'm the named lead and do the work myself. I can start this week.

The next step is a quick 15 minute call. Just reply here or send me a message on Upwork, I'll send over three times, and we'll get everything started.

Lorenzo

P.S. A few other things I've done:

-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Scaled my own AI agency to $10,000 a month.
