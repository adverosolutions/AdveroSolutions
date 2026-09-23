@direction LR
@spacing 60

[1 - SPF, DKIM, DMARC and Blacklists Checked on All 30 Domains] -> [2 - Smartlead Warmup On, Daily Cap Set per Inbox]
[2 - Smartlead Warmup On, Daily Cap Set per Inbox] -> {3 - Inbox Healthy? Warmup Score, Bounces, Spam Placement}
{3 - Inbox Healthy? Warmup Score, Bounces, Spam Placement} -> "true" -> [4 - Clay Table per ICP: Source, Enrich, Find the Decision-Maker]
{3 - Inbox Healthy? Warmup Score, Bounces, Spam Placement} -> "false" -> [3b - Rotate It Out, Fix DNS or Rewarm, Then Back In]
[3b - Rotate It Out, Fix DNS or Rewarm, Then Back In] --> [2 - Smartlead Warmup On, Daily Cap Set per Inbox]
[4 - Clay Table per ICP: Source, Enrich, Find the Decision-Maker] -> [5 - Verify, Drop Catch-Alls, Suppress Clients and Past Contacts]
[5 - Verify, Drop Catch-Alls, Suppress Clients and Past Contacts] -> [6 - One Sequence per ICP, Plain Text, Spintax on Every Line]
[6 - One Sequence per ICP, Plain Text, Spintax on Every Line] -> [7 - Two Angles per ICP, 3 Follow-Ups, First Line From Clay]
[7 - Two Angles per ICP, 3 Follow-Ups, First Line From Clay] -> [8 - Launch in Smartlead: Inbox Rotation, Send Windows, Low Volume]
[8 - Launch in Smartlead: Inbox Rotation, Send Windows, Low Volume] -> [9 - A/B by ICP and Angle, Kill or Scale on Reply Rate]
[9 - A/B by ICP and Angle, Kill or Scale on Reply Rate] -> {10 - Positive Reply Meets Your Qualified-Meeting Definition?}
{10 - Positive Reply Meets Your Qualified-Meeting Definition?} -> "true" -> [11 - Calendly Link Sent, Booked With Qualification Notes]
{10 - Positive Reply Meets Your Qualified-Meeting Definition?} -> "false" -> [10b - Not Yet: Answer, Nurture, No Calendly Link]
[10b - Not Yet: Answer, Nurture, No Calendly Link] --> {10 - Positive Reply Meets Your Qualified-Meeting Definition?}
[11 - Calendly Link Sent, Booked With Qualification Notes] -> [12 - Weekly Report per ICP: Sends, Replies, Positive, Qualified]
