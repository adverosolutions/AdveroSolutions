# Your AI Agent for Your Existing Database: Retrieve, Update and Manage

```mermaid
flowchart LR
    subgraph sec_agent["1 - AN AI AGENT ON YOUR EXISTING DATABASE"]
        direction TB
        chat(["1 - You Ask Your Database in Plain English"])
        agent{{"2 - Claude Finds the Records You Asked For"}}
        model{{"Claude - Reads Your Data and Plans the Change<br/><i>anthropic</i>"}}
        memory{{"Memory - Remembers the Chat and the Change Waiting for Your Yes"}}
        search{{"Tool - Search Your Tables - Read-Only<br/><i>workflow</i>"}}
        stage{{"Tool - Hold an Update, Add or Archive Until You Say Yes<br/><i>workflow</i>"}}
        parser{{"Claude Writes the Reply and Says Answer, Confirm or Apply"}}
    end
    subgraph sec_manage["2 - RETRIEVE, UPDATE AND MANAGE: UPDATES WAIT FOR YOUR YES"]
        direction TB
        gate{"3 - Did You Say Yes to the Change?"}
        answer["3b - Answer You, or Show the Old and New Value to Confirm"]
    end
    subgraph sec_integrate["3 - INTEGRATED WITH YOUR CURRENT DATABASE"]
        direction TB
        apply[("4 - Postgres: Apply the Staged Change to Your Live Row<br/><i>postgres</i>")]
        log[("5 - Postgres: Log What Changed, When and in Which Chat<br/><i>postgres</i>")]
        done["6 - Tell You It Is Done, With the Old and New Value"]
    end
    subgraph sec_reliable["4 - RELIABLE PERFORMANCE: IF ANYTHING FAILS, YOU HEAR ABOUT IT"]
        direction TB
        err(["7 - If Any Step Fails<br/><i>n8n</i>"])
        alert["8 - Email You the Failed Step, the Error and the Run<br/><i>gmail</i>"]
    end
    chat --> agent
    agent --> gate
    gate -->|true| apply
    gate -->|false| answer
    apply --> log
    log --> done
    err --> alert
    model -.- agent
    memory -.- agent
    search -.- agent
    stage -.- agent
    parser -.- agent
    style sec_agent fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_manage fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_integrate fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_reliable fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - AN AI AGENT ON YOUR EXISTING DATABASE** - You ask your database a question in plain English. Claude reads your tables and answers from the real rows, never from memory.
- **2 - RETRIEVE, UPDATE AND MANAGE: UPDATES WAIT FOR YOUR YES** - Your parts 2 and 3: retrieving and updating in one smooth chat. A change is shown back to you as old value and new value first, and only a yes moves it forward.
- **3 - INTEGRATED WITH YOUR CURRENT DATABASE** - The approved change is written to your own Postgres, inside one transaction, only to the tables and columns you allowed. Every change lands in a change log you can undo from.
- **4 - RELIABLE PERFORMANCE: IF ANYTHING FAILS, YOU HEAR ABOUT IT** - A failed query or a timeout never fails quietly. You get an email with the step, the error and a link to the run.
