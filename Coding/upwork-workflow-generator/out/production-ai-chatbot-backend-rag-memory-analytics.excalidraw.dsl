@direction LR
@spacing 60

(1 - Message Arrives From the Web Widget) -> [2 - Load the User, the Session and Recent History]
[2 - Load the User, the Session and Recent History] -> [3 - Answer From Your Knowledge Base and Your APIs]
[3 - Answer From Your Knowledge Base and Your APIs] -> [4 - Assemble the Reply With Its Sources]
[4 - Assemble the Reply With Its Sources] -> {5 - Does This One Need a Human?}
{5 - Does This One Need a Human?} -> "true" -> [6a - Hand It to Support With the Whole Thread]
{5 - Does This One Need a Human?} -> "false" -> [6b - Stream the Answer Back Into the Widget]
[6a - Hand It to Support With the Whole Thread] -> [[7 - Save This Turn to Conversation History]]
[6b - Stream the Answer Back Into the Widget] -> [[7 - Save This Turn to Conversation History]]
[[7 - Save This Turn to Conversation History]] -> [[8 - Log Intent, Answer Time, Token Cost and Rating]]
(9 - Re-Index Your Knowledge Base Every Night) -> [10 - Crawl Your Docs, Help Centre and Product Pages]
[10 - Crawl Your Docs, Help Centre and Product Pages] -> [11 - Keep Only the Pages That Changed Since Last Night]
[11 - Keep Only the Pages That Changed Since Last Night] -> [12 - Split Each Page Into Passages the Bot Can Quote]
[12 - Split Each Page Into Passages the Bot Can Quote] -> [13 - Embed the Passages and Upsert Into the Vector Store]
(14 - Any Step Fails, Anywhere) -> [15 - Alert With a Link to the Failed Run]
[OpenAI GPT-4.1] --> [3 - Answer From Your Knowledge Base and Your APIs]
[Conversation History, One Thread Per User] --> [3 - Answer From Your Knowledge Base and Your APIs]
[[Your Knowledge Base, Searched by Meaning]] --> [3 - Answer From Your Knowledge Base and Your APIs]
[Turns the Question Into a Search Vector] --> [[Your Knowledge Base, Searched by Meaning]]
[Your REST API: Account, Orders, Subscription] --> [3 - Answer From Your Knowledge Base and Your APIs]
[Force: Answer, Sources, Confidence, Escalate Yes or No] --> [3 - Answer From Your Knowledge Base and Your APIs]
