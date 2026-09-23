@direction LR
@spacing 60

[1 - Lookalike Domains and Mailboxes on Your Card, Never the Main Domain] -> [2 - SPF, DKIM, DMARC, Tracking Domain, Warmup On Day One]
[2 - SPF, DKIM, DMARC, Tracking Domain, Warmup On Day One] -> [3 - Instantly Set Up, Connected to Your CRM for Replies]
[3 - Instantly Set Up, Connected to Your CRM for Replies] -> [4 - Seller Lists: Probate, Tax Lien, Pre-Foreclosure, Divorce, Skip Traced]
[3 - Instantly Set Up, Connected to Your CRM for Replies] -> [5 - Agent Lists: Aged, Expired and Off-Market Listings]
[4 - Seller Lists: Probate, Tax Lien, Pre-Foreclosure, Divorce, Skip Traced] -> {6 - Verified and Not Suppressed?}
[5 - Agent Lists: Aged, Expired and Off-Market Listings] -> {6 - Verified and Not Suppressed?}
{6 - Verified and Not Suppressed?} -> "true" -> [7 - Two Sequences: Seller and Agent, Plain Text, 3 to 4 Touches]
{6 - Verified and Not Suppressed?} -> "false" -> [6b - Bounces, Catch-Alls and Opt-Outs Never Load]
[7 - Two Sequences: Seller and Agent, Plain Text, 3 to 4 Touches] -> [8 - First Line From the Record: the Property, the Listing, the Filing]
[8 - First Line From the Record: the Property, the Listing, the Filing] -> [9 - A/B on Subject and CTA, One Variable at a Time]
[9 - A/B on Subject and CTA, One Variable at a Time] -> [10 - Two Week Pilot: Sellers at Tight Volume, Agents at Full]
[10 - Two Week Pilot: Sellers at Tight Volume, Agents at Full] -> {11 - Bounce Under 3 Percent, Replies Coming In?}
{11 - Bounce Under 3 Percent, Replies Coming In?} -> "true" -> [12 - Add Inboxes and Domains, Raise Daily Limits in Steps]
{11 - Bounce Under 3 Percent, Replies Coming In?} -> "false" -> [11b - Pause the Losing Variant, Re-Clean the List, Retry]
[11b - Pause the Losing Variant, Re-Clean the List, Retry] --> [10 - Two Week Pilot: Sellers at Tight Volume, Agents at Full]
[12 - Add Inboxes and Domains, Raise Daily Limits in Steps] -> [13 - Automation Engine: Daily Pulls, Personalization, Reply Routing to CRM]
[13 - Automation Engine: Daily Pulls, Personalization, Reply Routing to CRM] -> [14 - Scorecard and Runbook: Your Team Runs It Without Me]
