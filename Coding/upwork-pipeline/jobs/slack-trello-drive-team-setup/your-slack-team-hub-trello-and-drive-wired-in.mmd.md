# Your Slack Team Hub - Trello and Drive Wired In

```mermaid
flowchart LR
    subgraph sec_events["1 - TRELLO AND DRIVE EVENTS COME IN"]
        direction TB
        hook(["1 - Trello Card or Drive File Event Arrives"])
    end
    subgraph sec_route["2 - ROUTE TO THE RIGHT TEAM CHANNEL"]
        direction TB
        map["2 - Private Channel Map"]
        pick["3 - Pick the Team Channel From the Map"]
    end
    subgraph sec_post["3 - POST TO SLACK"]
        direction TB
        build["4 - Build the Message"]
        kind{"5 - Card Update or File Upload?"}
        post_card["6 - Post the Card Update to the Team Channel<br/><i>slack</i>"]
        post_file["6b - Post the File Link and Who Uploaded It<br/><i>slack</i>"]
    end
    subgraph sec_reliable["4 - KEEP IT RELIABLE"]
        direction TB
        ok{"7 - Posted OK?"}
        opsalert["8 - Alert Ops That the Post Failed<br/><i>slack</i>"]
        log[("9 - Log Every Notification<br/><i>googleSheets</i>")]
    end
    hook --> map
    map --> pick
    pick --> build
    build --> kind
    kind -->|true| post_card
    kind -->|false| post_file
    post_card --> ok
    post_file --> ok
    ok -->|true| log
    ok -->|false| opsalert
    opsalert --> log
    style sec_events fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_route fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_post fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_reliable fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - TRELLO AND DRIVE EVENTS COME IN** - Two ways in. A Trello card is created or moved to a new list, or a file lands in a watched Drive folder. Make allows one trigger per scenario, so this ships as two scenarios that share everything downstream.
- **2 - ROUTE TO THE RIGHT TEAM CHANNEL** - One table holds team to channel. The board or list name on a Trello card, or the folder name on a Drive file, picks the arm. Anything unrecognised falls to the default arm so nothing is lost.
- **3 - POST TO SLACK** - The message is built once, then posted into the private channel for that team. Card updates and file uploads read differently, so each gets its own wording and its own link back.
- **4 - KEEP IT RELIABLE** - Every post is checked. A refused post alerts ops instead of vanishing, and every notification lands in an audit sheet so you can prove what fired and when.
