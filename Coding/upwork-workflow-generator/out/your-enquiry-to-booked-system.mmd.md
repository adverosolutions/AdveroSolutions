# Your Enquiry to Booked System

```mermaid
flowchart LR
    subgraph sec_capture["1 - CAPTURE AND VALIDATE"]
        direction TB
        hook(["1 - Enquiry Arrives From the Website Form"])
        idem["15 - Idempotency Key: Hash of Email Phone and Timestamp, Skip if Seen"]
        normalize["2 - Standardize Name, Phone E.164, Email Lowercase"]
        required{"3 - Required Fields Present?"}
        incomplete["3b - GHL: Tag Incomplete and Ask for the Missing Field"]
        lookup["4 - GHL: Look Up Existing Contact by Email or Phone"]
        exists{"5 - Already Exists?"}
    end
    subgraph sec_qualify["2 - AI QUALIFICATION, NEVER INVENTED"]
        direction TB
        classify{{"6 - Extract Service, Summarize, Classify Hot Warm Cold Unclear"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        parser{{"Service, Summary, Class, Missing Fields"}}
        clear{"7 - Clear Enough to Qualify?"}
        review["7b - Manual Review Queue With the Summary<br/><i>slack</i>"]
    end
    subgraph sec_crm["3 - INTO GOHIGHLEVEL"]
        direction TB
        upsert["8 - GHL: Create or Update the Contact and Custom Fields"]
        tag["9 - GHL: Tag by Class"]
        opportunity["10 - GHL: Create or Move the Opportunity to the Stage"]
        note["11 - GHL: Write the Summary and Result to the Contact Notes"]
    end
    subgraph sec_followup["4 - FOLLOW UP UNTIL THEY REPLY, BOOK OR OPT OUT"]
        direction TB
        enroll["12 - GHL: Enroll in the Follow-Up Workflow With the Booking Link"]
        stophook(["13 - GHL: Replied, Booked, Opted Out or Paused"])
        unenroll["14 - GHL: Remove From the Follow-Up Workflow"]
    end
    subgraph sec_ops["5 - LOGS, RETRIES AND ALERTS"]
        direction TB
        log[("16 - Execution Log Row<br/><i>googleSheets</i>")]
        err(["17 - Any Step Fails<br/><i>n8n</i>"])
        wait["18 - Retry After 2 Minutes"]
        alert["19 - Alert After the Retry<br/><i>slack</i>"]
    end
    hook --> idem
    idem --> normalize
    normalize --> required
    required -->|false| incomplete
    required -->|true| lookup
    lookup --> exists
    exists -->|true| classify
    exists -->|false| classify
    classify --> clear
    clear -->|false| review
    clear -->|true| upsert
    upsert --> tag
    tag --> opportunity
    opportunity --> note
    note --> enroll
    enroll --> log
    stophook --> unenroll
    err --> wait
    wait --> alert
    model -.- classify
    parser -.- classify
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_qualify fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_crm fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_followup fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_ops fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - CAPTURE AND VALIDATE** - One form, one webhook. Every enquiry is de-duplicated, standardized and checked against GoHighLevel before anything is created.
- **2 - AI QUALIFICATION, NEVER INVENTED** - Claude extracts the service, summarizes the enquiry and classifies it. Anything it cannot read is flagged, not guessed.
- **3 - INTO GOHIGHLEVEL** - Contact, custom fields, tags, opportunity stage and notes. Sales opens one record and sees the whole enquiry.
- **4 - FOLLOW UP UNTIL THEY REPLY, BOOK OR OPT OUT** - Approved messaging and the booking link go out on a sequence that stops itself the moment the lead responds.
- **5 - LOGS, RETRIES AND ALERTS** - Every run writes a log row. A failed step retries once on a delay, then it tells you instead of failing quietly.
