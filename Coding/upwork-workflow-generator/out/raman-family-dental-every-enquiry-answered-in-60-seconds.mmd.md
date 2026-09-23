# Raman Family Dental: Every Enquiry Answered in 60 Seconds

```mermaid
flowchart LR
    subgraph sec_intake["1 - CATCH EVERY WEBSITE ENQUIRY"]
        direction TB
        hook(["1 - New Enquiry From Your Website Form"])
        sort{{"2 - Sort It: New Patient, Emergency or Billing"}}
        urgent{"3 - Emergency?"}
        crm["4 - GoHighLevel: Save the Patient Enquiry"]
        model{{"Claude<br/><i>anthropic</i>"}}
    end
    hook --> sort
    sort --> urgent
    urgent -->|true| crm
    model -.- sort
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
```

- **1 - CATCH EVERY WEBSITE ENQUIRY** - Every enquiry is sorted.
