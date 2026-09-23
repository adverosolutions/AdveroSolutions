@direction LR
@spacing 60

(1 · New Inquiry Lands in the Outlook Inbox) -> [2 · Claude Reads the Email and Pulls the Shipment Details]
[2 · Claude Reads the Email and Pulls the Shipment Details] -> {3 · Did the Email Contain Every Field We Need to Quote?}
{3 · Did the Email Contain Every Field We Need to Quote?} -> "false" -> [3b · Outlook: Ask the Client for the Missing Details]
{3 · Did the Email Contain Every Field We Need to Quote?} -> "true" -> [[4 · Log the Inquiry as a New Quote Reference]]
[[4 · Log the Inquiry as a New Quote Reference]] -> {5 · Route the Rate Request by Trade Lane}
{5 · Route the Rate Request by Trade Lane} -> "China and Southeast Asia" -> [6 · Outlook: Email the Rate Request to Agents in That Country]
{5 · Route the Rate Request by Trade Lane} -> "Europe and Mediterranean" -> [6 · Outlook: Email the Rate Request to Agents in That Country]
{5 · Route the Rate Request by Trade Lane} -> "Middle East and Gulf" -> [6 · Outlook: Email the Rate Request to Agents in That Country]
[6 · Outlook: Email the Rate Request to Agents in That Country] -> [7 · Hold the Lane Open for 24 Hours While Agents Reply]
[7 · Hold the Lane Open for 24 Hours While Agents Reply] -> [8 · Outlook: Collect the Agent Rate Replies for This Quote]
[8 · Outlook: Collect the Agent Rate Replies for This Quote] -> [9 · Claude Normalizes Every Rate and Ranks Them Side by Side]
[9 · Claude Normalizes Every Rate and Ranks Them Side by Side] -> {10 · Is the Best Rate Inside Our Target Margin?}
{10 · Is the Best Rate Inside Our Target Margin?} -> "false" -> [10b · Outlook: Send the Agent a Counter Offer, Two Rounds Maximum]
[10b · Outlook: Send the Agent a Counter Offer, Two Rounds Maximum] --> [9 · Claude Normalizes Every Rate and Ranks Them Side by Side]
{10 · Is the Best Rate Inside Our Target Margin?} -> "true" -> [11 · Ask a Human to Approve the Rate Before Anything Is Quoted]
[11 · Ask a Human to Approve the Rate Before Anything Is Quoted] -> [12 · Claude Writes the Quote From Your Template and Terms]
[12 · Claude Writes the Quote From Your Template and Terms] -> [13 · Outlook: Send the Quote to the Client]
[13 · Outlook: Send the Quote to the Client] -> [14 · Wait Out the Follow Up Timer]
[14 · Wait Out the Follow Up Timer] -> {15 · Has the Client Replied or Accepted the Quote?}
{15 · Has the Client Replied or Accepted the Quote?} -> "false" -> [15b · Outlook: Send the Next Follow Up, Three Maximum, Then Stop]
[15b · Outlook: Send the Next Follow Up, Three Maximum, Then Stop] --> [14 · Wait Out the Follow Up Timer]
{15 · Has the Client Replied or Accepted the Quote?} -> "true" -> [16 · Wafeq: Raise the Invoice for the Accepted Quote]
[16 · Wafeq: Raise the Invoice for the Accepted Quote] -> [[17 · Archive the Quote PDF in the Client's Drive Folder]]
[[17 · Archive the Quote PDF in the Client's Drive Folder]] -> [[18 · Log the Outcome, Won or Lost, Against the Quote Reference]]
(19 · Any Step Fails, Anywhere in the Workflow) -> [20 · Alert the Team With the Quote Reference and a Link to the Run]
[Claude] --> [2 · Claude Reads the Email and Pulls the Shipment Details]
[Force Origin Port, Destination Port, Weight, Volume, Cargo Type, Dangerous Goods Class, Incoterms] --> [2 · Claude Reads the Email and Pulls the Shipment Details]
[Claude 2] --> [9 · Claude Normalizes Every Rate and Ranks Them Side by Side]
[Force One All In Cost Per Agent in a Single Currency] --> [9 · Claude Normalizes Every Rate and Ranks Them Side by Side]
[Claude 3] --> [12 · Claude Writes the Quote From Your Template and Terms]
