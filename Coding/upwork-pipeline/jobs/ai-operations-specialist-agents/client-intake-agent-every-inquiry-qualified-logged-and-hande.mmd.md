# Client Intake Agent: Every Inquiry Qualified, Logged and Handed Off

```mermaid
flowchart LR
    subgraph sec_agent["1 - CLIENT INTAKE AGENT"]
        direction TB
        hook(["1 - New Client Inquiry From Your Website Form"])
        agent{{"2 - Intake Agent Qualifies the Client and Sets Up the Work"}}
        model{{"Claude - Runs the Intake Agent<br/><i>anthropic</i>"}}
        t_contact{{"HubSpot - Save the Client as a Contact<br/><i>http</i>"}}
        t_deal{{"HubSpot - Open a Deal in Your Pipeline<br/><i>http</i>"}}
        t_task{{"ClickUp - Create the Scoping Task for the Owner<br/><i>http</i>"}}
        t_slack{{"Slack - Hand the Client to the Owner<br/><i>http</i>"}}
        parser{{"Parser - Fit, Owner and Client Reply"}}
    end
    subgraph sec_tools["2 - YOUR TOOLS: HUBSPOT, CLICKUP AND SLACK UNDER THE AGENT, GMAIL HERE"]
        direction TB
        gate{"3 - Safe to Send Without a Person?"}
        reply_send["4 - Gmail: Send the Client Their Next Step<br/><i>gmail</i>"]
        reply_draft["4b - Gmail: Hold the Reply as a Draft for the Owner<br/><i>gmail</i>"]
    end
    subgraph sec_monitor["3 - TEST, MONITOR AND ITERATE"]
        direction TB
        err(["5 - If Any Step Fails<br/><i>n8n</i>"])
        alert["6 - Slack: Alert Ops With the Failed Step and Run Link<br/><i>slack</i>"]
    end
    hook --> agent
    agent --> gate
    gate -->|true| reply_send
    gate -->|false| reply_draft
    err --> alert
    model -.- agent
    t_contact -.- agent
    t_deal -.- agent
    t_task -.- agent
    t_slack -.- agent
    parser -.- agent
    style sec_agent fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_tools fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_monitor fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 - CLIENT INTAKE AGENT** - The first task on your list. Each inquiry from your website form goes to an agent that checks it against your fit rules, then decides which of its four tools to call.
- **2 - YOUR TOOLS: HUBSPOT, CLICKUP AND SLACK UNDER THE AGENT, GMAIL HERE** - HubSpot, ClickUp and Slack are the agent's tools, hanging under it in section 1, and write while it works. Here the client's reply goes out from your Gmail, or waits as a draft when a person should read it first.
- **3 - TEST, MONITOR AND ITERATE** - Any failed step posts to Slack with a link to the run, where the inquiry waits for a retry. Every run keeps the agent's tool calls in n8n, and those are what we review each week to tune it.
