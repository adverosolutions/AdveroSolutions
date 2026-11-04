#!/usr/bin/env python3
"""Distill Eric Nowoslawski transcripts via Claude Code CLI (Max subscription).
Leave ANTHROPIC_API_KEY unset. Idempotent: skips batches whose output already exists.
"""
from __future__ import annotations
import csv, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TDIR = ROOT / "transcripts"
PDIR = ROOT / "playbooks"
META = ROOT / "index" / "videos_12mo.csv"
LOGDIR = ROOT / "logs"
BATCH_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 5

PROMPT_HEADER = """You are distilling Eric Nowoslawski (Growth Engine X) cold-email YouTube content into reusable playbooks for AdveroSolutions (Lorenzo Villarreal / Instantly outbound).

From the transcript(s) below, extract ONLY actionable systems Copywriter and Lorenzo can reuse. Structure as markdown with these sections (omit empty ones):
1. Frameworks / mental models
2. Copy formulas (subject, first line, body, CTA, follow-up) — quote short examples
3. Offer / angle patterns
4. List-building & enrichment tactics (Clay, signals, scrapes, Apollo, etc.)
5. Deliverability / inbox infra notes
6. Metrics & testing cadence
7. Tools mentioned (with how used)
8. Caveats / dated claims to re-validate

Rules:
- Be concise. Prefer bullets, checklists, and fill-in templates over prose.
- Tag every item with source video id(s) like [id].
- Do NOT invent stats. If a number is claimed, quote it and note the video id.
- Start with a one-line "# Playbook batch: <short theme>" title synthesizing the batch.
- End with "## Source videos" listing id — title for each input.
"""

def main():
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + path

    PDIR.mkdir(parents=True, exist_ok=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(open(META)))
    # newest-first as in CSV; keep that order for batching
    titles = {r["id"]: r["title"] for r in rows}
    ordered = [r["id"] for r in rows]
    # only those with transcripts
    vids = [v for v in ordered if (TDIR / f"{v}.txt").exists() and (TDIR / f"{v}.txt").stat().st_size > 50]
    print(f"transcripts_ready={len(vids)} batch_size={BATCH_SIZE}")

    batches = [vids[i:i+BATCH_SIZE] for i in range(0, len(vids), BATCH_SIZE)]
    results = []
    for bi, batch in enumerate(batches, 1):
        tag = f"batch_{bi:02d}_of_{len(batches):02d}"
        outfile = PDIR / f"playbook_{tag}.md"
        manifest = PDIR / f"playbook_{tag}.sources.json"
        # skip if already good
        if outfile.exists() and outfile.stat().st_size > 500:
            print(f"[skip] {outfile.name} exists ({outfile.stat().st_size}B)")
            results.append({"batch": bi, "ids": batch, "file": outfile.name, "status": "skipped"})
            continue

        parts = [PROMPT_HEADER, ""]
        for vid in batch:
            parts.append(f"===== VIDEO {vid} — {titles.get(vid,'')} =====\n")
            parts.append((TDIR / f"{vid}.txt").read_text(encoding="utf-8", errors="replace"))
            parts.append("\n")
        prompt = "\n".join(parts)
        prompt_path = LOGDIR / f"distill_prompt_{tag}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        err_path = LOGDIR / f"distill_{tag}.err"
        print(f"[claude] {tag} ids={batch} prompt_chars={len(prompt)} -> {outfile.name}")
        t0 = time.time()
        cmd = [
            "claude", "-p", prompt,
            "--model", "opus",
            "--tools", "",
            "--no-session-persistence",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                env=os.environ.copy(), stdin=subprocess.DEVNULL,
            )
            elapsed = time.time() - t0
            err_path.write_text((proc.stderr or "") + f"\n---rc={proc.returncode} elapsed={elapsed:.1f}s---\n", encoding="utf-8")
            out = (proc.stdout or "").strip()
            if proc.returncode != 0 or len(out) < 200:
                print(f"[fail] {tag} rc={proc.returncode} out_len={len(out)} elapsed={elapsed:.1f}s")
                print((proc.stderr or proc.stdout or "")[:400])
                # leave partial for inspection
                if out:
                    outfile.write_text(out + "\n", encoding="utf-8")
                results.append({"batch": bi, "ids": batch, "file": outfile.name, "status": "failed",
                                "rc": proc.returncode, "elapsed": elapsed, "out_len": len(out)})
                continue
            # prepend source header for traceability
            header = (
                f"<!-- distill: {tag} | videos: {', '.join(batch)} | "
                f"model: opus | elapsed_s: {elapsed:.0f} -->\n\n"
            )
            outfile.write_text(header + out + "\n", encoding="utf-8")
            manifest.write_text(json.dumps({"batch": bi, "ids": batch,
                "titles": {v: titles.get(v) for v in batch},
                "elapsed_s": round(elapsed,1), "chars": len(out)}, indent=2), encoding="utf-8")
            print(f"[ok] {outfile.name} ({len(out)} chars, {elapsed:.1f}s)")
            results.append({"batch": bi, "ids": batch, "file": outfile.name, "status": "ok",
                            "elapsed": elapsed, "chars": len(out)})
        except subprocess.TimeoutExpired:
            print(f"[fail] {tag} TIMEOUT")
            results.append({"batch": bi, "ids": batch, "file": outfile.name, "status": "timeout"})
        except Exception as e:
            print(f"[fail] {tag} {e}")
            results.append({"batch": bi, "ids": batch, "file": outfile.name, "status": "error", "error": str(e)})

        # polite pause between batches
        time.sleep(2)

    summary = {
        "batch_size": BATCH_SIZE,
        "n_batches": len(batches),
        "n_videos": len(vids),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": sum(1 for r in results if r["status"] not in ("ok", "skipped")),
        "results": results,
    }
    (LOGDIR / "distill_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n_batches","n_videos","ok","skipped","failed")}, indent=2))
    return 0 if summary["failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
