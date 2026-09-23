@direction LR
@spacing 60

(1 · Form Submitted) -> [2 · Validate Required Fields + Email Format]
[2 · Validate Required Fields + Email Format] -> {3 · Valid?}
{3 · Valid?} -> "false" -> [4 · Reject With Field Errors]
{3 · Valid?} -> "true" -> [[5 · Add Row to Submissions Sheet]]
[[5 · Add Row to Submissions Sheet]] -> [6 · Send Confirmation Email]
[6 · Send Confirmation Email] -> [7 · 200 OK to the Form]
(8 · Any Node Fails, Anywhere) -> [9 · Alert on Failure]
