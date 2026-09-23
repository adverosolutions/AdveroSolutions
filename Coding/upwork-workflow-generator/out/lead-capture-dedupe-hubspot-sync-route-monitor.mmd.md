# Lead Capture → Dedupe → HubSpot Sync → Route → Monitor

```mermaid
flowchart LR
    subgraph sec_capture["1 · CAPTURE FROM ANY SOURCE"]
        direction TB
        trig(["Lead Submitted — Form, Landing Page, Ad, or API"])
        normalize["Normalize Fields and Tag Lead Source and Campaign"]
        validate_branch{"Required Fields Present: Email or Phone?"}
        log_invalid["Alert: Incomplete Lead Received<br/><i>slack</i>"]
    end
    subgraph sec_dedupe["2 · DEDUPE & MATCH"]
        direction TB
        check_dup["Search HubSpot for an Existing Contact by Email or Phone"]
    end
    subgraph sec_sync["3 · CREATE/UPDATE & ROUTE"]
        direction TB
        map_fields["Map Lead Fields to HubSpot Properties"]
        upsert_contact["Create or Update the Contact in HubSpot<br/><i>hubspot</i>"]
        route_rules["Apply Routing Rules: Assign Lead by Source, Territory, or Product"]
        notify_owner["Notify the Assigned Rep of the New Lead<br/><i>slack</i>"]
    end
    subgraph sec_monitor["4 · NOTIFY & MONITOR"]
        direction TB
        run_branch{"Sync Completed Without Errors?"}
        log_success[("Log Lead and Routing Result to the Tracking Sheet<br/><i>googleSheets</i>")]
        alert_error["Alert: Sync Error, Needs Manual Review<br/><i>slack</i>"]
    end
    trig --> normalize
    normalize --> validate_branch
    validate_branch -->|true| check_dup
    validate_branch -->|false| log_invalid
    check_dup --> map_fields
    map_fields --> upsert_contact
    upsert_contact --> route_rules
    route_rules --> notify_owner
    notify_owner --> run_branch
    run_branch -->|true| log_success
    run_branch -->|false| alert_error
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_dedupe fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_sync fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_monitor fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · CAPTURE FROM ANY SOURCE** — One webhook accepts leads from forms, landing pages, ads, or a direct API call, and bad submissions get caught before they touch the CRM.
- **2 · DEDUPE & MATCH** — Every lead gets checked against HubSpot by email or phone before anything is written, so the next step knows whether to create or update.
- **3 · CREATE/UPDATE & ROUTE** — Fields map to the right HubSpot properties, source and campaign get tagged, and the lead is routed by the rules you set.
- **4 · NOTIFY & MONITOR** — The assigned rep gets notified, every run gets logged, and a failed sync alerts instead of silently disappearing.
