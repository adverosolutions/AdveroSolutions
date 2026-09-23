# Lead In → AI Tier → HubSpot With Retries → Slack → Run Log

```mermaid
flowchart LR
    subgraph sec_intake["1 · RECEIVE AND VALIDATE THE LEAD"]
        direction TB
        hook(["1 · New Lead Arrives From the Website Form"])
        validate["2 · Check Required Fields and Clean Up the Data"]
        valid{"3 · Does the Lead Have an Email and a Company?"}
        reject["3b · Reject With the Missing Field Named"]
    end
    subgraph sec_dedupe["2 · CHECK HUBSPOT FOR AN EXISTING CONTACT"]
        direction TB
        lookup["4 · HubSpot: Search Contacts by Email"]
        dupe{"5 · Is This Contact Already in HubSpot?"}
    end
    subgraph sec_qualify["3 · AI QUALIFIES THE LEAD INTO A TIER"]
        direction TB
        agent{{"6 · Qualify the Lead Into Hot, Warm or Cold"}}
        model{{"OpenAI GPT-4.1<br/><i>openai</i>"}}
        parser{{"Force One of: Hot, Warm, Cold, Plus a Reason and Score"}}
    end
    subgraph sec_act["4 · ACT BY TIER, RETRY THE CRM IF IT FAILS"]
        direction TB
        route{"7 · Route by Tier"}
        contact["8a · HubSpot: Create the Contact<br/><i>hubspot</i>"]
        crmok{"9 · Did the CRM Call Succeed?"}
        wait["9b · Wait 30 Seconds and Retry, Up to 3 Times"]
        deal["10 · HubSpot: Open a Deal for Sales<br/><i>hubspot</i>"]
        nurture["8b · Send the Warm Lead a Nurture Email<br/><i>gmail</i>"]
        coldlog["8c · Cold Lead: Log Only, No Outreach"]
    end
    subgraph sec_log["5 · LOG EVERY RUN, ALERT ON ANY FAILURE"]
        direction TB
        slack["11 · Post the Lead, Tier and Reason to the Sales Channel<br/><i>slack</i>"]
        logrow[("12 · Write a Run Log Row With Tier, Ids, Retries and Timing<br/><i>googleSheets</i>")]
        err(["13 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["14 · Alert the Channel With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> validate
    validate --> valid
    valid -->|false| reject
    valid -->|true| lookup
    lookup --> dupe
    dupe -->|true| logrow
    dupe -->|false| agent
    agent --> route
    route -->|Hot| contact
    route -->|Warm| nurture
    route -->|Cold| coldlog
    contact --> crmok
    crmok -->|true| deal
    crmok -->|false| wait
    wait -.-> contact
    deal --> slack
    nurture --> slack
    coldlog --> logrow
    slack --> logrow
    err --> alert
    model -.- agent
    parser -.- agent
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_dedupe fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_qualify fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_act fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_log fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · RECEIVE AND VALIDATE THE LEAD** — Every lead is checked before anything downstream runs. A bad payload is rejected with the missing field named, not failed halfway through.
- **2 · CHECK HUBSPOT FOR AN EXISTING CONTACT** — One search by email before we create anything. A returning contact is logged and never duplicated in the CRM.
- **3 · AI QUALIFIES THE LEAD INTO A TIER** — OpenAI reads the form answers and company details and returns one of Hot, Warm or Cold with a reason. The parser forces the shape so the switch below never gets free text.
- **4 · ACT BY TIER, RETRY THE CRM IF IT FAILS** — Hot goes straight into HubSpot as a contact plus a deal. Warm gets a nurture email. Cold is logged only. If HubSpot errors or rate limits, we wait and retry up to three times before giving up.
- **5 · LOG EVERY RUN, ALERT ON ANY FAILURE** — Sales sees every qualified lead in Slack. Every run writes a log row with tier, ids and timing. Anything that breaks anywhere pings the channel with a link to the failed execution.
