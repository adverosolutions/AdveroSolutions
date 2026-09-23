# Property Preservation Pilot: Photo Review, Bid Build, QA, Submit

```mermaid
flowchart LR
    subgraph sec_intake["1 · WORK ORDER INTAKE"]
        direction TB
        hook(["1 · New Work Order From PPW · API, Export, or RPA Feed"])
        pull["2 · PPW: Pull Work Order Notes and Photos<br/><i>ppw</i>"]
    end
    subgraph sec_photos["2 · BEFORE-PHOTO REVIEW AND SCOPE CHECK"]
        direction TB
        split["3 · One Photo at a Time"]
        vision{{"4 · Claude Vision: Describe Condition and Check Scope vs Instructions"}}
        visionmodel{{"Claude<br/><i>anthropic</i>"}}
        combine["5 · Combine Photo Findings"]
        photocheck{"6 · Photos Complete and In Scope?"}
        reupload["6a · Flag: Missing or Off-Scope Photos, Request Re-Upload<br/><i>slack</i>"]
    end
    subgraph sec_bid["3 · BID SHEET GENERATION"]
        direction TB
        pricing["7 · Pricing DB: Historical Bids by Geography and Work Order Type<br/><i>pricingdb</i>"]
        bidagent{{"8 · Claude: Build Bid Sheet Line Items"}}
        bidmodel{{"Claude<br/><i>anthropic</i>"}}
        toolhist{{"Historical Pricing Lookup"}}
        toolrules{{"Client Pricing Rules"}}
        bidparser{{"Force Line Items, Quantities, Unit Prices, and Margin"}}
    end
    subgraph sec_qa["4 · QA PASS AND HUMAN CHECKPOINT"]
        direction TB
        qapass{{"9 · QA Pass: Flag Underpriced, Overpriced, Incomplete"}}
        qamodel{{"Claude<br/><i>anthropic</i>"}}
        qacheck{"10 · QA Clean?"}
        needsreview["10a · Bid Needs Human Review, With the Reasons Attached<br/><i>slack</i>"]
        approve["11 · Human Approval: One-Tap Submit<br/><i>slack</i>"]
    end
    subgraph sec_submit["5 · SUBMIT, LOG, AND CATCH FAILURES"]
        direction TB
        submitbid["12 · PPW: Submit Bid<br/><i>ppw</i>"]
        log[("13 · Log the Bid, the Pricing Basis, and the QA Result<br/><i>googleSheets</i>")]
        err(["14 · Any Step Fails, Anywhere<br/><i>n8n</i>"])
        alert["15 · Alert Ops With the Work Order Number and a Link to the Run<br/><i>slack</i>"]
    end
    hook --> pull
    pull --> split
    split -->|loop| vision
    vision -.-> split
    split -->|done| combine
    combine --> photocheck
    photocheck -->|false| reupload
    photocheck -->|true| pricing
    pricing --> bidagent
    bidagent --> qapass
    qapass --> qacheck
    qacheck -->|false| needsreview
    qacheck -->|true| approve
    approve --> submitbid
    submitbid --> log
    err --> alert
    visionmodel -.- vision
    bidmodel -.- bidagent
    toolhist -.- bidagent
    toolrules -.- bidagent
    bidparser -.- bidagent
    qamodel -.- qapass
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_photos fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_bid fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_qa fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_submit fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · WORK ORDER INTAKE** — One work order type to start. The feed from PPW is a swappable first step: API if they expose one, scheduled export if not, browser automation as the fallback. Discovery decides which.
- **2 · BEFORE-PHOTO REVIEW AND SCOPE CHECK** — Every before-photo is described and checked against the work order instructions. Missing or off-scope photos go back to the contractor before anyone builds a bid. Phase 2 runs the same pattern on after-photos once work is approved and completed.
- **3 · BID SHEET GENERATION** — The bid is built from the photo findings, the measurements, and historical bids for that geography and work order type. Client pricing rules and target margin are tools the model has to call, not text in a prompt.
- **4 · QA PASS AND HUMAN CHECKPOINT** — A second model reviews the bid for underpriced, overpriced, or incomplete lines. Nothing reaches a client until a person taps approve. The checkpoint stays even after the QA pass earns trust.
- **5 · SUBMIT, LOG, AND CATCH FAILURES** — The approved bid goes back into PPW and every line is logged with the pricing it was based on, so the pricing model gets better with each order. "Ready for office" routing after verification is Phase 2 on this same pattern.
