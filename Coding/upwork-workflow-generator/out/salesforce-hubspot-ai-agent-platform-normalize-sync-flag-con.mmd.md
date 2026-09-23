# Salesforce ↔ HubSpot ↔ AI Agent Platform — Normalize, Sync, Flag Conflicts

```mermaid
flowchart LR
    subgraph sec_capture["1 · CAPTURE FROM BOTH CRMS"]
        direction TB
        sf_trig(["Salesforce Record Created or Updated"])
        hs_trig(["HubSpot Record Created or Updated"])
        loop_guard{"Was This Change Just Written by This Workflow?"}
        skip_loop["Skip: Prevent Sync Loop"]
    end
    subgraph sec_normalize["2 · NORMALIZE FOR THE AI AGENT"]
        direction TB
        normalize_agent{{"Normalize Fields Against One Common Schema"}}
        normalize_model{{"GPT-4.1<br/><i>openai</i>"}}
        conflict_branch{"Field Values Conflict Between Source and Target?"}
    end
    subgraph sec_sync["3 · SYNC ACROSS PLATFORMS"]
        direction TB
        sf_write["Write Normalized Record to Salesforce"]
        hs_write["Write Normalized Record to HubSpot<br/><i>hubspot</i>"]
        ai_platform_write["Push Normalized Record to the AI Agent Platform"]
    end
    subgraph sec_validate["4 · VALIDATE & LOG"]
        direction TB
        alert_conflict["Alert: Normalization Conflict Needs Review<br/><i>slack</i>"]
        log_result["Log Sync Result: Updated, Conflicts, Errors"]
    end
    sf_trig --> loop_guard
    hs_trig --> loop_guard
    loop_guard -->|true| skip_loop
    loop_guard -->|false| normalize_agent
    normalize_agent --> conflict_branch
    conflict_branch -->|true| alert_conflict
    conflict_branch -->|false| sf_write
    conflict_branch -->|false| hs_write
    conflict_branch -->|false| ai_platform_write
    sf_write --> log_result
    hs_write --> log_result
    ai_platform_write --> log_result
    alert_conflict --> log_result
    normalize_model -.- normalize_agent
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_normalize fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_sync fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_validate fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · CAPTURE FROM BOTH CRMS** — Either CRM can trigger the sync, and a loop guard drops anything this workflow just wrote itself.
- **2 · NORMALIZE FOR THE AI AGENT** — Fields get mapped to one common schema before anything moves, and a real conflict gets flagged instead of silently overwritten.
- **3 · SYNC ACROSS PLATFORMS** — Clean records write to Salesforce, HubSpot, and the AI agent platform together.
- **4 · VALIDATE & LOG** — Every run logs what updated, what conflicted, and what failed.
