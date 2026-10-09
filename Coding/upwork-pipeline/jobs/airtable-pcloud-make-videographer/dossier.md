# Dossier - Automation needed- Zapier, Airtable, PCloud, Honeybook

url: https://www.upwork.com/jobs/~022104589787399541224

## Who they are
- First name: unknown
- Company: unknown
- Industry: wedding and corporate event videographer ("I do video for weddings, corporate events, etc.")
- Location / timezone: United States
- Website read: none named

## Client
no client intel

## Tools they named
Zapier, Airtable, PCloud (pcloud.com), Honeybook (title only), Make.

## Every number in the post
- "2x subfolders"
- "a preview only link AND a preview/download link" (four links in total: upload to parent, preview/download to edits, preview-only and preview/download to raw)
- Metadata: Hourly $20-$35, entry level, part time. Recorded bids avg $43.49 (basis unspecified). Posted 2026-09-28.
- Plan tiers: Make free, Zapier paid ("would like to keep it that way").

## Their requirements, verbatim, in their order
1. "I want to trigger the creation of the following pcloud.com folders when a project moves to a PCLOUD view within my airtable. -Parent folder called "project date_couple name" -Sub folders called "Raw" + "edits""
   Detailed later as: "create a Pcloud.com parent folder named, "Project date_client name" as well as 2x subfolders named, "Client name edits" and "Client name raw.""
2. "I would like upload and download links" / "populate my airtable with an upload link to the "Project date_client name". A preview/download link to the "Client name edits" folder as well as a preview only link AND a preview/download link to the "Client name raw" folder."

2 parts in the post, 2 working screens for them (Folders, Links), plus Overview, The zap (steps, naming, safeguards) and Next (HoneyBook, from the title and "Future projects will be coming soon").

## The odd ask only they would recognize
The raw folder gets two different links: a preview-only one AND a preview/download one. Also the naming shape "Project date_client name" with an underscore, and subfolders named "Client name edits" / "Client name raw". The post names the subfolders two ways ("Raw" + "edits" and "Client name raw"); the prototype uses the detailed version and offers the plain version as a switch.

## What their hiring history implies
Not pulled. Entry-level budget, "highly motivated and ready to move forward soon", future projects promised: wants it working fast, will judge by seeing the folders and links appear.

## Their likely data
```json
{
  "Client Name": "Ava & Theo Linden",
  "Project Type": "Wedding",
  "Project Date": "2026-10-17",
  "Venue": "Hollis Barn",
  "View": "PCLOUD",
  "Upload link (project folder)": "https://u.pcloud.link/...",
  "Edits - preview & download": "https://u.pcloud.link/...",
  "Raw - preview only": "https://u.pcloud.link/...",
  "Raw - preview & download": "https://u.pcloud.link/...",
  "Folder status": "Folders ready"
}
```
Illustrative, made-up couple.

## Sizing
Not a volume job; the post gives no project count. Per project the zap is about 8 billable Zapier tasks (3 folder creates, 4 links, 1 Airtable update; trigger, Formatter and Filter steps are free). Their project volume per month is an input for the assessment.

## Three things they would recognize on screen
1. Their PCLOUD view as the trigger: the board's drop column is labelled PCLOUD (Folders screen, beat 2).
2. Their naming shape: "2026-10-17_Ava and Theo Linden" with "Ava and Theo Linden edits" / "... raw" (folder tree, naming playground, beat 3).
3. The raw folder's two links, preview-only and preview/download (record fields, Links screen, beat 4).

## Beat 1 draft
"This is your pCloud folder automation for your wedding video business."
