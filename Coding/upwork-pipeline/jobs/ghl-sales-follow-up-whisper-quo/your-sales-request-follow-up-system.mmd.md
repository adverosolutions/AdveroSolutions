# Your Sales Request Follow-Up System

```mermaid
flowchart LR
    subgraph sec_in["1 - SALES REQUEST COMES IN"]
        direction TB
        form(["1 - Sales Request Form Submitted<br/><i>ghl</i>"])
        tag_req["2 - Tag the Contact sales-request<br/><i>ghl</i>"]
        opp["3 - Open the Request in the Sales Pipeline<br/><i>ghl</i>"]
    end
    subgraph sec_call["2 - CALL YOU FIRST, WHISPER, THEN CONNECT"]
        direction TB
        call["4 - Call You, Whisper the Details, Then Connect<br/><i>ghl</i>"]
        gate{"5 - Did the Call Connect"}
        opp_spoke["6 - Move the Request to Spoke With<br/><i>ghl</i>"]
    end
    subgraph sec_seq["3 - IF THE CALL DOES NOT CONNECT, THE SEQUENCE STARTS"]
        direction TB
        sms1["7 - Text: Sorry I Missed You<br/><i>ghl</i>"]
        w1["8 - Wait 1 Day"]
        email1["9 - Email: Getting You on the Schedule<br/><i>ghl</i>"]
        w2["10 - Wait 2 Days"]
        manual["11 - Manual Call Task for You<br/><i>ghl</i>"]
        w3["12 - Wait 3 Days"]
        sms2["13 - Text: Still Want This on the Calendar<br/><i>ghl</i>"]
        w4["14 - Wait 4 Days"]
        email2["15 - Email: Last Note From Us<br/><i>ghl</i>"]
    end
    subgraph sec_reply["4 - STOP THE MOMENT THEY REPLY OR BOOK"]
        direction TB
        goal["16 - Goal: They Replied or Booked<br/><i>ghl</i>"]
        untag["17 - Remove the sales-request Tag<br/><i>ghl</i>"]
        opp_replied["18 - Move the Request to Replied<br/><i>ghl</i>"]
        notify["19 - Text You That They Answered<br/><i>ghl</i>"]
    end
    form --> tag_req
    tag_req --> opp
    opp --> call
    call --> gate
    gate -->|true| opp_spoke
    gate -->|false| sms1
    sms1 --> w1
    w1 --> email1
    email1 --> w2
    w2 --> manual
    manual --> w3
    w3 --> sms2
    sms2 --> w4
    w4 --> email2
    email2 --> goal
    goal --> untag
    untag --> opp_replied
    opp_replied --> notify
    style sec_in fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_call fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_seq fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_reply fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - SALES REQUEST COMES IN** - The Sales Request form fires this. The contact is tagged and the request is opened in the Sales pipeline so nothing lives only in an inbox.
- **2 - CALL YOU FIRST, WHISPER, THEN CONNECT** - GoHighLevel rings you first, reads the lead source, square footage and desired service in your ear, then bridges the customer in. Needs the three form fields lead_source, square_footage and desired_service on the contact record, and a phone number on your user profile.
- **3 - IF THE CALL DOES NOT CONNECT, THE SEQUENCE STARTS** - Text, email, a manual call task, text, email. Every text sends from the Quo business number hosted into GoHighLevel under Settings, Phone Numbers, hosted messaging, so replies land on your number and in the GoHighLevel conversation.
- **4 - STOP THE MOMENT THEY REPLY OR BOOK** - The goal pulls any replier out of the sequence on whatever day they answer, moves the opportunity and texts you. A two-step reply catcher workflow adds the sales-replied tag the goal listens for.
