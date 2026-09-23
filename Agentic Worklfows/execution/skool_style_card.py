"""
Skool Style Card Builder
========================

Reads a corpus produced by skool_scraper.py and distills it into a structured
"style card" — the mechanical fingerprint of how someone writes, plus a bank of
verbatim exemplars.

The style card is what skool_tone_rewrite.py loads to rewrite your drafts.
Build it once per person; rebuild when you've collected a lot more material.

Usage:
    python3 skool_style_card.py --member nick-saraev
    python3 skool_style_card.py --member nick-saraev --max-blocks 200

Output:
    execution/style_cards/<member>.json

Dependencies:
    pip install anthropic python-dotenv
"""

import os
import sys
import json
import argparse
from typing import List, Dict

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), '.env'))

try:
    from anthropic import Anthropic
except ImportError:
    print("Missing anthropic package. Run: pip install anthropic")
    sys.exit(1)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Deliberately NOT ANTHROPIC_MODEL — that's set to Haiku repo-wide for bulk lead
# enrichment. Voice analysis needs the frontier model, and Haiku rejects `effort`.
MODEL = os.getenv('SKOOL_STYLE_MODEL', 'claude-opus-5')
TMP_DIR = os.path.join(os.path.dirname(BASE_DIR), '.tmp')
CARDS_DIR = os.path.join(BASE_DIR, 'style_cards')

# Enough signal to characterize the voice without burning the context window.
DEFAULT_MAX_BLOCKS = 150
MIN_WORDS = 15   # one-liners like "congrats!" teach nothing about voice


STYLE_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "voice_summary": {
            "type": "string",
            "description": "3-4 sentences describing how this person sounds, as if briefing a ghostwriter."
        },
        "sentence_rhythm": {
            "type": "string",
            "description": "Sentence and paragraph length patterns. Are they uniform or varied? Do they use one-line paragraphs? Where do they place the short punchy sentence?"
        },
        "capitalization_and_punctuation": {
            "type": "string",
            "description": "Concrete mechanics: sentence case vs lowercase, em dashes, ellipses, parentheses, exclamation marks, emoji use and frequency."
        },
        "formatting_habits": {
            "type": "string",
            "description": "How they lay text out: bullets, numbered lists, line breaks, bold, headers, or unbroken prose."
        },
        "opener_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "4-8 recurring ways they start a post, described as reusable patterns, each with a short real example."
        },
        "closer_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 recurring ways they end a post, each with a short real example."
        },
        "rhetorical_moves": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5-10 structural or persuasive techniques they lean on repeatedly (e.g. concrete number up front, contrarian reframe, story then lesson, direct address)."
        },
        "vocabulary_fingerprint": {
            "type": "array",
            "items": {"type": "string"},
            "description": "10-20 distinctive words, phrases, or constructions they reach for often."
        },
        "never_does": {
            "type": "array",
            "items": {"type": "string"},
            "description": "6-12 things absent from their writing that a generic imitation would wrongly add. This is the highest-value section — be specific."
        },
        "exemplars": {
            "type": "array",
            "items": {"type": "string"},
            "description": "8-12 verbatim excerpts copied exactly from the corpus, chosen to span their range. Do not paraphrase or clean them up."
        },
        "register_notes": {
            "type": "string",
            "description": "Where the two sections of the corpus diverge in voice, and which habits belong to which register. Say plainly which traits should NOT carry over into standalone posts."
        }
    },
    "required": [
        "voice_summary", "sentence_rhythm", "capitalization_and_punctuation",
        "formatting_habits", "opener_patterns", "closer_patterns",
        "rhetorical_moves", "vocabulary_fingerprint", "never_does", "exemplars",
        "register_notes"
    ],
    "additionalProperties": False
}


ANALYST_PROMPT = """You are a forensic prose analyst. Below is a corpus written by one person in a Skool community, split into two sections.

SECTION A — REPLIES: their responses inside other people's threads. This is their substantive teaching and coaching voice, and it is the bulk of the corpus.

SECTION B — ROOT POSTS: their own standalone posts. In this community these are largely operational and promotional (event announcements, setup guides, offers), and they are written in a noticeably different register from the replies.

Your job is to produce a style card: a precise, mechanical description of HOW this person writes. Not what they write about — how.

The style card describes the voice in SECTION A. That is the real writing voice being modelled, and it is what the card will be used to imitate.

Treat SECTION B as evidence about structure only — how they open and close a standalone piece, how they lay out a post that has to stand on its own. Do NOT let Section B's promotional habits (emoji, hype punctuation, sales framing, announcement scaffolding) leak into the main body of the card. Record those in `register_notes` as things that belong to the announcement register and must NOT carry into ordinary posts.

If the two sections genuinely agree on some trait, say so — that makes it a reliable rule.

Rules:
- Be concrete and falsifiable. "Uses short punchy sentences after a long setup" is useful. "Engaging and authentic" is useless — never write anything like that.
- Quote real fragments from the corpus as evidence throughout.
- The `never_does` list matters most. Someone imitating this writer will default to generic LLM prose: hedging, tricolons, "it's not just X, it's Y", rhetorical questions, tidy summary paragraphs, em-dash overuse, emoji bullets. Note which of those this writer genuinely never does, plus anything else conspicuously absent.
- `exemplars` must be copied verbatim from the corpus. Do not paraphrase, trim, or clean up. Preserve their exact line breaks and punctuation.
- Describe only patterns you can actually see repeated. If something appears once, don't generalize it into a rule.

CORPUS:
{corpus}
"""


# =============================================================================
# CORPUS LOADING
# =============================================================================

def load_corpus(member: str, max_blocks: int) -> List[Dict]:
    path = os.path.join(TMP_DIR, f'skool_corpus_{member}.json')
    if not os.path.isfile(path):
        print(f"No corpus found at {path}")
        print(f"Run: python3 skool_scraper.py --group <group> --member {member}")
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    blocks = [b for b in data.get('blocks', [])
              if len(b.get('content', '').split()) >= MIN_WORDS]

    # Longest-first: substantial posts carry more style signal than short replies.
    blocks.sort(key=lambda b: len(b.get('content', '')), reverse=True)
    return blocks[:max_blocks]


def format_corpus(blocks: List[Dict]) -> str:
    """Present replies and root posts as labelled sections.

    They're different registers in practice — blending them into one undifferentiated
    pile produces a style card describing an average voice the person never uses.
    """
    replies = [b for b in blocks if b.get('kind') != 'post']
    posts = [b for b in blocks if b.get('kind') == 'post']

    def render(group: List[Dict], tag: str) -> List[str]:
        out = []
        for i, b in enumerate(group, 1):
            header = f"--- {tag} #{i}"
            if b.get('title'):
                header += f" | title: {b['title']}"
            out.append(f"{header} ---\n{b['content']}")
        return out

    parts = [f"=== SECTION A — REPLIES ({len(replies)}) ==="]
    parts += render(replies, "reply")
    parts.append(f"\n=== SECTION B — ROOT POSTS ({len(posts)}) ===")
    parts += render(posts, "post")
    return "\n\n".join(parts)


# =============================================================================
# ANALYSIS
# =============================================================================

def build_style_card(member: str, blocks: List[Dict]) -> Dict:
    client = Anthropic()
    corpus_text = format_corpus(blocks)

    words = sum(len(b['content'].split()) for b in blocks)
    print(f"Analyzing {len(blocks)} blocks (~{words:,} words) with {MODEL}...")

    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": STYLE_CARD_SCHEMA},
        },
        messages=[{
            "role": "user",
            "content": ANALYST_PROMPT.format(corpus=corpus_text),
        }],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        print(f"Model declined: {getattr(response.stop_details, 'explanation', 'no detail')}")
        sys.exit(1)

    text = next(b.text for b in response.content if b.type == "text")
    card = json.loads(text)

    card['_meta'] = {
        'member': member,
        'blocks_analyzed': len(blocks),
        'words_analyzed': words,
        'model': MODEL,
    }
    return card


# =============================================================================
# MAIN
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description="Distill a Skool corpus into a style card.")
    ap.add_argument('--member', required=True, help='Member handle, e.g. nick-saraev')
    ap.add_argument('--max-blocks', type=int, default=DEFAULT_MAX_BLOCKS)
    args = ap.parse_args()

    blocks = load_corpus(args.member, args.max_blocks)
    if len(blocks) < 15:
        print(f"⚠ Only {len(blocks)} usable blocks. The style card will be shaky.")
        print("  Scrape more posts before relying on this.")

    card = build_style_card(args.member, blocks)

    os.makedirs(CARDS_DIR, exist_ok=True)
    out_path = os.path.join(CARDS_DIR, f'{args.member}.json')
    with open(out_path, 'w') as f:
        json.dump(card, f, indent=2)

    print(f"\n✓ Style card → {out_path}\n")
    print("Voice summary:")
    print(f"  {card['voice_summary']}\n")
    print(f"Never does ({len(card['never_does'])} items):")
    for item in card['never_does'][:5]:
        print(f"  - {item}")


if __name__ == '__main__':
    main()
