# Customer Support Automation System - Answer, Escalate, Learn

```mermaid
flowchart LR
    subgraph sec_intake["1 - EVERY TICKET AND CHAT ARRIVES HERE"]
        direction TB
        hook(["1 - Support Ticket or Chat Message In - From Your Support Platform"])
        context["2 - Identify the Customer, the Channel, and Their Prior Tickets"]
    end
    subgraph sec_draft["2 - CLAUDE WRITES THE ANSWER FROM YOUR OWN DOCS"]
        direction TB
        agent{{"3 - Claude: Draft the Answer From Your Help Docs and Past Tickets"}}
        model{{"Claude<br/><i>anthropic</i>"}}
        memory{{"Remember the Rest of This Conversation"}}
        docs{{"Help Center Search"}}
        lookup{{"Order / Account Lookup"}}
        parser{{"Answer + Confidence + Intent"}}
    end
    subgraph sec_reply["3 - ROUTE THE ANSWER AND SEND THE REPLY"]
        direction TB
        route{"4 - Route by Intent"}
        confident{"5 - Confident Enough to Send This Without a Person?"}
        send["6 - Support Platform: Post the Reply and Close the Ticket"]
        account["7 - Support Platform: Reply With Account Details, Keep It Open"]
    end
    subgraph sec_escalate["4 - HAND OFF TO A HUMAN, LOG EVERY TICKET"]
        direction TB
        review["8 - Send the Draft to a Human to Check Before It Goes Out<br/><i>slack</i>"]
        escalate["9 - Escalate to a Human With the Full Ticket History<br/><i>slack</i>"]
        log[("10 - Log the Ticket, Intent, Confidence, and Who Resolved It<br/><i>googleSheets</i>")]
    end
    subgraph sec_learn["5 - THE SYSTEM GETS MORE ACCURATE EVERY WEEK"]
        direction TB
        weekly(["11 - Once a Week, Look Back at Every Ticket"])
        rollup["12 - Roll Up the Low-Confidence and Escalated Tickets"]
        improve{{"13 - Claude: Suggest New Answers and Help Doc Fixes"}}
        report["14 - Weekly Accuracy Report to Your Team<br/><i>slack</i>"]
        err(["15 - Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["16 - Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> context
    context --> agent
    agent --> route
    route -->|FAQ| confident
    route -->|Account Issue| account
    route -->|Refund or Complaint| escalate
    confident -->|true| send
    confident -->|false| review
    send --> log
    account --> log
    review --> log
    escalate --> log
    weekly --> rollup
    rollup --> improve
    improve --> report
    err --> alert
    model -.- agent
    memory -.- agent
    docs -.- agent
    lookup -.- agent
    parser -.- agent
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_draft fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_reply fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_escalate fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_learn fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - EVERY TICKET AND CHAT ARRIVES HERE** - One entry point for every channel. Before anything is written we know who is asking and what they asked last time.
- **2 - CLAUDE WRITES THE ANSWER FROM YOUR OWN DOCS** - It answers from your help center and past tickets, not from guesswork. It also returns how confident it is.
- **3 - ROUTE THE ANSWER AND SEND THE REPLY** - Simple questions get answered and closed. Anything about an account gets answered but stays open.
- **4 - HAND OFF TO A HUMAN, LOG EVERY TICKET** - Low confidence, refunds and complaints go to a person with the draft attached. Every ticket lands in the log either way.
- **5 - THE SYSTEM GETS MORE ACCURATE EVERY WEEK** - Once a week Claude reads what it got wrong and tells you which help docs to write next.
