@direction LR
@spacing 60

(Webhook Receives the Request) -> [Validate and Shape the Payload in JavaScript]
[Validate and Shape the Payload in JavaScript] -> [Call the External API With Auth and Rate-Limit Backoff]
[Call the External API With Auth and Rate-Limit Backoff] -> {More Pages to Fetch?}
{More Pages to Fetch?} --> [Call the External API With Auth and Rate-Limit Backoff]
{More Pages to Fetch?} -> "false" -> [Normalize Every Page Into One Clean Row Set in JavaScript]
[Normalize Every Page Into One Clean Row Set in JavaScript] -> [[Append the Structured Rows to Google Sheets]]
[[Append the Structured Rows to Google Sheets]] -> [Respond 200 With the Row Count]
[Respond 200 With the Row Count] -> {Did Anything Fail?}
{Did Anything Fail?} -> "true" -> [Alert With the Step and the Error]
{Did Anything Fail?} -> "false" -> [[Write the Run Log Row: Time, Rows, Pages, Status]]
[Alert With the Step and the Error] -> [[Write the Run Log Row: Time, Rows, Pages, Status]]
