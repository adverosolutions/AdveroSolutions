# Your Lead Intake and Qualification System: Reliable, Easy to Maintain

```mermaid
flowchart LR
    subgraph sec_capture["1 - YOUR LEAD CAPTURE FLOW"]
        direction TB
        hook(["1 - New Lead From Your Website or Ad Form"])
        clean["2 - Clean Up Name, Email, Phone and Source"]
        blank["3 - Drop Blank Submissions With No Email or Phone"]
    end
    subgraph sec_qualify["2 - QUALIFY EVERY LEAD WITH OPENAI"]
        direction TB
        qualify{{"4 - OpenAI Scores the Lead Against Your Rules"}}
        model{{"OpenAI - Scores and Qualifies the Lead<br/><i>openai</i>"}}
        parser{{"Parser - Score, Team and Reason"}}
        gate{"5 - Qualified by Your Rules?"}
        notq["5b - Not Qualified: Keep the Score and Reason"]
    end
    subgraph sec_route["3 - ROUTE QUALIFIED LEADS TO THE RIGHT TEAM"]
        direction TB
        route["6 - Match the Lead to the Right Team From Your Routing Table"]
        notify["7 - Email the Team the Lead and Why It Qualified<br/><i>gmail</i>"]
    end
    subgraph sec_tracker["4 - YOUR LEAD STATUS TRACKER"]
        direction TB
        track[("8 - Add the Lead to Your Status Tracker<br/><i>googleSheets</i>")]
    end
    subgraph sec_dashboard["5 - YOUR REPORTING DASHBOARD"]
        direction TB
        morning(["9 - Every Morning: Start the Lead Report"])
        readall[("10 - Read Every Lead in the Tracker<br/><i>googleSheets</i>")]
        stats["11 - Count Leads by Source, Team and Status"]
        dash[("12 - Refresh Your Dashboard Tab<br/><i>googleSheets</i>")]
        report["13 - Email You the Morning Lead Numbers<br/><i>gmail</i>"]
    end
    subgraph sec_errors["6 - RELIABLE: IF ANYTHING BREAKS, YOU HEAR ABOUT IT"]
        direction TB
        err(["14 - If Any Step Fails<br/><i>n8n</i>"])
        alert["15 - Email You the Failed Step and a Link to the Run<br/><i>gmail</i>"]
    end
    hook --> clean
    clean --> blank
    blank --> qualify
    qualify --> gate
    gate -->|true| route
    gate -->|false| notq
    route --> notify
    route --> track
    notq --> track
    morning --> readall
    readall --> stats
    stats --> dash
    dash --> report
    err --> alert
    model -.- qualify
    parser -.- qualify
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_qualify fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_tracker fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_dashboard fill:#fef9c3,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#ffedd5,stroke:#94a3b8,color:#0f172a
```

- **1 - YOUR LEAD CAPTURE FLOW** - Your website form, an ad lead form or anything that can send a webhook posts here. Names, emails and phones are cleaned up first, and blank submissions stop before they cost an OpenAI call.
- **2 - QUALIFY EVERY LEAD WITH OPENAI** - OpenAI scores each lead against the qualification rules you write in plain English in Config, and says why in one sentence. A missing budget or timeline lowers the score instead of being guessed.
- **3 - ROUTE QUALIFIED LEADS TO THE RIGHT TEAM** - You list your teams and their inboxes once in Config. OpenAI picks the team, this step finds its inbox, and a lead it cannot place goes to your default inbox.
- **4 - YOUR LEAD STATUS TRACKER** - Every lead lands in one Google Sheet, qualified or not, with its score, team and reason. Your team moves the Status column on to Contacted, Booked, Won or Lost.
- **5 - YOUR REPORTING DASHBOARD** - Every morning the Dashboard tab is rebuilt from the tracker: leads today, the last 7 days, the last 30 days and all time, by source, team and status, and who is still waiting for first contact. The same numbers arrive by email.
- **6 - RELIABLE: IF ANYTHING BREAKS, YOU HEAR ABOUT IT** - Nothing fails quietly. Any failed step emails you the step, the error and a link to the run, and the lead waits in that run for a retry.
