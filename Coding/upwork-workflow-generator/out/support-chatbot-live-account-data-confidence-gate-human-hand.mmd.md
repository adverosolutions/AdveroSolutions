# Support Chatbot: Live Account Data, Confidence Gate, Human Handoff

```mermaid
flowchart LR
    subgraph sec_intake["1 · CUSTOMER MESSAGE COMES IN"]
        direction TB
        chat(["1 · Customer Message Comes In"])
        ident["2 · Identify Session and Customer ID"]
    end
    subgraph sec_agent["2 · THE SUPPORT AGENT ANSWERS WITH LIVE ACCOUNT DATA"]
        direction TB
        agent{{"3 · Support Agent · Prompt Architecture"}}
        model{{"OpenAI GPT-4.1<br/><i>openai</i>"}}
        memory{{"Conversation Memory · Last 10 Turns"}}
        tool_account{{"Backend API: Fetch Account Details<br/><i>http</i>"}}
        tool_orders{{"Backend API: Order and Billing Status<br/><i>http</i>"}}
        tool_help{{"Help Center Search<br/><i>http</i>"}}
        parser{{"Answer + Confidence + Needs Human"}}
    end
    subgraph sec_gate["3 · SEND IT, RETRY IT, OR HAND IT TO A HUMAN"]
        direction TB
        confident{"4 · Confident and Safe to Send?"}
        respond["5 · Reply in Real Time"]
        apierr{"6 · Backend API Error? · Max 2 Retries"}
        wait["7 · Pause 2 Seconds and Retry the Call"]
        escalate["8 · Escalate to a Human With Context<br/><i>slack</i>"]
    end
    subgraph sec_ops["4 · LOG EVERY TURN, FAIL LOUDLY"]
        direction TB
        log[("9 · Log Turn, Tokens, and Outcome<br/><i>googleSheets</i>")]
        err(["10 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["11 · Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    chat --> ident
    ident --> agent
    agent --> confident
    confident -->|true| respond
    confident -->|false| apierr
    apierr -->|true| wait
    wait -.-> agent
    apierr -->|false| escalate
    respond --> log
    escalate --> log
    err --> alert
    model -.- agent
    memory -.- agent
    tool_account -.- agent
    tool_orders -.- agent
    tool_help -.- agent
    parser -.- agent
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_agent fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_gate fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_ops fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · CUSTOMER MESSAGE COMES IN** — Every message is tied to a session and a customer id before the model sees it, so the agent never guesses whose account it is looking at.
- **2 · THE SUPPORT AGENT ANSWERS WITH LIVE ACCOUNT DATA** — One agent, a locked system prompt, and three tools that call your backend API. It reads real account, order and billing data instead of making it up.
- **3 · SEND IT, RETRY IT, OR HAND IT TO A HUMAN** — The reply only goes out when the model reports high confidence and no sensitive action. Backend errors retry once, everything else goes to a person with full context.
- **4 · LOG EVERY TURN, FAIL LOUDLY** — Each turn is logged with tokens and outcome so prompt changes can be measured. Any node failure alerts a human with a link to the run.
