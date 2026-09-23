# Website Chatbot — Answer from Site Content, Escalate the Rest

```mermaid
flowchart LR
    subgraph sec_chat["1 · CHAT"]
        direction TB
        hook(["Visitor Opens the Website Chat"])
    end
    subgraph sec_answer["2 · ANSWER"]
        direction TB
        agent{{"Answer from Website Content"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        mem{{"Conversation Memory"}}
        vec{{"Website Pages & FAQs"}}
        emb{{"Site Content Embeddings<br/><i>openai</i>"}}
    end
    subgraph sec_handle["3 · REPLY OR ESCALATE"]
        direction TB
        gate{"Answered from the knowledge base"}
        resp["Reply in the Chat Widget"]
        cap[("Capture Email & Log the Gap<br/><i>googleSheets</i>")]
        team["Notify the Team<br/><i>gmail</i>"]
    end
    hook --> agent
    agent --> gate
    gate -->|true| resp
    gate -->|false| cap
    cap --> team
    model -.- agent
    mem -.- agent
    vec -.- agent
    emb -.- vec
    style sec_chat fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_answer fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_handle fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 · CHAT** — A single embed snippet on the existing site. No replatforming, no page rebuild.
- **2 · ANSWER** — Answers are retrieved from your own pages and FAQs, so the bot can only say things your site actually says.
- **3 · REPLY OR ESCALATE** — The important half: when the bot does not know, it says so, captures an email and tells you — instead of guessing at a customer.
