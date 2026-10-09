# Assessment (private)

## Time
- Recruiting agent v0.1 (Vapi assistant + question bank + follow-up rule, post-call webhook to n8n, Claude scoring against a rubric sheet, row + Slack summary): 5-8 real hours including 3 test calls, so it can honestly ship in one working day; the "4 hours" framing holds for the build, not the rubric tuning.
- v0.2 (rubric tuned on 10 real interviews, per-role question banks, ATS hand-off): another 6-10 hours over week 2.
- Each next agent (content/research, ad creative, market research, performance, ops): 4-12 hours to v0.1 each. Full-time ongoing: realistic 20-40 h/week retainer.

## Likelihood
- High for v0.1. Vapi and Retell both give transcripts and end-of-call webhooks; Claude scoring a transcript to JSON is reliable.
- Risks: voice latency and interruptions with non-native English speakers (German market; may need German-language interviews, check Vapi voice/transcriber for German); candidate consent and GDPR for recording and AI evaluation in Germany (EU AI Act classes recruitment AI as high-risk: human decision must stay final, candidates informed). Scorecard must be decision support, never auto-reject.
- Unverified for Lorenzo: he has not shipped a Vapi/Retell voice agent in production per the facts list; frame as "the stack I'd use", not a past project. Question 1 of the post asks for real projects and links; Lorenzo's own outbound agent (100k+ emails/month, agent-researched messages) is the honest answer.

## Standard pricing
- Market for pragmatic AI agent builders: $60-120/h freelance; $4k-10k/month retainers for part-time embedded builders. Post's recorded bids avg $33.07 (basis unspecified), far under market; client says ongoing and full-time.
- Recurring software: Vapi about $0.05-0.15/min all-in with LLM and voice; Claude API cents per scorecard; n8n cloud from about $24/mo or self-hosted.

## Pricing path (Lorenzo only)
- Value (assumption): first-round screening across their ventures at 8 h/week of founder/hiring-manager time at EUR 80/h = about EUR 33k/yr for recruiting alone; the five other agent categories plausibly 3-5x that. Call it EUR 100k+/yr of time across the studio (assumption).
- Price range: 10-20% of EUR 100k = EUR 10k-20k/yr, i.e. about EUR 1k-1.7k/month minimum; a real full-time retainer sits above that on hours.
- Land offer (milestone 1): recruiting agent v0.1 live on one real role in a week, with the teach-us doc and a walkthrough recording.
- Upsell: monthly agent retainer, one new v0.1 agent every 1-2 weeks plus improvement passes on the live ones.
- Milestones: 1) 25% paid once the recruiting v0.1 (voice interview, scorecard sheet, docs) is delivered and you've signed off; 2) 25% paid once v0.2 tuned on 10 real interviews is delivered and you've signed off; 3) 25% paid once the second agent v0.1 (content & research) is delivered and you've signed off; 4) 25% paid once the third agent v0.1 and the "build the next one" playbook are delivered and you've signed off.

## Ask before quoting
- Interview language(s): German, English, both?
- Which roles first, and do rubrics already exist?
- Where candidates come from and where scorecards should land (ATS? Sheet? Notion?)
- Voice tool already paid for (Vapi, Retell, ElevenLabs agents)?
- Weekly hours expected for "full time"; who on their side learns the builds?

## Flags
- Full-time, ongoing: pitch as a retainer.
- Post wants answers to 5 questions and links to real projects; no generic cover letter.
- GDPR / EU AI Act on automated candidate evaluation: keep a human decision on screen (the prototype's recommendation says "for the hiring manager").
- Client first name and company unknown.
