# Full Cold Email Funnel - Scrape, Enrich, Personalize, Send, Reply

```mermaid
flowchart LR
    subgraph sec_scrape["1 - SCRAPE THE TARGET COMPANIES"]
        direction TB
        sched(["1 - Daily Prospect Run"])
        apify["2 - Apify: Scrape Target Companies From Google Maps and LinkedIn"]
        split["3 - Take One Company at a Time"]
    end
    subgraph sec_contact["2 - FIND AND VERIFY THE DECISION MAKER"]
        direction TB
        find["4 - Snov.io: Find the Decision Maker's Email"]
        verify["5 - Snov.io: Verify That Email Is Deliverable"]
        deliverable{"6 - Did the Address Come Back Deliverable?"}
    end
    subgraph sec_write["3 - RESEARCH AND WRITE A PERSONAL FIRST LINE"]
        direction TB
        agent{{"8 - Research the Company and Write a Personalized First Line"}}
        model{{"OpenAI<br/><i>openai</i>"}}
        site{{"Read the Company Website"}}
        parser{{"Force Back a First Line, an Angle, and a Fit Score"}}
        fit{"9 - Is the Fit Score Above Your Threshold?"}
    end
    subgraph sec_send["4 - LOAD THE CAMPAIGN AND KEEP THE RECORD"]
        direction TB
        skiplog["7 - Record Why This Company Was Skipped"]
        addcamp["10 - Snov.io: Add the Prospect to the Campaign With Custom Fields"]
        sheet[("11 - Log Every Company Added and Rejected, With the Reason<br/><i>googleSheets</i>")]
    end
    subgraph sec_replies["5 - HANDLE EVERY REPLY THE SAME DAY"]
        direction TB
        hook(["12 - A Reply Comes Back From Snov.io"])
        classify{{"13 - OpenAI: Read the Reply and Label It Interested, Not Now, or Unsubscribe"}}
        route{"14 - Route on What They Actually Said"}
        slackhot["14a - Send Interested Leads Straight to You<br/><i>slack</i>"]
        pause["14b - Snov.io: Pause the Sequence and Try Again Later"]
        unsub["14c - Snov.io: Unsubscribe Them and Stop All Email"]
        err(["15 - Any Step Fails, Anywhere<br/><i>n8n</i>"])
        alert["16 - Alert You With a Link to the Failed Run<br/><i>slack</i>"]
    end
    sched --> apify
    apify --> split
    split -->|loop| find
    split -->|done| sheet
    find --> verify
    verify --> deliverable
    deliverable -->|true| agent
    deliverable -->|false| skiplog
    agent --> fit
    fit -->|true| addcamp
    fit -->|false| skiplog
    addcamp -.-> split
    skiplog -.-> split
    hook --> classify
    classify --> route
    route -->|Interested| slackhot
    route -->|Not Now| pause
    route -->|Unsubscribe| unsub
    err --> alert
    model -.- agent
    site -.- agent
    parser -.- agent
    style sec_scrape fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_contact fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_write fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_send fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_replies fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - SCRAPE THE TARGET COMPANIES** - Apify pulls the company list on a schedule. Nothing is typed in by hand.
- **2 - FIND AND VERIFY THE DECISION MAKER** - Snov.io finds the person and checks the address before a single email is queued.
- **3 - RESEARCH AND WRITE A PERSONAL FIRST LINE** - The agent reads their website and writes one line about them, plus a fit score.
- **4 - LOAD THE CAMPAIGN AND KEEP THE RECORD** - Only prospects that passed both checks get added. Everything else is logged with a reason.
- **5 - HANDLE EVERY REPLY THE SAME DAY** - Interested reaches you in Slack. Not now and unsubscribe are handled without you touching them.
