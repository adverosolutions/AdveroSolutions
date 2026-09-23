# GoHighLevel Form → Field Mapping → Monday.com Item

```mermaid
flowchart LR
    subgraph sec_receive["1 · RECEIVE & MAP"]
        direction TB
        trig(["GoHighLevel Form Submitted"])
        map_fields["Map Form Fields to Monday.com Board Columns"]
    end
    subgraph sec_sync["2 · SYNC & CONFIRM"]
        direction TB
        create_item["Create New Item on the Monday.com Board"]
        check_branch{"Item Created Successfully?"}
        confirm_ok["Return Success to GoHighLevel"]
        alert_fail["Alert: Submission Did Not Sync to Monday.com<br/><i>slack</i>"]
    end
    trig --> map_fields
    map_fields --> create_item
    create_item --> check_branch
    check_branch -->|true| confirm_ok
    check_branch -->|false| alert_fail
    style sec_receive fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_sync fill:#dcfce7,stroke:#94a3b8,color:#0f172a
```

- **1 · RECEIVE & MAP** — Catches the form submission the moment it happens and maps it to your board's actual columns.
- **2 · SYNC & CONFIRM** — Creates the item, then checks it actually landed instead of assuming it did.
