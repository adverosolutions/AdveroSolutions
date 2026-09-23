@direction LR
@spacing 60

(1 · Customer or Staff Message) -> [2 · Normalize Channel, Sender, Business ID]
[2 · Normalize Channel, Sender, Business ID] -> [[3 · Read the Prompt Profile for This Business]]
[[3 · Read the Prompt Profile for This Business]] -> [4 · Assemble System Prompt · Tone + Rules + Context]
[4 · Assemble System Prompt · Tone + Rules + Context] -> [5 · Claude Handles the Request]
[5 · Claude Handles the Request] -> {6 · Money, Booking Change, or Complaint?}
{6 · Money, Booking Change, or Complaint?} -> "true" -> [7a · Send to Owner for a One-Tap Approve]
{6 · Money, Booking Change, or Complaint?} -> "false" -> [7b · Reply to the Customer]
[7a · Send to Owner for a One-Tap Approve] -> [8 · Score the Exchange Against the Prompt Rules]
[7b · Reply to the Customer] -> [8 · Score the Exchange Against the Prompt Rules]
[8 · Score the Exchange Against the Prompt Rules] -> [[9 · Log Prompt Version, Score, Tools Used]]
[Claude] --> [5 · Claude Handles the Request]
[Conversation Memory · per customer] --> [5 · Claude Handles the Request]
[MCP — CRM: Find or Update a Customer] --> [5 · Claude Handles the Request]
[MCP — Calendar: Check and Book Slots] --> [5 · Claude Handles the Request]
[MCP — Invoicing: Balance and Payment Link] --> [5 · Claude Handles the Request]
[MCP — Business Docs: Policies and FAQs] --> [5 · Claude Handles the Request]
[Reply + Action Taken + Confidence] --> [5 · Claude Handles the Request]
