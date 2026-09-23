# Partner Operations Hub - One Record, Tier Activation, AI Deliverables

```mermaid
flowchart LR
    subgraph sec_record["1 - ONE PARTNER RECORD"]
        direction TB
        hook(["1 - Partner Created or Updated in CRM, PRM, Notion or Sheets"])
        normalize["2 - Normalize to One Partner Record - Tier, Type, Owner, Stage"]
        crm["3 - Update the Partner in the CRM<br/><i>hubspot</i>"]
        prm["4 - Update the Same Record in the PRM"]
        notion["5 - Update the Notion Partner Page<br/><i>notion</i>"]
        sheet[("6 - Update the Master Sheet Row<br/><i>googleSheets</i>")]
    end
    subgraph sec_activate["2 - ACTIVATION BY PARTNER TIER"]
        direction TB
        route{"7 - Route Activation by Partner Tier"}
        t1tasks["8a - Tier 1: Create the Joint Campaign Task Set<br/><i>clickup</i>"]
        t1email["8b - Tier 1: Send the Kickoff Email to the Partner<br/><i>gmail</i>"]
        t2checklist["9 - Tier 2: Create the Webinar Checklist<br/><i>clickup</i>"]
        t3wait["10a - Tier 3: Wait 30 Days"]
        t3email["10b - Tier 3: Send the Automated Check-In<br/><i>gmail</i>"]
    end
    subgraph sec_deliver["3 - AI DELIVERABLES FROM YOUR OWN TEMPLATES"]
        direction TB
        brief(["11 - Client Inputs Submitted - the Project Brief"])
        agent{{"12 - Claude Drafts the Deliverable From Your Template"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        tpl{{"Template and Framework Library - Notion"}}
        lookup{{"Partner Record Lookup"}}
        parser{{"Force Your Sections: Objective, Audience, Offer, Plan, Next Steps"}}
        doc["13 - Put the Draft in Google Docs for Review<br/><i>googleDocs</i>"]
    end
    subgraph sec_review["4 - REVIEW AND MEASURE"]
        direction TB
        reviewping["14 - Send the Review Request to the Partner Owner<br/><i>slack</i>"]
        log[("15 - Log the Activity and the Hours It Saved<br/><i>googleSheets</i>")]
    end
    subgraph sec_errors["5 - WHEN SOMETHING BREAKS"]
        direction TB
        err(["16 - Any Step Fails, Anywhere<br/><i>n8n</i>"])
        alert["17 - Alert the Owner With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> normalize
    normalize --> crm
    normalize --> prm
    normalize --> notion
    normalize --> sheet
    crm --> route
    prm --> route
    notion --> route
    sheet --> route
    route -->|Tier 1| t1tasks
    route -->|Tier 2| t2checklist
    route -->|Tier 3| t3wait
    t1tasks --> t1email
    t3wait --> t3email
    brief --> agent
    agent --> doc
    doc --> reviewping
    reviewping --> log
    t1email --> log
    t2checklist --> log
    t3email --> log
    err --> alert
    model -.- agent
    tpl -.- agent
    lookup -.- agent
    parser -.- agent
    style sec_record fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_activate fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_deliver fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_review fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - ONE PARTNER RECORD** - A partner changes in any one system and the same record updates everywhere else. No more typing the same fields into four tools.
- **2 - ACTIVATION BY PARTNER TIER** - The tier decides what happens next, from a full joint campaign task set down to an automated check-in.
- **3 - AI DELIVERABLES FROM YOUR OWN TEMPLATES** - Client inputs go in, a draft built on your framework comes out. Claude writes into your structure, never its own.
- **4 - REVIEW AND MEASURE** - A person approves every draft before it leaves, and each run logs the hours it saved so the value is visible.
- **5 - WHEN SOMETHING BREAKS** - A failed run pings the partner owner with a link straight to it. Nothing fails quietly.
