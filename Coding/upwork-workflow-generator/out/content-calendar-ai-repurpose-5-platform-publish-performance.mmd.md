# Content Calendar → AI Repurpose → 5-Platform Publish → Performance Tracking

```mermaid
flowchart LR
    subgraph sec_queue["1 · CONTENT CALENDAR & QUEUE"]
        direction TB
        trig(["Check for Scheduled Posts Every Hour"])
        pull_calendar[("Pull Posts Due to Publish from the Content Calendar<br/><i>airtable</i>")]
        approved_branch{"Post Marked Approved and Ready?"}
    end
    subgraph sec_repurpose["2 · REPURPOSE FOR EACH PLATFORM"]
        direction TB
        repurpose_agent{{"Repurpose Base Content for Each Platform's Format and Tone"}}
        repurpose_model{{"GPT-4.1<br/><i>openai</i>"}}
    end
    subgraph sec_publish["3 · PUBLISH ACROSS PLATFORMS"]
        direction TB
        fb_post["Publish to Facebook Page<br/><i>facebook</i>"]
        ig_post["Publish to Instagram<br/><i>instagram</i>"]
        tiktok_post["Publish to TikTok<br/><i>tiktok</i>"]
        li_post["Publish to LinkedIn<br/><i>linkedin</i>"]
        tw_post["Publish to X · Twitter<br/><i>twitter</i>"]
        merge_results["Merge Publish Results Across All Platforms"]
    end
    subgraph sec_confirm["4 · CONFIRM & LOG"]
        direction TB
        publish_check{"Every Platform Published Successfully?"}
        log_status[("Log Post URLs and Status Back to the Calendar<br/><i>airtable</i>")]
        alert_fail["Alert: Publish Failed on One or More Platforms<br/><i>slack</i>"]
    end
    subgraph sec_track["5 · PERFORMANCE TRACKING"]
        direction TB
        perf_trig(["Daily Performance Pull"])
        fb_insights["Pull Facebook Post Engagement<br/><i>facebook</i>"]
        ig_insights["Pull Instagram Post Engagement<br/><i>instagram</i>"]
        tiktok_insights["Pull TikTok Video Metrics<br/><i>tiktok</i>"]
        li_insights["Pull LinkedIn Post Metrics<br/><i>linkedin</i>"]
        tw_insights["Pull X · Twitter Post Metrics<br/><i>twitter</i>"]
        aggregate_perf["Aggregate Likes, Comments, Shares, and Clicks by Post"]
        write_perf[("Write Performance Data Back to the Calendar<br/><i>airtable</i>")]
    end
    trig --> pull_calendar
    pull_calendar --> approved_branch
    approved_branch -->|true| repurpose_agent
    repurpose_agent --> fb_post
    repurpose_agent --> ig_post
    repurpose_agent --> tiktok_post
    repurpose_agent --> li_post
    repurpose_agent --> tw_post
    fb_post --> merge_results
    ig_post --> merge_results
    tiktok_post --> merge_results
    li_post --> merge_results
    tw_post --> merge_results
    merge_results --> publish_check
    publish_check -->|true| log_status
    publish_check -->|false| alert_fail
    perf_trig --> fb_insights
    perf_trig --> ig_insights
    perf_trig --> tiktok_insights
    perf_trig --> li_insights
    perf_trig --> tw_insights
    fb_insights --> aggregate_perf
    ig_insights --> aggregate_perf
    tiktok_insights --> aggregate_perf
    li_insights --> aggregate_perf
    tw_insights --> aggregate_perf
    aggregate_perf --> write_perf
    repurpose_model -.- repurpose_agent
    style sec_queue fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_repurpose fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_publish fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_confirm fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_track fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · CONTENT CALENDAR & QUEUE** — Checks the calendar every hour for posts due to go out, and only touches ones marked approved.
- **2 · REPURPOSE FOR EACH PLATFORM** — One base piece of content gets reshaped into each platform's own format and tone before anything publishes.
- **3 · PUBLISH ACROSS PLATFORMS** — Fans out to all five platforms in parallel so one slow API doesn't hold up the others.
- **4 · CONFIRM & LOG** — Every publish result gets checked before the calendar is updated, so a silent failure never gets logged as a success.
- **5 · PERFORMANCE TRACKING** — Pulls engagement daily from every platform and writes it straight back to the same calendar record.
