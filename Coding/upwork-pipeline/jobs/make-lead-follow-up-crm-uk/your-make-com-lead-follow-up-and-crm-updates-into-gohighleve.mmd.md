# Your Make.com Lead Follow-Up and CRM Updates Into GoHighLevel

```mermaid
flowchart LR
    subgraph sec_follow["1 - LEAD FOLLOW-UP"]
        direction TB
        hook(["1 - New Lead From Your Website Form"])
        read{{"2 - Read the Enquiry and Write the First Reply"}}
        real{"3 - Is It a Real Enquiry?"}
        spam["3b - Spam or Test Entry: Stop, Nothing Sent"]
    end
    subgraph sec_crm["2 - CRM UPDATES"]
        direction TB
        upsert["4 - GoHighLevel: Create or Update the Contact"]
    end
    subgraph sec_reliable["3 - RELIABLE, CONNECTED, DATA FLOWING CORRECTLY"]
        direction TB
        saved{"5 - Did GoHighLevel Save the Lead?"}
        alert["5b - Email You the Lead and What Went Wrong<br/><i>gmail</i>"]
    end
    subgraph sec_ongoing["4 - ONGOING LEAD MANAGEMENT"]
        direction TB
        note["6 - GoHighLevel: Save the Enquiry as a Note"]
        newlead{"7 - New Lead or Already in GoHighLevel?"}
        opp["8 - GoHighLevel: Add the Lead to Your Pipeline"]
        text["9 - GoHighLevel: Text the First Reply"]
        sequence["10 - GoHighLevel: Start Your Follow-Up Sequence"]
        task["7b - GoHighLevel: Task for You to Call Them Back"]
    end
    hook --> read
    read --> real
    real -->|real enquiry| upsert
    real -->|spam or test entry| spam
    upsert --> saved
    saved -->|saved| note
    saved -->|not saved| alert
    note --> newlead
    newlead -->|new lead| opp
    newlead -->|returning lead| task
    opp --> text
    text --> sequence
    style sec_follow fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_crm fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_reliable fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_ongoing fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - LEAD FOLLOW-UP** - A new enquiry from your website form is read the moment it arrives and a first reply is written from what they actually asked. Spam and test entries stop at step 3, before anything is sent. If your form tool cannot send to a webhook, step 1 becomes a Make mailhook on the form's notification email and nothing after it changes.
- **2 - CRM UPDATES** - The lead is created in GoHighLevel, or updated if they are already there, matched on email and phone so each person is one contact, with UK mobiles saved as +44 so GoHighLevel can text them.
- **3 - RELIABLE, CONNECTED, DATA FLOWING CORRECTLY** - Your reliable process, connected systems and data flowing correctly between platforms, grouped here: form, Make and GoHighLevel in one scenario, and a lead GoHighLevel refuses comes to your inbox with the reason. Failed runs nobody sees are the first gap I check in your current setup.
- **4 - ONGOING LEAD MANAGEMENT** - What they asked is saved on the contact as a note for whoever calls them back. New leads then get a card in your pipeline, the first text and your follow-up sequence, and someone already in GoHighLevel who enquires again becomes a task for you. Room to add a booking step next, so the card moves when they book.
