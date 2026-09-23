# Your AI Request Handler - From Request to Done in Seconds

```mermaid
flowchart LR
    subgraph sec_intake["1 - A REQUEST COMES IN"]
        direction TB
        hook(["1 - New Request Comes In"])
        tidy["2 - Tidy the Name, Email and Message"]
    end
    subgraph sec_ai["2 - OPENAI READS IT AND WRITES THE REPLY"]
        direction TB
        read{{"3 - OpenAI Sorts It and Drafts the Reply"}}
        model{{"OpenAI<br/><i>openai</i>"}}
        parser{{"Category, Urgency, Key Details, Reply"}}
        log[("4 - Log It to the Requests Sheet<br/><i>googleSheets</i>")]
    end
    subgraph sec_route["3 - THE RIGHT PERSON HEARS ABOUT IT"]
        direction TB
        switch{"5 - Route by Category"}
        send["6a - Email the Reply Right Away<br/><i>gmail</i>"]
        sales["7a - Tell Sales: New Quote, Reply Sent<br/><i>slack</i>"]
        draft["6b - Save the Reply as a Draft to Approve<br/><i>gmail</i>"]
        support["7b - Tell Support a Draft Is Waiting<br/><i>slack</i>"]
        spam["6c - Spam: Logged, No Reply"]
    end
    subgraph sec_close["4 - CLOSE THE LOOP, FAIL LOUDLY"]
        direction TB
        done[("8 - Mark the Row Handled<br/><i>googleSheets</i>")]
        err(["9 - Any Step Fails<br/><i>n8n</i>"])
        alert["10 - Alert Slack With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> tidy
    tidy --> read
    read --> log
    log --> switch
    switch -->|Quote Request| send
    switch -->|Support Issue| draft
    switch -->|Spam| spam
    send --> sales
    draft --> support
    sales --> done
    support --> done
    err --> alert
    model -.- read
    parser -.- read
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_ai fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_close fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - A REQUEST COMES IN** - Any website form, inbox or app that can send a webhook plugs in here. The fields get tidied first, so a messy entry never breaks a later step.
- **2 - OPENAI READS IT AND WRITES THE REPLY** - One OpenAI call returns the category, urgency, key details and a ready reply, in a fixed format. Every request is logged to the sheet before anything else happens.
- **3 - THE RIGHT PERSON HEARS ABOUT IT** - Quote requests get a reply in seconds and sales gets the summary. Support issues, and anything the AI is unsure about, wait as a Gmail draft a person approves. Spam stops here.
- **4 - CLOSE THE LOOP, FAIL LOUDLY** - The row is marked handled with the Slack link and the time it took, so the team sees status in one place. If any step fails, Slack gets an alert with a link to the failed run.
