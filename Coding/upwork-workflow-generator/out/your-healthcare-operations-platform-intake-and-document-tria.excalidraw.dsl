@direction LR
@spacing 60

(1 - New Intake Item or Document From the Staff Portal) -> [[2 - Look Up the Staff Role, Mark the Item In Progress]]
[[2 - Look Up the Staff Role, Mark the Item In Progress]] -> {3 - Role Allowed to Submit Intake?}
{3 - Role Allowed to Submit Intake?} -> "true" -> [4 - Mask Patient Identifiers Before Any Model Sees Them]
{3 - Role Allowed to Submit Intake?} -> "false" -> [3b - Refuse: Role Not Allowed to Submit Intake]
[3b - Refuse: Role Not Allowed to Submit Intake] -> [12 - Build One Audit Row per Action Taken]
[4 - Mask Patient Identifiers Before Any Model Sees Them] -> [5 - OpenAI: Turn the Masked Text Into a Search Vector]
[5 - OpenAI: Turn the Masked Text Into a Search Vector] -> [[6 - Supabase: Find the Matching Policy, SOP and Form Passages]]
[[6 - Supabase: Find the Matching Policy, SOP and Form Passages]] -> {7 - Found a Passage That Covers This Item?}
{7 - Found a Passage That Covers This Item?} -> "true" -> [8 - Claude Triages Using Only Your Documents]
{7 - Found a Passage That Covers This Item?} -> "false" -> [[11b - Add It to the Human Review Queue]]
[8 - Claude Triages Using Only Your Documents] -> {9 - Claude Returned a Usable Answer?}
{9 - Claude Returned a Usable Answer?} -> "true" -> {10 - Confident, Cited, Known Queue, Nothing Clinical?}
{9 - Claude Returned a Usable Answer?} -> "false" -> [9b - OpenAI Fallback: Same Rules, Same Sources]
[9b - OpenAI Fallback: Same Rules, Same Sources] -> {10 - Confident, Cited, Known Queue, Nothing Clinical?}
{10 - Confident, Cited, Known Queue, Nothing Clinical?} -> "true" -> [11 - Your Internal Tools API: Create the Task in the Right Queue]
{10 - Confident, Cited, Known Queue, Nothing Clinical?} -> "false" -> [[11b - Add It to the Human Review Queue]]
[11 - Your Internal Tools API: Create the Task in the Right Queue] -> [12 - Build One Audit Row per Action Taken]
[[11b - Add It to the Human Review Queue]] -> [12 - Build One Audit Row per Action Taken]
[12 - Build One Audit Row per Action Taken] -> [[13 - Supabase: Write the Append-Only Audit Rows]]
[[13 - Supabase: Write the Append-Only Audit Rows]] -> [[14 - Update the Staff Screen: Status, Owner, Sources]]
(15 - Any Step Fails, Anywhere) -> [[16 - Log It and Flag the Admin Screen, No Patient Details]]
(KB 1 - Admin Saves or Edits a Policy, SOP, Form or Guideline) -> [KB 2 - Split Into Passages Tagged With Doc, Version, Section]
[KB 2 - Split Into Passages Tagged With Doc, Version, Section] -> [KB 3 - OpenAI: Embed Every Passage in One Call]
[KB 3 - OpenAI: Embed Every Passage in One Call] -> [[KB 4 - Supabase: Store the New Version, Retire the Old One]]
[Claude - Triages Against Your SOPs] --> [8 - Claude Triages Using Only Your Documents]
[Triage Result: Queue, Confidence, Cited Sources] --> [8 - Claude Triages Using Only Your Documents]
[OpenAI - Fallback Triage Model] --> [9b - OpenAI Fallback: Same Rules, Same Sources]
[Fallback Result: Same Fields as Claude] --> [9b - OpenAI Fallback: Same Rules, Same Sources]
