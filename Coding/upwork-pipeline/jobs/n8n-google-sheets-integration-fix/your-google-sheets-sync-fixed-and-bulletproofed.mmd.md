# Your Google Sheets Sync, Fixed and Bulletproofed

```mermaid
flowchart LR
    subgraph sec_intake["1 - THE DATA COMES IN"]
        direction TB
        hook(["1 - Record Arrives"])
    end
    subgraph sec_causes["2 - THE FIVE THINGS THAT BREAK SHEETS SYNCS"]
        direction TB
        coerce["2 - Coerce Types and Dates"]
        drop["3 - Drop Empty Rows"]
        tabgate{"4 - Sheet and Tab Still Exist?"}
        renamed["4b - Alert: Sheet or Tab Renamed<br/><i>slack</i>"]
        lookup[("5 - Look Up the Row by Key<br/><i>googleSheets</i>")]
        exists{"6 - Row Already There?"}
    end
    subgraph sec_write["3 - WRITE IT THE RIGHT WAY"]
        direction TB
        update[("7 - Update the Existing Row<br/><i>googleSheets</i>")]
        append[("7b - Append a New Row<br/><i>googleSheets</i>")]
    end
    subgraph sec_guards["4 - QUOTA AND AUTH GUARDS"]
        direction TB
        wrote{"8 - Write Succeeded?"}
        backoff["9 - Back Off 30 Seconds"]
        refresh["10 - Refresh Google OAuth Token"]
    end
    subgraph sec_proof["5 - PROVE IT KEEPS WORKING"]
        direction TB
        heartbeat[("11 - Write a Heartbeat Row to the Log Tab<br/><i>googleSheets</i>")]
        respond["12 - Reply 200 Synced to the Sender"]
        err(["13 - Any Node Fails<br/><i>n8n</i>"])
        alert["14 - Alert With the Failing Node and Row<br/><i>slack</i>"]
    end
    hook --> coerce
    coerce --> drop
    drop --> tabgate
    tabgate -->|true| lookup
    tabgate -->|false| renamed
    lookup --> exists
    exists -->|true| update
    exists -->|false| append
    update --> wrote
    append --> wrote
    wrote -->|true| heartbeat
    wrote -->|false| backoff
    backoff --> refresh
    refresh -.-> lookup
    err --> alert
    heartbeat --> respond
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_causes fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_write fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_guards fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_proof fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - THE DATA COMES IN** - Whatever feeds the sheet lands here, one record at a time, so every run can be replayed against the exact payload that broke it.
- **2 - THE FIVE THINGS THAT BREAK SHEETS SYNCS** - Wrong types, empty rows, a renamed tab, a moved header, and appending when it should update. Each one gets its own guard before a single cell is written.
- **3 - WRITE IT THE RIGHT WAY** - Matched on a key column, so the same record updates its row instead of quietly stacking duplicates at the bottom of the sheet.
- **4 - QUOTA AND AUTH GUARDS** - Google throttles bursts and OAuth tokens expire. A failed write backs off, refreshes the credential, and retries instead of dying silently.
- **5 - PROVE IT KEEPS WORKING** - A heartbeat row on a log tab shows the sync is alive, and any node that fails names itself and the row it was on.
