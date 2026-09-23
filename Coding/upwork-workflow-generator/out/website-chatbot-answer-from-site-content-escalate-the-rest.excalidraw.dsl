@direction LR
@spacing 60

(Visitor Opens the Website Chat) -> [Answer from Website Content]
[Answer from Website Content] -> {Answered from the knowledge base}
{Answered from the knowledge base} -> "true" -> [Reply in the Chat Widget]
{Answered from the knowledge base} -> "false" -> [[Capture Email & Log the Gap]]
[[Capture Email & Log the Gap]] -> [Notify the Team]
[Claude] --> [Answer from Website Content]
[Conversation Memory] --> [Answer from Website Content]
[[Website Pages & FAQs]] --> [Answer from Website Content]
[Site Content Embeddings] --> [[Website Pages & FAQs]]
