# Your Seller and Agent Outbound System

```mermaid
flowchart LR
    subgraph sec_lists["1 - TWO LISTS, ONE PIPE"]
        direction TB
        sched(["1 - Every Weekday at 6am"])
        sellers["2 - Pull Fresh Distressed-Owner Records: Probate, Tax Lien, Pre-Foreclosure"]
        agents["2b - Pull Agents With Aged or Off-Market Listings"]
        queue["3 - One Queue, Tagged Seller or Agent"]
    end
    subgraph sec_clean["2 - CLEAN BEFORE ANYTHING SENDS"]
        direction TB
        verify["4 - Verify Every Email"]
        deliverable{"5 - Deliverable?"}
        suppress[("5b - Suppressed: Bounces and Catch-Alls<br/><i>googleSheets</i>")]
        history[("6 - Already Contacted or Opted Out?<br/><i>googleSheets</i>")]
        isnew{"7 - New Contact?"}
    end
    subgraph sec_write["3 - WRITE THE HUMAN VERSION"]
        direction TB
        writer{{"8 - Claude Writes the Plain-Text First Line and Picks the Angle"}}
        writermodel{{"Claude<br/><i>anthropic</i>"}}
        writertool{{"Read the Property Record or Listing"}}
        writerparser{{"First Line, Angle, Campaign"}}
        which{"9 - Seller or Agent?"}
        seqseller["10a - Instantly: Add to the Seller Sequence"]
        seqagent["10b - Instantly: Add to the Agent Sequence"]
    end
    subgraph sec_replies["4 - REPLIES INTO YOUR CRM"]
        direction TB
        reply(["11 - Instantly: Reply Comes In"])
        sort{{"12 - Sort the Reply: Interested, Question, Not Now, Remove"}}
        sortmodel{{"Claude<br/><i>anthropic</i>"}}
        route{"13 - Route"}
        crm["14 - CRM: Create the Lead and Alert Acquisitions"]
        human["14b - Hand to a Human<br/><i>slack</i>"]
        nurture[("14c - Nurture, Retry in 90 Days<br/><i>googleSheets</i>")]
        unsub["14d - Instantly: Unsubscribe and Suppress"]
    end
    subgraph sec_numbers["5 - NUMBERS AND NOTHING FAILS QUIETLY"]
        direction TB
        scorecard[("15 - Daily Scorecard: Sent, Bounce, Reply, Positive, Appointments<br/><i>googleSheets</i>")]
        err(["16 - Any Step Fails<br/><i>n8n</i>"])
        alert["17 - Alert With the Failing Node<br/><i>slack</i>"]
    end
    sched --> sellers
    sched --> agents
    sellers --> queue
    agents --> queue
    queue --> verify
    verify --> deliverable
    deliverable -->|true| history
    deliverable -->|false| suppress
    history --> isnew
    isnew -->|true| writer
    isnew -->|false| suppress
    writer --> which
    which -->|Seller| seqseller
    which -->|Agent| seqagent
    reply --> sort
    sort --> route
    route -->|Interested| crm
    route -->|Question| human
    route -->|Not Now| nurture
    route -->|Remove| unsub
    seqseller --> scorecard
    seqagent --> scorecard
    crm --> scorecard
    err --> alert
    writermodel -.- writer
    writertool -.- writer
    writerparser -.- writer
    sortmodel -.- sort
    style sec_lists fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_clean fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_write fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_replies fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_numbers fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - TWO LISTS, ONE PIPE** - Fresh distressed-owner records and agents sitting on aged or off-market listings get pulled on the same schedule, then merged into one queue with a seller or agent tag. Two campaigns, one system, nobody uploads a CSV.
- **2 - CLEAN BEFORE ANYTHING SENDS** - Every address is verified, bounces and catch-alls are suppressed instead of sent, and anyone already contacted or opted out is filtered out. This is what keeps the sending domains alive.
- **3 - WRITE THE HUMAN VERSION** - Claude reads the actual property record or listing and writes the plain-text first line off what it found, picks the angle, then the lead drops into the seller or the agent sequence.
- **4 - REPLIES INTO YOUR CRM** - Every reply is read and sorted within minutes. Interested goes straight to the CRM with acquisitions alerted, questions go to a human, not now goes to nurture, remove is suppressed everywhere.
- **5 - NUMBERS AND NOTHING FAILS QUIETLY** - One scorecard row a day with sent, bounce, reply, positive and appointments, so scaling is a decision off real numbers. If any step fails you get told which node and which record.
