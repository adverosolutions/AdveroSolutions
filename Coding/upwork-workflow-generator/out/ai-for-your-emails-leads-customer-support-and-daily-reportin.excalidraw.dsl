@direction LR
@spacing 60

(1 - New Email Lands in Your Inbox) -> [2 - Claude Sorts It: New Lead, Customer Support or Other]
[2 - Claude Sorts It: New Lead, Customer Support or Other] -> [[3 - Google Sheets: Log Every Email With Its Category]]
[[3 - Google Sheets: Log Every Email With Its Category]] -> {4 - New Lead or Support Question?}
{4 - New Lead or Support Question?} -> "lead" -> [5 - Gmail: Follow Up With the New Lead Right Away]
{4 - New Lead or Support Question?} -> "support" -> [6 - Gmail: Draft the Answer for Your Team to Check]
(7 - Every Morning Before You Start) -> [[8 - Google Sheets: Read the Inbox Log]]
[[8 - Google Sheets: Read the Inbox Log]] -> [9 - Count Yesterday's Leads, Support Questions and Open Drafts]
[9 - Count Yesterday's Leads, Support Questions and Open Drafts] -> [10 - Gmail: Send You the Daily Report]
(11 - If Any Step Fails) -> [12 - Gmail: Alert You With the Step and the Error]
[Claude - Reads the Email and Writes the Reply] --> [2 - Claude Sorts It: New Lead, Customer Support or Other]
[Parser - Returns Category, Contact, Summary and Reply] --> [2 - Claude Sorts It: New Lead, Customer Support or Other]
