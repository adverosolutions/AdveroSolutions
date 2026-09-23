# Form Webhook → Validate → Google Sheets → Confirmation Email

```mermaid
flowchart LR
    subgraph sec_intake["1 · CATCH THE FORM AND CHECK IT"]
        direction TB
        hook(["1 · Form Submitted"])
        validate["2 · Validate Required Fields + Email Format"]
        valid{"3 · Valid?"}
        reject["4 · Reject With Field Errors"]
    end
    subgraph sec_store["2 · WRITE IT TO GOOGLE SHEETS"]
        direction TB
        sheet[("5 · Add Row to Submissions Sheet<br/><i>googleSheets</i>")]
    end
    subgraph sec_confirm["3 · CONFIRM TO THE SUBMITTER AND THE FORM"]
        direction TB
        email["6 · Send Confirmation Email<br/><i>gmail</i>"]
        ok["7 · 200 OK to the Form"]
    end
    subgraph sec_alert["4 · FAIL LOUDLY"]
        direction TB
        err(["8 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["9 · Alert on Failure<br/><i>slack</i>"]
    end
    hook --> validate
    validate --> valid
    valid -->|false| reject
    valid -->|true| sheet
    sheet --> email
    email --> ok
    err --> alert
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_store fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_confirm fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_alert fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · CATCH THE FORM AND CHECK IT** — The form posts to one webhook URL. Missing fields or a bad email get rejected right away with a clear reason, so junk never reaches the sheet.
- **2 · WRITE IT TO GOOGLE SHEETS** — One clean row per submission, with a timestamp and a submission id. The same webhook can feed an AI agent later without touching this part.
- **3 · CONFIRM TO THE SUBMITTER AND THE FORM** — A personalized confirmation email goes out, then the form gets a 200 with the submission id.
- **4 · FAIL LOUDLY** — If Sheets or Gmail ever errors, a Slack alert with a link to the failed run. Nothing drops silently.
