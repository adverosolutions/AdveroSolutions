@direction LR
@spacing 60

(1 - New Request Arrives by Webhook) -> [2 - Claude Agent Reads It and Picks Its Tools]
(1b - Claude Code Calls the Same Agent by Webhook) -> [2 - Claude Agent Reads It and Picks Its Tools]
[2 - Claude Agent Reads It and Picks Its Tools] -> [3 - Send the Answer Back on the Webhook]
[3 - Send the Answer Back on the Webhook] -> [[4 - Log the Run: Topic, Tools Called, Hand-Off]]
(5 - If Any Step Fails) -> [6 - Slack: Alert With the Failed Step and Run Link]
[Claude - Runs the Operations Agent] --> [2 - Claude Agent Reads It and Picks Its Tools]
[HubSpot - Find the Contact] --> [2 - Claude Agent Reads It and Picks Its Tools]
[Database - Look Up Their Orders and Invoices] --> [2 - Claude Agent Reads It and Picks Its Tools]
[HubSpot - Update the Contact] --> [2 - Claude Agent Reads It and Picks Its Tools]
[Slack - Hand It to the Team] --> [2 - Claude Agent Reads It and Picks Its Tools]
[Claude's Answer Form - Topic, Actions and Reply Draft] --> [2 - Claude Agent Reads It and Picks Its Tools]
