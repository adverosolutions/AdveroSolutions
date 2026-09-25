"""
LinkedIn Content Generator
===========================

Generates 5-10 LinkedIn posts per day across 5 content pillars.
Outputs to Google Sheets content calendar for manual scheduling via LinkedIn's native scheduler.

Content Pillars:
    1. Contractor Growth
    2. AI in Home Services
    3. Lead Generation
    4. Sales
    5. Founder Journey

Usage:
    # Generate a week of content (7 posts/day)
    python3 linkedin_content_generator.py --days 7

    # Dry run (preview without writing to sheet)
    python3 linkedin_content_generator.py --days 1 --posts-per-day 3 --dry-run

    # Focus on specific pillar
    python3 linkedin_content_generator.py --days 3 --pillar "ai in home services"

Dependencies:
    pip install anthropic gspread google-auth python-dotenv
"""

import os
import sys
import json
import time
import random
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from dotenv import load_dotenv

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

try:
    from anthropic import Anthropic
except ImportError:
    print("Missing anthropic package. Run: pip install anthropic")
    sys.exit(1)

try:
    from google_sheets_client import get_sheets_client, open_sheet
except ImportError:
    # Allow dry-run without Google Sheets
    get_sheets_client = None
    open_sheet = None


# =============================================================================
# CONFIGURATION
# =============================================================================

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
LINKEDIN_SHEET_ID = os.getenv('LINKEDIN_SHEET_ID', '')
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH',
                             os.path.join(os.path.dirname(__file__), 'credentials.json'))
# Fallback: check parent directory (common project layout)
if not os.path.isfile(CREDENTIALS_PATH):
    _parent_creds = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
    if os.path.isfile(_parent_creds):
        CREDENTIALS_PATH = _parent_creds
# Fallback: use GOOGLE_CREDENTIALS_JSON env var (JSON string)
CREDENTIALS_JSON_ENV = os.getenv('GOOGLE_CREDENTIALS_JSON', '')
SWIPE_FILE_PATH = os.path.join(os.path.dirname(__file__), 'linkedin_swipe_file.json')
PROFILE_PATH = os.path.join(os.path.dirname(__file__), 'linkedin_post_profile.json')


# =============================================================================
# SWIPE FILE & PROFILE LOADERS
# =============================================================================

def load_swipe_file() -> dict:
    """Load the viral post swipe file for few-shot examples."""
    try:
        with open(SWIPE_FILE_PATH, 'r') as f:
            data = json.load(f)
        print(f"  [OK] Loaded swipe file: {len(data.get('hook_formulas', []))} hook formulas, "
              f"{len(data.get('viral_structures', []))} viral structures")

        # Count user swipes
        user_swipes = [s for s in data.get('user_swipes', []) if s.get('text', '').strip()]
        if user_swipes:
            print(f"  [OK] Found {len(user_swipes)} user-submitted swipe posts")

        return data
    except FileNotFoundError:
        print(f"  [WARN] Swipe file not found at {SWIPE_FILE_PATH}. Using basic prompts.")
        return {}
    except json.JSONDecodeError as e:
        print(f"  [WARN] Invalid swipe file JSON: {e}. Using basic prompts.")
        return {}


def load_post_profile() -> dict:
    """Load the founder's post profile for grounding content in reality."""
    try:
        with open(PROFILE_PATH, 'r') as f:
            data = json.load(f)
        print(f"  [OK] Loaded post profile: {data.get('identity', {}).get('name', 'Unknown')} "
              f"— stage: {data.get('current_stage', {}).get('phase', 'unknown')}")
        return data
    except FileNotFoundError:
        print(f"  [WARN] Post profile not found at {PROFILE_PATH}. Posts won't be grounded.")
        return {}
    except json.JSONDecodeError as e:
        print(f"  [WARN] Invalid profile JSON: {e}. Posts won't be grounded.")
        return {}


SWIPE_DATA = load_swipe_file()
PROFILE = load_post_profile()


# Content pillars with weights and descriptions
PILLARS = {
    "Contractor Growth": {
        "weight": 0.20,
        "topics": [
            "scaling from solo to team", "hiring first employees", "systemizing operations",
            "revenue milestones", "choosing a niche", "reputation building",
            "customer retention strategies", "seasonal planning", "pricing strategy",
            "breaking through revenue plateaus", "delegating as a founder",
            "building SOPs for your crew", "when to say no to jobs",
            "commercial vs residential pivot", "geographic expansion"
        ],
        "voice": "experienced advisor who's seen contractors scale"
    },
    "AI in Home Services": {
        "weight": 0.20,
        "topics": [
            "AI answering services for contractors", "automated follow-ups after estimates",
            "predictive maintenance scheduling", "AI-powered dispatch optimization",
            "chatbots for contractor websites", "voice AI for missed calls",
            "AI estimating tools", "automated review requests",
            "AI-driven lead scoring", "computer vision for inspections",
            "AI scheduling optimization", "automated customer communication",
            "the future of home service tech", "why contractors who adopt AI win",
            "simple AI tools any contractor can use today"
        ],
        "voice": "tech-forward builder making AI accessible"
    },
    "Lead Generation": {
        "weight": 0.25,
        "topics": [
            "cold email for contractors", "email deliverability secrets",
            "response rate optimization", "building prospect lists",
            "Google LSA ads", "SEO for home services", "referral systems",
            "door-to-door vs digital", "Facebook ads for contractors",
            "nurturing cold leads", "follow-up sequences that convert",
            "why most contractor marketing fails", "cost per lead benchmarks",
            "outbound vs inbound strategies", "the perfect contractor offer",
            "lead quality vs quantity", "speed to lead"
        ],
        "voice": "data-driven marketer with real campaign results"
    },
    "Sales": {
        "weight": 0.15,
        "topics": [
            "one-call close framework", "handling 'let me think about it'",
            "pricing with confidence", "the kitchen table close",
            "building urgency without being pushy", "upselling maintenance plans",
            "phone vs in-person estimates", "same-day close strategies",
            "overcoming 'too expensive'", "financing as a close tool",
            "reading buying signals", "the assumptive close",
            "following up without being annoying", "bundling services",
            "anchoring high then discounting"
        ],
        "voice": "closer who respects the customer but doesn't leave money on the table"
    },
    "Founder Journey": {
        "weight": 0.20,
        "topics": [
            "why I started AdveroSolutions", "lessons from early failures",
            "building in public", "what I'd do differently",
            "the hard parts nobody talks about", "celebrating small wins",
            "morning routine that keeps me sharp", "tools I use daily",
            "how I make decisions fast", "dealing with imposter syndrome",
            "balancing building with selling", "the loneliness of entrepreneurship",
            "what working with contractors taught me", "my content creation process",
            "automating my own business", "mistakes that cost me money"
        ],
        "voice": "raw, honest founder sharing the real journey"
    }
}

# Post types with structures
POST_TYPES = [
    {
        "name": "Hook + Story",
        "structure": "Attention-grabbing first line → short narrative (2-3 paragraphs) → clear lesson/takeaway → engagement question",
        "best_for": ["Founder Journey", "Contractor Growth"],
        "weight": 0.25
    },
    {
        "name": "Hot Take",
        "structure": "Contrarian statement → 2-3 lines of reasoning → reframe that makes reader rethink → optional question",
        "best_for": ["AI in Home Services", "Lead Generation", "Sales"],
        "weight": 0.20
    },
    {
        "name": "Listicle",
        "structure": "'X things/mistakes/lessons' → numbered items (each 1-2 lines) → closing thought",
        "best_for": ["Lead Generation", "Sales", "Contractor Growth"],
        "weight": 0.15
    },
    {
        "name": "Data/Results",
        "structure": "Specific number or result → context of what was done → breakdown of why it worked → takeaway for reader",
        "best_for": ["Lead Generation", "Contractor Growth"],
        "weight": 0.15
    },
    {
        "name": "Question/Poll",
        "structure": "Provocative question → brief context (2-3 lines max) → invite discussion or give options",
        "best_for": ["Sales", "AI in Home Services", "Contractor Growth"],
        "weight": 0.10
    },
    {
        "name": "How-To",
        "structure": "Problem statement → 3-5 actionable steps → expected result → optional CTA",
        "best_for": ["Lead Generation", "Sales", "AI in Home Services"],
        "weight": 0.10
    },
    {
        "name": "Behind-the-Scenes",
        "structure": "What you're working on right now → why it matters → early results or challenges → what's next",
        "best_for": ["Founder Journey", "AI in Home Services"],
        "weight": 0.05
    }
]

# Time slots for daily posting schedule
TIME_SLOTS = [
    "7:00 AM", "8:30 AM", "10:00 AM", "11:30 AM",
    "12:30 PM", "2:00 PM", "3:30 PM", "5:00 PM",
    "6:30 PM", "8:00 PM"
]


# =============================================================================
# GENERATION ENGINE
# =============================================================================

def build_system_prompt() -> str:
    # Build formatting rules from swipe file
    formatting_rules = ""
    if SWIPE_DATA.get("formatting_rules"):
        formatting_rules = "\n\nFORMATTING RULES (follow these exactly):\n" + "\n".join(
            f"- {rule}" for rule in SWIPE_DATA["formatting_rules"]
        )

    # Build engagement patterns
    engagement_section = ""
    if SWIPE_DATA.get("engagement_patterns"):
        engagement_section = "\n\nENGAGEMENT CLOSERS (use one of these patterns to end posts):\n" + "\n".join(
            f"- {ep['pattern']} — {ep['why']}" for ep in SWIPE_DATA["engagement_patterns"]
        )

    # Build profile context
    profile_section = ""
    if PROFILE:
        identity = PROFILE.get("identity", {})
        stage = PROFILE.get("current_stage", {})
        claims = PROFILE.get("what_you_can_claim", {})
        fabricate = PROFILE.get("what_you_can_fabricate", {})
        voice = PROFILE.get("voice_and_personality", {})
        hot_takes = PROFILE.get("hot_takes_and_opinions", [])
        themes = PROFILE.get("content_themes_by_stage", {})

        profile_section = f"""

== FOUNDER PROFILE (this is WHO you are writing as — stay grounded in this reality) ==

IDENTITY: {identity.get('name', 'Lorenzo')} — {identity.get('title', 'Founder')}
{identity.get('one_liner', '')}

CURRENT STAGE: {stage.get('phase', 'startup').upper()}
- {stage.get('description', '')}
- Revenue: {stage.get('revenue_range', 'early stage')}
- Clients: {stage.get('clients', 'prospecting')}
- Team: {stage.get('team', 'solo')}

REAL WINS YOU CAN REFERENCE:
{chr(10).join(f'- {w}' for w in claims.get('real_wins', []))}

BELIEVABLE NUMBERS:
- Max monthly revenue to claim: {claims.get('believable_numbers', {}).get('max_monthly_revenue', '$10K')}
- Max clients: {claims.get('believable_numbers', {}).get('max_clients_at_once', 'a handful')}
- Emails sent: {claims.get('believable_numbers', {}).get('emails_sent', 'thousands')}
- Leads generated: {claims.get('believable_numbers', {}).get('leads_generated', 'hundreds')}

OFF LIMITS (NEVER do these):
{chr(10).join(f'- {o}' for o in claims.get('off_limits', []))}

WHAT YOU CAN MAKE UP (must be realistic for your stage):
{chr(10).join(f'- {a}' for a in fabricate.get('allowed', []))}
Tone: {fabricate.get('tone', '')}

YOUR ACTUAL HOT TAKES (use these — they are genuinely yours):
{chr(10).join(f'- {ht}' for ht in hot_takes)}

VOICE:
{chr(10).join(f'- {t}' for t in voice.get('core_traits', []))}
Perspective: {voice.get('perspective', '')}

DO NOT SOUND LIKE:
{chr(10).join(f'- {d}' for d in voice.get('do_not_sound_like', []))}

PRIMARY CONTENT THEMES FOR YOUR STAGE:
{chr(10).join(f'- {t}' for t in themes.get('primary', []))}

SECONDARY THEMES:
{chr(10).join(f'- {t}' for t in themes.get('secondary', []))}

== END PROFILE =="""

    return f"""You are writing LinkedIn posts AS {PROFILE.get('identity', {}).get('name', 'Lorenzo Villarreal')}, founder of AdveroSolutions — an AI-powered lead generation company for home service contractors (HVAC, Plumbing, Electrical, Roofing).

CRITICAL: Every post must be grounded in the founder profile below. You are writing from the perspective of an EARLY-STAGE startup founder who is IN THE GRIND right now. Not someone looking back from success. Not a guru. A builder who is actively figuring it out and sharing the journey.
{profile_section}

Your job is to write LinkedIn posts that MIMIC the style, structure, and energy of viral LinkedIn posts — but grounded in Lorenzo's ACTUAL reality.

Core principles:
- Write as a startup founder sharing the real journey — not a thought leader dispensing wisdom
- Are authentic, direct, and personal (first person, conversational tone)
- Stop the scroll with the first line (the hook)
- Use short paragraphs (1-2 sentences per line)
- Include line breaks for readability
- Stay under 2,000 characters (sweet spot: 800-1,500)
- End with something that drives engagement (question, hot take, or CTA)
- Never use hashtags in the body — only 3-5 at the very end, separated by a blank line
- Never sound corporate, generic, or AI-generated
- Only reference numbers, wins, and stories that fit the profile above
- Vary sentence length — mix punchy one-liners with longer thoughts

Voice guidelines:
- Talk like a founder who's in the trenches RIGHT NOW, not looking back
- Be opinionated — take sides (use the hot takes from the profile)
- Be honest about the stage — early, grinding, learning, building
- Admit you don't have all the answers yet — but you're figuring it out faster than most
- Never be preachy or lecture-y
- Write like you talk — contractions, fragments, casual tone
- Short punchy lines. Then a longer one to balance it out.
{formatting_rules}
{engagement_section}"""


def build_post_prompt(pillar: str, post_type: dict, topic: str, recent_posts: List[str]) -> str:
    recent_context = ""
    if recent_posts:
        recent_context = f"""
IMPORTANT — Avoid repeating these recent topics/angles (last posts generated):
{chr(10).join(f'- {p[:100]}...' for p in recent_posts[-10:])}

Make this post fresh and different from the above."""

    # Pull a matching viral structure example from swipe file
    structure_example = ""
    if SWIPE_DATA.get("viral_structures"):
        # Find a structure that matches the post type
        matching = [s for s in SWIPE_DATA["viral_structures"]
                    if post_type["name"].lower().split()[0] in s["name"].lower()
                    or any(word in s["name"].lower() for word in post_type["name"].lower().split())]
        if not matching:
            matching = SWIPE_DATA["viral_structures"]
        chosen_structure = random.choice(matching)
        structure_example = f"""
VIRAL STRUCTURE TO MIMIC: "{chosen_structure['name']}"
Structure: {chosen_structure['structure']}

EXAMPLE POST (mimic this style, energy, and formatting — but with YOUR topic):
---
{chosen_structure['example']}
---"""

    # Pull a matching hook formula
    hook_instruction = ""
    if SWIPE_DATA.get("hook_formulas"):
        hook = random.choice(SWIPE_DATA["hook_formulas"])
        hook_example = random.choice(hook["examples"])
        hook_instruction = f"""
HOOK FORMULA TO USE: "{hook['name']}"
Formula: {hook['formula']}
Example hook: "{hook_example}"
Why it works: {hook['why_works']}"""

    # Pull user swipe examples if available
    user_swipe_context = ""
    user_swipes = [s for s in SWIPE_DATA.get("user_swipes", []) if s.get("text", "").strip()]
    if user_swipes:
        sample = random.choice(user_swipes)
        user_swipe_context = f"""
REFERENCE POST (from your own high-performing content — match this voice):
---
{sample['text'][:1500]}
---"""

    return f"""Write a LinkedIn post with these parameters:

CONTENT PILLAR: {pillar}
POST TYPE: {post_type['name']}
TOPIC SEED: {topic}
VOICE: {PILLARS[pillar]['voice']}
{hook_instruction}
{structure_example}
{user_swipe_context}
{recent_context}

Rules:
- First line MUST be a scroll-stopping hook using the hook formula above
- MIMIC the viral example's structure, pacing, and formatting exactly
- Use blank lines between paragraphs for readability
- Keep under 1,800 characters
- End with engagement driver (use one of the engagement closer patterns from your instructions)
- Add 3-5 relevant hashtags on a final separate line
- Do NOT use emojis excessively (max 0-2 per post, and only if natural)
- Write ONLY the post content — no titles, labels, or metadata
- Make it feel like a REAL person wrote this — not an AI. Imperfect, opinionated, specific.

Write the post now:"""


# Every model call runs on Claude Opus 5.5 (Lorenzo, 2026-09-25).
DEFAULT_MODEL = "claude-opus-5-5"
# Opus 5.5 always thinks (thinking can't be disabled; temperature/top_p/top_k
# return a 400). Effort is the control, "low" for a short post. Thinking counts
# toward max_tokens, so the call gets headroom on top of the post's own budget.
POST_EFFORT = "low"
THINKING_HEADROOM_TOKENS = 1024


def generate_post(client: Anthropic, pillar: str, post_type: dict, topic: str,
                  recent_posts: List[str], model: str = DEFAULT_MODEL) -> Optional[str]:
    """Generate a single LinkedIn post using Claude."""
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024 + THINKING_HEADROOM_TOKENS,
            output_config={"effort": POST_EFFORT},
            system=build_system_prompt(),
            messages=[{
                "role": "user",
                "content": build_post_prompt(pillar, post_type, topic, recent_posts)
            }]
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            print(f"  [ERROR] No usable post (stop_reason={response.stop_reason})")
            return None
        # A thinking block may come first; keep only the text.
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
        return text or None
    except Exception as e:
        print(f"  [ERROR] Failed to generate post: {e}")
        return None


def plan_content_calendar(days: int, posts_per_day: int,
                          focus_pillar: Optional[str] = None) -> List[Dict]:
    """Plan which pillars, types, and topics to generate for each slot."""
    calendar = []
    start_date = datetime.now() + timedelta(days=1)  # Start tomorrow

    used_topics = set()

    for day_offset in range(days):
        post_date = start_date + timedelta(days=day_offset)
        date_str = post_date.strftime("%Y-%m-%d")

        # Select time slots for this day
        day_slots = TIME_SLOTS[:posts_per_day]

        for i, time_slot in enumerate(day_slots):
            # Pick pillar (weighted random, or focused)
            if focus_pillar:
                pillar = focus_pillar
            else:
                pillar = _weighted_choice_pillar()

            # Pick post type (weighted, prefer types that match this pillar)
            post_type = _weighted_choice_type(pillar)

            # Pick topic (avoid repeats)
            topic = _pick_topic(pillar, used_topics)
            used_topics.add(topic)

            calendar.append({
                "date": date_str,
                "time_slot": time_slot,
                "pillar": pillar,
                "post_type": post_type["name"],
                "topic": topic,
                "post_type_obj": post_type
            })

    return calendar


def _weighted_choice_pillar() -> str:
    """Select a pillar based on configured weights."""
    pillars = list(PILLARS.keys())
    weights = [PILLARS[p]["weight"] for p in pillars]
    return random.choices(pillars, weights=weights, k=1)[0]


def _weighted_choice_type(pillar: str) -> dict:
    """Select a post type, preferring types suited to this pillar."""
    adjusted_weights = []
    for pt in POST_TYPES:
        weight = pt["weight"]
        if pillar in pt["best_for"]:
            weight *= 1.5  # Boost types that match the pillar
        adjusted_weights.append(weight)

    return random.choices(POST_TYPES, weights=adjusted_weights, k=1)[0]


def _pick_topic(pillar: str, used: set) -> str:
    """Pick a topic that hasn't been used yet."""
    topics = PILLARS[pillar]["topics"]
    available = [t for t in topics if t not in used]
    if not available:
        available = topics  # Reset if all used
    return random.choice(available)


# =============================================================================
# GOOGLE SHEETS OUTPUT
# =============================================================================

def get_existing_posts(worksheet) -> List[str]:
    """Read existing posts from sheet to avoid repetition."""
    try:
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:  # Only header
            return []
        # Content is in column 5 (index 4)
        return [row[4] for row in all_values[1:] if len(row) > 4 and row[4]]
    except Exception as e:
        print(f"  [WARN] Could not read existing posts: {e}")
        return []


def write_posts_to_sheet(worksheet, posts: List[Dict]):
    """Write generated posts to Google Sheet."""
    # Check if header exists
    try:
        header = worksheet.row_values(1)
    except:
        header = []

    if not header or header[0] != "Date":
        worksheet.update('A1:G1', [["Date", "Time Slot", "Pillar", "Post Type", "Content", "Status", "Engagement"]])
        print("  [INFO] Created header row")

    # Find next empty row
    all_values = worksheet.get_all_values()
    next_row = len(all_values) + 1

    # Prepare rows
    rows = []
    for post in posts:
        rows.append([
            post["date"],
            post["time_slot"],
            post["pillar"],
            post["post_type"],
            post["content"],
            "Generated",
            ""
        ])

    # Batch write
    if rows:
        cell_range = f"A{next_row}:G{next_row + len(rows) - 1}"
        worksheet.update(cell_range, rows)
        print(f"  [OK] Wrote {len(rows)} posts to sheet (rows {next_row}-{next_row + len(rows) - 1})")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate LinkedIn content calendar")
    parser.add_argument("--days", type=int, default=7, help="Number of days to generate (default: 7)")
    parser.add_argument("--posts-per-day", type=int, default=7, help="Posts per day (default: 7, range 5-10)")
    parser.add_argument("--pillar", type=str, default=None, help="Focus on specific pillar")
    parser.add_argument("--sheet-id", type=str, default=None, help="Google Sheet ID (overrides .env)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help="Model to use (default: %s)" % DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to sheet")
    parser.add_argument("--tab", type=str, default="LinkedIn Queue", help="Sheet tab name")
    args = parser.parse_args()

    # Validate
    if not ANTHROPIC_API_KEY:
        print("[ERROR] ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)

    posts_per_day = max(5, min(10, args.posts_per_day))
    total_posts = args.days * posts_per_day

    # Resolve pillar focus
    focus_pillar = None
    if args.pillar:
        pillar_lower = args.pillar.lower()
        for p in PILLARS:
            if pillar_lower in p.lower():
                focus_pillar = p
                break
        if not focus_pillar:
            print(f"[ERROR] Unknown pillar: {args.pillar}")
            print(f"  Available: {', '.join(PILLARS.keys())}")
            sys.exit(1)

    print("=" * 60)
    print("LINKEDIN CONTENT GENERATOR")
    print("=" * 60)
    print(f"  Days:          {args.days}")
    print(f"  Posts/day:     {posts_per_day}")
    print(f"  Total posts:   {total_posts}")
    print(f"  Pillar focus:  {focus_pillar or 'All (weighted)'}")
    print(f"  Model:         {args.model}")
    print(f"  Dry run:       {args.dry_run}")
    print("=" * 60)

    # Initialize Claude client
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Connect to Google Sheets (unless dry run)
    worksheet = None
    existing_posts = []
    if not args.dry_run:
        sheet_id = args.sheet_id or LINKEDIN_SHEET_ID
        if not sheet_id:
            print("[ERROR] No sheet ID. Set LINKEDIN_SHEET_ID in .env or pass --sheet-id")
            print("  To test without sheets, use --dry-run")
            sys.exit(1)

        if not get_sheets_client:
            print("[ERROR] google_sheets_client not available. Install: pip install gspread google-auth")
            sys.exit(1)

        try:
            # Use credentials file if available, otherwise fall back to env var JSON
            creds_source = CREDENTIALS_PATH if os.path.isfile(CREDENTIALS_PATH) else CREDENTIALS_JSON_ENV
            gs_client = get_sheets_client(creds_source)
            worksheet = open_sheet(gs_client, sheet_id, args.tab)
            existing_posts = get_existing_posts(worksheet)
            print(f"  [OK] Connected to sheet. Found {len(existing_posts)} existing posts.")
        except Exception as e:
            print(f"[ERROR] Failed to connect to Google Sheets: {e}")
            sys.exit(1)

    # Plan calendar
    print("\n[1/3] Planning content calendar...")
    calendar = plan_content_calendar(args.days, posts_per_day, focus_pillar)

    # Show distribution
    pillar_dist = {}
    type_dist = {}
    for entry in calendar:
        pillar_dist[entry["pillar"]] = pillar_dist.get(entry["pillar"], 0) + 1
        type_dist[entry["post_type"]] = type_dist.get(entry["post_type"], 0) + 1

    print("\n  Pillar distribution:")
    for p, count in sorted(pillar_dist.items(), key=lambda x: -x[1]):
        print(f"    {p}: {count} posts")

    print("\n  Post type distribution:")
    for t, count in sorted(type_dist.items(), key=lambda x: -x[1]):
        print(f"    {t}: {count} posts")

    # Generate posts
    print(f"\n[2/3] Generating {total_posts} posts...")
    generated_posts = []
    recent_posts = existing_posts[-20:]  # Last 20 for context

    for i, entry in enumerate(calendar):
        print(f"  [{i+1}/{total_posts}] {entry['pillar']} | {entry['post_type']} | {entry['topic']}")

        content = generate_post(
            client=client,
            pillar=entry["pillar"],
            post_type=entry["post_type_obj"],
            topic=entry["topic"],
            recent_posts=recent_posts,
            model=args.model
        )

        if content:
            entry["content"] = content
            generated_posts.append(entry)
            recent_posts.append(content)

            if args.dry_run:
                print(f"\n{'─' * 40}")
                print(content)
                print(f"{'─' * 40}\n")
        else:
            print(f"  [SKIP] Failed to generate post {i+1}")

        # Rate limiting — small delay between calls
        if i < total_posts - 1:
            time.sleep(0.5)

    # Output
    print(f"\n[3/3] Output...")
    print(f"  Generated: {len(generated_posts)}/{total_posts} posts")

    if args.dry_run:
        print("\n  [DRY RUN] No posts written to sheet.")
        print("  Run without --dry-run to write to Google Sheets.")
    elif worksheet and generated_posts:
        write_posts_to_sheet(worksheet, generated_posts)

    # Cost estimate
    # Claude Opus 5.5: $4/1M input tokens, $20/1M output tokens
    # Rough estimate: ~500 input tokens + ~400 output tokens per post, plus
    # ~300 thinking tokens (billed as output) at low effort
    est_input_cost = (total_posts * 500 / 1_000_000) * 4.00
    est_output_cost = (total_posts * 700 / 1_000_000) * 20.00
    est_total = est_input_cost + est_output_cost

    print(f"\n{'=' * 60}")
    print(f"COMPLETE")
    print(f"  Posts generated: {len(generated_posts)}")
    print(f"  Est. cost:       ${est_total:.4f}")
    print(f"  Days covered:    {args.days}")
    if not args.dry_run:
        print(f"  Sheet:           Google Sheets → '{args.tab}' tab")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
