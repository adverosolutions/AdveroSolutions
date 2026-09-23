# n8n Hardening: Validate, Retry, Fallback, Log, Alert

```mermaid
flowchart LR
    subgraph sec_validate["1 - VALIDATE BEFORE ANYTHING ELSE RUNS"]
        direction TB
        hook(["1 - Incoming Record"])
        check["2 - Validate Schema and Required Fields"]
        valid{"3 - Is the Record Valid?"}
        reject["4 - Reject With Field Errors"]
    end
    subgraph sec_call["2 - CALL SYSTEM A, RETRY ON FAILURE"]
        direction TB
        fetch["5 - System A: Fetch Related Record"]
        ok{"6 - Did the Call Succeed?"}
        exhausted{"7 - Are the Retries Used Up?"}
        wait["8 - Back Off 30 Seconds"]
    end
    subgraph sec_fallback["3 - FALLBACK WHEN IT KEEPS FAILING"]
        direction TB
        queue["9 - Fallback: Queue for Manual Retry"]
    end
    subgraph sec_write["4 - MAP THE FIELDS AND WRITE TO SYSTEM B"]
        direction TB
        map["10 - Map Fields Between Systems"]
        write["11 - System B: Create or Update Record"]
    end
    subgraph sec_alert["5 - LOG EVERY RUN, ALERT ON ANY FAILURE"]
        direction TB
        log[("12 - Run Log: Status, Latency, Retries<br/><i>googleSheets</i>")]
        respond["13 - Return 200 OK"]
        err(["14 - Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["15 - Alert With Link to Failed Execution<br/><i>slack</i>"]
    end
    hook --> check
    check --> valid
    valid -->|false| reject
    valid -->|true| fetch
    fetch --> ok
    ok -->|true| map
    ok -->|false| exhausted
    exhausted -->|true| queue
    exhausted -->|false| wait
    wait -.-> fetch
    queue --> log
    map --> write
    write --> log
    log --> respond
    err --> alert
    style sec_validate fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_call fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_fallback fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_write fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_alert fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - VALIDATE BEFORE ANYTHING ELSE RUNS** - A bad record is rejected here with the exact field that is wrong, instead of blowing up three API calls later.
- **2 - CALL SYSTEM A, RETRY ON FAILURE** - A failed call waits and tries again rather than killing the run. The retry count is a setting, not a guess.
- **3 - FALLBACK WHEN IT KEEPS FAILING** - Once retries are used up the record is queued for manual retry. Nothing is ever dropped on the floor.
- **4 - MAP THE FIELDS AND WRITE TO SYSTEM B** - One place where field names are translated between the two systems, so a change is a one line edit.
- **5 - LOG EVERY RUN, ALERT ON ANY FAILURE** - Every run leaves a row you can read. Anything that still breaks pings you with a link to the run.
