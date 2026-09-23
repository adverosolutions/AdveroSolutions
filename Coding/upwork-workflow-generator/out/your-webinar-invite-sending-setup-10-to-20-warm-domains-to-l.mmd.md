# Your Webinar Invite Sending Setup - 10 to 20 Warm Domains to Login

```mermaid
flowchart LR
    subgraph sec_scope["1 - SIZE IT FROM YOUR LIST"]
        direction TB
        size["1 - Count the List and Pick the Send-By Date"]
        count["2 - Work Out Domains and Mailboxes: 30 a Day Each, 3 per Domain"]
    end
    subgraph sec_list["2 - CLEAN THE OLD LIST FIRST"]
        direction TB
        verify_list["3 - Verify Every Address on the Old List"]
        clean{"4 - Deliverable?"}
        park["4b - Bounces and Catch-Alls Split Out, Never Loaded"]
    end
    subgraph sec_provision["3 - DOMAINS AND MAILBOXES, NEVER YOUR MAIN DOMAIN"]
        direction TB
        rush{"5 - Webinar Date Close?"}
        prewarmed["5a - Pre-Warmed Mailboxes So Invites Go Out This Week"]
        buy["6 - Provision 10 to 20 Lookalike Domains and Their Mailboxes on Your Card"]
    end
    subgraph sec_dns["4 - AUTHENTICATION THAT KEEPS YOU OUT OF SPAM"]
        direction TB
        dns["7 - Publish SPF, DKIM, DMARC, MX and a Tracking Domain"]
        check{"8 - Every Record Passes?"}
        fix["8b - Fix the Failing Record and Re-Check"]
    end
    subgraph sec_handover["5 - INSTANTLY IN YOUR NAME, THEN YOUR LOGIN"]
        direction TB
        import["9 - Import Every Mailbox Into Your Instantly Workspace"]
        warm["10 - Warmup On, Limits Ramped, One Unibox for Replies"]
        login["11 - Your Login: Paste the List and the Sequence, Press Send"]
    end
    size --> count
    count --> verify_list
    verify_list --> clean
    clean -->|true| rush
    clean -->|false| park
    rush -->|true| prewarmed
    prewarmed --> buy
    rush -->|false| buy
    buy --> dns
    dns --> check
    check -->|false| fix
    fix -.-> dns
    check -->|true| import
    import --> warm
    warm --> login
    style sec_scope fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_list fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_provision fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_dns fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_handover fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - SIZE IT FROM YOUR LIST** - The list size and how fast you want the invites out decide the domain and mailbox count. 30 a day per mailbox, 3 mailboxes per domain, so 10 to 20 domains is 30 to 60 mailboxes and 900 to 1,800 invites a day once warm.
- **2 - CLEAN THE OLD LIST FIRST** - An old list is the fastest way to burn 20 new domains. Every address is verified before it is loaded, bounces and catch-alls are split out, and the clean list is what goes in.
- **3 - DOMAINS AND MAILBOXES, NEVER YOUR MAIN DOMAIN** - Lookalike sending domains and their mailboxes are provisioned together through a mailbox provider on your account and your card, about $3 to $4 per mailbox a month. Pre-warmed mailboxes if the webinar date is close.
- **4 - AUTHENTICATION THAT KEEPS YOU OUT OF SPAM** - SPF, DKIM, DMARC, MX and a custom tracking domain on every sending domain, verified before a single invite goes out.
- **5 - INSTANTLY IN YOUR NAME, THEN YOUR LOGIN** - Every mailbox imported into an Instantly workspace you own, warmup running, limits ramped, one unibox for replies. You get the login, paste the list and the sequence, and press send.
