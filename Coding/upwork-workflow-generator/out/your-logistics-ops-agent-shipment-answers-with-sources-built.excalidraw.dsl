@direction LR
@spacing 60

(1 - Your Team Asks About a Shipment or an SOP) -> [2 - Operations Agent Finds the Answer and Its Source]
[2 - Operations Agent Finds the Answer and Its Source] -> {3 - Answered From a Source, No Person Needed?}
{3 - Answered From a Source, No Person Needed?} -> "true" -> [3a - Reply in Chat With the Answer and Its Sources]
{3 - Answered From a Source, No Person Needed?} -> "false" -> [4 - Your Shipment System: Open a Task for the Ops Team]
[4 - Your Shipment System: Open a Task for the Ops Team] -> [4b - Tell the Team Who Has It and the Task Number]
(5 - Add an SOP Section Through the Upload Form) -> [0b - Config: Your Settings]
[0b - Config: Your Settings] -> [5b - OpenAI: Turn the SOP Section Into Search Vectors]
[5b - OpenAI: Turn the SOP Section Into Search Vectors] -> [5c - Pinecone: Save It Where the Agent Searches]
[Claude - Reasons Over Your SOPs and Shipments] --> [2 - Operations Agent Finds the Answer and Its Source]
[[RAG Tool - Search Your SOPs and Procedures]] --> [2 - Operations Agent Finds the Answer and Its Source]
[OpenAI Embeddings - Match the Question to Your SOPs] --> [[RAG Tool - Search Your SOPs and Procedures]]
[Tool - Look Up the Shipment in Your System] --> [2 - Operations Agent Finds the Answer and Its Source]
[Tool - Save a Draft Customer Update on the Shipment] --> [2 - Operations Agent Finds the Answer and Its Source]
[Parser - Answer, Sources and Needs a Person] --> [2 - Operations Agent Finds the Answer and Its Source]
