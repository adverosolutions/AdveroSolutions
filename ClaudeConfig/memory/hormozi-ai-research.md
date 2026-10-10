---
name: hormozi-ai-research
description: "Proposed 2026-10-06 - scrape Hormozi's AI/automation videos (last 6 months, incl. clip channels) into offers + positioning rules for AI agency campaigns; feasibility probe results"
metadata:
  node_type: memory
  type: project
  originSessionId: 96fcd179-fe7e-4700-bfa7-c9bdb00a64e3
  modified: 2026-10-07T00:46:13.981Z
---

Lorenzo asked (2026-10-06) to mine every Alex Hormozi video from the last 6 months that talks about AI/automation, including his smaller and clip channels, into a big list of offers and positioning rules he can plug into AI-agency cold campaigns ([[ai-agents-cold-pivot]]).

Feasibility probe (2026-10-06, window since 2026-04-06):
- @AlexHormozi: 31 long videos, 16 streams, ~917 shorts. @MoreMozi is his OFFICIAL second channel (148K subs, bio "Founder Acquisition.com, Co-Founder Skool.com"): ~1,893 long clips, ~3,900 shorts. @mozi-digest and @HormoziClips are unofficial fan reposts.
- About 80 titles name AI outright. Transcript sample: 7/12 main videos, 5/6 streams, 3/13 MoreMozi clips mention AI, so roughly 400-600 long pieces carry real AI content.
- youtube-transcript-api works, but YouTube IP-blocked the laptop after ~30 fetches at 1.5 s spacing. Local yt-dlp is stuck at 2025.10.14 (Python 3.9) and cannot read per-video metadata; upload dates come from the watch-page HTML instead.
- Paid transcript routes: Supadata Pro listed at $17 for 3,000 transcripts, which covers every long video plus main-channel shorts. Apify transcript actors are listed at about $2-7 per 1,000. See [[apify-free-plan-api-gate]] before relying on Apify.

- Lorenzo declined the $17 (2026-10-06), so plan the free route. The Game podcast RSS (https://rss2.flightcast.com/zz5nwp81tktx53wb8fw6qq7j.xml) has 49 episodes in the window, about 14 h of audio, mirroring the main channel's long videos; 5 titles are AI-specific (Ep 963, 968, 976, 982, 993). Transcribe locally with whisper.cpp (brew; the Mac is an M5 Pro), so no YouTube block applies. The IP block was still on about an hour later. Other free routes: a throttled fetcher for the 16 streams and AI-titled clips, and Apify's free monthly credit (UI run) for a full MoreMozi sweep.

- Lite test DONE 2026-10-06 for $0: 26 pieces (5 AI podcast eps + 21 AI-titled clips), whisper.cpp large-v3-turbo-q5 on the M5 Pro (~7.5 min for all), 2 Sonnet extractors (169 ideas), Opus merge, reviewer APPROVE after one fix round (a co-host's lines had been credited to Hormozi). Result is the Claude Doc "Hormozi on Selling AI: Playbook (lite test)": https://claude.ai/code/artifact/74198b3a-d961-4a68-bcc6-0b0cbb050db1 . It has 10 rules, 15 offers and 15 angles. Working files are in the madtom worktree under .tmp/hormozi_ai/ (sources.tsv, text/, extract/, playbook.md), and the scripts are in that session's scratchpad. yt-dlp from brew downloads YouTube audio fine even while the transcript endpoint is IP-blocked.

- 2026-10-06: added a "Grand Slam Offers" tab to the same doc with all 15 offers rebuilt as grand slam offers. Each covers the name, pitch, who, dream outcome, stack table, bonuses, guarantee, scarcity and urgency, price shape, proof and built-on, and the tab opens with an index table. It took 3 rounds of review: the recruiting guarantee is 180 days, not 90; there is no phone answering; and seasonal guarantees are measured as rates. Open decisions for Lorenzo are every [n] placeholder, and the new money back plus $200 gift card guarantees on offers that offers.md doesn't have. The source files are in .tmp/hormozi_ai/gso/.

**Why:** Hormozi's views are opinion, not proof. Per [[offer-intel]], nothing mined here counts as proof in Lorenzo's copy, and proof still comes only from config/offers.md.
**How to apply:** if he says go, pay for transcripts only after he approves the spend. The extraction is workflow-sized, so it needs his explicit workflow go-ahead and a test slice first. Keep transcripts in .tmp/, and write the outputs as paraphrased rules with video links and timestamps.
