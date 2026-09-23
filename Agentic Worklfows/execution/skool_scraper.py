"""
Skool Corpus Scraper
====================

Collects a single member's posts and comments from a Skool community you are
logged into, and writes them to .tmp/ as a corpus for style analysis.

Reads the member's own profile endpoint (/@<member>?g=<group>&p=N), which returns
an author-linked, paginated list of everything they've written. Every block is
matched against the member's canonical user id — no guessing from page text.

Uses a persistent Chrome profile (same approach as automated_social_monitor.py's
Nextdoor auth) — you log in by hand once, the session survives across runs.

Usage:
    # First run — opens a browser, you log in manually
    python3 skool_scraper.py --group makerschool --member nick-saraev

    # Bigger corpus
    python3 skool_scraper.py --group makerschool --member nick-saraev --max-blocks 300

    # Only their own top-level posts, not their replies
    python3 skool_scraper.py --group makerschool --member nick-saraev --posts-only

    # Headless once the profile is warm
    python3 skool_scraper.py --group makerschool --member nick-saraev --headless

Output:
    .tmp/skool_corpus_<member>.json

Dependencies:
    pip install playwright && playwright install chromium
"""

import os
import sys
import json
import time
import random
import asyncio
import argparse
from typing import Dict, List, Optional, Any, Iterator, Tuple

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, '.sessions', 'skool_profile')
TMP_DIR = os.path.join(os.path.dirname(BASE_DIR), '.tmp')

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

# Human-ish pacing. Skool rate-limits and flags fast automated traffic.
TIMING = {
    'nav_timeout': 45000,
    'page_load_wait': 3.0,
    'between_pages': (2.5, 4.5),   # random range between profile pages
}

LOGIN_WAIT_MINUTES = 10
TREES_PER_PAGE = 10       # what Skool returns per profile page
MAX_EMPTY_PAGES = 3       # consecutive dry pages before we stop


# =============================================================================
# NEXT.JS PAYLOAD
# =============================================================================

async def _next_data(page: Page) -> Optional[dict]:
    """Skool is a Next.js app — the real content lives in the __NEXT_DATA__ blob.

    Far more stable than scraping rendered DOM, which changes constantly.
    """
    try:
        raw = await page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__');"
            " return el ? el.textContent : null; }"
        )
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _page_props(page: Page) -> Dict[str, Any]:
    data = await _next_data(page)
    if not data:
        return {}
    return data.get('props', {}).get('pageProps', {}) or {}


# =============================================================================
# AUTH
# =============================================================================

async def _auth_state(page: Page) -> Dict[str, Any]:
    """Read auth state out of the Next.js payload rather than sniffing HTML.

    `pageProps.self` is null for logged-out visitors and populated once you have
    a session — the one signal Skool can't render differently per page. A logged-in
    non-member gets redirected to /<group>/about (the paywall), so the path tells
    us membership separately from authentication.
    """
    props = await _page_props(page)
    if not props:
        return {'logged_in': False, 'is_member': False, 'who': None, 'path': page.url}

    me = props.get('self')
    path = ((props.get('currentPage') or {}).get('path')) or page.url

    who = None
    if isinstance(me, dict):
        who = me.get('name') or (me.get('metadata') or {}).get('firstName')

    return {
        'logged_in': bool(me),
        'is_member': bool(me) and not path.rstrip('/').endswith('/about'),
        'who': who,
        'path': path,
    }


async def setup_auth(playwright_instance, group: str, headless: bool):
    """Open a persistent-profile browser and make sure we're inside the group."""
    os.makedirs(PROFILE_DIR, exist_ok=True)

    context: BrowserContext = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=headless,
        viewport={'width': 1400, 'height': 950},
        user_agent=USER_AGENT,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-first-run',
            '--no-default-browser-check',
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        window.chrome = { runtime: {} };
    """)

    feed_url = f'https://www.skool.com/{group}'
    await page.goto(feed_url, timeout=TIMING['nav_timeout'])
    await asyncio.sleep(TIMING['page_load_wait'])

    state = await _auth_state(page)
    if state['is_member']:
        who = f" as {state['who']}" if state['who'] else ""
        print(f"✓ Skool session restored{who} — inside /{group}", flush=True)
        return page, context

    if state['logged_in']:
        print(f"✗ Logged in{' as ' + state['who'] if state['who'] else ''}, "
              f"but this account can't see /{group} (landed on {state['path']}).", flush=True)
        print(f"  Check you're a paid member of {group} with this same account.", flush=True)
        await context.close()
        sys.exit(1)

    if headless:
        print("✗ Not logged in, and --headless can't prompt for a login.")
        print("  Run once without --headless to authenticate, then retry.")
        await context.close()
        sys.exit(1)

    print("\n=== Skool Login Required ===", flush=True)
    print("A browser window is open. Log in to Skool — no keypress needed here,", flush=True)
    print(f"this script polls and navigates itself (waiting up to {LOGIN_WAIT_MINUTES} min).\n", flush=True)

    # Poll rather than block on input(): works when run interactively AND when
    # driven by another process that doesn't share the user's terminal.
    deadline = time.time() + LOGIN_WAIT_MINUTES * 60
    announced = False
    while time.time() < deadline:
        await asyncio.sleep(5)
        try:
            state = await _auth_state(page)
        except Exception:
            continue  # mid-navigation; try again next tick

        if state['is_member']:
            await asyncio.sleep(2)
            who = f" as {state['who']}" if state['who'] else ""
            print(f"✓ Login detected{who} — saved to persistent profile.", flush=True)
            return page, context

        if state['logged_in'] and not announced:
            announced = True
            print(f"  Logged in{' as ' + state['who'] if state['who'] else ''} — "
                  f"navigating to /{group} myself...", flush=True)
            # Auth is done, so it's safe to drive the browser now. Without this
            # we'd only ever inspect whatever page the user happened to land on.
            try:
                await page.goto(feed_url, timeout=TIMING['nav_timeout'])
                await asyncio.sleep(TIMING['page_load_wait'])
                state = await _auth_state(page)
                if state['is_member']:
                    who = f" as {state['who']}" if state['who'] else ""
                    print(f"✓ Login detected{who} — saved to persistent profile.", flush=True)
                    return page, context
                print(f"  Still bounced to {state['path']} — this account may not "
                      f"have access to /{group}.", flush=True)
            except Exception as e:
                print(f"  Navigation retry failed ({e.__class__.__name__}); polling on.", flush=True)

        remaining = int(deadline - time.time())
        if remaining % 30 < 5:
            print(f"  still waiting... ({remaining}s left)", flush=True)

    print("✗ Timed out waiting for login.", flush=True)
    print(f"  If the profile is wedged: rm -rf \"{PROFILE_DIR}\"", flush=True)
    await context.close()
    sys.exit(1)


# =============================================================================
# EXTRACTION
# =============================================================================

def profile_url(member: str, group: str, page_num: int) -> str:
    base = f'https://www.skool.com/@{member}?g={group}'
    return base if page_num <= 1 else f'{base}&p={page_num}'


async def resolve_member_id(page: Page, member: str, group: str) -> str:
    """Get the member's canonical user id from their profile payload.

    Everything downstream filters on this id. Matching on displayed names is
    unreliable — a group owner's name appears in the chrome of every page.
    """
    await page.goto(profile_url(member, group, 1), timeout=TIMING['nav_timeout'])
    await asyncio.sleep(TIMING['page_load_wait'])

    props = await _page_props(page)
    user = props.get('currentUser') or {}
    uid = user.get('id')

    if not uid:
        print(f"✗ Couldn't resolve a user id for @{member} in /{group}.")
        print(f"  Check the handle is right: https://www.skool.com/@{member}?g={group}")
        sys.exit(1)

    print(f"✓ Resolved @{member} → {uid} (name: {user.get('name')})", flush=True)
    return str(uid)


def walk_tree(node: dict, depth: int = 0) -> Iterator[Tuple[int, dict]]:
    """Yield (depth, post) for a post tree. Depth 0 is the root post, 1+ replies."""
    post = node.get('post')
    if isinstance(post, dict):
        yield depth, post
    for child in (node.get('children') or []):
        if isinstance(child, dict):
            yield from walk_tree(child, depth + 1)


def blocks_from_trees(trees: List[dict], member_id: str, posts_only: bool) -> List[dict]:
    """Pull only the target member's own writing out of a page of post trees."""
    out = []
    for tree in trees:
        for depth, post in walk_tree(tree):
            user = post.get('user') or {}
            if str(user.get('id')) != member_id:
                continue

            meta = post.get('metadata') or {}
            content = (meta.get('content') or '').strip()
            if not content:
                continue

            kind = 'post' if depth == 0 else 'comment'
            if posts_only and kind != 'post':
                continue

            out.append({
                'id': post.get('id'),
                'kind': kind,
                'depth': depth,
                'title': (meta.get('title') or '').strip(),
                'content': content,
                'author': user.get('name'),
                'created_at': post.get('createdAt'),
                'upvotes': meta.get('upvotes'),
            })
    return out


async def scrape_profile(page: Page, member: str, group: str, member_id: str,
                         max_blocks: int, posts_only: bool) -> List[dict]:
    """Page through the member's profile, collecting their own posts and replies."""
    corpus: List[dict] = []
    seen_ids = set()
    page_num = 1
    empty_streak = 0

    print(f"\nWalking @{member}'s profile ({TREES_PER_PAGE} trees/page)...\n", flush=True)

    while len(corpus) < max_blocks and empty_streak < MAX_EMPTY_PAGES:
        try:
            await page.goto(profile_url(member, group, page_num), timeout=TIMING['nav_timeout'])
            await asyncio.sleep(TIMING['page_load_wait'])
            props = await _page_props(page)
        except Exception as e:
            print(f"  p{page_num}: fetch failed ({e.__class__.__name__}) — stopping", flush=True)
            break

        trees = props.get('postTrees') or []
        if not trees:
            empty_streak += 1
            print(f"  p{page_num}: no trees returned ({empty_streak}/{MAX_EMPTY_PAGES})", flush=True)
            page_num += 1
            continue

        found = blocks_from_trees(trees, member_id, posts_only)
        fresh = [b for b in found if b['id'] not in seen_ids]
        for b in fresh:
            seen_ids.add(b['id'])
        corpus.extend(fresh)

        if not fresh:
            empty_streak += 1
        else:
            empty_streak = 0

        posts = sum(1 for b in fresh if b['kind'] == 'post')
        print(f"  p{page_num}: +{len(fresh)} blocks ({posts} posts, "
              f"{len(fresh) - posts} replies) — total {len(corpus)}", flush=True)

        page_num += 1
        await asyncio.sleep(random.uniform(*TIMING['between_pages']))

    return corpus[:max_blocks]


async def scrape_feed(page: Page, group: str, member_id: str,
                      max_posts: int, max_pages: int) -> List[dict]:
    """Harvest the member's own top-level posts from the group feed.

    The profile endpoint is ordered by recent activity, so for a prolific
    commenter it's almost entirely replies. Root posts are a different register
    — standalone, with a hook and a payoff — and that's what the group feed
    surfaces. Roughly 33 roots per page, a few of them the target member's.
    """
    found: List[dict] = []
    seen = set()
    page_num = 1
    empty_streak = 0

    print(f"\nWalking /{group} feed for @{member_id[:8]}…'s own posts...\n", flush=True)

    while len(found) < max_posts and page_num <= max_pages and empty_streak < MAX_EMPTY_PAGES:
        url = f'https://www.skool.com/{group}'
        if page_num > 1:
            url += f'?p={page_num}'
        try:
            await page.goto(url, timeout=TIMING['nav_timeout'])
            await asyncio.sleep(TIMING['page_load_wait'])
            props = await _page_props(page)
        except Exception as e:
            print(f"  feed p{page_num}: fetch failed ({e.__class__.__name__}) — stopping", flush=True)
            break

        trees = props.get('postTrees') or []
        if not trees:
            empty_streak += 1
            print(f"  feed p{page_num}: no trees ({empty_streak}/{MAX_EMPTY_PAGES})", flush=True)
            page_num += 1
            continue

        # Roots only — replies are already covered by the profile pass.
        mine = [b for b in blocks_from_trees(trees, member_id, posts_only=True)
                if b['id'] not in seen]
        for b in mine:
            seen.add(b['id'])
        found.extend(mine)

        # Only a page with NO trees means we've run off the end. A page with
        # trees but none by this member is the normal case — he's ~3 of every
        # 30 roots — so it must not count toward the stop condition.
        empty_streak = 0
        print(f"  feed p{page_num}: +{len(mine)} posts (total {len(found)}) "
              f"[{len(trees)} roots scanned]", flush=True)

        page_num += 1
        await asyncio.sleep(random.uniform(*TIMING['between_pages']))

    return found[:max_posts]


# =============================================================================
# MAIN
# =============================================================================

async def run(group: str, member: str, max_blocks: int, posts_only: bool,
              headless: bool, source: str, feed_posts: int, feed_pages: int):
    os.makedirs(TMP_DIR, exist_ok=True)
    out_path = os.path.join(TMP_DIR, f'skool_corpus_{member}.json')

    async with async_playwright() as p:
        page, context = await setup_auth(p, group, headless)
        try:
            member_id = await resolve_member_id(page, member, group)

            corpus: List[dict] = []
            seen = set()

            # Feed first — root posts are the scarce, high-value register.
            if source in ('feed', 'both'):
                for b in await scrape_feed(page, group, member_id, feed_posts, feed_pages):
                    if b['id'] not in seen:
                        seen.add(b['id'])
                        corpus.append(b)

            if source in ('profile', 'both'):
                for b in await scrape_profile(page, member, group, member_id,
                                              max_blocks, posts_only):
                    if b['id'] not in seen:
                        seen.add(b['id'])
                        corpus.append(b)

            payload = {
                'group': group,
                'member': member,
                'member_id': member_id,
                'collected_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'block_count': len(corpus),
                'blocks': corpus,
            }
            with open(out_path, 'w') as f:
                json.dump(payload, f, indent=2)

            words = sum(len(b['content'].split()) for b in corpus)
            posts = sum(1 for b in corpus if b['kind'] == 'post')
            print(f"\n✓ {len(corpus)} blocks ({posts} posts, {len(corpus) - posts} replies, "
                  f"~{words:,} words) → {out_path}", flush=True)

            if len(corpus) < 30:
                print("⚠ Thin corpus. 50+ blocks makes a much better style card.", flush=True)

        finally:
            await context.close()


def main():
    ap = argparse.ArgumentParser(description="Scrape one Skool member's writing into a corpus.")
    ap.add_argument('--group', required=True, help='Community slug, e.g. makerschool')
    ap.add_argument('--member', required=True, help='Member handle, e.g. nick-saraev')
    ap.add_argument('--max-blocks', type=int, default=200,
                    help='Stop after this many of their blocks (default 200)')
    ap.add_argument('--posts-only', action='store_true',
                    help='Only their own top-level posts, skip their replies')
    ap.add_argument('--headless', action='store_true',
                    help='Run headless (profile must already be logged in)')
    ap.add_argument('--source', choices=('profile', 'feed', 'both'), default='both',
                    help="'feed' = their own root posts, 'profile' = mostly their replies, "
                         "'both' = default")
    ap.add_argument('--feed-posts', type=int, default=40,
                    help='Target number of their root posts from the feed (default 40)')
    ap.add_argument('--feed-pages', type=int, default=40,
                    help='Max feed pages to scan (default 40)')
    args = ap.parse_args()

    asyncio.run(run(args.group, args.member, args.max_blocks, args.posts_only,
                    args.headless, args.source, args.feed_posts, args.feed_pages))


if __name__ == '__main__':
    main()
