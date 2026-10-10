---
name: upwork-only-the-job-post
description: Upwork builds, beats and proposals use only what the job post says; never the client's hiring history, reviews, company or names from reviews
metadata:
  type: feedback
---

Everything a client sees (build title, labels, sticky, samples, beats, proposal greeting) comes from the job post alone. No company, industry, tool or first name that the post doesn't state, even when the hiring history or freelancer reviews make it obvious. History can inform the private assessment only. When the post names no tool, commit to the common default (HubSpot, Postgres), not the one their history shows.

**Why:** 2026-09-25 the database-agent build was titled "your Lendersa database" and greeted "Moshon", both pulled from past job titles and a 2023 review. Lorenzo: "We don't want to use anything that's not in their job post because we're just generating everything off the job post." He couldn't pronounce the name and the client never mentioned it.

**How to apply:** `_AGENT_BRIEF.md` "Only the job post" section and SKILL.md. Batch step 1 writes `client first name:` only from the post's signature or when Lorenzo gives it. Supersedes the review-name part of [[upwork-quality-overhaul-2026-09]] client intel.

Same day: match the post's own wording on the build too. Don't add buzzwords the post didn't use ("agents" on the PI chart): "people have good or bad knowledge of those... we should just match the wording of the post."
