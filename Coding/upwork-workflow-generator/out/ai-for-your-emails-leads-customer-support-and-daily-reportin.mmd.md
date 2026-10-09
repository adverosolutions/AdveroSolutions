# AI for Your Emails, Leads, Customer Support and Daily Reporting

```mermaid
flowchart LR
    subgraph sec_emails["1 - EMAILS"]
        direction TB
        inbox(["1 - New Email Lands in Your Inbox"])
        sort{{"2 - Claude Sorts It: New Lead, Customer Support or Other"}}
        model{{"Claude - Reads the Email and Writes the Reply<br/><i>anthropic</i>"}}
        parser{{"Parser - Returns Category, Contact, Summary and Reply"}}
        log[("3 - Google Sheets: Log Every Email With Its Category<br/><i>googleSheets</i>")]
        route{"4 - New Lead or Support Question?"}
    end
    subgraph sec_leads["2 - LEAD MANAGEMENT"]
        direction TB
        followup["5 - Gmail: Follow Up With the New Lead Right Away<br/><i>gmail</i>"]
    end
    subgraph sec_support["3 - CUSTOMER SUPPORT"]
        direction TB
        draft["6 - Gmail: Draft the Answer for Your Team to Check<br/><i>gmail</i>"]
    end
    subgraph sec_report["4 - REPORTING"]
        direction TB
        daily(["7 - Every Morning Before You Start"])
        read[("8 - Google Sheets: Read the Inbox Log<br/><i>googleSheets</i>")]
        count["9 - Count Yesterday's Leads, Support Questions and Open Drafts"]
        send_report["10 - Gmail: Send You the Daily Report<br/><i>gmail</i>"]
    end
    subgraph sec_errors["5 - ERROR HANDLING"]
        direction TB
        failed(["11 - If Any Step Fails<br/><i>n8n</i>"])
        alert["12 - Gmail: Alert You With the Step and the Error<br/><i>gmail</i>"]
    end
    inbox --> sort
    sort --> log
    log --> route
    route -->|lead| followup
    route -->|support| draft
    daily --> read
    read --> count
    count --> send_report
    failed --> alert
    model -.- sort
    parser -.- sort
    style sec_emails fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_leads fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_support fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_report fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - EMAILS** - Every email that lands in your inbox is read by AI and sorted into new lead, customer support or other. Each one is logged in your Google Sheet.
- **2 - LEAD MANAGEMENT** - A new lead gets a follow-up right away, written from what they asked, with your booking link.
- **3 - CUSTOMER SUPPORT** - A support question gets a drafted answer in Gmail, and your team checks it and presses send.
- **4 - REPORTING** - Every morning you get one email with yesterday's leads, support questions and anything still waiting.
- **5 - ERROR HANDLING** - If any step fails, you get an email naming the step and the error.
