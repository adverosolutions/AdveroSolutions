"""
Skool Tone Rewriter
===================

Takes your rough draft and rewrites it in a target writer's voice, using the
style card built by skool_style_card.py.

You supply the substance. The rewriter only reshapes voice, structure, and
rhythm — it is forbidden from introducing any fact, number, or anecdote that
wasn't in your draft. A QA pass checks that rule and retries once if broken.

Usage:
    # From a file
    python3 skool_tone_rewrite.py --style nick-saraev --file draft.txt

    # From stdin (pipe or type, Ctrl-D to finish)
    python3 skool_tone_rewrite.py --style nick-saraev

    # Inline
    python3 skool_tone_rewrite.py --style nick-saraev --text "here's my rough draft..."

    # Three options to pick from
    python3 skool_tone_rewrite.py --style nick-saraev --file draft.txt --variants 3

Dependencies:
    pip install anthropic python-dotenv
"""

import os
import sys
import json
import argparse
from typing import Dict, List

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), '.env'))

try:
    from anthropic import Anthropic
except ImportError:
    print("Missing anthropic package. Run: pip install anthropic")
    sys.exit(1)


# Deliberately NOT ANTHROPIC_MODEL — the local .env still sets that to an old
# Haiku id, and Haiku rejects `effort`. Every model call runs on Claude Opus 5.5
# (Lorenzo, 2026-09-25); it always thinks, and effort sets how much.
MODEL = os.getenv('SKOOL_STYLE_MODEL', 'claude-opus-5-5')
CARDS_DIR = os.path.join(BASE_DIR, 'style_cards')


# =============================================================================
# PROMPTS
# =============================================================================

REWRITE_SYSTEM = """You rewrite drafts into a specific person's writing voice.

You are given a style card describing how that person writes, and a rough draft written by someone else. Your job is to re-express the draft's exact substance in the target voice.

THE HARD RULE — this is not negotiable:
You may not introduce any fact, number, statistic, name, date, client, result, or anecdote that is not already present in the draft. The target writer's style is built on concrete specifics; you will feel pressure to invent specifics to sound more like them. Do not. If the draft says "we got good results," you write it in their voice at that same level of specificity — you do not upgrade it to "we got 47 booked calls."

You may:
- Restructure and reorder freely
- Change sentence length, rhythm, and paragraph breaks
- Cut anything weak, redundant, or throat-clearing
- Rewrite the opening and closing to match their patterns
- Swap generic phrasing for their characteristic phrasing
- Make an implicit point explicit, if it was genuinely implicit in the draft

You may not:
- Add new claims, evidence, or examples
- Add a call to action that wasn't in the draft
- Inflate a vague claim into a specific one
- Copy the target writer's own stories, clients, or results

Output the rewritten post and nothing else. No preamble, no explanation, no options, no notes about what you changed."""


REWRITE_USER = """STYLE CARD — the voice to write in:

{style_card}

---

ROUGH DRAFT — the substance to preserve:

{draft}

---

Rewrite the draft in the style card's voice. Same substance, same level of specificity, their rhythm and structure. Output only the rewritten post."""


QA_SYSTEM = """You audit rewrites for fabricated content.

You get an original draft and a rewritten version. Identify every factual claim in the rewrite that is NOT supported by the original draft — new numbers, named entities, results, dates, events, anecdotes, or specific assertions that the draft did not make.

Reordering, rephrasing, tone changes, cuts, and making an implicit point explicit are all fine — do not flag those. Flag only genuinely new information.

Be strict about specificity inflation: if the draft said "a lot of people" and the rewrite says "hundreds of people," that is a new claim."""


QA_SCHEMA = {
    "type": "object",
    "properties": {
        "added_claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim quotes from the rewrite containing information absent from the draft. Empty if clean."
        },
        "verdict": {
            "type": "string",
            "enum": ["clean", "fabricated"],
            "description": "'clean' if added_claims is empty, otherwise 'fabricated'."
        }
    },
    "required": ["added_claims", "verdict"],
    "additionalProperties": False
}


# =============================================================================
# HELPERS
# =============================================================================

def load_style_card(name: str) -> Dict:
    path = os.path.join(CARDS_DIR, f'{name}.json')
    if not os.path.isfile(path):
        print(f"No style card at {path}")
        available = []
        if os.path.isdir(CARDS_DIR):
            available = [f[:-5] for f in os.listdir(CARDS_DIR) if f.endswith('.json')]
        if available:
            print(f"Available: {', '.join(available)}")
        else:
            print("Build one first: python3 skool_style_card.py --member <handle>")
        sys.exit(1)

    with open(path) as f:
        card = json.load(f)
    card.pop('_meta', None)
    return card


def read_draft(args) -> str:
    if args.text:
        return args.text.strip()
    if args.file:
        with open(args.file) as f:
            return f.read().strip()
    if sys.stdin.isatty():
        print("Paste your rough draft, then press Ctrl-D:\n")
    draft = sys.stdin.read().strip()
    if not draft:
        print("Empty draft — nothing to rewrite.")
        sys.exit(1)
    return draft


def _text_of(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


# =============================================================================
# PIPELINE
# =============================================================================

def rewrite(client: Anthropic, card: Dict, draft: str, note: str = "") -> str:
    user = REWRITE_USER.format(style_card=json.dumps(card, indent=2), draft=draft)
    if note:
        user += f"\n\nCORRECTION — your previous attempt broke the hard rule:\n{note}\nRewrite again without those additions."

    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=[{"type": "text", "text": REWRITE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        print(f"Model declined: {getattr(response.stop_details, 'explanation', 'no detail')}")
        sys.exit(1)

    return _text_of(response)


def audit(client: Anthropic, draft: str, output: str) -> Dict:
    with client.messages.stream(
        model=MODEL,
        max_tokens=8000,
        system=QA_SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": QA_SCHEMA}},
        messages=[{
            "role": "user",
            "content": f"ORIGINAL DRAFT:\n{draft}\n\n---\n\nREWRITE:\n{output}",
        }],
    ) as stream:
        response = stream.get_final_message()

    return json.loads(_text_of(response))


def produce(client: Anthropic, card: Dict, draft: str, label: str) -> str:
    """Rewrite, audit, and retry once if the model smuggled in new claims."""
    output = rewrite(client, card, draft)
    report = audit(client, draft, output)

    if report['verdict'] == 'clean':
        return output

    print(f"  [{label}] QA caught {len(report['added_claims'])} fabricated claim(s) — retrying", file=sys.stderr)
    note = "\n".join(f"- {c}" for c in report['added_claims'])
    output = rewrite(client, card, draft, note=note)

    recheck = audit(client, draft, output)
    if recheck['verdict'] != 'clean':
        print(f"  [{label}] ⚠ STILL FABRICATING — verify before posting:", file=sys.stderr)
        for c in recheck['added_claims']:
            print(f"      {c}", file=sys.stderr)

    return output


# =============================================================================
# MAIN
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description="Rewrite a draft in a target writer's voice.")
    ap.add_argument('--style', required=True, help='Style card name, e.g. nick-saraev')
    ap.add_argument('--file', help='Path to a draft file')
    ap.add_argument('--text', help='Draft passed inline')
    ap.add_argument('--variants', type=int, default=1, help='How many versions to generate (default 1)')
    ap.add_argument('--out', help='Write result to this file instead of stdout')
    args = ap.parse_args()

    card = load_style_card(args.style)
    draft = read_draft(args)
    client = Anthropic()

    print(f"Rewriting in {args.style}'s voice ({MODEL})...\n", file=sys.stderr)

    outputs: List[str] = []
    for i in range(args.variants):
        label = f"v{i + 1}"
        outputs.append(produce(client, card, draft, label))

    if args.out:
        with open(args.out, 'w') as f:
            f.write("\n\n---\n\n".join(outputs))
        print(f"✓ → {args.out}", file=sys.stderr)
        return

    for i, out in enumerate(outputs, 1):
        if args.variants > 1:
            print(f"\n{'=' * 60}\nVERSION {i}\n{'=' * 60}\n")
        print(out)


if __name__ == '__main__':
    main()
