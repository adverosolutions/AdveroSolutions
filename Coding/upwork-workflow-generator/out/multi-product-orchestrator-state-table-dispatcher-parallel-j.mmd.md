# Multi-Product Orchestrator — State Table → Dispatcher → Parallel Jobs → Results, Retries, Manual Holds → Nightly Classification

```mermaid
flowchart LR
    subgraph sec_intake["1 · INTAKE & PRODUCT STATE"]
        direction TB
        link_trig(["AliExpress Link Submitted"])
        create_record["Create the Product Record: One Row, One State, One Source of Truth"]
        write_state[("Write the Product to the State Table as Queued<br/><i>airtable</i>")]
    end
    subgraph sec_dispatch["2 · DISPATCHER: NEXT ACTION PER PRODUCT"]
        direction TB
        dispatch_trig(["Dispatcher Runs Every Minute"])
        read_states[("Read Every Product and Its Current State<br/><i>airtable</i>")]
        next_switch{"What Does This Product Need Next?"}
        job_store["Kick Off the Store Build · Supplied Tool"]
        job_creative["Kick Off Creative and Video · Supplied Tool"]
        job_ads["Kick Off Ad Deployment as a Browser Job"]
        job_llm{{"Codex/Claude Job: Offer Copy, Policy Check, and Product Classification"}}
        job_llm_model{{"Claude<br/><i>anthropic</i>"}}
        mark_running[("Mark the Job Running With a Job Id and Started Time<br/><i>airtable</i>")]
    end
    subgraph sec_results["3 · JOBS REPORT BACK"]
        direction TB
        result_trig(["Any Job Reports Back: Done, Failed, or Needs a Human"])
        result_switch{"How Did It End?"}
        advance[("Advance the Product to Its Next State<br/><i>airtable</i>")]
        retry_branch{"Under the Retry Cap?"}
        requeue[("Requeue With Backoff, Attempt Count Plus One<br/><i>airtable</i>")]
        alert_stuck["Alert: Product Stuck After 3 Attempts, With the Last Error<br/><i>slack</i>"]
        hold_manual[("Park It as Waiting on Manual Check and Ping the Reviewer<br/><i>airtable</i>")]
    end
    subgraph sec_report["4 · TESTING, CLASSIFICATION & REPORTING"]
        direction TB
        nightly_trig(["Nightly Results Pull"])
        pull_results["Pull Ad Results, Spend, and COGS per Product"]
        classify{{"Classify Each Product: Scale, Iterate, or Kill, With the Reason"}}
        classify_model{{"Claude<br/><i>anthropic</i>"}}
        write_report[("Write the Daily Report per Product<br/><i>googleSheets</i>")]
        post_summary["Post Winners, Losers, and Anything Waiting on a Human<br/><i>slack</i>"]
    end
    link_trig --> create_record
    create_record --> write_state
    dispatch_trig --> read_states
    read_states --> next_switch
    next_switch -->|store setup| job_store
    next_switch -->|creative| job_creative
    next_switch -->|ad deployment| job_ads
    next_switch -->|codex/claude| job_llm
    job_store --> mark_running
    job_creative --> mark_running
    job_ads --> mark_running
    job_llm --> mark_running
    result_trig --> result_switch
    result_switch -->|done| advance
    result_switch -->|failed| retry_branch
    result_switch -->|needs a human| hold_manual
    retry_branch -->|true| requeue
    retry_branch -->|false| alert_stuck
    nightly_trig --> pull_results
    pull_results --> classify
    classify --> write_report
    write_report --> post_summary
    job_llm_model -.- job_llm
    classify_model -.- classify
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_dispatch fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_results fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_report fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · INTAKE & PRODUCT STATE** — Every product gets one row in a state table the moment its link comes in. That row is the only source of truth for where it is, so products can never interfere with each other.
- **2 · DISPATCHER: NEXT ACTION PER PRODUCT** — A dispatcher reads every product's state each minute and kicks off whatever that product needs next, store, creative, ads, or a Codex/Claude job, in parallel across products.
- **3 · JOBS REPORT BACK** — Every job, however long it runs, reports back through one door. Done advances the product, failed retries with backoff up to a cap, and needs-a-human parks it and pings the reviewer.
- **4 · TESTING, CLASSIFICATION & REPORTING** — Nightly, real ad results and COGS come in per product and get classified scale, iterate, or kill, so the next morning's dispatcher is already acting on it.
