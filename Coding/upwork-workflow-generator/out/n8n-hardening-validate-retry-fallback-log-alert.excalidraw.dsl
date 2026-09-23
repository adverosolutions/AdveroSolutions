@direction LR
@spacing 60

(1 - Incoming Record) -> [2 - Validate Schema and Required Fields]
[2 - Validate Schema and Required Fields] -> {3 - Is the Record Valid?}
{3 - Is the Record Valid?} -> "false" -> [4 - Reject With Field Errors]
{3 - Is the Record Valid?} -> "true" -> [5 - System A: Fetch Related Record]
[5 - System A: Fetch Related Record] -> {6 - Did the Call Succeed?}
{6 - Did the Call Succeed?} -> "true" -> [10 - Map Fields Between Systems]
{6 - Did the Call Succeed?} -> "false" -> {7 - Are the Retries Used Up?}
{7 - Are the Retries Used Up?} -> "true" -> [9 - Fallback: Queue for Manual Retry]
{7 - Are the Retries Used Up?} -> "false" -> [8 - Back Off 30 Seconds]
[8 - Back Off 30 Seconds] --> [5 - System A: Fetch Related Record]
[9 - Fallback: Queue for Manual Retry] -> [[12 - Run Log: Status, Latency, Retries]]
[10 - Map Fields Between Systems] -> [11 - System B: Create or Update Record]
[11 - System B: Create or Update Record] -> [[12 - Run Log: Status, Latency, Retries]]
[[12 - Run Log: Status, Latency, Retries]] -> [13 - Return 200 OK]
(14 - Any Node Fails, Anywhere) -> [15 - Alert With Link to Failed Execution]
