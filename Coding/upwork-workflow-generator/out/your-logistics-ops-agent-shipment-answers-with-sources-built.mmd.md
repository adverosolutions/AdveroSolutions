# Your Logistics Ops Agent: Shipment Answers With Sources, Built on RAG

```mermaid
flowchart LR
    subgraph sec_identify["1 - IDENTIFY THE PROCESS: QUESTIONS YOUR TEAM ASKS"]
        direction TB
        chat(["1 - Your Team Asks About a Shipment or an SOP"])
    end
    subgraph sec_tools["2 - PRACTICAL TOOLS: N8N, CLAUDE AND A VECTOR STORE"]
        direction TB
        agent{{"2 - Operations Agent Finds the Answer and Its Source"}}
        model{{"Claude - Reasons Over Your SOPs and Shipments<br/><i>anthropic</i>"}}
        sops{{"RAG Tool - Search Your SOPs and Procedures<br/><i>pinecone</i>"}}
        embed{{"OpenAI Embeddings - Match the Question to Your SOPs<br/><i>openai</i>"}}
        lookup{{"Tool - Look Up the Shipment in Your System<br/><i>http</i>"}}
        draft{{"Tool - Save a Draft Customer Update on the Shipment<br/><i>http</i>"}}
        parser{{"Parser - Answer, Sources and Needs a Person"}}
    end
    subgraph sec_agent["3 - THE AGENT ANSWERS WITH SOURCES OR HANDS OFF"]
        direction TB
        gate{"3 - Answered From a Source, No Person Needed?"}
        reply["3a - Reply in Chat With the Answer and Its Sources"]
    end
    subgraph sec_integrate["4 - INTEGRATED WITH YOUR EXISTING SYSTEMS"]
        direction TB
        task["4 - Your Shipment System: Open a Task for the Ops Team"]
        handed["4b - Tell the Team Who Has It and the Task Number"]
    end
    subgraph sec_rag["5 - RAG: YOUR SOPS BECOME THE AGENT'S KNOWLEDGE"]
        direction TB
        form(["5 - Add an SOP Section Through the Upload Form"])
        cfg2["0b - Config: Your Settings"]
        vectors["5b - OpenAI: Turn the SOP Section Into Search Vectors"]
        upsert["5c - Pinecone: Save It Where the Agent Searches"]
    end
    chat --> agent
    agent --> gate
    gate -->|true| reply
    gate -->|false| task
    task --> handed
    form --> cfg2
    cfg2 --> vectors
    vectors --> upsert
    model -.- agent
    sops -.- agent
    embed -.- sops
    lookup -.- agent
    draft -.- agent
    parser -.- agent
    style sec_identify fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_tools fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_agent fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_integrate fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_rag fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - IDENTIFY THE PROCESS: QUESTIONS YOUR TEAM ASKS** - Discovery starts by ranking the work your team does by hand today: shipment status questions, customer ETA updates, CMR and POD paperwork, quoting and invoicing. This canvas builds the first of those so you can see where discovery leads.
- **2 - PRACTICAL TOOLS: N8N, CLAUDE AND A VECTOR STORE** - Practical means tools your team can run and change. n8n runs the flow, Claude does the reasoning, and a vector store holds your documents.
- **3 - THE AGENT ANSWERS WITH SOURCES OR HANDS OFF** - The agent replies only when a tool gave it a source. Anything it cannot source, or anything that needs a decision like a claim or a credit, goes to a person.
- **4 - INTEGRATED WITH YOUR EXISTING SYSTEMS** - The agent reads and writes your existing shipment system through its API. When it cannot answer, it opens a task there for your ops team.
- **5 - RAG: YOUR SOPS BECOME THE AGENT'S KNOWLEDGE** - This is the RAG part of your post. Each SOP added here is turned into search vectors so the agent can find the right section and quote it.
