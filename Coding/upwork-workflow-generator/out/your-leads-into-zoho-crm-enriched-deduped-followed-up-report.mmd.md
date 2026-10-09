# Your Leads Into Zoho CRM: Enriched, Deduped, Followed Up, Reported

```mermaid
flowchart LR
    subgraph sec_capture["1 - CAPTURE LEADS FROM YOUR ADS AND WEBSITE FORMS"]
        direction TB
        hook(["1 - New Lead From Your Ads or Website Form"])
    end
    subgraph sec_enrich["2 - ENRICH EACH LEAD THROUGH APOLLO"]
        direction TB
        apollo["2 - Apollo: Enrich With Job Title, Company and Website"]
    end
    subgraph sec_zoho["3 - ROUTE INTO ZOHO CRM: FIELD MAPPING AND DEDUP"]
        direction TB
        upsert["3 - Zoho CRM: Match by Email or Phone, Then Create or Update"]
        isnew{"4 - New to Zoho CRM?"}
    end
    subgraph sec_follow["4 - FOLLOW-UP SEQUENCE: EMAIL NOW, TEXT NEXT DAY"]
        direction TB
        email1["5 - Gmail: Send Email 1 Within a Minute<br/><i>gmail</i>"]
        wait["6 - Wait 1 Day"]
        status["7 - Zoho CRM: Check the Lead Status"]
        notyet{"8 - Not Contacted Yet and Has a Phone?"}
        sms["9 - Twilio: Send the Next-Day Text<br/><i>twilio</i>"]
    end
    subgraph sec_report["5 - REPORT: LEAD VOLUME AND CONVERSION BY SOURCE"]
        direction TB
        monday(["10 - Every Monday Morning"])
        pull["11 - Zoho CRM: Pull Leads, Converted Ones Included"]
        count["12 - Count Leads and Conversions by Source"]
        dash[("13 - Google Sheets: Refresh Your Lead Dashboard<br/><i>googleSheets</i>")]
    end
    hook --> apollo
    apollo --> upsert
    upsert --> isnew
    isnew -->|true| email1
    email1 --> wait
    wait --> status
    status --> notyet
    notyet -->|true| sms
    monday --> pull
    pull --> count
    count --> dash
    style sec_capture fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_enrich fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_zoho fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_follow fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_report fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - CAPTURE LEADS FROM YOUR ADS AND WEBSITE FORMS** - Your website and ad landing-page forms post every lead to one webhook, carrying the UTM tag your Google and Facebook ads add. That tag becomes the lead's source in Zoho. A form that drops the tag files the lead as Website, and your by-source report goes flat.
- **2 - ENRICH EACH LEAD THROUGH APOLLO** - Apollo looks the lead up by work email and adds job title, company, website and location. No match, and the lead carries on without them.
- **3 - ROUTE INTO ZOHO CRM: FIELD MAPPING AND DEDUP** - Every field maps to your Zoho CRM lead layout, and Zoho checks email, then phone, before it writes. New leads are created; returning ones are updated and skip the follow-up.
- **4 - FOLLOW-UP SEQUENCE: EMAIL NOW, TEXT NEXT DAY** - Email 1 goes from your Gmail within a minute, BCC'd to Zoho so it shows on the lead. The next day a text goes out, only if Zoho still shows them not contacted.
- **5 - REPORT: LEAD VOLUME AND CONVERSION BY SOURCE** - Every Monday your Lead Dashboard tab refreshes from Zoho: leads, converted leads and conversion rate per source for the last 30 days.
