# Intake to First Draft, Follow-Ups and Email Your Paralegal Can Run

```mermaid
flowchart LR
    subgraph sec_intake["1 - NEW CLIENT INTAKE"]
        direction TB
        hook(["1 - Lawmatics: Website, Phone or Referral Lead You Mark Ready to Engage"])
        lm["2 - Lawmatics: Pull the Full Intake Questionnaire"]
        contact["3 - Clio: Create the Client Contact"]
        matter["4 - Clio: Open the Estate Planning Matter"]
        sheet[("5 - Google Sheet: Add the Client to Your Intake Sheet<br/><i>googleSheets</i>")]
        engage["6 - Google Docs: Fill In Their Engagement Letter"]
        welcome["7 - Gmail: Send the Welcome Email and Engagement Letter<br/><i>gmail</i>"]
    end
    subgraph sec_draft["2 - DOCUMENT DRAFTING"]
        direction TB
        drafter{{"8 - Claude Fills Your Will, Trust and POA Templates"}}
        dmodel{{"Claude - Reads the Questionnaire<br/><i>anthropic</i>"}}
        dparser{{"Returns Fill-Ins and Open Questions"}}
        fill["9 - Google Docs: Save the First Drafts in the Client Folder"]
        task["10 - Clio: Task Your Paralegal to Review the Drafts"]
    end
    subgraph sec_follow["3 - FOLLOW-UPS ON QUIET CLIENTS"]
        direction TB
        sched(["11 - Every Weekday Morning"])
        open["12 - Clio: Pull Every Open Matter and Its Stage"]
        quiet["13 - Pick Clients Quiet on Signing, Documents or Retainer"]
        remind["14 - Gmail: Remind the Client, Copy Your Paralegal<br/><i>gmail</i>"]
    end
    subgraph sec_email["4 - EMAIL ROUTED TO YOUR PARALEGAL"]
        direction TB
        mail(["15 - New Email in Your Gmail Inbox"])
        sort{{"16 - Claude Reads It and Writes a Short Summary"}}
        smodel{{"Claude - Sorts Your Mail<br/><i>anthropic</i>"}}
        sparser{{"Returns Route and Summary"}}
        gate{"17 - Can Your Paralegal Handle It?"}
        route["18 - Gmail: Route It to Your Paralegal With the Summary<br/><i>gmail</i>"]
    end
    subgraph sec_errors["5 - IF ANY STEP FAILS"]
        direction TB
        err(["19 - Any Step Fails<br/><i>n8n</i>"])
        alert["20 - Gmail: Alert Your Paralegal, Not You<br/><i>gmail</i>"]
    end
    hook --> lm
    lm --> contact
    contact --> matter
    matter --> sheet
    sheet --> engage
    engage --> welcome
    welcome --> drafter
    drafter --> fill
    fill --> task
    sched --> open
    open --> quiet
    quiet --> remind
    mail --> sort
    sort --> gate
    gate -->|true| route
    err --> alert
    dmodel -.- drafter
    dparser -.- drafter
    smodel -.- sort
    sparser -.- sort
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_draft fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_follow fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_email fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - NEW CLIENT INTAKE** - Website form, phone and referral leads all go into Lawmatics once. After the consult and conflict check, the attorney moves the prospect to the engage stage in Lawmatics, and then Clio, your Google Sheet, the welcome email and the engagement letter follow without anyone retyping or remembering.
- **2 - DOCUMENT DRAFTING** - Claude reads the intake questionnaire and fills the blanks in your own will, trust and POA templates. Your paralegal is editing, not typing, and anything unclear is flagged for her.
- **3 - FOLLOW-UPS ON QUIET CLIENTS** - Every weekday morning, clients quiet on signing appointments, missing documents or unpaid retainers get a reminder. Your paralegal is copied, so you hear before the client calls annoyed.
- **4 - EMAIL ROUTED TO YOUR PARALEGAL** - Claude reads new mail in your inbox and writes a short summary. What your paralegal can handle goes to her; legal advice and anything sensitive stays with you.
- **5 - IF ANY STEP FAILS** - Your paralegal gets the failed step and a link to fix it, never client details in the alert.
