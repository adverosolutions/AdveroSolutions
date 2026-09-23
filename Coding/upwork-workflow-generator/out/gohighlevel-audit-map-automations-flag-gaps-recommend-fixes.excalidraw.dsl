@direction LR
@spacing 60

(Audit Requested) -> [Pull Every Active Workflow and Funnel from GoHighLevel]
[Pull Every Active Workflow and Funnel from GoHighLevel] -> [Map Each Workflow: Trigger, Actions, and Exit Point]
[Map Each Workflow: Trigger, Actions, and Exit Point] -> {Trigger Fires But No Follow-Up Action Configured?}
[Map Each Workflow: Trigger, Actions, and Exit Point] -> [Flag Workflows With Broken or Orphaned Triggers]
[Map Each Workflow: Trigger, Actions, and Exit Point] -> {Step Timing Exceeds Lead Response SLA?}
{Trigger Fires But No Follow-Up Action Configured?} -> "true" -> [Cross-Check Every Flag Against Common Lead-Flow Gap Checklist]
[Flag Workflows With Broken or Orphaned Triggers] -> [Cross-Check Every Flag Against Common Lead-Flow Gap Checklist]
{Step Timing Exceeds Lead Response SLA?} -> "true" -> [Cross-Check Every Flag Against Common Lead-Flow Gap Checklist]
[Cross-Check Every Flag Against Common Lead-Flow Gap Checklist] -> [Score Each Confirmed Gap by Lead-Flow Impact]
[Score Each Confirmed Gap by Lead-Flow Impact] -> [Rank Gaps: Fastest Fix vs Highest Impact]
[Rank Gaps: Fastest Fix vs Highest Impact] -> [Draft a Specific Recommended Fix for Each Gap]
[Draft a Specific Recommended Fix for Each Gap] -> [Compile Findings Into Audit Report]
[Compile Findings Into Audit Report] -> [Send Audit Report and Recommendations to Client]
[GPT-4.1] --> [Cross-Check Every Flag Against Common Lead-Flow Gap Checklist]
[GPT-4.1 2] --> [Draft a Specific Recommended Fix for Each Gap]
