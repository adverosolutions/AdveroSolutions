# Production AI Chatbot Backend - RAG, Memory, Analytics

```mermaid
flowchart LR
    subgraph sec_conversation["1 - THE CONVERSATION"]
        direction TB
        chat(["1 - Message Arrives From the Web Widget"])
        load["2 - Load the User, the Session and Recent History"]
    end
    subgraph sec_answer["2 - HOW THE ANSWER GETS BUILT"]
        direction TB
        agent{{"3 - Answer From Your Knowledge Base and Your APIs"}}
        model{{"OpenAI GPT-4.1<br/><i>openai</i>"}}
        memory{{"Conversation History, One Thread Per User"}}
        kb{{"Your Knowledge Base, Searched by Meaning<br/><i>supabase</i>"}}
        embed{{"Turns the Question Into a Search Vector<br/><i>openai</i>"}}
        apitool{{"Your REST API: Account, Orders, Subscription"}}
        parser{{"Force: Answer, Sources, Confidence, Escalate Yes or No"}}
        compose["4 - Assemble the Reply With Its Sources"]
    end
    subgraph sec_handoff["3 - REPLY, HAND OFF, AND LOG EVERY TURN"]
        direction TB
        escalate{"5 - Does This One Need a Human?"}
        handoff["6a - Hand It to Support With the Whole Thread<br/><i>slack</i>"]
        reply["6b - Stream the Answer Back Into the Widget"]
        save[("7 - Save This Turn to Conversation History<br/><i>supabase</i>")]
        analytics[("8 - Log Intent, Answer Time, Token Cost and Rating<br/><i>googleSheets</i>")]
    end
    subgraph sec_ingestion["4 - KEEPING THE KNOWLEDGE BASE CURRENT"]
        direction TB
        nightly(["9 - Re-Index Your Knowledge Base Every Night"])
        crawl["10 - Crawl Your Docs, Help Centre and Product Pages"]
        changed["11 - Keep Only the Pages That Changed Since Last Night"]
        chunk["12 - Split Each Page Into Passages the Bot Can Quote"]
        upsert["13 - Embed the Passages and Upsert Into the Vector Store"]
    end
    subgraph sec_errors["5 - WHEN SOMETHING BREAKS"]
        direction TB
        err(["14 - Any Step Fails, Anywhere<br/><i>n8n</i>"])
        alert["15 - Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    chat --> load
    load --> agent
    agent --> compose
    compose --> escalate
    escalate -->|true| handoff
    escalate -->|false| reply
    handoff --> save
    reply --> save
    save --> analytics
    nightly --> crawl
    crawl --> changed
    changed --> chunk
    chunk --> upsert
    err --> alert
    model -.- agent
    memory -.- agent
    kb -.- agent
    embed -.- kb
    apitool -.- agent
    parser -.- agent
    style sec_conversation fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_answer fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_handoff fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_ingestion fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - THE CONVERSATION** - Every message arrives with a user id and a session id, so the bot knows who it is talking to before it thinks.
- **2 - HOW THE ANSWER GETS BUILT** - One agent, with your knowledge base and your REST API attached to it. It has to cite where the answer came from.
- **3 - REPLY, HAND OFF, AND LOG EVERY TURN** - Low confidence goes to a human with the full thread. Everything else streams back and gets written down either way.
- **4 - KEEPING THE KNOWLEDGE BASE CURRENT** - Runs on its own every night. This is the part that stops the bot answering from last quarter's docs.
- **5 - WHEN SOMETHING BREAKS** - A failed run pings me with a link to it. Nothing fails quietly in front of a customer.
