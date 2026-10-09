# From Capturing a Lead to the Opportunity and the Follow-Up

```mermaid
flowchart LR
    subgraph sec_capture["1 - CAPTURING THE LEAD"]
        direction TB
        form(["1 - Lead Capture Form Submitted<br/><i>ghl</i>"])
        tag_src["2 - Tag the Contact lead-form<br/><i>ghl</i>"]
        field_src["3 - Save the Lead Source on the Contact<br/><i>ghl</i>"]
        notify_new["4 - Tell the Team a New Lead Came In<br/><i>ghl</i>"]
    end
    subgraph sec_opp["2 - MANAGING THE OPPORTUNITY"]
        direction TB
        create_opp["5 - Open the Opportunity at the New Lead Stage<br/><i>ghl</i>"]
    end
    subgraph sec_follow["3 - AUTOMATING THE FOLLOW-UP"]
        direction TB
        sms1["6 - Text Them Right Away<br/><i>ghl</i>"]
        email1["7 - Email Them the Booking Link<br/><i>ghl</i>"]
        w1["8 - Wait 1 Day"]
        sms2["9 - Text: Still Want to Chat<br/><i>ghl</i>"]
        w2["10 - Wait 2 Days"]
        email2["11 - Email: Two Quick Questions Before the Call<br/><i>ghl</i>"]
        w3["12 - Wait 3 Days"]
        sms3["13 - Text: Last Check In<br/><i>ghl</i>"]
        w4["14 - Wait 2 Days for a Reply to the Last Text"]
        no_resp["15 - Move the Opportunity to No Response<br/><i>ghl</i>"]
        task["16 - Give the Team a Task to Call Them Once<br/><i>ghl</i>"]
    end
    subgraph sec_reply["4 - STOP WHEN THEY REPLY"]
        direction TB
        goal["17 - Goal: They Replied or Booked<br/><i>ghl</i>"]
        replied(["1 - Lead Replied on Any Channel<br/><i>ghl</i>"])
        r_gate{"2 - Is This a Lead in the Follow-Up?"}
        r_tag["3 - Tag the Contact lead-engaged<br/><i>ghl</i>"]
        r_opp["4 - Move the Opportunity to Replied<br/><i>ghl</i>"]
        r_notify["5 - Text the Owner to Answer Now<br/><i>ghl</i>"]
    end
    subgraph sec_booked["5 - STOP WHEN THEY BOOK ON THE CALENDAR"]
        direction TB
        appt(["1 - Appointment Booked on the Calendar<br/><i>ghl</i>"])
        b_gate{"2 - Is This a Lead in the Follow-Up?"}
        b_tag["3 - Tag the Contact lead-engaged<br/><i>ghl</i>"]
        b_opp["4 - Move the Opportunity to Call Booked<br/><i>ghl</i>"]
        b_notify["5 - Email the Owner the Booking<br/><i>ghl</i>"]
    end
    form --> tag_src
    tag_src --> field_src
    field_src --> notify_new
    notify_new --> create_opp
    create_opp --> sms1
    sms1 --> email1
    email1 --> w1
    w1 --> sms2
    sms2 --> w2
    w2 --> email2
    email2 --> w3
    w3 --> sms3
    sms3 --> w4
    w4 --> no_resp
    no_resp --> task
    task --> goal
    replied --> r_gate
    r_gate -->|true| r_tag
    r_tag --> r_opp
    r_opp --> r_notify
    appt --> b_gate
    b_gate -->|true| b_tag
    b_tag --> b_opp
    b_opp --> b_notify
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_opp fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_follow fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_reply fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_booked fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - CAPTURING THE LEAD** - This covers your forms, surveys, calendars and lead capture, and your tags, custom fields, triggers and actions. A form or survey starts everything, the lead gets a source tag and field, and the team is told.
- **2 - MANAGING THE OPPORTUNITY** - This covers your pipelines and opportunity stages and connecting leads to the right pipeline. Every lead opens at New Lead so the stage always shows where it stands.
- **3 - AUTOMATING THE FOLLOW-UP** - This covers your workflows, automated follow-ups and email and SMS automation.
- **4 - STOP WHEN THEY REPLY** - A small second workflow catches any reply, moves the opportunity to Replied and tags the lead so the follow-up stops wherever it is.
- **5 - STOP WHEN THEY BOOK ON THE CALENDAR** - A third workflow fires on the calendar booking, moves the opportunity to Call Booked and stops the follow-up the same way.
