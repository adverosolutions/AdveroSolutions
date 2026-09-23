# Fleet Notes to Structured Records Pipeline - Milestone 1 and 3

```mermaid
flowchart LR
    subgraph sec_intake["1 - NOTE INTAKE"]
        direction TB
        hook_note(["1 - Voice or Text Note From Dispatcher or Driver"])
        is_audio{"2 - Is This an Audio Recording?"}
        whisper["3 - Whisper: Turn the Recording Into Text"]
        normalize["4 - Clean the Note and Attach Truck, Driver and Date"]
    end
    subgraph sec_extract["2 - EXTRACT AND VALIDATE"]
        direction TB
        extract{{"5 - Extraction Model, Cheap: Note Into Structured JSON"}}
        extract_model{{"Provider Adapter: Anthropic / OpenAI / Google<br/><i>anthropic</i>"}}
        extract_parser{{"Force the Schema: Loads, Expenses, Driver Events, Broker Contacts, Maintenance"}}
        validate["6 - Check the JSON Against the Record Schema"]
        is_valid{"7 - Did It Come Back Valid?"}
        repair["8 - Send It Back With a Repair Prompt, Twice at Most"]
    end
    subgraph sec_save["3 - SAVE AND REVIEW"]
        direction TB
        save_record[("9 - Save the Record, Row Locked to That Fleet<br/><i>supabase</i>")]
        respond["10 - Hand the Record to the Review Screen"]
    end
    subgraph sec_loads["4 - LOAD PARSER AND SCORING"]
        direction TB
        hook_board(["11 - Raw Load-Board Text Pasted In"])
        parse_loads{{"12 - Extraction Model: Pull the Loads Out of Messy Text"}}
        loads_parser{{"Force One Row per Load: Pickup, Drop, Rate, Miles, Vehicles"}}
        score["13 - Score Revenue per Mile, Deadhead, 9-Car Unit and Weight Limits"]
        combine["14 - Pick the Best Legal Combination for Each Truck"]
        card{{"15 - Synthesis Model, Larger: Write the HTML Load Card"}}
        card_model{{"Provider Adapter: Same Interface, Bigger Model<br/><i>anthropic</i>"}}
        save_loads[("16 - Save the Scored Loads and the Card<br/><i>supabase</i>")]
    end
    subgraph sec_errors["5 - WHEN SOMETHING BREAKS"]
        direction TB
        err(["17 - Any Step Fails, Anywhere<br/><i>n8n</i>"])
        alert["18 - Post the Failure With a Link to the Run<br/><i>slack</i>"]
    end
    hook_note --> is_audio
    is_audio -->|true| whisper
    is_audio -->|false| normalize
    whisper --> normalize
    normalize --> extract
    extract --> validate
    validate --> is_valid
    is_valid -->|true| save_record
    is_valid -->|false| repair
    repair -.-> extract
    save_record --> respond
    hook_board --> parse_loads
    parse_loads --> score
    score --> combine
    combine --> card
    card --> save_loads
    err --> alert
    extract_model -.- extract
    extract_parser -.- extract
    loads_parser -.- parse_loads
    card_model -.- card
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_extract fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_save fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_loads fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_errors fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - NOTE INTAKE** - A dispatcher or driver sends a voice note or a text note. Audio goes through Whisper first, text skips straight ahead.
- **2 - EXTRACT AND VALIDATE** - The cheap model turns the note into JSON. Nothing is trusted until it passes the schema check.
- **3 - SAVE AND REVIEW** - The clean record lands in Supabase and comes back to the review screen for a human to confirm.
- **4 - LOAD PARSER AND SCORING** - Pasted load-board text becomes scored loads, then the best legal combination for each truck, then a load card.
- **5 - WHEN SOMETHING BREAKS** - Every failure is caught and posted with a link to the exact run. Nothing drops silently.
