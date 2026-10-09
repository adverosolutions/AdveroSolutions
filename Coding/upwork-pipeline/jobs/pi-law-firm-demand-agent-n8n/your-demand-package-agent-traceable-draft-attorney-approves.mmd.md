# Your Demand Package Agent: Traceable Draft, Attorney Approves

```mermaid
flowchart LR
    subgraph sec_ready["1 - CASE READY FOR DEMAND: PULL THE RECORDS"]
        direction TB
        hook(["1 - Case Marked Ready for Demand in Your Case System"])
        pull["2 - Google Drive: Pull Every Record and Bill, Page by Page"]
    end
    subgraph sec_extract["2 - YOUR PART 3: EXTRACT, TOTAL AND FLAG GAPS"]
        direction TB
        extract{{"3 - Claude Extracts Every Visit, Charge and Its Source Page"}}
        extract_model{{"Claude - Reads the Records and Bills<br/><i>anthropic</i>"}}
        extract_result{{"Extraction Result: Each Fact With Its File and Page"}}
        totals["4 - Total Medical Expenses by Provider, Flag Gaps and Missing Records"]
    end
    subgraph sec_draft["3 - YOUR PART 4: DRAFT FROM YOUR TEMPLATE"]
        direction TB
        draft{{"5 - Claude Drafts the Demand Letter From Extracted Facts Only"}}
        draft_model{{"Claude - Writes the Demand Draft<br/><i>anthropic</i>"}}
        doc["6 - Google Docs: Save the Draft With the Exhibit Index"]
    end
    subgraph sec_approve["4 - ATTORNEY REVIEWS, EDITS AND APPROVES"]
        direction TB
        gate["7 - Gmail: Attorney Approves or Sends Edits Back<br/><i>gmail</i>"]
        approved{"8 - Approved by the Attorney?"}
        export["9 - Export the Demand Package as Word and PDF"]
    end
    subgraph sec_errors["5 - IF ANY STEP FAILS"]
        direction TB
        err(["10 - Any Step Fails<br/><i>n8n</i>"])
        alert["11 - Gmail: Alert the Case Manager, No Medical Details<br/><i>gmail</i>"]
    end
    hook --> pull
    pull --> extract
    extract --> totals
    totals --> draft
    draft --> doc
    doc --> gate
    gate --> approved
    approved -->|true| export
    approved -.->|false| draft
    err --> alert
    extract_model -.- extract
    extract_result -.- extract
    draft_model -.- draft
    style sec_ready fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_extract fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_draft fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_approve fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - CASE READY FOR DEMAND: PULL THE RECORDS** - Your part 4 starts here: collect the case information automatically. The case's medical records and bills come from its Google Drive folder.
- **2 - YOUR PART 3: EXTRACT, TOTAL AND FLAG GAPS** - Every visit, diagnosis, procedure, provider and charge, each traceable to its document and page. Expenses by provider, and missing records or gaps flagged before a draft exists.
- **3 - YOUR PART 4: DRAFT FROM YOUR TEMPLATE** - The demand letter is drafted from your firm-approved template using only extracted facts, with an organized exhibit index. Nothing is invented.
- **4 - ATTORNEY REVIEWS, EDITS AND APPROVES** - Nothing leaves without attorney approval. Edits go back into the draft; approved packages export to Word and PDF.
- **5 - IF ANY STEP FAILS** - The case manager gets the case number and the failed step, never medical details in the email.
