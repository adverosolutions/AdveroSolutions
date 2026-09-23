# Your Virtual Receptionist: Every Call, Demo, Invoice and CRM Update

```mermaid
flowchart LR
    subgraph sec_calls["1 - ANSWER EVERY CALL ABOUT YOUR MACHINES"]
        direction TB
        ring(["1 - Retell Answers Your Line and Sends the Caller's Number"])
        lookup["2 - HubSpot: Look Up the Caller by Phone Number"]
        greet["3 - Greet Them by Name in English or Spanish"]
    end
    subgraph sec_questions["2 - ANSWER THEIR QUESTIONS FROM YOUR INVENTORY"]
        direction TB
        ask(["4 - Caller Asks About a Machine"])
        stock[("5 - Read Your Inventory List, Live<br/><i>googleSheets</i>")]
        answer{{"6 - Answer From Your Inventory Only, in Their Language"}}
        answer_model{{"Claude - Answers From Your Inventory<br/><i>anthropic</i>"}}
    end
    subgraph sec_demo["3 - SCHEDULE THE LOOK OR DEMO AT YOUR FACILITY"]
        direction TB
        visit(["7 - Caller Wants to See It in Person"])
        book["8 - Book the Look or Demo on Your Facility Calendar<br/><i>googleCalendar</i>"]
        text["9 - Text Them the Time, the Machine and Your Address<br/><i>twilio</i>"]
    end
    subgraph sec_invoices["4 - SEND THE INVOICE"]
        direction TB
        sold(["10 - Tell It Who Bought Which Machine"])
        invoice["11 - QuickBooks: Create the Invoice for the Machine<br/><i>quickbooks</i>"]
        send["12 - QuickBooks: Email the Invoice to the Buyer"]
    end
    subgraph sec_crm["5 - UPDATE THE CRM"]
        direction TB
        ended(["13 - Call Ends: Retell Sends the Transcript"])
        analyzed["14 - Keep Only Finished Calls With a Transcript"]
        extract{{"15 - Write the CRM Note in English, Even From a Spanish Call"}}
        extract_model{{"Claude - Writes the English CRM Note<br/><i>anthropic</i>"}}
        crm_fields{{"CRM Fields: Caller, Machine, Next Step, Note"}}
        save["16 - HubSpot: Save the Caller, the Machine and the Next Step"]
    end
    subgraph sec_errors["6 - IF A STEP FAILS, YOU HEAR ABOUT IT"]
        direction TB
        err(["17 - Any Step Fails<br/><i>n8n</i>"])
        alert["18 - Email You the Step That Broke<br/><i>gmail</i>"]
    end
    ring --> lookup
    lookup --> greet
    ask --> stock
    stock --> answer
    visit --> book
    book --> text
    sold --> invoice
    invoice --> send
    ended --> analyzed
    analyzed --> extract
    extract --> save
    err --> alert
    answer_model -.- answer
    extract_model -.- extract
    crm_fields -.- extract
    style sec_calls fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_questions fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_demo fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_invoices fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_crm fill:#fef9c3,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#ffedd5,stroke:#94a3b8,color:#0f172a
```

- **1 - ANSWER EVERY CALL ABOUT YOUR MACHINES** - Usually 2-7 calls a day means one every 1 to 4 hours, so a full-time seat mostly waits by the phone. Retell answers every call on the first ring, after hours too, and greets returning callers by name in English or Spanish.
- **2 - ANSWER THEIR QUESTIONS FROM YOUR INVENTORY** - Every answer about your excavators, skid steers and forklifts comes from your inventory list, read live on each question. A machine or a detail that is not on the list gets a callback from you, never a guess.
- **3 - SCHEDULE THE LOOK OR DEMO AT YOUR FACILITY** - The point of every call: get them to your facility to take a look or see a demo in person. It books the time on your calendar and texts them the machine, the time and your address in their language.
- **4 - SEND THE INVOICE** - After a sale you fill a short form from your phone and QuickBooks emails the invoice from your company. Nothing is invoiced until you say who bought which machine and for how much.
- **5 - UPDATE THE CRM** - After every call your CRM gets the caller, the machine they asked about and the next step, written in English even when the call was in Spanish. It is keyed on the caller's phone, so a repeat caller never becomes a duplicate.
- **6 - IF A STEP FAILS, YOU HEAR ABOUT IT** - One alert covers every step: you get the step that broke and a link to the run, so no caller falls through.
