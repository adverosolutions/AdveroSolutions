#!/usr/bin/env python3
"""Personalize leads row by row, writing each result to the Google Sheet as it
lands so progress is visible live.

  python3 personalize/live_personalize.py <sheet_id> --niche cleaning --limit 5     # test
  python3 personalize/live_personalize.py <sheet_id> --niche all                    # full

Per-row lifecycle in the sheet (column personalization_status):
    ""  ->  "working"  ->  "done" | "skipped" | "error: <why>"
Resumable: rows already "done" are never re-generated. Each row costs one
Claude call; the per-niche prompt lives in personalize/prompts.json so the
offer/angle can be changed without touching code.
"""
import argparse, json, os, sys, time
from datetime import datetime
from pathlib import Path
import anthropic
from sheet_io import open_tab, ROOT

PROMPTS = ROOT / "personalize" / "prompts.json"
MODEL = "claude-opus-5-5"   # every model call runs on Opus 5.5 (Lorenzo, 2026-09-25)
# Opus 5.5 always thinks and rejects temperature/top_p/top_k with a 400. Effort
# is the control ("low" for one short line); thinking counts toward max_tokens,
# so the call gets headroom on top of the reply's 300.
EFFORT = "low"
THINKING_HEADROOM_TOKENS = 1024

BANNED = ["—", "–", " - ", "I hope this finds you", "I came across", "reaching out", "touch base"]


def api_key() -> str:
    for envf in (ROOT / ".env", ROOT.parents[1] / "Agentic Worklfows" / ".env"):
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("ANTHROPIC_API_KEY", "") or sys.exit("ANTHROPIC_API_KEY not found")


def generate(client, prompt_cfg: dict, lead: dict) -> tuple:
    ctx = {k: (lead.get(k) or "") for k in
           ["first_name", "company_name", "job_title", "city", "state", "company_size",
            "company_description", "company_technologies", "headline", "industry", "company_website"]}
    user = prompt_cfg["user"].format(**ctx)
    r = client.messages.create(model=MODEL, max_tokens=300 + THINKING_HEADROOM_TOKENS,
                               output_config={"effort": EFFORT},
                               system=prompt_cfg["system"], messages=[{"role": "user", "content": user}])
    if r.stop_reason in ("refusal", "max_tokens"):
        return "", "", f"error: stop_reason {r.stop_reason}"
    # A thinking block may come first; keep only the text.
    text = "".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip()
    try:
        out = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception:
        return "", "", f"error: non-json output"
    ice, angle = (out.get("icebreaker") or "").strip(), (out.get("angle") or "").strip()
    for b in BANNED:
        ice = ice.replace(b, ", " if b in ("—", "–", " - ") else "")
    if not ice or len(ice) > 320:
        return ice, angle, "error: empty or too long"
    return ice, angle, "done"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("sheet_id"); p.add_argument("--niche", default="all")
    p.add_argument("--limit", type=int, default=0); p.add_argument("--only-clean", action="store_true")
    a = p.parse_args()

    prompts = json.loads(PROMPTS.read_text())
    ws = open_tab(a.sheet_id)
    hdr = ws.row_values(1); col = {h: i + 1 for i, h in enumerate(hdr)}
    need = ["niche", "mv_result", "personalization_status", "icebreaker", "angle", "personalized_at"]
    missing = [c for c in need if c not in col]
    if missing: sys.exit(f"sheet missing columns: {missing}")

    rows = ws.get_all_records()
    todo = [(i + 2, r) for i, r in enumerate(rows)
            if (a.niche == "all" or r["niche"] == a.niche)
            and r.get("personalization_status") != "done"
            and (not a.only_clean or r.get("mv_result") == "ok")]
    if a.limit: todo = todo[: a.limit]
    print(f"[live] {len(todo)} rows to personalize (niche={a.niche}, model={MODEL})")

    client = anthropic.Anthropic(api_key=api_key())
    done = err = 0
    for n, (rownum, lead) in enumerate(todo, 1):
        cfg = prompts.get(lead["niche"])
        if not cfg:
            ws.update_cell(rownum, col["personalization_status"], "skipped: no prompt for niche"); continue
        ws.update_cell(rownum, col["personalization_status"], "working")
        try:
            ice, angle, status = generate(client, cfg, lead)
        except Exception as e:
            ice, angle, status = "", "", f"error: {type(e).__name__}"
        ws.batch_update([
            {"range": gspread_a1(rownum, col["icebreaker"]), "values": [[ice]]},
            {"range": gspread_a1(rownum, col["angle"]), "values": [[angle]]},
            {"range": gspread_a1(rownum, col["personalization_status"]), "values": [[status]]},
            {"range": gspread_a1(rownum, col["personalized_at"]), "values": [[datetime.now().strftime("%Y-%m-%d %H:%M")]]},
        ])
        done += status == "done"; err += status.startswith("error")
        if n % 10 == 0 or n == len(todo):
            print(f"  [{n}/{len(todo)}] done={done} err={err}  last: {lead['company_name'][:30]} -> {ice[:60]}")
        time.sleep(0.4)   # ~4 sheet writes/row; stays under the 60 writes/min quota
    print(f"[live] finished: done={done} err={err}")


def gspread_a1(row: int, c: int) -> str:
    s = ""
    while c: c, r = divmod(c - 1, 26); s = chr(65 + r) + s
    return f"{s}{row}"


if __name__ == "__main__":
    main()
