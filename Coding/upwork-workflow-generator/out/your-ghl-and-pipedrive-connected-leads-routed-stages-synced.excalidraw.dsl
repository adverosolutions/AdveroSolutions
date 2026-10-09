@direction LR
@spacing 60

(1 - GoHighLevel: New Lead or Stage Change Sends a Webhook) -> [0 - Config: Your Settings]
[0 - Config: Your Settings] -> [2 - Clean the Record: Names, Phone Format, Email and Lead Source]
(9 - Run Once: Migrate Your Existing GHL Opportunities) -> [10 - GoHighLevel: Pull Existing Opportunities and Their Contacts]
[10 - GoHighLevel: Pull Existing Opportunities and Their Contacts] -> [11 - Reshape Each Into the Same Lead Record]
[11 - Reshape Each Into the Same Lead Record] -> [0 - Config: Your Settings]
[2 - Clean the Record: Names, Phone Format, Email and Lead Source] -> [3 - Pipedrive: Search for This Person by Email Before Creating Anyone]
[3 - Pipedrive: Search for This Person by Email Before Creating Anyone] -> [4 - Route by Lead Source: Pick the Owner, Pipeline and Stage]
[4 - Route by Lead Source: Pick the Owner, Pipeline and Stage] -> {5 - Already a Person in Pipedrive?}
{5 - Already a Person in Pipedrive?} -> "true" -> {6 - Deal Already Linked to This GHL Opportunity?}
{5 - Already a Person in Pipedrive?} -> "false" -> [5b - Pipedrive: Create the Person With a Clean Name and Phone]
[5b - Pipedrive: Create the Person With a Clean Name and Phone] -> {6 - Deal Already Linked to This GHL Opportunity?}
{6 - Deal Already Linked to This GHL Opportunity?} -> "true" -> [7 - Pipedrive: Move the Linked Deal to the Same Stage]
{6 - Deal Already Linked to This GHL Opportunity?} -> "false" -> [7b - Pipedrive: Create the Deal in the Right Pipeline, Stage and Owner]
[7b - Pipedrive: Create the Deal in the Right Pipeline, Stage and Owner] -> [8 - GoHighLevel: Write the Clean Record and Deal ID Back to the Contact]
(12 - Pipedrive: A Rep Moves a Deal to a New Stage) -> [13 - Match the Pipedrive Stage to Your GHL Stage, Skip Our Own Echo]
[13 - Match the Pipedrive Stage to Your GHL Stage, Skip Our Own Echo] -> [14 - GoHighLevel: Move the Opportunity So Your Follow-Up Workflows Fire]
[14 - GoHighLevel: Move the Opportunity So Your Follow-Up Workflows Fire] -> [15 - Pipedrive: Log the Move and Book the Owner's Next Call]
(16 - Any Step Fails) -> [17 - Email You the Failed Step and a Link to the Run]
