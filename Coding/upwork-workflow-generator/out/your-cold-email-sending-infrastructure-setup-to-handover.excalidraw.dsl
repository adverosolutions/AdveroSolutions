@direction LR
@spacing 60

[1 - Set Target Volume: Emails per Day and Campaigns Planned] -> [2 - Work Out Mailboxes and Domains Needed - 30 a Day per Mailbox, 3 per Domain]
[2 - Work Out Mailboxes and Domains Needed - 30 a Day per Mailbox, 3 per Domain] -> {3 - Need to Send Right Away?}
{3 - Need to Send Right Away?} -> "true" -> [3a - Use Pre-Warmed Mailboxes So Campaigns Start This Week]
[3a - Use Pre-Warmed Mailboxes So Campaigns Start This Week] -> [4 - Provision Lookalike Domains and Mailboxes on Your Account and Billing]
{3 - Need to Send Right Away?} -> "false" -> [4 - Provision Lookalike Domains and Mailboxes on Your Account and Billing]
[4 - Provision Lookalike Domains and Mailboxes on Your Account and Billing] -> [5 - Publish SPF, DKIM, DMARC, MX and a Custom Tracking Domain]
[5 - Publish SPF, DKIM, DMARC, MX and a Custom Tracking Domain] -> {6 - Every Record Passes Verification?}
{6 - Every Record Passes Verification?} -> "false" -> [6a - Fix the Failing Record and Re-Check Before Anything Sends]
[6a - Fix the Failing Record and Re-Check Before Anything Sends] --> [5 - Publish SPF, DKIM, DMARC, MX and a Custom Tracking Domain]
{6 - Every Record Passes Verification?} -> "true" -> [7 - Import Every Mailbox Into Instantly]
[7 - Import Every Mailbox Into Instantly] -> [8 - Warmup On, Daily Limits Ramped, Sending Schedule Set to Your Spec]
[8 - Warmup On, Daily Limits Ramped, Sending Schedule Set to Your Spec] -> [9 - One Unibox: Every Reply From Every Mailbox in One Place]
[9 - One Unibox: Every Reply From Every Mailbox in One Place] -> [10 - Connect Instantly to Claude: Replies Sorted and Drafts Written]
[10 - Connect Instantly to Claude: Replies Sorted and Drafts Written] -> [11 - Handover: Your Accounts, Your Billing, One Page Runbook]
