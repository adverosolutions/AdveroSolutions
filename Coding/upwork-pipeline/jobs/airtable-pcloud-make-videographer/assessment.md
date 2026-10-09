# Assessment (private)

## Time
- Build: 4 to 6 hours real work (Zapier zap with Formatter, Filter and Webhooks-by-Zapier calls to the pCloud API, Airtable field setup, view filter, tests on 3 sample records). Calendar: 2 to 4 days including their pCloud/Airtable access and one review.

## Likelihood
High for folders and the upload link, medium for the two different links on the raw folder.
- Preview-only raw link, checked 2026-09-28 against docs.pcloud.com (`getfolderpublink`, `changepublink`): the API has no parameter to disable downloads or make a link view-only. Supported options are `expire`, `maxdownloads`, `maxtraffic`, `linkpassword`, `shortlink`. The prototype now shows that link as a "view link" with a password and a 30-day expiry. Still to check on their account: whether pCloud's own web link settings can turn downloads off (if so, set by hand once per link or ask pCloud support), and whether one folder can hold two public links (docs silent). Tell the client plainly on the call.
- pCloud API: `createfolderifnotexists` (handles duplicates), `createuploadlink` (upload link to parent), `getfolderpublink` (share link). Unverified: whether one folder can hold two public links with different download settings, and whether "preview only / downloads off" is a link option on their pCloud plan. Fallback if not: the preview-only link points at a tree link or a second shared view; confirm on their account before quoting firmly.
- Zapier's native pCloud app is limited; the pCloud steps run through Webhooks by Zapier, which needs a paid Zapier plan (they have one). Needs a pCloud OAuth/API token.
- Airtable "New record in view" trigger dedupes by record id: a record that leaves and re-enters PCLOUD will not run twice. Handled by adding "Project Date is not empty" to the view filter so incomplete records never enter early.
- Make free (1,000 credits a month, 2 active scenarios, 15-minute minimum interval) would work at low volume but spends one of their two scenarios; Zapier is the right home given "keep it that way".
- Polling delay depends on their Zapier tier (1 to 15 minutes).

## Standard pricing
- Market: $250 to $600 fixed for this zap, or 5 to 7 hours at $45 to $80. Their posted $20-$35/hr is below market for a working API build; recorded bids avg $43.49.
- Recurring software: none new (Zapier paid, pCloud, Airtable already in place).

## Ask before quoting
- Their Zapier plan tier (Paths, polling speed, task count).
- pCloud plan (Premium/Business) and whether download-disabled links are available.
- Exact Airtable field names for date and client name, and the date format they want in folder names.
- Where in pCloud the project folders should live (one "Clients" root?).
- Projects per month (for task usage).
- Which HoneyBook flows they have in mind next.

## Flags
US client, entry-level rate, "future projects" (retainer potential). No client record pulled.

## Pricing path (Lorenzo only)
- Value: assumption 3 to 5 projects a month x 15 minutes of manual folder and link work = roughly 9 to 15 hours a year plus fewer wrong links sent to couples. Small in hours; the value is reliability and the follow-on work.
- Price: $300 to $450 fixed (above 10-20% of hours value; justified as a land offer for future projects).
- Land offer (milestone 1): the zap live on one real project.
- Upsell: HoneyBook booked project creates the Airtable record; edits link sent to the couple when the edits are uploaded; monthly retainer for future automations.
- Milestones: 1) folders and naming live on a test record, 40%, paid once the folders are delivered and you've signed off; 2) all four links writing to Airtable, 40%, paid once the links are delivered and you've signed off; 3) safeguards and a short Loom handover, 20%, paid once the handover is delivered and you've signed off.
