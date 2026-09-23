@direction LR
@spacing 60

(1 - Every Weekday at 5am, Next Zip Cluster) -> [2 - Outscraper: Offices, Medical, Gyms, Schools, Warehouses Over 5,000 Sq Ft]
[2 - Outscraper: Offices, Medical, Gyms, Schools, Warehouses Over 5,000 Sq Ft] -> [3 - Normalize: Name, Address, Phone, Category, Reviews]
[3 - Normalize: Name, Address, Phone, Category, Reviews] -> [[4 - Seen Before? Check the Prospect Database]]
[[4 - Seen Before? Check the Prospect Database]] -> {5 - New Prospect?}
{5 - New Prospect?} -> "true" -> [6 - Apollo: Find the Facilities or Office Manager and Verified Email]
{5 - New Prospect?} -> "false" -> [5b - Skip, Already Known]
[6 - Apollo: Find the Facilities or Office Manager and Verified Email] -> {7 - Decision Maker Found?}
{7 - Decision Maker Found?} -> "true" -> [8 - Research Agent: Size, Foot Traffic, Current Vendor Signals, Hiring]
{7 - Decision Maker Found?} -> "false" -> [[7b - Park for Manual Enrichment]]
[8 - Research Agent: Size, Foot Traffic, Current Vendor Signals, Hiring] -> {9 - Score 7 or Higher?}
{9 - Score 7 or Higher?} -> "true" -> [10 - Post the Top Prospects to #approvals With Approve and Reject Buttons]
{9 - Score 7 or Higher?} -> "false" -> [[9b - Store as Low Priority]]
[10 - Post the Top Prospects to #approvals With Approve and Reject Buttons] -> (11 - Approval Decision Comes Back)
(11 - Approval Decision Comes Back) -> {12 - Approved?}
{12 - Approved?} -> "true" -> [13 - HighLevel: Create Contact, Tag, Opportunity in Prospecting Pipeline]
{12 - Approved?} -> "false" -> [[12b - Rejected, With the Reason, Feeds the Scoring Prompt]]
[13 - HighLevel: Create Contact, Tag, Opportunity in Prospecting Pipeline] -> [14 - HighLevel: Trigger the Sales Follow-Up Workflow]
[14 - HighLevel: Trigger the Sales Follow-Up Workflow] -> [[15 - Write the Prospect Record With Score, Source, Approval]]
(16 - Any Step Fails) -> [17 - Alert With the Failing Node]
[GPT-4o] --> [8 - Research Agent: Size, Foot Traffic, Current Vendor Signals, Hiring]
[Read the Website and Google Profile] --> [8 - Research Agent: Size, Foot Traffic, Current Vendor Signals, Hiring]
[Score 1 to 10, Reason, Best Angle] --> [8 - Research Agent: Size, Foot Traffic, Current Vendor Signals, Hiring]
