@direction LR
@spacing 60

(Lead Submitted — Form, Landing Page, Ad, or API) -> [Normalize Fields and Tag Lead Source and Campaign]
[Normalize Fields and Tag Lead Source and Campaign] -> {Required Fields Present: Email or Phone?}
{Required Fields Present: Email or Phone?} -> "true" -> [Search HubSpot for an Existing Contact by Email or Phone]
{Required Fields Present: Email or Phone?} -> "false" -> [Alert: Incomplete Lead Received]
[Search HubSpot for an Existing Contact by Email or Phone] -> [Map Lead Fields to HubSpot Properties]
[Map Lead Fields to HubSpot Properties] -> [Create or Update the Contact in HubSpot]
[Create or Update the Contact in HubSpot] -> [Apply Routing Rules: Assign Lead by Source, Territory, or Product]
[Apply Routing Rules: Assign Lead by Source, Territory, or Product] -> [Notify the Assigned Rep of the New Lead]
[Notify the Assigned Rep of the New Lead] -> {Sync Completed Without Errors?}
{Sync Completed Without Errors?} -> "true" -> [[Log Lead and Routing Result to the Tracking Sheet]]
{Sync Completed Without Errors?} -> "false" -> [Alert: Sync Error, Needs Manual Review]
