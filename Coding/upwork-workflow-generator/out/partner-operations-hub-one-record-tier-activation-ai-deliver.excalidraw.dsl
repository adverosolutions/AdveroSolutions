@direction LR
@spacing 60

(1 - Partner Created or Updated in CRM, PRM, Notion or Sheets) -> [2 - Normalize to One Partner Record - Tier, Type, Owner, Stage]
[2 - Normalize to One Partner Record - Tier, Type, Owner, Stage] -> [3 - Update the Partner in the CRM]
[2 - Normalize to One Partner Record - Tier, Type, Owner, Stage] -> [4 - Update the Same Record in the PRM]
[2 - Normalize to One Partner Record - Tier, Type, Owner, Stage] -> [[5 - Update the Notion Partner Page]]
[2 - Normalize to One Partner Record - Tier, Type, Owner, Stage] -> [[6 - Update the Master Sheet Row]]
[3 - Update the Partner in the CRM] -> {7 - Route Activation by Partner Tier}
[4 - Update the Same Record in the PRM] -> {7 - Route Activation by Partner Tier}
[[5 - Update the Notion Partner Page]] -> {7 - Route Activation by Partner Tier}
[[6 - Update the Master Sheet Row]] -> {7 - Route Activation by Partner Tier}
{7 - Route Activation by Partner Tier} -> "Tier 1" -> [8a - Tier 1: Create the Joint Campaign Task Set]
{7 - Route Activation by Partner Tier} -> "Tier 2" -> [9 - Tier 2: Create the Webinar Checklist]
{7 - Route Activation by Partner Tier} -> "Tier 3" -> [10a - Tier 3: Wait 30 Days]
[8a - Tier 1: Create the Joint Campaign Task Set] -> [8b - Tier 1: Send the Kickoff Email to the Partner]
[10a - Tier 3: Wait 30 Days] -> [10b - Tier 3: Send the Automated Check-In]
(11 - Client Inputs Submitted - the Project Brief) -> [12 - Claude Drafts the Deliverable From Your Template]
[12 - Claude Drafts the Deliverable From Your Template] -> [13 - Put the Draft in Google Docs for Review]
[13 - Put the Draft in Google Docs for Review] -> [14 - Send the Review Request to the Partner Owner]
[14 - Send the Review Request to the Partner Owner] -> [[15 - Log the Activity and the Hours It Saved]]
[8b - Tier 1: Send the Kickoff Email to the Partner] -> [[15 - Log the Activity and the Hours It Saved]]
[9 - Tier 2: Create the Webinar Checklist] -> [[15 - Log the Activity and the Hours It Saved]]
[10b - Tier 3: Send the Automated Check-In] -> [[15 - Log the Activity and the Hours It Saved]]
(16 - Any Step Fails, Anywhere) -> [17 - Alert the Owner With a Link to the Failed Run]
[Claude] --> [12 - Claude Drafts the Deliverable From Your Template]
[Template and Framework Library - Notion] --> [12 - Claude Drafts the Deliverable From Your Template]
[Partner Record Lookup] --> [12 - Claude Drafts the Deliverable From Your Template]
[Force Your Sections: Objective, Audience, Offer, Plan, Next Steps] --> [12 - Claude Drafts the Deliverable From Your Template]
