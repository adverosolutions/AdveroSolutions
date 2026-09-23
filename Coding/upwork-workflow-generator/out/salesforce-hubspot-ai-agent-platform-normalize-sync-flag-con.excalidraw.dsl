@direction LR
@spacing 60

(Salesforce Record Created or Updated) -> {Was This Change Just Written by This Workflow?}
(HubSpot Record Created or Updated) -> {Was This Change Just Written by This Workflow?}
{Was This Change Just Written by This Workflow?} -> "true" -> [Skip: Prevent Sync Loop]
{Was This Change Just Written by This Workflow?} -> "false" -> [Normalize Fields Against One Common Schema]
[Normalize Fields Against One Common Schema] -> {Field Values Conflict Between Source and Target?}
{Field Values Conflict Between Source and Target?} -> "true" -> [Alert: Normalization Conflict Needs Review]
{Field Values Conflict Between Source and Target?} -> "false" -> [Write Normalized Record to Salesforce]
{Field Values Conflict Between Source and Target?} -> "false" -> [Write Normalized Record to HubSpot]
{Field Values Conflict Between Source and Target?} -> "false" -> [Push Normalized Record to the AI Agent Platform]
[Write Normalized Record to Salesforce] -> [Log Sync Result: Updated, Conflicts, Errors]
[Write Normalized Record to HubSpot] -> [Log Sync Result: Updated, Conflicts, Errors]
[Push Normalized Record to the AI Agent Platform] -> [Log Sync Result: Updated, Conflicts, Errors]
[Alert: Normalization Conflict Needs Review] -> [Log Sync Result: Updated, Conflicts, Errors]
[GPT-4.1] --> [Normalize Fields Against One Common Schema]
