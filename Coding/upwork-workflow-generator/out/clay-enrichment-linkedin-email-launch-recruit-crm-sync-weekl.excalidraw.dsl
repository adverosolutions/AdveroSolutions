@direction LR
@spacing 60

(Daily Clay Table Sync) -> [Pull Newly Enriched Rows from Clay]
[Pull Newly Enriched Rows from Clay] -> [Score Contact Against ICP]
[Score Contact Against ICP] -> {ICP Fit Score 70 or Higher?}
{ICP Fit Score 70 or Higher?} -> "true" -> [Check Recruit CRM for Existing Contact]
[Check Recruit CRM for Existing Contact] -> [Drop Duplicates, Recent Touches, and Missing Email or LinkedIn URL]
[Drop Duplicates, Recent Touches, and Missing Email or LinkedIn URL] -> [Add to LinkedIn Campaign in HeyReach]
[Drop Duplicates, Recent Touches, and Missing Email or LinkedIn URL] -> [Add to Cold Email Sequence]
[Add to LinkedIn Campaign in HeyReach] -> [Merge LinkedIn and Email Touchpoints]
[Add to Cold Email Sequence] -> [Merge LinkedIn and Email Touchpoints]
[Merge LinkedIn and Email Touchpoints] -> [Upsert Contact and Log Campaign Activity in Recruit CRM]
(Inbound Reply Received) -> [Classify Reply: Interested, Not Interested, or Out of Office]
[Classify Reply: Interested, Not Interested, or Out of Office] -> {Interested?}
{Interested?} -> "true" -> [Move Deal to Interested Stage and Pause Outreach]
(Weekly Health Check — Monday 8am) -> [Aggregate Sends, Opens, Replies, and Bounce Rate]
[Aggregate Sends, Opens, Replies, and Bounce Rate] -> {Bounce Rate Above 3 Percent?}
{Bounce Rate Above 3 Percent?} -> "true" -> [Alert: Inbox Health Degrading]
[Aggregate Sends, Opens, Replies, and Bounce Rate] -> [Draft Weekly Summary of Campaigns, Issues, and Recommendations]
[Draft Weekly Summary of Campaigns, Issues, and Recommendations] -> [Post Weekly Summary to Team]
[GPT-4.1] --> [Score Contact Against ICP]
[GPT-4.1 2] --> [Classify Reply: Interested, Not Interested, or Out of Office]
[GPT-4.1 3] --> [Draft Weekly Summary of Campaigns, Issues, and Recommendations]
