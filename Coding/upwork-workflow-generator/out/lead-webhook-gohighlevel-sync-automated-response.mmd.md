# Lead Webhook → GoHighLevel Sync → Automated Response

```mermaid
flowchart LR
    subgraph sec_intake["1 · LEAD INTAKE"]
        direction TB
        trig(["New Lead Submitted"])
        normalize["Normalize Name, Phone, Email, and Source"]
    end
    subgraph sec_sync["2 · SYNC TO GOHIGHLEVEL"]
        direction TB
        ghl_sync["Create or Update Contact in GoHighLevel<br/><i>gohighlevel</i>"]
        sync_branch{"Contact Synced Successfully?"}
    end
    subgraph sec_respond["3 · AUTOMATED LEAD RESPONSE"]
        direction TB
        ghl_reply["Send Automated Lead-Response Message<br/><i>gohighlevel</i>"]
        ghl_tag["Tag Contact as Auto-Responded<br/><i>gohighlevel</i>"]
    end
    subgraph sec_confirm["4 · CONFIRM & HANDLE ERRORS"]
        direction TB
        respond_ok["Return Success to Webhook Caller"]
        alert_fail["Alert: GoHighLevel Sync Failed<br/><i>slack</i>"]
    end
    trig --> normalize
    normalize --> ghl_sync
    ghl_sync --> sync_branch
    sync_branch -->|true| ghl_reply
    ghl_reply --> ghl_tag
    ghl_tag --> respond_ok
    sync_branch -->|false| alert_fail
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_sync fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_respond fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_confirm fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · LEAD INTAKE** — Catches the lead from its source and normalizes the fields before anything touches GoHighLevel.
- **2 · SYNC TO GOHIGHLEVEL** — Creates or updates the contact in GoHighLevel over its webhook API.
- **3 · AUTOMATED LEAD RESPONSE** — Fires the automated response and tags the contact once the sync succeeds.
- **4 · CONFIRM & HANDLE ERRORS** — Returns a success confirmation, or alerts if the GoHighLevel sync failed.
