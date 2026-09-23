# Content Calendar → Multi-Platform Publish → Performance Tracking

```mermaid
flowchart LR
    subgraph sec_queue["1 · CONTENT CALENDAR & QUEUE"]
        direction TB
        trig(["Check for Scheduled Posts Every Hour"])
        pull_calendar[("Pull Posts Due to Publish from the Content Calendar<br/><i>airtable</i>")]
        approved_branch{"Post Marked Approved and Ready?"}
    end
    subgraph sec_publish["2 · PUBLISH ACROSS PLATFORMS"]
        direction TB
        fb_post["Publish to Facebook Page<br/><i>facebook</i>"]
        tw_post["Publish to X · Twitter<br/><i>twitter</i>"]
        merge_results["Merge Publish Results Across Platforms"]
    end
    subgraph sec_confirm["3 · CONFIRM & LOG"]
        direction TB
        publish_check{"Every Platform Published Successfully?"}
        log_status[("Log Post URLs and Status Back to the Calendar<br/><i>airtable</i>")]
        alert_fail["Alert: Publish Failed on One or More Platforms<br/><i>slack</i>"]
    end
    subgraph sec_track["4 · PERFORMANCE TRACKING"]
        direction TB
        perf_trig(["Daily Performance Pull"])
        fb_insights["Pull Facebook Post Engagement<br/><i>facebook</i>"]
        tw_insights["Pull X · Twitter Post Metrics<br/><i>twitter</i>"]
        aggregate_perf["Aggregate Likes, Comments, Shares, and Clicks by Post"]
        write_perf[("Write Performance Data Back to the Calendar<br/><i>airtable</i>")]
    end
    trig --> pull_calendar
    pull_calendar --> approved_branch
    approved_branch -->|true| fb_post
    approved_branch -->|true| tw_post
    fb_post --> merge_results
    tw_post --> merge_results
    merge_results --> publish_check
    publish_check -->|true| log_status
    publish_check -->|false| alert_fail
    perf_trig --> fb_insights
    perf_trig --> tw_insights
    fb_insights --> aggregate_perf
    tw_insights --> aggregate_perf
    aggregate_perf --> write_perf
    style sec_queue fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_publish fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_confirm fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_track fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · CONTENT CALENDAR & QUEUE** — Checks the calendar every hour for posts due to go out, and only touches ones marked approved.
- **2 · PUBLISH ACROSS PLATFORMS** — Fans out to each platform in parallel so one slow API doesn't hold up the others.
- **3 · CONFIRM & LOG** — Every publish result gets checked before the calendar is updated, so a silent failure never gets logged as a success.
- **4 · PERFORMANCE TRACKING** — Pulls engagement daily and writes it straight back to the same calendar record.
