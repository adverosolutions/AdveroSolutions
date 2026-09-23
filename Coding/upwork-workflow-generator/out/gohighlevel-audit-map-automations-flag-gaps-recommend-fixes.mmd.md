# GoHighLevel Audit — Map Automations, Flag Gaps, Recommend Fixes

```mermaid
flowchart LR
    subgraph sec_pull["1 · PULL CURRENT STATE"]
        direction TB
        trig(["Audit Requested"])
        list_workflows["Pull Every Active Workflow and Funnel from GoHighLevel<br/><i>gohighlevel</i>"]
        map_flows["Map Each Workflow: Trigger, Actions, and Exit Point"]
    end
    subgraph sec_diagnose["2 · MAP & DIAGNOSE"]
        direction TB
        branch_followup{"Trigger Fires But No Follow-Up Action Configured?"}
        filter_broken["Flag Workflows With Broken or Orphaned Triggers"]
        branch_sla{"Step Timing Exceeds Lead Response SLA?"}
        gap_agent{{"Cross-Check Every Flag Against Common Lead-Flow Gap Checklist"}}
        gap_model{{"GPT-4.1<br/><i>openai</i>"}}
    end
    subgraph sec_score["3 · SCORE & PRIORITIZE"]
        direction TB
        score_impact["Score Each Confirmed Gap by Lead-Flow Impact"]
        rank_fixes["Rank Gaps: Fastest Fix vs Highest Impact"]
    end
    subgraph sec_deliver["4 · DELIVER REPORT & RECOMMENDATIONS"]
        direction TB
        fix_agent{{"Draft a Specific Recommended Fix for Each Gap"}}
        fix_model{{"GPT-4.1<br/><i>openai</i>"}}
        compile_report["Compile Findings Into Audit Report<br/><i>google_docs</i>"]
        send_report["Send Audit Report and Recommendations to Client<br/><i>gmail</i>"]
    end
    trig --> list_workflows
    list_workflows --> map_flows
    map_flows --> branch_followup
    map_flows --> filter_broken
    map_flows --> branch_sla
    branch_followup -->|true| gap_agent
    filter_broken --> gap_agent
    branch_sla -->|true| gap_agent
    gap_agent --> score_impact
    score_impact --> rank_fixes
    rank_fixes --> fix_agent
    fix_agent --> compile_report
    compile_report --> send_report
    gap_model -.- gap_agent
    fix_model -.- fix_agent
    style sec_pull fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_diagnose fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_score fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_deliver fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · PULL CURRENT STATE** — Pulls every active workflow and funnel straight from the account instead of relying on a description of what should be running.
- **2 · MAP & DIAGNOSE** — Maps each workflow's trigger, actions, and exit point, then runs it through three checks a lead can silently fall through.
- **3 · SCORE & PRIORITIZE** — Scores every confirmed gap by lead-flow impact so the fix list is ordered by what actually costs leads, not by what's easiest.
- **4 · DELIVER REPORT & RECOMMENDATIONS** — Turns the flagged gaps into specific, named fixes and sends the report rather than a vague punch list.
