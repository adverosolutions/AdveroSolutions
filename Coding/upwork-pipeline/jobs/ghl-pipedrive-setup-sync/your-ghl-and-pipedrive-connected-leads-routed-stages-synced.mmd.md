# Your GHL and Pipedrive, Connected: Leads Routed, Stages Synced

```mermaid
flowchart LR
    subgraph sec_fields["1 - CUSTOM FIELDS, TAGS AND LEAD SOURCES"]
        direction TB
        hook(["1 - GoHighLevel: New Lead or Stage Change Sends a Webhook"])
        __config["0 - Config: Your Settings"]
        clean["2 - Clean the Record: Names, Phone Format, Email and Lead Source"]
        search["3 - Pipedrive: Search for This Person by Email Before Creating Anyone"]
    end
    subgraph sec_route["2 - LEAD ASSIGNMENT AND ROUTING"]
        direction TB
        route["4 - Route by Lead Source: Pick the Owner, Pipeline and Stage"]
    end
    subgraph sec_connect["3 - CONNECT GHL AND PIPEDRIVE"]
        direction TB
        exists{"5 - Already a Person in Pipedrive?"}
        newperson["5b - Pipedrive: Create the Person With a Clean Name and Phone<br/><i>pipedrive</i>"]
        linked{"6 - Deal Already Linked to This GHL Opportunity?"}
        movedeal["7 - Pipedrive: Move the Linked Deal to the Same Stage"]
        newdeal["7b - Pipedrive: Create the Deal in the Right Pipeline, Stage and Owner"]
        writeback["8 - GoHighLevel: Write the Clean Record and Deal ID Back to the Contact"]
    end
    subgraph sec_migrate["4 - MIGRATE EXISTING CONTACTS AND OPPORTUNITIES"]
        direction TB
        mrun(["9 - Run Once: Migrate Your Existing GHL Opportunities"])
        mpull["10 - GoHighLevel: Pull Existing Opportunities and Their Contacts"]
        mshape["11 - Reshape Each Into the Same Lead Record"]
    end
    subgraph sec_move["5 - PIPELINE MOVEMENT AND ACTIVITY AUTOMATION"]
        direction TB
        pdhook(["12 - Pipedrive: A Rep Moves a Deal to a New Stage"])
        map["13 - Match the Pipedrive Stage to Your GHL Stage, Skip Our Own Echo"]
        ghlopp["14 - GoHighLevel: Move the Opportunity So Your Follow-Up Workflows Fire"]
        activity["15 - Pipedrive: Log the Move and Book the Owner's Next Call"]
    end
    subgraph sec_errors["6 - IF A STEP FAILS"]
        direction TB
        err(["16 - Any Step Fails<br/><i>n8n</i>"])
        alert["17 - Email You the Failed Step and a Link to the Run<br/><i>gmail</i>"]
    end
    hook --> __config
    __config --> clean
    mrun --> mpull
    mpull --> mshape
    mshape --> __config
    clean --> search
    search --> route
    route --> exists
    exists -->|true| linked
    exists -->|false| newperson
    newperson --> linked
    linked -->|true| movedeal
    linked -->|false| newdeal
    newdeal --> writeback
    pdhook --> map
    map --> ghlopp
    ghlopp --> activity
    err --> alert
    style sec_fields fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_connect fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_migrate fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_move fill:#fef9c3,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#ffedd5,stroke:#94a3b8,color:#0f172a
```

- **1 - CUSTOM FIELDS, TAGS AND LEAD SOURCES** - Your part on custom fields, tags and lead sources, with the CRM data quality you asked for. Names, phone format and lead source are cleaned, and Pipedrive is searched by email before anyone is created.
- **2 - LEAD ASSIGNMENT AND ROUTING** - Lead source decides which rep owns the lead and which stage the deal opens in. A person already in Pipedrive stays with their rep.
- **3 - CONNECT GHL AND PIPEDRIVE** - One person and one deal per lead in Pipedrive, linked both ways. The Pipedrive deal id goes back onto the GHL contact, and the clean record replaces the messy one.
- **4 - MIGRATE EXISTING CONTACTS AND OPPORTUNITIES** - Run once before launch. Your existing GHL opportunities and their contacts go through the same cleaner, dedupe and routing as a new lead.
- **5 - PIPELINE MOVEMENT AND ACTIVITY AUTOMATION** - When a rep moves a deal in Pipedrive, the GHL opportunity moves to the same stage and your GHL follow-up workflows fire. The rep's next call is booked on the deal.
- **6 - IF A STEP FAILS** - Any failure emails you the step that stopped and a link to the run, so you can fix it and retry.
