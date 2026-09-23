@direction LR
@spacing 60

(1 · New Lead Arrives From the Website Form) -> [2 · Check Required Fields and Clean Up the Data]
[2 · Check Required Fields and Clean Up the Data] -> {3 · Does the Lead Have an Email and a Company?}
{3 · Does the Lead Have an Email and a Company?} -> "false" -> [3b · Reject With the Missing Field Named]
{3 · Does the Lead Have an Email and a Company?} -> "true" -> [4 · HubSpot: Search Contacts by Email]
[4 · HubSpot: Search Contacts by Email] -> {5 · Is This Contact Already in HubSpot?}
{5 · Is This Contact Already in HubSpot?} -> "true" -> [[12 · Write a Run Log Row With Tier, Ids, Retries and Timing]]
{5 · Is This Contact Already in HubSpot?} -> "false" -> [6 · Qualify the Lead Into Hot, Warm or Cold]
[6 · Qualify the Lead Into Hot, Warm or Cold] -> {7 · Route by Tier}
{7 · Route by Tier} -> "Hot" -> [8a · HubSpot: Create the Contact]
{7 · Route by Tier} -> "Warm" -> [8b · Send the Warm Lead a Nurture Email]
{7 · Route by Tier} -> "Cold" -> [8c · Cold Lead: Log Only, No Outreach]
[8a · HubSpot: Create the Contact] -> {9 · Did the CRM Call Succeed?}
{9 · Did the CRM Call Succeed?} -> "true" -> [10 · HubSpot: Open a Deal for Sales]
{9 · Did the CRM Call Succeed?} -> "false" -> [9b · Wait 30 Seconds and Retry, Up to 3 Times]
[9b · Wait 30 Seconds and Retry, Up to 3 Times] --> [8a · HubSpot: Create the Contact]
[10 · HubSpot: Open a Deal for Sales] -> [11 · Post the Lead, Tier and Reason to the Sales Channel]
[8b · Send the Warm Lead a Nurture Email] -> [11 · Post the Lead, Tier and Reason to the Sales Channel]
[8c · Cold Lead: Log Only, No Outreach] -> [[12 · Write a Run Log Row With Tier, Ids, Retries and Timing]]
[11 · Post the Lead, Tier and Reason to the Sales Channel] -> [[12 · Write a Run Log Row With Tier, Ids, Retries and Timing]]
(13 · Any Node Fails, Anywhere) -> [14 · Alert the Channel With a Link to the Failed Run]
[OpenAI GPT-4.1] --> [6 · Qualify the Lead Into Hot, Warm or Cold]
[Force One of: Hot, Warm, Cold, Plus a Reason and Score] --> [6 · Qualify the Lead Into Hot, Warm or Cold]
