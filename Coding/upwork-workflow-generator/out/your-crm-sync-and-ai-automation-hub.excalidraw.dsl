@direction LR
@spacing 60

(1 - HubSpot or Your CRM: Deal Moved to Closed Won) -> [2 - Normalize and Validate Into One Standard Record]
[2 - Normalize and Validate Into One Standard Record] -> {3 - Record Passes Validation?}
{3 - Record Passes Validation?} -> "true" -> [[4 - Sync Ledger: Claim This Event Id Once]]
{3 - Record Passes Validation?} -> "false" -> [[3b - Park It in Needs Review With the Failing Field]]
[[4 - Sync Ledger: Claim This Event Id Once]] -> [5 - Only New Events Continue]
[5 - Only New Events Continue] -> [6 - Acknowledge the CRM Right Away]
[6 - Acknowledge the CRM Right Away] -> [7 - Claude Maps and Enriches the Record]
[7 - Claude Maps and Enriches the Record] -> [[8 - Airtable: Create the Ops Project Record]]
[[8 - Airtable: Create the Ops Project Record]] -> [9 - QuickBooks: Create the First Invoice]
[9 - QuickBooks: Create the First Invoice] -> {10 - QuickBooks Accepted It?}
{10 - QuickBooks Accepted It?} -> "true" -> [11 - Slack: Tell the Team the Deal Is Live]
{10 - QuickBooks Accepted It?} -> "false" -> [10b - Back Off 30 Seconds, Then Retry]
[10b - Back Off 30 Seconds, Then Retry] --> [9 - QuickBooks: Create the First Invoice]
[11 - Slack: Tell the Team the Deal Is Live] -> [12 - HubSpot or Your CRM: Write Ids and Sync Status to the Deal]
[12 - HubSpot or Your CRM: Write Ids and Sync Status to the Deal] -> [[13 - Sync Ledger: Mark Done With Every Id]]
(14 - Any Node Fails, Anywhere) -> [[15 - Sync Ledger: Mark Failed, Ready to Replay]]
[[15 - Sync Ledger: Mark Failed, Ready to Replay]] -> [16 - Alert With the Deal, the Failed Step and a Run Link]
[Claude] --> [7 - Claude Maps and Enriches the Record]
[Target Schema: Ops Record, Invoice Terms, Team Summary] --> [7 - Claude Maps and Enriches the Record]
