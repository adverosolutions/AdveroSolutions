# Your Claude Agent Layer: CRM, Database and Slack From One Webhook

```mermaid
flowchart LR
    subgraph sec_agent["1 - CLAUDE AGENT AND ITS CRM, DATABASE AND SLACK TOOLS"]
        direction TB
        hook(["1 - New Request Arrives by Webhook"])
        hook_cc(["1b - Claude Code Calls the Same Agent by Webhook"])
        agent{{"2 - Claude Agent Reads It and Picks Its Tools"}}
        model{{"Claude - Runs the Operations Agent<br/><i>anthropic</i>"}}
        t_find{{"HubSpot - Find the Contact<br/><i>http</i>"}}
        t_orders{{"Database - Look Up Their Orders and Invoices<br/><i>http</i>"}}
        t_update{{"HubSpot - Update the Contact<br/><i>http</i>"}}
        t_slack{{"Slack - Hand It to the Team<br/><i>http</i>"}}
        parser{{"Claude's Answer Form - Topic, Actions and Reply Draft"}}
    end
    subgraph sec_systems["2 - ANSWER SENT BACK ON THE WEBHOOK"]
        direction TB
        reply["3 - Send the Answer Back on the Webhook"]
    end
    subgraph sec_monitor["3 - ERROR HANDLING, MONITORING AND TESTING"]
        direction TB
        log[("4 - Log the Run: Topic, Tools Called, Hand-Off<br/><i>postgres</i>")]
        err(["5 - If Any Step Fails<br/><i>n8n</i>"])
        alert["6 - Slack: Alert With the Failed Step and Run Link<br/><i>slack</i>"]
    end
    hook --> agent
    hook_cc --> agent
    agent --> reply
    reply --> log
    err --> alert
    model -.- agent
    t_find -.- agent
    t_orders -.- agent
    t_update -.- agent
    t_slack -.- agent
    parser -.- agent
    style sec_agent fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_systems fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_monitor fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 - CLAUDE AGENT AND ITS CRM, DATABASE AND SLACK TOOLS** - Your parts 1 to 4 and 6. A customer or team request, or a Claude Code task, hits the webhook. The Claude agent finds the contact in HubSpot, reads their records, updates HubSpot and hands off to Slack.
- **2 - ANSWER SENT BACK ON THE WEBHOOK** - Your part 5. Whatever called the webhook gets the reply draft and a list of what the agent did.
- **3 - ERROR HANDLING, MONITORING AND TESTING** - Your parts 7 to 9. Every run is logged with the tools the agent called, and any failed step posts to Slack with a link to retry it.
