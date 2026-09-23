@direction LR
@spacing 60

[1 - List Every Manual Pile: Trade Logs, Leads, Tickets, ID Checks] -> {2 - Needs Judgement, or Just Moving Data?}
{2 - Needs Judgement, or Just Moving Data?} -> "true" -> [3 - Cluster Last 90 Days of Tickets, Find the Top 10 Questions]
{2 - Needs Judgement, or Just Moving Data?} -> "false" -> [2b - Plain Automation: Excel to a Database, Zapier or n8n on AWS]
[2b - Plain Automation: Excel to a Database, Zapier or n8n on AWS] -> [10 - One Page: Order, Effort, AWS Pieces, What Is AI and What Is Not]
[3 - Cluster Last 90 Days of Tickets, Find the Top 10 Questions] -> [4 - Claude Answers the Top 10 From Your Docs, Human Sees the Rest]
[4 - Claude Answers the Top 10 From Your Docs, Human Sees the Rest] -> [5 - Document OCR and Face Match Score the Upload]
[5 - Document OCR and Face Match Score the Upload] -> {6 - Score Clear Either Way?}
{6 - Score Clear Either Way?} -> "true" -> [6a - Auto Approve or Reject, Logged]
{6 - Score Clear Either Way?} -> "false" -> [6b - Human Queue, Now a Fraction of Today]
[6b - Human Queue, Now a Fraction of Today] -> [10 - One Page: Order, Effort, AWS Pieces, What Is AI and What Is Not]
[6a - Auto Approve or Reject, Logged] -> [7 - Start With Statistical Rules: Z-Scores, Velocity, Size Limits]
[7 - Start With Statistical Rules: Z-Scores, Velocity, Size Limits] -> [8 - Measure: Catch Rate vs Human, False Alarms]
[8 - Measure: Catch Rate vs Human, False Alarms] -> {9 - Rules Miss Real Cases?}
{9 - Rules Miss Real Cases?} -> "true" -> [9a - Then a Model: Isolation Forest in Scikit-Learn, Not Deep Learning Yet]
{9 - Rules Miss Real Cases?} -> "false" -> [10 - One Page: Order, Effort, AWS Pieces, What Is AI and What Is Not]
[9a - Then a Model: Isolation Forest in Scikit-Learn, Not Deep Learning Yet] -> [10 - One Page: Order, Effort, AWS Pieces, What Is AI and What Is Not]
