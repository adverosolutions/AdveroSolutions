@direction LR
@spacing 60

(1 - New Client Inquiry From Your Website Form) -> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
[2 - Intake Agent Qualifies the Client and Sets Up the Work] -> {3 - Safe to Send Without a Person?}
{3 - Safe to Send Without a Person?} -> "true" -> [4 - Gmail: Send the Client Their Next Step]
{3 - Safe to Send Without a Person?} -> "false" -> [4b - Gmail: Hold the Reply as a Draft for the Owner]
(5 - If Any Step Fails) -> [6 - Slack: Alert Ops With the Failed Step and Run Link]
[Claude - Runs the Intake Agent] --> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
[HubSpot - Save the Client as a Contact] --> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
[HubSpot - Open a Deal in Your Pipeline] --> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
[ClickUp - Create the Scoping Task for the Owner] --> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
[Slack - Hand the Client to the Owner] --> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
[Parser - Fit, Owner and Client Reply] --> [2 - Intake Agent Qualifies the Client and Sets Up the Work]
