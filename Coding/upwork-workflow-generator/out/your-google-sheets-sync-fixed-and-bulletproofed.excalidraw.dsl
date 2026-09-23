@direction LR
@spacing 60

(1 - Record Arrives) -> [2 - Coerce Types and Dates]
[2 - Coerce Types and Dates] -> [3 - Drop Empty Rows]
[3 - Drop Empty Rows] -> {4 - Sheet and Tab Still Exist?}
{4 - Sheet and Tab Still Exist?} -> "true" -> [[5 - Look Up the Row by Key]]
{4 - Sheet and Tab Still Exist?} -> "false" -> [4b - Alert: Sheet or Tab Renamed]
[[5 - Look Up the Row by Key]] -> {6 - Row Already There?}
{6 - Row Already There?} -> "true" -> [[7 - Update the Existing Row]]
{6 - Row Already There?} -> "false" -> [[7b - Append a New Row]]
[[7 - Update the Existing Row]] -> {8 - Write Succeeded?}
[[7b - Append a New Row]] -> {8 - Write Succeeded?}
{8 - Write Succeeded?} -> "true" -> [[11 - Write a Heartbeat Row to the Log Tab]]
{8 - Write Succeeded?} -> "false" -> [9 - Back Off 30 Seconds]
[9 - Back Off 30 Seconds] -> [10 - Refresh Google OAuth Token]
[10 - Refresh Google OAuth Token] --> [[5 - Look Up the Row by Key]]
(13 - Any Node Fails) -> [14 - Alert With the Failing Node and Row]
[[11 - Write a Heartbeat Row to the Log Tab]] -> [12 - Reply 200 Synced to the Sender]
