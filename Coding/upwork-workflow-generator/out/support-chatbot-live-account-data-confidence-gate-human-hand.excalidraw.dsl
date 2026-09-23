@direction LR
@spacing 60

(1 · Customer Message Comes In) -> [2 · Identify Session and Customer ID]
[2 · Identify Session and Customer ID] -> [3 · Support Agent · Prompt Architecture]
[3 · Support Agent · Prompt Architecture] -> {4 · Confident and Safe to Send?}
{4 · Confident and Safe to Send?} -> "true" -> [5 · Reply in Real Time]
{4 · Confident and Safe to Send?} -> "false" -> {6 · Backend API Error? · Max 2 Retries}
{6 · Backend API Error? · Max 2 Retries} -> "true" -> [7 · Pause 2 Seconds and Retry the Call]
[7 · Pause 2 Seconds and Retry the Call] --> [3 · Support Agent · Prompt Architecture]
{6 · Backend API Error? · Max 2 Retries} -> "false" -> [8 · Escalate to a Human With Context]
[5 · Reply in Real Time] -> [[9 · Log Turn, Tokens, and Outcome]]
[8 · Escalate to a Human With Context] -> [[9 · Log Turn, Tokens, and Outcome]]
(10 · Any Node Fails, Anywhere) -> [11 · Alert With a Link to the Failed Run]
[OpenAI GPT-4.1] --> [3 · Support Agent · Prompt Architecture]
[Conversation Memory · Last 10 Turns] --> [3 · Support Agent · Prompt Architecture]
[Backend API: Fetch Account Details] --> [3 · Support Agent · Prompt Architecture]
[Backend API: Order and Billing Status] --> [3 · Support Agent · Prompt Architecture]
[Help Center Search] --> [3 · Support Agent · Prompt Architecture]
[Answer + Confidence + Needs Human] --> [3 · Support Agent · Prompt Architecture]
