# Private assessment, job 6 (10 AM batch 2026-10-22, U-024)
- Client: unnamed B2B outbound operation; no name in post. Personalization omitted (U-006 fallback "your team"). INDEX.csv: no match.
- Tools named: Instantly, Smartlead, lemlist, Apollo, Clay, custom SMTP, n8n (nice to have). No Instantly/Smartlead adapter exists, so no native sending-tool screen. Mechanism shown on n8n (named in post, supported adapter); audit and plan shown on the explicitly custom workbench.
- Approved facts used: 100k+ cold emails a month on Instantly, agent researching each message, Apify + MillionVerifier, Zapmail mailboxes and lookalike domains, Instantly API wired to Claude, works daily in n8n, DFW Central Time. Never the Zapmail price.
- NOT claimable: the post's "10M+ outbound emails sent" requirement, "hundreds of domains/mailboxes", dashboards/references. Lorenzo must supply or leave out.
- Opener "finished and connected" / "The build is done" overstates a consulting audit shown on sample data: kept locked line, flagged for Lorenzo.

## Scene map (default 2-minute route)
1. n8n morning inbox check (~45s). Purpose: show the monitoring mechanism from the plan. New fact: every inbox's bounce/spam numbers are pulled and scored daily; sample domain northpeak.example goes over the agreed 2% bounce limit and is held. Evidence: n8n canvas true branch to Slack alert, false branch to KPI sheet inactive.
2. Audit finding AUD-07 (~35s). Purpose: written audit with prioritized issues. New fact: why the domain failed (DMARC p=none, warm-up stopped, unverified list, 60/day per inbox) and the fix. Evidence: workbench record with setup snapshot and fix fields.
3. Infrastructure plan + KPI dashboard (~30s, required proof). New fact: domains/mailboxes/volume ramp plan and dashboard KPIs. Evidence: workbench outcome with stages Audit to Monitor and metrics.
Close: three directional KPIs from the post (inbox placement, bounce+complaints, positive replies), 15-minute call.
