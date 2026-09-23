# Lead → Validate → Dedupe → AI Qualify → GHL → Email → Slack

```mermaid
flowchart LR
    subgraph sec_intake["1 · CAPTURE AND VALIDATE THE LEAD"]
        direction TB
        hook(["1 · Lead Captured · Form or Webhook"])
        validate["2 · Validate Fields"]
    end
    subgraph sec_dedupe["2 · CHECK THE CRM FOR A DUPLICATE"]
        direction TB
        search["3 · GoHighLevel: Search Contact by Email"]
        dup{"4 · Duplicate?"}
        skip["5a · Skip, Already in CRM"]
    end
    subgraph sec_qualify["3 · QUALIFY AND PUSH TO THE CRM"]
        direction TB
        agent{{"5b · Qualify the Lead"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        parser{{"Force One of: Hot, Warm, Cold, Plus a Reason"}}
        create["6 · GoHighLevel: Create Contact + Tag"]
    end
    subgraph sec_followup["4 · FOLLOW UP AND NOTIFY SALES"]
        direction TB
        email["7 · Automated Follow-Up Email<br/><i>gmail</i>"]
        notify["8 · Notify Sales: Lead Processed<br/><i>slack</i>"]
    end
    subgraph sec_errors["5 · FAIL LOUDLY IF SOMETHING BREAKS"]
        direction TB
        err(["9 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["10 · Alert Sales With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> validate
    validate --> search
    search --> dup
    dup -->|true| skip
    dup -->|false| agent
    agent --> create
    create --> email
    email --> notify
    err --> alert
    model -.- agent
    parser -.- agent
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_dedupe fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_qualify fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_followup fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · CAPTURE AND VALIDATE THE LEAD** — One lead comes in from a form or any webhook. Missing email or a bad phone throws with a clear reason, so nothing half-broken reaches the CRM.
- **2 · CHECK THE CRM FOR A DUPLICATE** — Search GoHighLevel by email before creating anything. Swapping to Zoho CRM is the same two HTTP calls with different endpoints.
- **3 · QUALIFY AND PUSH TO THE CRM** — Claude reads the lead and returns hot, warm, or cold plus a one-line reason. The contact is created with that tag so sales can filter on it.
- **4 · FOLLOW UP AND NOTIFY SALES** — The lead gets a same-minute email. Sales gets one message with the score, the reason, and the CRM link.
- **5 · FAIL LOUDLY IF SOMETHING BREAKS** — Any node failing anywhere posts an alert with a link to the run. Nothing fails silently.
