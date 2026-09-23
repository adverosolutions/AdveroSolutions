# Invoice & Payment Tracking — Invoice In → Status Sync → Reminders → Overdue Alerts

```mermaid
flowchart LR
    subgraph sec_invoice["1 · INVOICE IN"]
        direction TB
        invoice_trig(["New Invoice Created in the Accounting Tool"])
        normalize["Normalize Invoice: Customer, Amount, Due Date, Status"]
        add_to_sheet[("Add the Invoice to the Tracking Sheet<br/><i>googleSheets</i>")]
    end
    subgraph sec_payment["2 · PAYMENT RECEIVED"]
        direction TB
        payment_trig(["Payment Received from the Payment Tool"])
        match_invoice["Match the Payment to Its Invoice"]
        mark_paid["Mark the Invoice Paid in the Accounting Tool"]
        sheet_paid[("Update the Sheet: Status Paid, Date Paid<br/><i>googleSheets</i>")]
        notify_paid["Notify the Team: Payment Received<br/><i>slack</i>"]
    end
    subgraph sec_reminders["3 · REMINDERS & OVERDUE"]
        direction TB
        daily_trig(["Daily Check, 8am"])
        find_unpaid["Find Unpaid Invoices Due in 3 Days, Due Today, or Past Due"]
        where_switch{"Where Is It: Upcoming, Due Today, or Overdue?"}
        remind_upcoming["Send a Friendly Heads-Up: Due in 3 Days<br/><i>gmail</i>"]
        remind_today["Send the Due-Today Reminder<br/><i>gmail</i>"]
        remind_overdue["Send the Overdue Notice<br/><i>gmail</i>"]
        sheet_overdue[("Update the Sheet: Status Overdue, Days Late<br/><i>googleSheets</i>")]
        notify_overdue["Notify the Team: Invoice Overdue<br/><i>slack</i>"]
    end
    invoice_trig --> normalize
    normalize --> add_to_sheet
    payment_trig --> match_invoice
    match_invoice --> mark_paid
    mark_paid --> sheet_paid
    sheet_paid --> notify_paid
    daily_trig --> find_unpaid
    find_unpaid --> where_switch
    where_switch -->|upcoming| remind_upcoming
    where_switch -->|due today| remind_today
    where_switch -->|overdue| remind_overdue
    remind_overdue --> sheet_overdue
    sheet_overdue --> notify_overdue
    style sec_invoice fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_payment fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_reminders fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 · INVOICE IN** — Every new invoice lands in the tracking sheet the moment it's created, so the sheet is the single source of truth, not a weekly export.
- **2 · PAYMENT RECEIVED** — A payment gets matched to its invoice and marked paid everywhere at once, accounting tool, sheet, and team, so no one chases an invoice that's already settled.
- **3 · REMINDERS & OVERDUE** — A daily check sends the right message for where each invoice actually is, upcoming, due today, or overdue, and the team only hears about the overdue ones.
