# Prospect Research, Fit-Check, Verify, Route to Hunter Campaign

```mermaid
flowchart LR
    subgraph sec_pull["1 · PULL TODAY'S CANDIDATE COMPANIES"]
        direction TB
        cron(["1 · Every Weekday at 7am"])
        source["2 · Apollo: Pull Candidate Companies by Industry and Size<br/><i>apollo</i>"]
        loop["3 · Work Through One Company at a Time"]
    end
    subgraph sec_fit["2 · RESEARCH AND FIT-CHECK AGAINST YOUR CRITERIA"]
        direction TB
        agent{{"4 · Fit-Check Against Your Written Criteria"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        site{{"Read the Company Website and About Page"}}
        parser{{"Force: Fit Yes/No, Segment, Confidence, Reason"}}
        fits{"5 · Does It Fit, With High Confidence?"}
    end
    subgraph sec_contact["3 · FIND AND VERIFY THE DECISION-MAKER"]
        direction TB
        finddm["6 · Hunter: Find Decision-Maker by Domain and Title<br/><i>hunter</i>"]
        verify["7 · Hunter: Verify the Email Address<br/><i>hunter</i>"]
        deliverable{"8 · Is the Email Deliverable?"}
    end
    subgraph sec_route["4 · DEDUPE AND ADD TO THE RIGHT CAMPAIGN"]
        direction TB
        dedupe["9 · Hunter: Check if Already in Any Campaign<br/><i>hunter</i>"]
        isnew{"10 · Is This a Brand New Lead?"}
        segment{"11 · Route by Segment"}
        addlocal["12a · Hunter: Add to Local Service Campaign<br/><i>hunter</i>"]
        addmed["12b · Hunter: Add to Medtech Campaign<br/><i>hunter</i>"]
        addb2b["12c · Hunter: Add to B2B Campaign<br/><i>hunter</i>"]
    end
    subgraph sec_digest["5 · LOG EVERY DECISION, SEND THE DAILY DIGEST"]
        direction TB
        log[("13 · Log the Decision: Added or Rejected, and Why<br/><i>googleSheets</i>")]
        slack["14 · Slack: Daily Digest of Added, Rejected, and Reasons<br/><i>slack</i>"]
        err(["15 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["16 · Slack: Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    cron --> source
    source --> loop
    loop -->|loop| agent
    loop -->|done| slack
    agent --> fits
    fits -->|true| finddm
    fits -->|false| log
    finddm --> verify
    verify --> deliverable
    deliverable -->|true| dedupe
    deliverable -->|false| log
    dedupe --> isnew
    isnew -->|true| segment
    isnew -->|false| log
    segment -->|Local Service| addlocal
    segment -->|Medtech| addmed
    segment -->|B2B| addb2b
    addlocal --> log
    addmed --> log
    addb2b --> log
    log -.-> loop
    err --> alert
    model -.- agent
    site -.- agent
    parser -.- agent
    style sec_pull fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_fit fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_contact fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_digest fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · PULL TODAY'S CANDIDATE COMPANIES** — Runs every weekday morning. Pulls a small batch from the source list and works through it one company at a time.
- **2 · RESEARCH AND FIT-CHECK AGAINST YOUR CRITERIA** — Claude reads the company site and judges it against your written criteria. Anything it is not sure about gets rejected with the reason, not added.
- **3 · FIND AND VERIFY THE DECISION-MAKER** — Hunter finds the right person by title, then verifies the address. Unverified emails never reach a campaign.
- **4 · DEDUPE AND ADD TO THE RIGHT CAMPAIGN** — Skips anyone already in a campaign, then routes by segment: local service, medtech, or B2B.
- **5 · LOG EVERY DECISION, SEND THE DAILY DIGEST** — Every company lands in the log, added or rejected, with the reason. One Slack message a day shows both lists.
