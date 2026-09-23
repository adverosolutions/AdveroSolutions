# CRM Stage Trigger to SMS + Email Follow-Up With Exit Rules

```mermaid
flowchart LR
    subgraph sec_trig["1 · CRM STAGE CHANGE COMES IN"]
        direction TB
        hook(["1 · CRM Stage Changed · GoHighLevel / HubSpot"])
        norm["2 · Normalize Contact, Stage, Consent and Touch Count"]
    end
    subgraph sec_route["2 · ROUTE BY PIPELINE STAGE"]
        direction TB
        route{"3 · Route by Pipeline Stage"}
    end
    subgraph sec_seq["3 · NEW LEAD SEQUENCE: SMS, WAIT, EMAIL, WAIT"]
        direction TB
        sms1["4 · Instant SMS: Thanks, Quick Question<br/><i>twilio</i>"]
        wait1["5 · Delay Timer: Wait 1 Hour"]
        email1["6 · Email: Intro and Booking Link<br/><i>gmail</i>"]
        wait2["7 · Delay Timer: Wait 1 Day"]
        pwait["12 · Proposal Sent: Delay Timer, Wait 2 Days"]
        pemail["13 · Email: Any Questions on the Proposal?<br/><i>gmail</i>"]
        nosms["14 · No Response: Breakup SMS, Should I Close Your File?<br/><i>twilio</i>"]
    end
    subgraph sec_exit["4 · EXIT RULES AND TOUCH CAP"]
        direction TB
        exit{"8 · Replied or Booked? · Exit Rule"}
        stop["9 · Stop Sequence: Lead Responded"]
        cap{"10 · Under 4 Touches? · Touch Cap"}
        sms2["11 · Next SMS Touch, Then Back to the Day Timer<br/><i>twilio</i>"]
    end
    subgraph sec_out["5 · NOTIFY THE REP, WRITE BACK TO THE CRM, CATCH ERRORS"]
        direction TB
        notify["15 · Notify the Rep in Slack: Touch Sent or Sequence Ended<br/><i>slack</i>"]
        writeback["16 · CRM: Update Contact Sequence Status"]
        err(["17 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["18 · Alert the Rep With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> norm
    norm --> route
    route -->|New Lead| sms1
    route -->|Proposal Sent| pwait
    route -->|No Response| nosms
    sms1 --> wait1
    wait1 --> email1
    email1 --> wait2
    wait2 --> exit
    exit -->|true| stop
    exit -->|false| cap
    cap -->|true| sms2
    cap -->|false| notify
    sms2 -.-> wait2
    stop --> notify
    pwait --> pemail
    pemail --> notify
    nosms --> notify
    notify --> writeback
    err --> alert
    style sec_trig fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_seq fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_exit fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_out fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · CRM STAGE CHANGE COMES IN** — GoHighLevel or HubSpot fires a webhook when a contact moves stage. We normalize the contact so every stage below reads the same fields.
- **2 · ROUTE BY PIPELINE STAGE** — One switch, one sequence per stage. Adding a stage later is one more arm, not a rebuild.
- **3 · NEW LEAD SEQUENCE: SMS, WAIT, EMAIL, WAIT** — Instant SMS while the lead is still warm, email an hour later, then a full day before the next check. Every delay timer is visible in its label.
- **4 · EXIT RULES AND TOUCH CAP** — If they replied or booked, the sequence stops. Otherwise one more SMS and back to the day timer, until the touch cap ends it.
- **5 · NOTIFY THE REP, WRITE BACK TO THE CRM, CATCH ERRORS** — The rep sees every touch in Slack and the CRM holds the sequence state. Any failure alerts with a link to the run.
