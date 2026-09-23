# Your Commercial Cleaning Prospecting Engine

```mermaid
flowchart LR
    subgraph sec_discover["1 - DISCOVER"]
        direction TB
        sched(["1 - Every Weekday at 5am, Next Zip Cluster"])
        outscraper["2 - Outscraper: Offices, Medical, Gyms, Schools, Warehouses Over 5,000 Sq Ft"]
        normalize["3 - Normalize: Name, Address, Phone, Category, Reviews"]
        seen[("4 - Seen Before? Check the Prospect Database<br/><i>postgres</i>")]
        isnew{"5 - New Prospect?"}
        skip["5b - Skip, Already Known"]
    end
    subgraph sec_enrich["2 - ENRICH"]
        direction TB
        apollo["6 - Apollo: Find the Facilities or Office Manager and Verified Email"]
        dmfound{"7 - Decision Maker Found?"}
        manual[("7b - Park for Manual Enrichment<br/><i>postgres</i>")]
    end
    subgraph sec_research["3 - RESEARCH AND SCORE"]
        direction TB
        agent{{"8 - Research Agent: Size, Foot Traffic, Current Vendor Signals, Hiring"}}
        model{{"GPT-4o<br/><i>openai</i>"}}
        tool{{"Read the Website and Google Profile"}}
        parser{{"Score 1 to 10, Reason, Best Angle"}}
        gate{"9 - Score 7 or Higher?"}
        lowpri[("9b - Store as Low Priority<br/><i>postgres</i>")]
    end
    subgraph sec_approval["4 - HUMAN APPROVAL, THEN THE CRM"]
        direction TB
        post["10 - Post the Top Prospects to #approvals With Approve and Reject Buttons<br/><i>slack</i>"]
        decision(["11 - Approval Decision Comes Back"])
        approved{"12 - Approved?"}
        rejected[("12b - Rejected, With the Reason, Feeds the Scoring Prompt<br/><i>postgres</i>")]
        ghlcontact["13 - HighLevel: Create Contact, Tag, Opportunity in Prospecting Pipeline"]
        ghlworkflow["14 - HighLevel: Trigger the Sales Follow-Up Workflow"]
    end
    subgraph sec_logs["5 - LOGS, DEDUPE, ALERTS"]
        direction TB
        record[("15 - Write the Prospect Record With Score, Source, Approval<br/><i>postgres</i>")]
        err(["16 - Any Step Fails<br/><i>n8n</i>"])
        alert["17 - Alert With the Failing Node<br/><i>slack</i>"]
    end
    sched --> outscraper
    outscraper --> normalize
    normalize --> seen
    seen --> isnew
    isnew -->|true| apollo
    isnew -->|false| skip
    apollo --> dmfound
    dmfound -->|true| agent
    dmfound -->|false| manual
    agent --> gate
    gate -->|true| post
    gate -->|false| lowpri
    post --> decision
    decision --> approved
    approved -->|true| ghlcontact
    approved -->|false| rejected
    ghlcontact --> ghlworkflow
    ghlworkflow --> record
    err --> alert
    model -.- agent
    tool -.- agent
    parser -.- agent
    style sec_discover fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_enrich fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_research fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_approval fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_logs fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - DISCOVER** - Outscraper works one zip cluster a morning and pulls the buildings that actually buy cleaning. Nobody uploads a list.
- **2 - ENRICH** - Apollo turns a building into a named facilities or office manager with a verified email. No name, no guessing, it parks.
- **3 - RESEARCH AND SCORE** - The agent reads the site and the Google profile, then scores the account on size, foot traffic, vendor signals and hiring.
- **4 - HUMAN APPROVAL, THEN THE CRM** - Nothing reaches HighLevel until a human says yes. The morning list posts to Slack, one tap approves, one tap rejects with a reason.
- **5 - LOGS, DEDUPE, ALERTS** - Postgres is the dedupe key, by place id and normalized phone, so the same building never shows up twice. Every failure names its node.
