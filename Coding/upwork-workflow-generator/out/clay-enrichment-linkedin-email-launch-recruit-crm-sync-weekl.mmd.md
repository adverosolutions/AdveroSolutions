# Clay Enrichment → LinkedIn + Email Launch → Recruit CRM Sync → Weekly Health Digest

```mermaid
flowchart LR
    subgraph sec_enrich["1 · CLAY ENRICHMENT & ICP SCORE"]
        direction TB
        trig(["Daily Clay Table Sync"])
        clay_pull["Pull Newly Enriched Rows from Clay<br/><i>clay</i>"]
        icp_agent{{"Score Contact Against ICP"}}
        icp_model{{"GPT-4.1<br/><i>openai</i>"}}
        icp_branch{"ICP Fit Score 70 or Higher?"}
    end
    subgraph sec_quality["2 · DEDUPE & DATA QUALITY"]
        direction TB
        crm_check["Check Recruit CRM for Existing Contact<br/><i>recruitcrm</i>"]
        dedup_filter["Drop Duplicates, Recent Touches, and Missing Email or LinkedIn URL"]
    end
    subgraph sec_launch["3 · LAUNCH: LINKEDIN + EMAIL"]
        direction TB
        heyreach_add["Add to LinkedIn Campaign in HeyReach<br/><i>heyreach</i>"]
        email_add["Add to Cold Email Sequence<br/><i>email_platform</i>"]
        merge_touch["Merge LinkedIn and Email Touchpoints"]
    end
    subgraph sec_sync["4 · CRM SYNC & REPLY ROUTING"]
        direction TB
        crm_sync["Upsert Contact and Log Campaign Activity in Recruit CRM<br/><i>recruitcrm</i>"]
        reply_trig(["Inbound Reply Received"])
        reply_agent{{"Classify Reply: Interested, Not Interested, or Out of Office"}}
        reply_model{{"GPT-4.1<br/><i>openai</i>"}}
        reply_branch{"Interested?"}
        crm_update["Move Deal to Interested Stage and Pause Outreach<br/><i>recruitcrm</i>"]
    end
    subgraph sec_digest["5 · WEEKLY HEALTH DIGEST"]
        direction TB
        weekly_trig(["Weekly Health Check — Monday 8am"])
        aggregate["Aggregate Sends, Opens, Replies, and Bounce Rate"]
        bounce_branch{"Bounce Rate Above 3 Percent?"}
        alert_slack["Alert: Inbox Health Degrading<br/><i>slack</i>"]
        digest_agent{{"Draft Weekly Summary of Campaigns, Issues, and Recommendations"}}
        digest_model{{"GPT-4.1<br/><i>openai</i>"}}
        post_digest["Post Weekly Summary to Team<br/><i>slack</i>"]
    end
    trig --> clay_pull
    clay_pull --> icp_agent
    icp_agent --> icp_branch
    icp_branch -->|true| crm_check
    crm_check --> dedup_filter
    dedup_filter --> heyreach_add
    dedup_filter --> email_add
    heyreach_add --> merge_touch
    email_add --> merge_touch
    merge_touch --> crm_sync
    reply_trig --> reply_agent
    reply_agent --> reply_branch
    reply_branch -->|true| crm_update
    weekly_trig --> aggregate
    aggregate --> bounce_branch
    bounce_branch -->|true| alert_slack
    aggregate --> digest_agent
    digest_agent --> post_digest
    icp_model -.- icp_agent
    reply_model -.- reply_agent
    digest_model -.- digest_agent
    style sec_enrich fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_quality fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_launch fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_sync fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_digest fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · CLAY ENRICHMENT & ICP SCORE** — Pulls newly enriched rows off the Clay table and scores each contact against the ICP before anything else runs.
- **2 · DEDUPE & DATA QUALITY** — Checks Recruit CRM for an existing contact and drops duplicates, recently-touched records, and rows missing an email or LinkedIn URL.
- **3 · LAUNCH: LINKEDIN + EMAIL** — Adds the surviving contacts to the LinkedIn campaign and the cold email sequence in parallel.
- **4 · CRM SYNC & REPLY ROUTING** — Logs every touchpoint back to Recruit CRM and routes inbound replies to pause outreach and move the deal stage.
- **5 · WEEKLY HEALTH DIGEST** — Rolls up sends, opens, replies and bounce rate every Monday and flags deliverability before it becomes a problem.
