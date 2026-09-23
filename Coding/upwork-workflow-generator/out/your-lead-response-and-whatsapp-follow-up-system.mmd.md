# Your Lead Response and WhatsApp Follow-Up System

```mermaid
flowchart LR
    subgraph sec_lead["1 - A LEAD WRITES IN"]
        direction TB
        hook(["1 - New Lead Writes In From Web Form, IG or FB DM"])
        norm["2 - Normalize the Lead"]
        save[("3 - Save the Lead in Supabase<br/><i>supabase</i>")]
    end
    subgraph sec_first["2 - INSTANT ALERT AND FIRST REPLY"]
        direction TB
        alert["4 - Instant Alert to the Team<br/><i>slack</i>"]
        wa1["5 - WhatsApp via Twilio: Instant Reply With Booking Link<br/><i>twilio</i>"]
    end
    subgraph sec_chase["3 - FOLLOW UP UNTIL BOOKED"]
        direction TB
        wait1["6 - Wait 1 Day"]
        gate{"7 - Booked or Replied?"}
        wa2["8 - WhatsApp: Confirm the Appointment<br/><i>twilio</i>"]
        cal["9 - Put It on the Calendar<br/><i>googleCalendar</i>"]
        wa3["8b - WhatsApp: Gentle Follow-Up<br/><i>twilio</i>"]
        again["9b - Wait 2 Days"]
    end
    subgraph sec_reply["4 - WHEN THEY REPLY ON WHATSAPP"]
        direction TB
        hook2(["1b - WhatsApp Reply Comes In From Twilio"])
        classify{{"10 - Classify the Reply"}}
        model{{"GPT-4o<br/><i>openai</i>"}}
        route{"11 - Route: Book, Question, Stop"}
        cal2["12 - Book the Appointment on the Calendar<br/><i>googleCalendar</i>"]
        human["13 - Hand to a Human<br/><i>slack</i>"]
        optout[("14 - Mark Opted Out<br/><i>supabase</i>")]
    end
    subgraph sec_safety["5 - NOTHING FAILS QUIETLY"]
        direction TB
        err(["15 - Any Step Fails, Anywhere<br/><i>n8n</i>"])
        errslack["16 - Alert: Flow Failed<br/><i>slack</i>"]
    end
    hook --> norm
    norm --> save
    save --> alert
    alert --> wa1
    wa1 --> wait1
    wait1 --> gate
    gate -->|true| wa2
    wa2 --> cal
    gate -->|false| wa3
    wa3 --> again
    again -.-> gate
    hook2 --> classify
    classify --> route
    route -->|Book| cal2
    route -->|Question| human
    route -->|Stop| optout
    err --> errslack
    model -.- classify
    style sec_lead fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_first fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_chase fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_reply fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_safety fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - A LEAD WRITES IN** - Web form, Instagram DM or Facebook DM all land on one webhook, get cleaned into the same shape, and are saved in Supabase before anything else runs.
- **2 - INSTANT ALERT AND FIRST REPLY** - The team hears about the lead in Slack, and the lead gets a WhatsApp reply with a booking link, both within seconds of writing in.
- **3 - FOLLOW UP UNTIL BOOKED** - One day later it checks Supabase. Booked or replied means confirm and put it on the calendar. Silence means a gentle nudge, wait two days, check again.
- **4 - WHEN THEY REPLY ON WHATSAPP** - Twilio posts the inbound message back in. The model reads it and routes it: book the time, hand a real question to a human, or stop messaging them for good.
- **5 - NOTHING FAILS QUIETLY** - If any step in the flow errors, Slack gets the lead, the step and a link to the failed run, so a silent break never costs a booking.
