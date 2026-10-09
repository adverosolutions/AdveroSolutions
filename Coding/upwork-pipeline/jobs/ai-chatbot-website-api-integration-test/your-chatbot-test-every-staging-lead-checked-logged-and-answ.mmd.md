# Your Chatbot Test: Every Staging Lead Checked, Logged and Answered

```mermaid
flowchart LR
    subgraph sec_site["1 - YOUR STAGING SITE AND CODE SNIPPET"]
        direction TB
        hook(["1 - Chatbot Snippet on Staging Posts the Lead Here"])
    end
    subgraph sec_collect["2 - TEST THE LEAD AND CONTACT COLLECTION"]
        direction TB
        check["2 - Check Name, Email, Phone and Message Arrived"]
    end
    subgraph sec_hook["3 - THE WEBHOOK: LOG EVERY CAPTURE"]
        direction TB
        log[("3 - Log Every Capture to the Test Sheet<br/><i>googleSheets</i>")]
    end
    subgraph sec_verify["4 - VERIFY IT PASSED CORRECTLY, FLAG WHAT DID NOT"]
        direction TB
        gate{"4 - All Four Fields There and Valid?"}
        ok["5 - Tell the Chatbot: Lead Received"]
        flag["5b - Flag the Missing Field to Your Test Inbox<br/><i>gmail</i>"]
        bad["5c - Tell the Chatbot Which Field Was Missing"]
    end
    subgraph sec_next["5 - NEXT PHASE: YOUR CRM (SHOWN IN HUBSPOT) AND GOOGLE CALENDAR"]
        direction TB
        crm["6 - Next Phase: HubSpot Creates the Contact From the Chat<br/><i>hubspot</i>"]
        cal["7 - Google Calendar: Book the Call Time They Asked For<br/><i>googleCalendar</i>"]
    end
    subgraph sec_errors["6 - IF A RUN BREAKS"]
        direction TB
        err(["8 - Any Step Fails<br/><i>n8n</i>"])
        alert["9 - Email You the Failed Step and a Link to the Run<br/><i>gmail</i>"]
    end
    hook --> check
    check --> log
    log --> gate
    gate -->|true| ok
    gate -->|false| flag
    flag --> bad
    ok --> crm
    crm --> cal
    err --> alert
    style sec_site fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_collect fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_hook fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_verify fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_next fill:#fef9c3,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#ffedd5,stroke:#94a3b8,color:#0f172a
```

- **1 - YOUR STAGING SITE AND CODE SNIPPET** - Your parts 1 and 2: the chatbot goes on staging, and its snippet posts every lead to this one webhook. If it posts through your own backend instead, that backend's webhook points here.
- **2 - TEST THE LEAD AND CONTACT COLLECTION** - Your part 3: each lead is checked for name, email, phone and message, whatever the snippet calls those fields.
- **3 - THE WEBHOOK: LOG EVERY CAPTURE** - Your part 4: every capture goes into the test sheet, good or bad, so you can see the test yourself.
- **4 - VERIFY IT PASSED CORRECTLY, FLAG WHAT DID NOT** - Your parts 5 and 6: a complete lead gets a received reply, a broken one gets flagged with the exact field so troubleshooting starts there.
- **5 - NEXT PHASE: YOUR CRM (SHOWN IN HUBSPOT) AND GOOGLE CALENDAR** - The onboarding work you named: a verified lead becomes a CRM contact and a booked call. HubSpot stands in for your CRM here. Switched on after the test passes.
- **6 - IF A RUN BREAKS** - Any failed step emails you the step, the error and a link to the run, so no test chat disappears without a trace.
