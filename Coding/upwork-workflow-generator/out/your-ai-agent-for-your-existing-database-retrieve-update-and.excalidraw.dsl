@direction LR
@spacing 60

(1 - You Ask Your Database in Plain English) -> [2 - Claude Finds the Records You Asked For]
[2 - Claude Finds the Records You Asked For] -> {3 - Did You Say Yes to the Change?}
{3 - Did You Say Yes to the Change?} -> "true" -> [[4 - Postgres: Apply the Staged Change to Your Live Row]]
{3 - Did You Say Yes to the Change?} -> "false" -> [3b - Answer You, or Show the Old and New Value to Confirm]
[[4 - Postgres: Apply the Staged Change to Your Live Row]] -> [[5 - Postgres: Log What Changed, When and in Which Chat]]
[[5 - Postgres: Log What Changed, When and in Which Chat]] -> [6 - Tell You It Is Done, With the Old and New Value]
(7 - If Any Step Fails) -> [8 - Email You the Failed Step, the Error and the Run]
[Claude - Reads Your Data and Plans the Change] --> [2 - Claude Finds the Records You Asked For]
[Memory - Remembers the Chat and the Change Waiting for Your Yes] --> [2 - Claude Finds the Records You Asked For]
[Tool - Search Your Tables - Read-Only] --> [2 - Claude Finds the Records You Asked For]
[Tool - Hold an Update, Add or Archive Until You Say Yes] --> [2 - Claude Finds the Records You Asked For]
[Claude Writes the Reply and Says Answer, Confirm or Apply] --> [2 - Claude Finds the Records You Asked For]
