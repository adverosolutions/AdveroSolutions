# Your Product and Service Update Email System in GoHighLevel

```mermaid
flowchart LR
    subgraph sec_draft["1 - YOUR ROUGH DRAFT IN"]
        direction TB
        copy["1 - Your Rough Draft Copy Comes In"]
        goal["2 - Set the Goal: The One Thing Readers Should Do Next"]
    end
    subgraph sec_design["2 - DESIGN: STRUCTURE AND BRAND KIT"]
        direction TB
        structure["3 - Structure the Update: Headline, Update Cards, One Button"]
        brand["4 - Apply Your Brand Kit: Colors, Fonts, Logo, Saved Header and Footer"]
    end
    subgraph sec_build["3 - BUILD AND TEST IN GOHIGHLEVEL"]
        direction TB
        build["5 - Build It in the GoHighLevel Email Builder With Merge Fields"]
        test["6 - Test Sends to Gmail, Outlook and iPhone, Mobile and Dark Mode"]
        passes{"7 - Looks Right in Every Inbox?"}
        fix["7a - Fix What Broke and Re-Test"]
    end
    subgraph sec_send["4 - SAVE, SEND AND LEARN"]
        direction TB
        save["8 - Save as a Reusable Template for the Next Update"]
        schedule["9 - Send or Schedule to the Right Smart List or Tag"]
        learn["10 - Check Opens and Clicks, Feed Them Into the Next Update"]
    end
    copy --> goal
    goal --> structure
    structure --> brand
    brand --> build
    build --> test
    test --> passes
    passes -->|false| fix
    fix -.-> test
    passes -->|true| save
    save --> schedule
    schedule --> learn
    style sec_draft fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_design fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_build fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_send fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - YOUR ROUGH DRAFT IN** - You send the copy the way it comes out, plus the one thing the update should get people to do. Nothing in your draft gets lost on the way to the finished email.
- **2 - DESIGN: STRUCTURE AND BRAND KIT** - The update is broken into sections people can scan in seconds, then dressed in your colors, fonts and logo. The header and footer are saved once in GoHighLevel, so every future update starts on brand.
- **3 - BUILD AND TEST IN GOHIGHLEVEL** - Built in the GoHighLevel email builder with your merge fields, then test sends to Gmail, Outlook and an iPhone, checked on mobile and in dark mode. Nothing goes out until it looks right everywhere.
- **4 - SAVE, SEND AND LEARN** - Saved as a reusable template, sent or scheduled to the right smart list or tag, and the opens and clicks shape the next update.
