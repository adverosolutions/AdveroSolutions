@direction LR
@spacing 60

(1 - New Request Comes In) -> [2 - Tidy the Name, Email and Message]
[2 - Tidy the Name, Email and Message] -> [3 - OpenAI Sorts It and Drafts the Reply]
[3 - OpenAI Sorts It and Drafts the Reply] -> [[4 - Log It to the Requests Sheet]]
[[4 - Log It to the Requests Sheet]] -> {5 - Route by Category}
{5 - Route by Category} -> "Quote Request" -> [6a - Email the Reply Right Away]
{5 - Route by Category} -> "Support Issue" -> [6b - Save the Reply as a Draft to Approve]
{5 - Route by Category} -> "Spam" -> [6c - Spam: Logged, No Reply]
[6a - Email the Reply Right Away] -> [7a - Tell Sales: New Quote, Reply Sent]
[6b - Save the Reply as a Draft to Approve] -> [7b - Tell Support a Draft Is Waiting]
[7a - Tell Sales: New Quote, Reply Sent] -> [[8 - Mark the Row Handled]]
[7b - Tell Support a Draft Is Waiting] -> [[8 - Mark the Row Handled]]
(9 - Any Step Fails) -> [10 - Alert Slack With a Link to the Failed Run]
[OpenAI] --> [3 - OpenAI Sorts It and Drafts the Reply]
[Category, Urgency, Key Details, Reply] --> [3 - OpenAI Sorts It and Drafts the Reply]
