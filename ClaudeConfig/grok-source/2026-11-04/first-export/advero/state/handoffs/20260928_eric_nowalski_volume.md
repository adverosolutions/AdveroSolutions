# Eric Nowoslawski YouTube — Volume Check (Phase 1)

**Date:** 2026-09-28 (America/Chicago)  
**Prepared for:** Lorenzo Villarreal / AdveroSolutions  
**Phase:** Volume + scaffold + smoke only — **full scrape NOT started**

## Channel confirmed

| Field | Value |
|-------|-------|
| Name | Eric Nowoslawski (Growth Engine X) |
| Handle | `@ericnowoslawski` |
| URL | https://www.youtube.com/@ericnowoslawski |
| Channel ID | `UC6ef5yDFz7gm8rARwX3HaDw` |
| Focus | Cold email / Clay / Instantly / outbound / AI-GTM |

Note: User query spelled “Nowalski”; correct spelling is **Nowoslawski**. LinkedIn: `outboundphd`.

## Last 12 months (upload_date ≥ 2025-09-28)

| Metric | Value |
|--------|-------|
| Video count | **51** |
| Total duration | **10.71 hours** (38,568 sec) |
| Average length | ~12.6 min |
| Window | 2025-10-15 → 2026-09-16 (no uploads 2025-09-28..2025-10-14) |
| Full channel (all time) | 266 videos |

Index files:
- `~/advero/knowledge/eric-nowalski/index/videos_12mo.csv`
- `~/advero/knowledge/eric-nowalski/index/videos_12mo.json`
- `~/advero/knowledge/eric-nowalski/index/videos_all.tsv`

Newest: `gKh33_2MXmA` — “How I Get 100 Positive Replies a Day Using Grokbot” (2026-09-16, ~11m)  
Oldest in window: `V5k2uY9T-Eg` — “Outbound Email Deliverability Update for End of 2025” (2025-10-15, ~11m)

## Caption coverage (estimate)

Sampled **14 / 51** videos (~every 4th + newest 2):

| Type | Coverage |
|------|----------|
| Any captions | **100%** (14/14) |
| Manual subs | 0% in sample |
| Auto captions (incl. English) | **100%** |

**Estimate for full year: ~95–100% usable English auto-captions.** Whisper fallback likely rare/unnecessary. Prefer `--write-auto-subs` / `--write-subs` only (no video).

## Disk / time estimates (full 12-month scrape)

| Path | Estimate |
|------|----------|
| Subs-only (VTT) | **~25–80 MB** total (tiny) |
| Transcripts (txt) | **~5–15 MB** |
| Audio-only fallback (if any) | ~5–10 MB per hour of audio; likely near zero given caps |
| Full video (NOT recommended) | ~5–15 GB — skip |
| Wall time (subs+convert) | **~15–40 min** polite rate (~0.5s sleep + yt-dlp) |
| Whisper (if needed) | ~1× realtime on CPU per missing video |
| Claude distill (51 videos, batches of 5) | ~11 Claude Code sessions; Max quota — **ask before running** |

## Scaffold paths

```
~/advero/knowledge/eric-nowalski/
  README.md
  scripts/
    00_refresh_index.sh
    01_download_subs.sh
    02_vtt_to_transcript.py
    03_whisper_fallback.sh
    04_distill_claude.sh
  index/  raw/subs/  raw/audio/  transcripts/  playbooks/  logs/
```

Deps: `yt-dlp` 2026.08.19 installed (`~/.local/bin`); `ffmpeg` present; `claude` 2.1.282 present; Whisper **not** installed (optional).


## Smoke test result (2026-09-28 CDT)

| Check | Result |
|-------|--------|
| Intent | 1–2 recent short videos (subs → transcript) |
| Actual | Script limit bug + YouTube 429 on dual-lang pulled **11** videos (en-orig still landed); converter produced **11** clean transcripts |
| Target newest | `gKh33_2MXmA` (11m) + `-LjvwKOIH9Y` (8m) — **both OK** |
| Sample quality | Readable English auto-captions; overlapping cue dedupe works |
| Status | **SUCCESS** (path proven). Download script fixed post-smoke (`en-orig` prefer + attempt-based limit + ignore-errors). |
| Distill | **Not run** (Claude Max quota — separate go/no-go) |
| Full year | **Not started** — awaiting Lorenzo go/no-go |

Transcript sample sizes: -LjvwKOIH9Y=10584c, 01jxZN2ZNsc=22204c, 4Kf3CkdvFTY=14403c, Ct4AUtQnIYE=11873c…

Remaining after smoke: ~40 of 51 videos still need subs (idempotent resume).


## Recommended next step (go / no-go)

**GO recommended for full caption scrape** — volume is modest (51 videos / ~11h), captions look universal, disk cost is negligible.

Suggested sequence after Lorenzo approves:
1. `./scripts/01_download_subs.sh` (all 51)
2. `python3 ./scripts/02_vtt_to_transcript.py`
3. Spot-check 3 transcripts for quality
4. **Separate go/no-go** for Claude distill (`04_distill_claude.sh`) — that burns Max quota, not disk

**NO-GO on:** downloading full video files; installing Whisper until a video actually lacks EN captions; running distill across all 51 without a batch plan.
