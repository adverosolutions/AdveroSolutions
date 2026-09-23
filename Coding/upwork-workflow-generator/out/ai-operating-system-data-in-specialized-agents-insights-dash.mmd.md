# AI Operating System — Data In → Specialized Agents → Insights → Dashboards & Action

```mermaid
flowchart LR
    subgraph sec_sources["1 · DATA ENTERS"]
        direction TB
        trig(["Continuous Sync, Every 15 Minutes"])
        src_marketing["Pull Google Ads and Meta Ads Spend and Leads"]
        src_ghl["Pull Leads, Pipeline, and Conversations from GoHighLevel"]
        src_servicem8["Pull Jobs, Scheduling, and Completion Data from ServiceM8"]
        src_xero["Pull Revenue, Invoices, and Margin from Xero"]
    end
    subgraph sec_connect["2 · CONNECT & ATTRIBUTE"]
        direction TB
        unify["Unify Into One Data Layer, Lead to Job to Invoice, Linked by Customer"]
        attribution["Attribute Every Job and Invoice Back to Its Lead Source and Campaign"]
    end
    subgraph sec_agents["3 · SPECIALIZED AGENTS"]
        direction TB
        agent_marketing{{"Marketing Intelligence Agent: CPL, CPA, and Return on Ad Spend by Channel"}}
        model_marketing{{"GPT-4.1<br/><i>openai</i>"}}
        agent_revenue{{"Revenue Agent: Pipeline, Conversion, and Sales Bottlenecks"}}
        model_revenue{{"GPT-4.1<br/><i>openai</i>"}}
        agent_ops{{"Operations Agent: Jobs Completed, Delayed, and Team Performance"}}
        model_ops{{"GPT-4.1<br/><i>openai</i>"}}
        agent_finance{{"Finance Agent: Revenue, Margin, and Cashflow Indicators"}}
        model_finance{{"GPT-4.1<br/><i>openai</i>"}}
        agent_cx{{"Customer Experience Agent: Reviews, Complaints, and Response Times"}}
        model_cx{{"GPT-4.1<br/><i>openai</i>"}}
    end
    subgraph sec_decide["4 · INSIGHTS & DECISIONS"]
        direction TB
        orchestrator{{"Executive Agent: Answers Business Questions and Flags Issues Across the Team"}}
        model_exec{{"GPT-4.1<br/><i>openai</i>"}}
        issue_branch{"Issue Detected: Slow Response, Lost Opportunity, Delayed Job, or Margin Drop?"}
    end
    subgraph sec_act["5 · DASHBOARDS & ACTION"]
        direction TB
        alert_team["Alert the Right Team Member With the Insight<br/><i>slack</i>"]
        create_task["Create a Follow-Up Task in Monday.com"]
        dashboards[("Update Executive Dashboards: Marketing, Sales, Ops, Finance, CX<br/><i>googleSheets</i>")]
    end
    trig --> src_marketing
    trig --> src_ghl
    trig --> src_servicem8
    trig --> src_xero
    src_marketing --> unify
    src_ghl --> unify
    src_servicem8 --> unify
    src_xero --> unify
    unify --> attribution
    attribution --> agent_marketing
    attribution --> agent_revenue
    attribution --> agent_ops
    attribution --> agent_finance
    attribution --> agent_cx
    agent_marketing --> orchestrator
    agent_revenue --> orchestrator
    agent_ops --> orchestrator
    agent_finance --> orchestrator
    agent_cx --> orchestrator
    orchestrator --> issue_branch
    issue_branch -->|true| alert_team
    issue_branch -->|true| create_task
    issue_branch -->|false| dashboards
    alert_team --> dashboards
    create_task --> dashboards
    model_marketing -.- agent_marketing
    model_revenue -.- agent_revenue
    model_ops -.- agent_ops
    model_finance -.- agent_finance
    model_cx -.- agent_cx
    model_exec -.- orchestrator
    style sec_sources fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_connect fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_agents fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_decide fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_act fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · DATA ENTERS** — Every business system feeds in on a continuous sync, marketing spend, CRM, jobs, and financials, so the AI layer sees the whole business, not one slice.
- **2 · CONNECT & ATTRIBUTE** — Everything lands in one data layer linked by customer, so a lead can be traced to its job and its invoice, that's what makes cost per lead and profitability answerable.
- **3 · SPECIALIZED AGENTS** — Not one chatbot, a team. Each agent owns one domain and reads only the data it needs, so the answers stay sharp instead of generic.
- **4 · INSIGHTS & DECISIONS** — An executive agent sits over the team, answers questions like how many roofing leads this month, and flags issues before someone has to notice them.
- **5 · DASHBOARDS & ACTION** — Insights become dashboards for management and alerts and tasks for the team, that's the part that actually saves staff time.
