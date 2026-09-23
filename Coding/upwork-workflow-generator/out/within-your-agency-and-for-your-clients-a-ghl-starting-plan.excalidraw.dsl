@direction LR
@spacing 60

[1 - New Lead Follow-Up in Your Agency: Instant Text, Team Alert] -> [2 - Same Workflow in Every Client Sub-Account via Custom Values]
[2 - Same Workflow in Every Client Sub-Account via Custom Values] -> {3 - Did the Lead Reply? Checked Before Every Follow-Up}
{3 - Did the Lead Reply? Checked Before Every Follow-Up} -> "true" -> [3a - Yes: No More Chasing, the Pipeline Moves to Replied]
{3 - Did the Lead Reply? Checked Before Every Follow-Up} -> "false" -> [3b - No: Next Follow-Up, Then the Pipeline Moves to No Response]
[3a - Yes: No More Chasing, the Pipeline Moves to Replied] -> [4 - Deal Won: Your Team Adds One new-client Tag, Welcome and Setup Tasks Follow]
[4 - Deal Won: Your Team Adds One new-client Tag, Welcome and Setup Tasks Follow] -> {5 - Day-3 Check-In: Did the Client Reply?}
{5 - Day-3 Check-In: Did the Client Reply?} -> "true" -> [5a - Yes: The Account Manager Answers the Same Day]
{5 - Day-3 Check-In: Did the Client Reply?} -> "false" -> [5b - No: Silence Becomes a Call Task]
[5a - Yes: The Account Manager Answers the Same Day] -> [6 - Both Workflows in Your Agency Snapshot: Fix Once, Push to Every Client]
[5b - No: Silence Becomes a Call Task] -> [6 - Both Workflows in Your Agency Snapshot: Fix Once, Push to Every Client]
[6 - Both Workflows in Your Agency Snapshot: Fix Once, Push to Every Client] -> [7 - Naming and Tag Conventions Your Team Follows]
[7 - Naming and Tag Conventions Your Team Follows] -> [8 - Test Contacts Through Every Branch Before Go-Live]
[8 - Test Contacts Through Every Branch Before Go-Live] -> [9 - Delivered: First Two Workflows and Team Playbook]
