@direction LR
@spacing 60

(1 - Support Ticket or Chat Message In - From Your Support Platform) -> [2 - Identify the Customer, the Channel, and Their Prior Tickets]
[2 - Identify the Customer, the Channel, and Their Prior Tickets] -> [3 - Claude: Draft the Answer From Your Help Docs and Past Tickets]
[3 - Claude: Draft the Answer From Your Help Docs and Past Tickets] -> {4 - Route by Intent}
{4 - Route by Intent} -> "FAQ" -> {5 - Confident Enough to Send This Without a Person?}
{4 - Route by Intent} -> "Account Issue" -> [7 - Support Platform: Reply With Account Details, Keep It Open]
{4 - Route by Intent} -> "Refund or Complaint" -> [9 - Escalate to a Human With the Full Ticket History]
{5 - Confident Enough to Send This Without a Person?} -> "true" -> [6 - Support Platform: Post the Reply and Close the Ticket]
{5 - Confident Enough to Send This Without a Person?} -> "false" -> [8 - Send the Draft to a Human to Check Before It Goes Out]
[6 - Support Platform: Post the Reply and Close the Ticket] -> [[10 - Log the Ticket, Intent, Confidence, and Who Resolved It]]
[7 - Support Platform: Reply With Account Details, Keep It Open] -> [[10 - Log the Ticket, Intent, Confidence, and Who Resolved It]]
[8 - Send the Draft to a Human to Check Before It Goes Out] -> [[10 - Log the Ticket, Intent, Confidence, and Who Resolved It]]
[9 - Escalate to a Human With the Full Ticket History] -> [[10 - Log the Ticket, Intent, Confidence, and Who Resolved It]]
(11 - Once a Week, Look Back at Every Ticket) -> [12 - Roll Up the Low-Confidence and Escalated Tickets]
[12 - Roll Up the Low-Confidence and Escalated Tickets] -> [13 - Claude: Suggest New Answers and Help Doc Fixes]
[13 - Claude: Suggest New Answers and Help Doc Fixes] -> [14 - Weekly Accuracy Report to Your Team]
(15 - Any Node Fails, Anywhere) -> [16 - Alert With a Link to the Failed Run]
[Claude] --> [3 - Claude: Draft the Answer From Your Help Docs and Past Tickets]
[Remember the Rest of This Conversation] --> [3 - Claude: Draft the Answer From Your Help Docs and Past Tickets]
[Help Center Search] --> [3 - Claude: Draft the Answer From Your Help Docs and Past Tickets]
[Order / Account Lookup] --> [3 - Claude: Draft the Answer From Your Help Docs and Past Tickets]
[Answer + Confidence + Intent] --> [3 - Claude: Draft the Answer From Your Help Docs and Past Tickets]
