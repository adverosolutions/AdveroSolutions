# Workiz Job to SMS Follow-Up System - AI Replies, Human Approval

```mermaid
flowchart LR
    subgraph sec_assigned["1 - A JOB LANDS ON YOUR BOARD"]
        direction TB
        job_hook(["1 - Workiz: Job Assigned to Me"])
        pull["2 - Pull Customer, Job Type, Address, Time Window"]
    end
    subgraph sec_firstsms["2 - THE FIRST TEXT GOES OUT"]
        direction TB
        write_sms{{"3 - OpenAI: Write the Personalized First SMS From Your Template<br/><i>openai</i>"}}
        write_model{{"OpenAI<br/><i>openai</i>"}}
        send_sms["4 - Quo / OpenPhone: Send SMS From Your Existing Number<br/><i>openphone</i>"]
        log_sent[("5 - Log Job + Message Sent<br/><i>googleSheets</i>")]
    end
    subgraph sec_replies["3 - THE CUSTOMER TEXTS BACK"]
        direction TB
        reply_hook(["6 - Quo / OpenPhone: Customer Replied"])
        agent{{"7 - OpenAI: Understand the Reply and Pick a Pre-Approved Template"}}
        agent_model{{"OpenAI<br/><i>openai</i>"}}
        agent_tool{{"Approved Template Library"}}
        agent_parser{{"Intent + Suggested Reply + Confidence"}}
    end
    subgraph sec_approval["4 - YOUR REP APPROVES BEFORE ANYTHING SENDS"]
        direction TB
        suggest["8 - Suggest Reply to Rep: Approve or Edit<br/><i>slack</i>"]
        approved_hook(["9 - Rep Approved or Edited"])
        send_reply["10 - Quo / OpenPhone: Send the Approved Reply<br/><i>openphone</i>"]
    end
    subgraph sec_log["5 - EVERY MESSAGE LOGGED, NOTHING FAILS QUIETLY"]
        direction TB
        log_reply[("11 - Log Reply + Approval<br/><i>googleSheets</i>")]
        err_hook(["12 - Any Step in the Scenario Fails<br/><i>make</i>"])
        alert["13 - Alert Me With the Job and What Broke<br/><i>slack</i>"]
    end
    job_hook --> pull
    pull --> write_sms
    write_sms --> send_sms
    send_sms --> log_sent
    reply_hook --> agent
    agent --> suggest
    approved_hook --> send_reply
    send_reply --> log_reply
    err_hook --> alert
    write_model -.- write_sms
    agent_model -.- agent
    agent_tool -.- agent
    agent_parser -.- agent
    style sec_assigned fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_firstsms fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_replies fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_approval fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_log fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - A JOB LANDS ON YOUR BOARD** - The moment Workiz assigns the job to you, this fires. Nobody has to remember to text anyone.
- **2 - THE FIRST TEXT GOES OUT** - Written from your own template, filled with this customer's real job details, sent from the Quo number they already know.
- **3 - THE CUSTOMER TEXTS BACK** - AI reads the reply and picks from your pre-approved templates. It never writes a message from scratch.
- **4 - YOUR REP APPROVES BEFORE ANYTHING SENDS** - The suggestion goes to a person first. Shown here in Slack, but this can just as easily be a Quo internal thread or a text to the rep.
- **5 - EVERY MESSAGE LOGGED, NOTHING FAILS QUIETLY** - One row per conversation, plus an alert the moment a step breaks so a customer is never left on read.
