# Your Sales Rep Scorecard

```mermaid
flowchart LR
    subgraph sec_capture["1 - EVERY EVENT THAT COUNTS"]
        direction TB
        hook(["1 - GHL Event: New Lead, Appointment, Call, Contract, Payment"])
        norm["2 - Normalize the Event: Type, Contact, Rep, Amount, Time"]
    end
    subgraph sec_credit["2 - CREDIT THE RIGHT REP"]
        direction TB
        which{"3 - Which Event?"}
        own_lead["4a - Credit the Contact Owner"]
        appt_user["4b - GHL: Read the Appointment's Assigned User From the Calendar"]
        own_contract["4c - Credit the Opportunity Owner"]
        own_payment["4d - Credit the Opportunity Owner"]
        resolved{"5 - Rep Resolved?"}
        fix_queue[("5b - Unassigned Queue for a Human to Fix<br/><i>googleSheets</i>")]
    end
    subgraph sec_raw["3 - WRITE THE RAW ROW"]
        direction TB
        events[("6 - Append to the Events Tab<br/><i>googleSheets</i>")]
    end
    subgraph sec_score["4 - THE SCORECARD"]
        direction TB
        nightly(["7 - Every Night at 11pm"])
        read_today[("8 - Read Today's Events<br/><i>googleSheets</i>")]
        rollup["9 - Per Rep: Leads, Booked, Held, Contracts, Revenue"]
        ratios["10 - Ratios: Booked per Lead, Held per Booked, Cash per Lead"]
        scorecard[("11 - Update the Scorecard Tab, One Row per Rep per Day<br/><i>googleSheets</i>")]
        leaderboard["12 - Post the Leaderboard<br/><i>slack</i>"]
    end
    subgraph sec_safety["5 - NOTHING FAILS QUIETLY"]
        direction TB
        err(["13 - Any Step Fails<br/><i>n8n</i>"])
        alert["14 - Alert With the Failing Node<br/><i>slack</i>"]
    end
    hook --> norm
    norm --> which
    which -->|New Lead| own_lead
    which -->|Appointment| appt_user
    which -->|Contract Sent| own_contract
    which -->|Payment| own_payment
    own_lead --> resolved
    appt_user --> resolved
    own_contract --> resolved
    own_payment --> resolved
    resolved -->|false| fix_queue
    resolved -->|true| events
    nightly --> read_today
    read_today --> rollup
    rollup --> ratios
    ratios --> scorecard
    scorecard --> leaderboard
    err --> alert
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_credit fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_raw fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_score fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_safety fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - EVERY EVENT THAT COUNTS** - One webhook, fed by a GHL workflow per event type. New lead, appointment booked or updated, call outcome, contract sent, payment received. Every one arrives in the same shape.
- **2 - CREDIT THE RIGHT REP** - This is the part that gets scorecards wrong. A booked call is credited to the assigned user on the calendar event, not to whoever owns the contact. Nothing gets counted until a rep is resolved.
- **3 - WRITE THE RAW ROW** - Every event lands on an Events tab, one row, timestamped. The scorecard is always rebuildable from it, so a bad number can be traced to the event that caused it.
- **4 - THE SCORECARD** - Once a night the events roll up per rep into leads, booked, held, contracts, revenue, and the ratios that actually get coached on. One row per rep per day, plus a leaderboard in Slack.
- **5 - NOTHING FAILS QUIETLY** - If a step breaks, you hear about it the same day with the failing node named. A silent scorecard is worse than no scorecard.
