# Eric Nowoslawski — Caption scrape complete

**Date:** 2026-09-28 22:52 CDT  
**Channel:** https://www.youtube.com/@ericnowoslawski  
**Window:** last 12 months (`index/videos_12mo.csv`)  
**Status:** **COMPLETE**  
**Claude distill:** NOT run (per Lorenzo)

## Counts

| Metric | Value |
|--------|-------|
| Total videos (12mo index) | **51** |
| Captions OK (VTT present) | **51** / 51 |
| Transcripts written | **51** / 51 |
| Failures (final) | **0** |
| Tiny/suspicious transcripts (<200B) | **0** |

## Failures (ids + reason)

_None. All 51 videos have captions and clean transcripts._

## Disk used

```
5.4M   ~/advero/knowledge/eric-nowalski/   (tree total, du -sh)
4.1M   raw/subs/                          (93 VTT files)
1.1M   transcripts/                       (51 .txt + meta)
112K   index/
```

## Notes

- First attempt (default web client) hit YouTube bot-check on all 40 remaining; zero new files.
- Retried with `yt-dlp --extractor-args youtube:player_client=android` — **40/40 OK**.
- Script `01_download_subs.sh` updated permanently to use android client + 1.5s pacing.
- Converted via `02_vtt_to_transcript.py` (idempotent; prior 11 smoke transcripts kept).
- Whisper **not** installed. `04_distill_claude.sh` **not** run.

## Paths

- Base: `~/advero/knowledge/eric-nowalski/`
- Subs: `~/advero/knowledge/eric-nowalski/raw/subs/`
- Transcripts: `~/advero/knowledge/eric-nowalski/transcripts/`
- Index: `~/advero/knowledge/eric-nowalski/index/videos_12mo.csv`
- This handoff: `~/advero/state/handoffs/20260928_eric_nowalski_scrape_done.md`

## Next (ask Lorenzo)

Run Claude Code distill in batches: `./scripts/04_distill_claude.sh` (burns Max quota).
