@direction LR
@spacing 60

[1 - Count the List and Pick the Send-By Date] -> [2 - Work Out Domains and Mailboxes: 30 a Day Each, 3 per Domain]
[2 - Work Out Domains and Mailboxes: 30 a Day Each, 3 per Domain] -> [3 - Verify Every Address on the Old List]
[3 - Verify Every Address on the Old List] -> {4 - Deliverable?}
{4 - Deliverable?} -> "true" -> {5 - Webinar Date Close?}
{4 - Deliverable?} -> "false" -> [4b - Bounces and Catch-Alls Split Out, Never Loaded]
{5 - Webinar Date Close?} -> "true" -> [5a - Pre-Warmed Mailboxes So Invites Go Out This Week]
[5a - Pre-Warmed Mailboxes So Invites Go Out This Week] -> [6 - Provision 10 to 20 Lookalike Domains and Their Mailboxes on Your Card]
{5 - Webinar Date Close?} -> "false" -> [6 - Provision 10 to 20 Lookalike Domains and Their Mailboxes on Your Card]
[6 - Provision 10 to 20 Lookalike Domains and Their Mailboxes on Your Card] -> [7 - Publish SPF, DKIM, DMARC, MX and a Tracking Domain]
[7 - Publish SPF, DKIM, DMARC, MX and a Tracking Domain] -> {8 - Every Record Passes?}
{8 - Every Record Passes?} -> "false" -> [8b - Fix the Failing Record and Re-Check]
[8b - Fix the Failing Record and Re-Check] --> [7 - Publish SPF, DKIM, DMARC, MX and a Tracking Domain]
{8 - Every Record Passes?} -> "true" -> [9 - Import Every Mailbox Into Your Instantly Workspace]
[9 - Import Every Mailbox Into Your Instantly Workspace] -> [10 - Warmup On, Limits Ramped, One Unibox for Replies]
[10 - Warmup On, Limits Ramped, One Unibox for Replies] -> [11 - Your Login: Paste the List and the Sequence, Press Send]
