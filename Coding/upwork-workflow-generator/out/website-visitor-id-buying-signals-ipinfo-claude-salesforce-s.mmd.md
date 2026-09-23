# Website Visitor ID + Buying Signals: IPinfo, Claude, Salesforce, Slack

```mermaid
flowchart LR
    subgraph sec_visit["1 · IDENTIFY WHO IS ON THE SITE"]
        direction TB
        hook(["1 · Tracking Script: Page View Event"])
        bots["2 · Filter Bots and ISPs"]
        ipinfo["3 · IPinfo: Reverse IP to Company<br/><i>ipinfo</i>"]
    end
    subgraph sec_score["2 · SCORE THE VISIT"]
        direction TB
        behav["4 · Behavioral Score · pages, time, pricing page"]
        thresh{"5 · Score Above Threshold?"}
        coldvisit["5b · Below Threshold: Keep the Visit, No Alert"]
    end
    subgraph sec_enrich["3 · CLAUDE ENRICHES, SALESFORCE AND SLACK GET IT"]
        direction TB
        agent{{"6 · Claude: Enrich and Summarize the Account"}}
        agent_model{{"Claude<br/><i>anthropic</i>"}}
        agent_tool{{"MCP: Salesforce Account Lookup<br/><i>mcp</i>"}}
        agent_parser{{"Account Summary, Fit Score, Suggested Next Step"}}
        sf_upsert["7 · Upsert Account + Visit Activity<br/><i>salesforce</i>"]
        hot_alert["8 · Hot Visitor Alert to Sales<br/><i>slack</i>"]
    end
    subgraph sec_signals["4 · EVERY MORNING: WATCH THE WEB FOR BUYING SIGNALS"]
        direction TB
        morning(["9 · Every Morning"])
        crawl["10 · Firecrawl: Crawl Watched Sources<br/><i>firecrawl</i>"]
        extract{{"11 · Claude: Extract Buying Signals"}}
        extract_model{{"Claude<br/><i>anthropic</i>"}}
        found{"12 · Signal Found?"}
        sf_task["13 · Salesforce: Create Task on Account<br/><i>salesforce</i>"]
        signal_alert["14 · Buying Signal Digest to Sales<br/><i>slack</i>"]
    end
    subgraph sec_errors["5 · FAIL LOUDLY"]
        direction TB
        err(["15 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        err_alert["16 · Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    hook --> bots
    bots --> ipinfo
    ipinfo --> behav
    behav --> thresh
    thresh -->|true| agent
    thresh -->|false| coldvisit
    agent --> sf_upsert
    sf_upsert --> hot_alert
    morning --> crawl
    crawl --> extract
    extract --> found
    found -->|true| sf_task
    sf_task --> signal_alert
    err --> err_alert
    agent_model -.- agent
    agent_tool -.- agent
    agent_parser -.- agent
    extract_model -.- extract
    style sec_visit fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_score fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_enrich fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_signals fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · IDENTIFY WHO IS ON THE SITE** — The tracking script posts every page view here. Bots and home ISPs get dropped, real companies get named by their IP.
- **2 · SCORE THE VISIT** — Pages viewed, time on site and a pricing page visit add up to one number. Only hot visits go further.
- **3 · CLAUDE ENRICHES, SALESFORCE AND SLACK GET IT** — Claude checks Salesforce over MCP for an existing account, writes a summary, then the account and a Slack alert are created.
- **4 · EVERY MORNING: WATCH THE WEB FOR BUYING SIGNALS** — Firecrawl pulls the watched sources, Claude reads them for hiring, funding and expansion signals, and a Salesforce task lands on the matching account.
- **5 · FAIL LOUDLY** — Any node failing anywhere sends a Slack alert with a link to the run. Nothing dies silently on the Mac mini.
