# AI Marketing Automation: Acquire, Nurture, Retain, Report

```mermaid
flowchart LR
    subgraph sec_capture["1 - CAPTURE EVERY LEAD AND CUSTOMER EVENT"]
        direction TB
        hook(["1 - New Lead or Customer Event Arrives"])
        norm["2 - Normalize Source, Stage, and Last Activity"]
    end
    subgraph sec_decide["2 - DECIDE WHO THEY ARE AND WHAT THEY GET NEXT"]
        direction TB
        agent{{"3 - Claude Segments and Picks the Next Best Message"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        tool{{"CRM Lookup: Past Opens, Purchases, and Stage"}}
        parser{{"Force Segment, Campaign, Channel, and Send Time"}}
        route{"4 - Route by Journey: Acquisition, Nurture, Retention"}
    end
    subgraph sec_acquisition["3 - ACQUISITION: WELCOME THE NEW ONES"]
        direction TB
        welcome["5 - Send the Welcome and First Offer Email<br/><i>gmail</i>"]
    end
    subgraph sec_journey["4 - NURTURE AND RETENTION: KEEP THEM MOVING"]
        direction TB
        wait["6 - Wait Two Days Before the Next Touch"]
        write{{"7 - Claude Writes the Personalized Nurture Touch"}}
        nurture_send["8 - Send the Nurture Email<br/><i>gmail</i>"]
        engaged{"9 - Did They Open or Click It?"}
        inactive{"10 - Quiet for 30 Days or More?"}
        winback["11 - Send the Win Back Campaign<br/><i>gmail</i>"]
    end
    subgraph sec_measure["5 - MEASURE, REPORT, AND CATCH FAILURES"]
        direction TB
        crm["12 - Update CRM Stage and Tags<br/><i>hubspot</i>"]
        sheet[("13 - Log a Campaign Metrics Row<br/><i>googleSheets</i>")]
        cron(["14 - Every Monday Morning"])
        rollup["15 - Roll Up Opens, Clicks, and Conversions"]
        digest["16 - Post the Weekly Performance Digest<br/><i>slack</i>"]
        err(["17 - Any Step Fails, Anywhere<br/><i>n8n</i>"])
        alert["18 - Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> norm
    norm --> agent
    agent --> route
    route -->|Acquisition| welcome
    route -->|Nurture| wait
    route -->|Retention| inactive
    welcome --> crm
    wait --> write
    write --> nurture_send
    nurture_send --> engaged
    engaged -->|true| crm
    engaged -.->|false| wait
    inactive -->|true| winback
    inactive -->|false| crm
    winback --> crm
    crm --> sheet
    cron --> rollup
    rollup --> digest
    err --> alert
    model -.- agent
    tool -.- agent
    parser -.- agent
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_decide fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_acquisition fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_journey fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_measure fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - CAPTURE EVERY LEAD AND CUSTOMER EVENT** - Form fills, purchases and signups all land in one place and get cleaned into the same shape.
- **2 - DECIDE WHO THEY ARE AND WHAT THEY GET NEXT** - Claude looks the person up in the CRM and picks the next best message instead of a fixed drip.
- **3 - ACQUISITION: WELCOME THE NEW ONES** - Brand new contacts get the welcome and the first offer straight away, while interest is highest.
- **4 - NURTURE AND RETENTION: KEEP THEM MOVING** - Nurture loops a personalized touch every two days until they engage, capped so nobody gets spammed. Quiet customers get a win back instead.
- **5 - MEASURE, REPORT, AND CATCH FAILURES** - Every send updates the CRM and logs a metrics row, and Monday morning the numbers land in Slack.
