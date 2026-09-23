# Small Business AI Assistant - Prompt Layer + MCP Tool Connections

```mermaid
flowchart LR
    subgraph sec_intake["1 - A REQUEST COMES IN FROM ANY CHANNEL"]
        direction TB
        chat(["1 - Customer or Staff Message"])
        norm["2 - Normalize Channel, Sender, Business ID"]
    end
    subgraph sec_prompt["2 - LOAD THE BUSINESS'S PROMPT PROFILE"]
        direction TB
        profile[("3 - Read the Prompt Profile for This Business<br/><i>googleSheets</i>")]
        build["4 - Assemble System Prompt - Tone + Rules + Context"]
    end
    subgraph sec_reason["3 - CLAUDE DECIDES AND USES THE BUSINESS'S OWN TOOLS"]
        direction TB
        agent{{"5 - Claude Handles the Request"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        memory{{"Conversation Memory - per customer"}}
        mcp_crm{{"MCP - CRM: Find or Update a Customer"}}
        mcp_cal{{"MCP - Calendar: Check and Book Slots"}}
        mcp_inv{{"MCP - Invoicing: Balance and Payment Link"}}
        mcp_kb{{"MCP - Business Docs: Policies and FAQs"}}
        parser{{"Reply + Action Taken + Confidence"}}
    end
    subgraph sec_guard["4 - CHECK THE ANSWER BEFORE IT GOES OUT"]
        direction TB
        risky{"6 - Money, Booking Change, or Complaint?"}
        review["7a - Send to Owner for a One-Tap Approve<br/><i>slack</i>"]
        reply["7b - Reply to the Customer"]
    end
    subgraph sec_learn["5 - LOG IT SO THE PROMPTS GET BETTER EVERY WEEK"]
        direction TB
        score{{"8 - Score the Exchange Against the Prompt Rules"}}
        log[("9 - Log Prompt Version, Score, Tools Used<br/><i>googleSheets</i>")]
    end
    chat --> norm
    norm --> profile
    profile --> build
    build --> agent
    agent --> risky
    risky -->|true| review
    risky -->|false| reply
    review --> score
    reply --> score
    score --> log
    model -.- agent
    memory -.- agent
    mcp_crm -.- agent
    mcp_cal -.- agent
    mcp_inv -.- agent
    mcp_kb -.- agent
    parser -.- agent
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_prompt fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_reason fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_guard fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_learn fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - A REQUEST COMES IN FROM ANY CHANNEL** - Chat widget, email, or an internal form. Every request lands in the same lane so one set of prompts serves all of them.
- **2 - LOAD THE BUSINESS'S PROMPT PROFILE** - Tone, services, pricing rules, and what the assistant is never allowed to promise live in a sheet the owner can edit. No code change to update a prompt.
- **3 - CLAUDE DECIDES AND USES THE BUSINESS'S OWN TOOLS** - Each tool is an MCP connection into software the business already pays for. Claude reads and writes real records instead of guessing.
- **4 - CHECK THE ANSWER BEFORE IT GOES OUT** - Anything touching money, bookings, or a complaint goes to a human first. Everything else replies on its own.
- **5 - LOG IT SO THE PROMPTS GET BETTER EVERY WEEK** - Every exchange is scored. Low-scoring ones become next week's prompt revisions.
