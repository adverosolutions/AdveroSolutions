@direction LR
@spacing 60

(1 · Lead Captured · Form or Webhook) -> [2 · Validate Fields]
[2 · Validate Fields] -> [3 · GoHighLevel: Search Contact by Email]
[3 · GoHighLevel: Search Contact by Email] -> {4 · Duplicate?}
{4 · Duplicate?} -> "true" -> [5a · Skip, Already in CRM]
{4 · Duplicate?} -> "false" -> [5b · Qualify the Lead]
[5b · Qualify the Lead] -> [6 · GoHighLevel: Create Contact + Tag]
[6 · GoHighLevel: Create Contact + Tag] -> [7 · Automated Follow-Up Email]
[7 · Automated Follow-Up Email] -> [8 · Notify Sales: Lead Processed]
(9 · Any Node Fails, Anywhere) -> [10 · Alert Sales With a Link to the Failed Run]
[Claude] --> [5b · Qualify the Lead]
[Force One of: Hot, Warm, Cold, Plus a Reason] --> [5b · Qualify the Lead]
