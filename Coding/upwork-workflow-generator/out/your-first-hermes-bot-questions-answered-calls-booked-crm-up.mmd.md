# Your First Hermes Bot: Questions Answered, Calls Booked, CRM Updated

```mermaid
flowchart LR
    subgraph sec_build["1 - THE BOT TALKS TO STUDENTS AND PARENTS"]
        direction TB
        ask["1 - A student or parent asks the bot a question on your website or social page"]
        answer["2 - The bot answers from your own program details, dates and prices"]
        qual["3 - It asks a few questions to learn the student's grade, goals and start date"]
        human{"4 - Does the question need a real person, like a complaint or a special case?"}
        handoff["4b - If it does, the bot hands the chat to your team and tells them why"]
    end
    subgraph sec_connect["2 - CONNECTED TO YOUR TOOLS"]
        direction TB
        book["5 - If not, the bot offers a call or the next enrollment step and books it"]
        crm["6 - The lead and the full chat are sent to your CRM by webhook"]
        notify["7 - Your team gets a notification with the details they need for the call"]
    end
    subgraph sec_test["3 - TESTED BEFORE LAUNCH, KEPT RUNNING AFTER"]
        direction TB
        test["8 - Before launch, I run test chats through every path and fix what breaks"]
        keep["9 - After launch, I update the bot as your programs and dates change"]
    end
    ask --> answer
    answer --> qual
    qual --> human
    human -->|Yes| handoff
    human -->|No| book
    handoff --> crm
    book --> crm
    crm --> notify
    notify --> test
    test --> keep
    style sec_build fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_connect fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_test fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 - THE BOT TALKS TO STUDENTS AND PARENTS** - The bot answers from your own information and learns what each family needs. Anything sensitive goes straight to a person.
- **2 - CONNECTED TO YOUR TOOLS** - Every conversation ends in a booked next step, and the lead lands in your CRM so nobody retypes it.
- **3 - TESTED BEFORE LAUNCH, KEPT RUNNING AFTER** - You asked for someone who tests their own work, so every path gets tested first, and the bot is kept up to date as things change.
