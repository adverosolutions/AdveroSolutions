# Four Weekly Marketing Tasks, Automated — Report, Repurpose, Clean Leads, Triage Replies

```mermaid
flowchart LR
    subgraph sec_trigger["1 · ONE WEEKLY TRIGGER"]
        direction TB
        trig(["Every Monday, 8am"])
    end
    subgraph sec_report["2 · TASK 1 · WEEKLY PERFORMANCE REPORT"]
        direction TB
        pull_metrics["Pull Last Week's Ads and Analytics Numbers"]
        summarize_agent{{"Summarize Performance and Flag What Changed"}}
        summarize_model{{"Claude<br/><i>anthropic</i>"}}
        send_report["Post the Weekly Report to Slack<br/><i>slack</i>"]
    end
    subgraph sec_content["3 · TASK 2 · REPURPOSE & SCHEDULE CONTENT"]
        direction TB
        pull_content["Pull This Week's Blog Post or Newsletter"]
        repurpose_agent{{"Repurpose Into Social Posts in the Brand Voice"}}
        repurpose_model{{"Claude<br/><i>anthropic</i>"}}
        schedule_posts["Push the Posts to the Scheduler"]
    end
    subgraph sec_leads["4 · TASK 3 · CLEAN LEADS & SYNC THE CRM"]
        direction TB
        pull_leads["Pull New Leads From Forms and Signups"]
        clean_leads["Dedupe and Drop Incomplete Records"]
        sync_crm["Create or Update Contacts in the CRM<br/><i>hubspot</i>"]
    end
    subgraph sec_triage["5 · TASK 4 · TRIAGE REPLIES & DRAFT FOLLOW-UPS"]
        direction TB
        pull_replies["Pull Unanswered Replies From the Inbox"]
        triage_agent{{"Classify Hot, Warm, or Cold and Draft the Follow-Up"}}
        triage_model{{"Claude<br/><i>anthropic</i>"}}
        create_tasks["Create Follow-Up Tasks for the Hot Ones"]
    end
    subgraph sec_refine["6 · TEST & REFINE"]
        direction TB
        run_log[("Log the Run: What Ran, What Failed, How Long<br/><i>googleSheets</i>")]
        fail_branch{"Did Any Task Fail?"}
        alert_fail["Alert Immediately With Which Task and Why<br/><i>slack</i>"]
        all_clean["All Four Ran Clean"]
    end
    trig --> pull_metrics
    trig --> pull_content
    trig --> pull_leads
    trig --> pull_replies
    pull_metrics --> summarize_agent
    summarize_agent --> send_report
    pull_content --> repurpose_agent
    repurpose_agent --> schedule_posts
    pull_leads --> clean_leads
    clean_leads --> sync_crm
    pull_replies --> triage_agent
    triage_agent --> create_tasks
    send_report --> run_log
    schedule_posts --> run_log
    sync_crm --> run_log
    create_tasks --> run_log
    run_log --> fail_branch
    fail_branch -->|true| alert_fail
    fail_branch -->|false| all_clean
    summarize_model -.- summarize_agent
    repurpose_model -.- repurpose_agent
    triage_model -.- triage_agent
    style sec_trigger fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_report fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_content fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_leads fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_triage fill:#fef9c3,stroke:#94a3b8,color:#0f172a
    style sec_refine fill:#ffedd5,stroke:#94a3b8,color:#0f172a
```

- **1 · ONE WEEKLY TRIGGER** — One schedule kicks off all four tasks, so nothing depends on someone remembering to start it.
- **2 · TASK 1 · WEEKLY PERFORMANCE REPORT** — Pulls last week's numbers, has AI summarize what actually changed, and posts it before the week starts.
- **3 · TASK 2 · REPURPOSE & SCHEDULE CONTENT** — Turns the week's long-form piece into social posts in the brand voice and pushes them to the scheduler.
- **4 · TASK 3 · CLEAN LEADS & SYNC THE CRM** — New signups get deduped and checked before they touch the CRM, so the list stays clean without a weekly manual pass.
- **5 · TASK 4 · TRIAGE REPLIES & DRAFT FOLLOW-UPS** — Unanswered replies get classified hot, warm, or cold, with a follow-up drafted for each, so nothing sits in the inbox.
- **6 · TEST & REFINE** — Every run logs what ran, what failed, and how long it took, and a failure alerts immediately, that's how the workflows get refined on real data instead of guesswork.
