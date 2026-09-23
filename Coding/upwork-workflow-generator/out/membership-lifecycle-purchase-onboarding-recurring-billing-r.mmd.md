# Membership Lifecycle — Purchase → Onboarding → Recurring Billing → Retention → Cancellation, Fully Logged

```mermaid
flowchart LR
    subgraph sec_purchase["1 · PURCHASE & ONBOARDING"]
        direction TB
        purchase_trig(["New Purchase or Subscription Started"])
        normalize["Normalize Customer, Plan, Tier, and Payment Terms"]
        grant_access["Grant Membership Access and Tag the Tier"]
        start_onboard["Add to the Onboarding Email and SMS Flow"]
    end
    subgraph sec_billing["2 · RECURRING BILLING & RETENTION"]
        direction TB
        renewal_trig(["Recurring Payment Succeeded or Failed"])
        paid_branch{"Did the Payment Fail?"}
        extend_access["Extend Access and Update the Renewal Date"]
        start_dunning["Start Dunning: Retry Notice by Email and SMS"]
        wait_3d["Wait 3 Days for a Payment Update"]
        unpaid_branch{"Still Unpaid After 3 Days?"}
        pause_access["Pause Access and Tag At-Risk"]
        mark_recovered["Mark Recovered and Clear the At-Risk Tag"]
    end
    subgraph sec_cancel["3 · CANCELLATION"]
        direction TB
        cancel_trig(["Cancellation Requested"])
        revoke_access["Revoke Access at Period End and Tag Churned"]
        winback["Start the Win-Back Sequence"]
    end
    subgraph sec_qa["4 · QA & LOGGING"]
        direction TB
        event_log[("Log Every Event: What Fired, What Tagged, What Charged<br/><i>googleSheets</i>")]
        fail_branch{"Did Anything Fail to Fire, Tag, or Charge?"}
        alert_fail["Alert With the Customer, the Step, and Why<br/><i>slack</i>"]
        all_clean["All Clean"]
    end
    purchase_trig --> normalize
    normalize --> grant_access
    grant_access --> start_onboard
    start_onboard --> event_log
    renewal_trig --> paid_branch
    paid_branch -->|false| extend_access
    paid_branch -->|true| start_dunning
    start_dunning --> wait_3d
    wait_3d --> unpaid_branch
    unpaid_branch -->|true| pause_access
    unpaid_branch -->|false| mark_recovered
    extend_access --> event_log
    pause_access --> event_log
    mark_recovered --> event_log
    cancel_trig --> revoke_access
    revoke_access --> winback
    winback --> event_log
    event_log --> fail_branch
    fail_branch -->|true| alert_fail
    fail_branch -->|false| all_clean
    style sec_purchase fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_billing fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_cancel fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_qa fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · PURCHASE & ONBOARDING** — A new purchase grants access, tags the tier, and starts onboarding in one pass, so no one is paying without access or getting access without paying.
- **2 · RECURRING BILLING & RETENTION** — Every renewal either extends access or starts dunning, with a real wait before access is paused, that's the retention step most setups skip.
- **3 · CANCELLATION** — Access ends at period end, not the moment they click, and the win-back sequence starts automatically.
- **4 · QA & LOGGING** — Every event logs what fired, what tagged, and what charged, and anything that didn't gets flagged immediately, that's how you find out before the customer does.
