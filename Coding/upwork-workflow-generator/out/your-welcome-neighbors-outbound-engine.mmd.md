# Your Welcome Neighbors Outbound Engine

```mermaid
flowchart LR
    subgraph sec_source["1 - SOURCE LOCAL BUSINESSES BY AREA"]
        direction TB
        sched(["1 - Every Weekday at 6am, Next Target Metro"])
        maps["2 - Google Maps: Pull HVAC, Dental, Roofing and Plumbing Businesses in the Zip Codes"]
    end
    subgraph sec_clay["2 - CLAY ENRICHMENT WATERFALL"]
        direction TB
        enrich["3 - Clay: Enrich the Business, Website, Phone, Size and Reviews"]
        owner["4 - Clay: Find the Owner or Decision Maker"]
        waterfall["5 - Clay Waterfall: Email From 3 Providers, Then Verify It Is Deliverable"]
        found{"6 - Deliverable and Owner Found?"}
    end
    subgraph sec_qualify["3 - QUALIFY AND PERSONALIZE"]
        direction TB
        score{{"7 - Claude Scores Fit: Serves New Movers, Size, Reviews, Ads Running"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        tool{{"Read Their Website and Google Profile"}}
        parser{{"Score 1 to 10, Segment, First Line"}}
        gate{"8 - Score 7 or Higher?"}
        park[("9 - Park It: Log the Reason, Retry Next Cycle<br/><i>googleSheets</i>")]
    end
    subgraph sec_campaign["4 - INTO THE CAMPAIGN"]
        direction TB
        instantly["10 - Instantly: Add Lead to the Segment Campaign With the First Line and Follow-Ups"]
    end
    subgraph sec_replies["5 - REPLIES, ROUTING AND THE NUMBERS"]
        direction TB
        reply(["11 - Instantly: Reply Comes In"])
        sort{{"12 - Claude Sorts the Reply: Interested, Question, Not Now, Unsubscribe"}}
        sortmodel{{"Claude<br/><i>anthropic</i>"}}
        route{"13 - Route the Reply"}
        ghl["14 - GoHighLevel: Create the Lead and Notify Sales"]
        human["14b - Hand to a Human<br/><i>slack</i>"]
        nurture[("14c - Nurture List, Retry in 90 Days<br/><i>googleSheets</i>")]
        unsub["14d - Instantly: Unsubscribe Everywhere"]
        scorecard[("15 - Daily Scorecard: Sent, Delivered, Replies, Positive, Booked<br/><i>googleSheets</i>")]
        err(["16 - Any Step Fails<br/><i>n8n</i>"])
        alert["17 - Alert With the Failing Node<br/><i>slack</i>"]
    end
    sched --> maps
    maps --> enrich
    enrich --> owner
    owner --> waterfall
    waterfall --> found
    found -->|true| score
    found -->|false| park
    score --> gate
    gate -->|true| instantly
    gate -->|false| park
    reply --> sort
    sort --> route
    route -->|Interested| ghl
    route -->|Question| human
    route -->|Not Now| nurture
    route -->|Unsubscribe| unsub
    ghl --> scorecard
    err --> alert
    instantly --> scorecard
    model -.- score
    tool -.- score
    parser -.- score
    sortmodel -.- sort
    style sec_source fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_clay fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_qualify fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_campaign fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_replies fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - SOURCE LOCAL BUSINESSES BY AREA** - Pick the metro, pull every HVAC, dental, roofing and plumbing business in those zip codes. Nobody uploads a CSV.
- **2 - CLAY ENRICHMENT WATERFALL** - Clay enriches the business, finds the owner, then runs three email providers in order until one returns a verified address.
- **3 - QUALIFY AND PERSONALIZE** - Claude reads their site and Google profile, scores the fit, and writes the first line off what it actually found.
- **4 - INTO THE CAMPAIGN** - The lead lands in the campaign for its segment with the variables already filled, and the follow-ups run on schedule.
- **5 - REPLIES, ROUTING AND THE NUMBERS** - Every reply is read and routed within minutes, and the day's real numbers land in one sheet you can open.
