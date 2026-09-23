# Inbound Lead → AI Qualify → CRM → Slack

```mermaid
flowchart LR
    subgraph sec_intake["1 · INTAKE"]
        direction TB
        hook(["New Lead Submitted"])
        normalize["Normalize Lead Fields"]
    end
    subgraph sec_enrich["2 · AI QUALIFY"]
        direction TB
        enrich["Enrich Company Domain"]
        agent{{"Score Lead vs ICP"}}
        model{{"GPT-4.1<br/><i>openai</i>"}}
        parser{{"Structured Score Output"}}
    end
    subgraph sec_route["3 · ROUTE"]
        direction TB
        gate{"Score ≥ 70?"}
    end
    subgraph sec_deliver["4 · DELIVER"]
        direction TB
        crm["Upsert CRM Contact<br/><i>hubspot</i>"]
        notify["Alert #sales<br/><i>slack</i>"]
        nurture[("Add to Nurture List<br/><i>googleSheets</i>")]
        respond["Confirm to Visitor"]
    end
    hook --> normalize
    normalize --> enrich
    enrich --> agent
    agent --> gate
    gate -->|true| crm
    gate -->|false| nurture
    crm --> notify
    notify --> respond
    model -.- agent
    parser -.- agent
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_enrich fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_deliver fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · INTAKE** — Every inbound lead — website form, landing page, or ad — lands on one webhook and is normalised into a single shape before anything downstream touches it.
- **2 · AI QUALIFY** — The company domain is enriched, then an AI agent scores fit against your ICP and writes a one-line rationale the rep can read at a glance.
- **3 · ROUTE** — Scored leads split: qualified leads go straight to the CRM and the sales channel, everything else drops into a nurture list instead of the reps' queue.
- **4 · DELIVER** — The CRM record is created or updated, the rep is notified with the score and rationale attached, and the webhook answers the form so the visitor sees an instant confirmation.
