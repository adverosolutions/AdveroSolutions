"""Read-only collection of Maker School wins posts.

Pure parsers (tested on recorded payloads): walk a Skool post tree, keep the
root post plus the AUTHOR's own replies, find the group's categories, build
page URLs. Other members' comments are dropped: the author's answers to
"what niche?" and "what's your offer?" hold the details, everyone else's
"congrats" does not.

Two live transports, both read-only, both Lorenzo's Mac only:

* ``collect_mcp`` is the one that works on the Mac. It runs
  skool_mcp_fetch.mjs with node, which imports the already-authenticated
  skool-mcp client (Coding/skool-mcp/dist/client.js) and makes two GET
  calls: the category feed (Next.js data route, ``pageProps.postTrees``) and
  a post's comments (api2 ``/posts/<id>/comments``, snake_case nodes that
  ``tree_from_api2`` turns into the feed's tree shape). The client reads its
  own cookie config; this module never opens it.
* ``collect`` (Playwright) reuses execution/skool_scraper.py's login flow and
  Chrome profile. It cannot run on the Mac today: no Chromium in the
  Playwright cache, no saved profile, and the login needs Lorenzo. That
  module calls sys.exit(1) at import when Playwright is missing, so it is
  imported lazily inside the live functions and never at module import.

Skool is a Next.js app; ``look`` dumps the payload keys it saw to
.tmp/offer_intel/look.json, and both collectors take the category page URL
exactly as the browser shows it. Post pages carry no comments. The api2
comments call returns at most 25 top-level comments (50 or 100 is an HTTP
400); a non-zero ``last`` marks a thread with more, and since its paging
parameter is not verified, that record is flagged ``thread_partial``.

Never posts, comments, reacts or messages. Paced like the existing scraper.
"""
import asyncio
import importlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from shared.paths import BASE_DIR

from services.offer_intel import files

logger = logging.getLogger("offer_intel.skool_read")

SKOOL_HOST = "https://www.skool.com"
DEFAULT_GROUP = "makerschool"  # what execution/skool_scraper.py uses; `look` confirms it
MAX_EMPTY_PAGES = 2
MAX_OLD_PAGES = 2       # feed order may be by activity, so one old page is not the end
REFRESH_DAYS = 14       # authors keep answering questions for a few days
MCP_SCRIPT = Path(__file__).resolve().parent / "skool_mcp_fetch.mjs"
MCP_TIMEOUT = 90        # seconds per node call
MCP_PACE = (2.5, 4.5)   # seconds between Skool calls, like the existing scraper


# ------------------------------------------------------------------ parsing
def walk_tree(node: Dict[str, Any], depth: int = 0) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """(depth, post) for a post tree; depth 0 is the root. Same as the scraper's."""
    post = node.get("post") if isinstance(node, dict) else None
    if isinstance(post, dict):
        yield depth, post
    for child in (node.get("children") or []) if isinstance(node, dict) else []:
        if isinstance(child, dict):
            for item in walk_tree(child, depth + 1):
                yield item


def trees_from_props(props: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Feed pages carry ``postTrees``; a single post page may carry ``postTree``."""
    trees = props.get("postTrees")
    if isinstance(trees, list):
        return [t for t in trees if isinstance(t, dict)]
    one = props.get("postTree")
    return [one] if isinstance(one, dict) else []


_FRACTION = re.compile(r"(\.\d+)")


def parse_time(value: Any) -> Optional[datetime]:
    """Skool's ISO stamps ('2026-09-20T15:04:05.123456789Z') -> aware UTC.
    Python 3.9's fromisoformat takes neither 'Z' nor nine fractional digits."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    text = _FRACTION.sub(lambda m: m.group(1)[:7].ljust(7, "0"), text, count=1)
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


_MEDIA_KEY = re.compile(r"image|attachment|video|media|preview", re.I)
_MEDIA_TEXT = re.compile(r"!\[[^\]]*\]\(|\.(png|jpe?g|gif|webp)\b", re.I)


def has_media(post: Dict[str, Any]) -> bool:
    """True when the post carries a screenshot, file or video. Those wins often
    put the numbers in the image, which v1 does not read."""
    meta = post.get("metadata") or {}
    for key, value in meta.items():
        if _MEDIA_KEY.search(str(key)) and value not in (None, "", [], {}, 0, "[]"):
            return True
    return bool(_MEDIA_TEXT.search(str(meta.get("content") or "")))


def post_url(group: str, slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    return "%s/%s/%s" % (SKOOL_HOST, group, slug)


def reply_order(reply: Dict[str, Any]) -> str:
    """The one sort key for author replies, so a first save and a re-save match."""
    return str(reply.get("created_at") or "")


def display_name(user: Dict[str, Any]) -> Optional[str]:
    """'First Last' when Skool has it, else the handle, else None."""
    full = " ".join(x for x in (str(user.get("firstName") or "").strip(),
                                str(user.get("lastName") or "").strip()) if x)
    return full or user.get("name") or None


def record_from_tree(tree: Dict[str, Any], group: str, collected_at: str,
                     thread_fetched: bool = False) -> Optional[Dict[str, Any]]:
    """One wins record: the root post plus the root author's own replies."""
    nodes = list(walk_tree(tree))
    if not nodes or nodes[0][0] != 0:
        return None
    root = nodes[0][1]
    user = root.get("user") or {}
    author_id = str(user.get("id") or "")
    meta = root.get("metadata") or {}
    post_id = root.get("id")
    if not post_id or not author_id:
        return None

    replies = []
    for depth, post in nodes[1:]:
        if str((post.get("user") or {}).get("id") or "") != author_id:
            continue
        text = ((post.get("metadata") or {}).get("content") or "").strip()
        if text:
            replies.append({"id": post.get("id"), "content": text, "created_at": post.get("createdAt"),
                            "depth": depth})
    replies.sort(key=reply_order)  # stable, same key as merge_records

    slug = root.get("name") or meta.get("slug")
    return {
        "source": "skool",
        "group": group,
        "post_id": str(post_id),
        "slug": slug,
        "url": post_url(group, slug),
        "title": (meta.get("title") or "").strip(),
        "content": (meta.get("content") or "").strip(),
        "author_id": author_id,
        "author_name": display_name(user),
        "created_at": root.get("createdAt"),
        "upvotes": meta.get("upvotes"),
        "comment_count": meta.get("comments"),
        "has_media": has_media(root),
        "author_replies": replies,
        "thread_fetched": bool(thread_fetched),
        "collected_at": collected_at,
    }


def merge_records(old: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
    """A re-read keeps every author reply seen so far (a reply the feed payload
    truncated must not vanish) and the newest post text."""
    if not old:
        return new
    merged = dict(old)
    merged.update({k: v for k, v in new.items() if v not in (None, "")})
    seen = {}
    for reply in (old.get("author_replies") or []) + (new.get("author_replies") or []):
        seen[str(reply.get("id") or reply.get("content"))] = reply
    merged["author_replies"] = sorted(seen.values(), key=reply_order)
    merged["thread_fetched"] = bool(old.get("thread_fetched")) or bool(new.get("thread_fetched"))
    return merged


def needs_thread(record: Optional[Dict[str, Any]], now: datetime, refresh_days: int = REFRESH_DAYS) -> bool:
    """Open the post page when we never read its comments, or it is young
    enough that the author may still be answering questions."""
    if not record or not record.get("thread_fetched"):
        return True
    created = parse_time(record.get("created_at"))
    return created is None or (now - created) <= timedelta(days=refresh_days)


_LABEL_KEY = re.compile(r"label|categor", re.I)


def _label_name(item: Dict[str, Any]) -> Optional[str]:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for source in (meta, item):
        for key in ("displayName", "display_name", "name", "title"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def find_labels(props: Any) -> List[Dict[str, str]]:
    """Every category-looking list in the payload: lists under a key that says
    label or category, whose items have an id and a name. Shape-tolerant on
    purpose, because the exact key has not been observed yet."""
    found = {}  # type: Dict[str, Dict[str, str]]

    def visit(node: Any, depth: int) -> None:
        if depth > 8:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if _LABEL_KEY.search(str(key)) and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and item.get("id"):
                            name = _label_name(item)
                            if name:
                                found.setdefault(str(item["id"]), {"id": str(item["id"]), "name": name,
                                                                  "key": str(key)})
                visit(value, depth + 1)
        elif isinstance(node, list):
            for value in node[:200]:
                visit(value, depth + 1)

    visit(props, 0)
    return sorted(found.values(), key=lambda x: x["name"].lower())


def wins_labels(labels: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [lab for lab in labels if re.search(r"\bwins?\b", lab["name"], re.I)]


def page_url(base_url: str, page_num: int) -> str:
    """The category URL as the browser shows it, with its page number set."""
    parts = urlparse(base_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "p"]
    if page_num > 1:
        query.append(("p", str(page_num)))
    return urlunparse(parts._replace(query=urlencode(query)))


def group_from_url(url: str) -> str:
    parts = urlparse(url)
    segment = parts.path.strip("/").split("/")[0] if parts.path.strip("/") else ""
    if not segment or parts.netloc.lower() not in ("www.skool.com", "skool.com"):
        raise ValueError("not a Skool group URL: %s" % url)
    return segment


def label_from_url(url: str) -> Optional[str]:
    """The category (label) id: the ``c`` query parameter of the category URL."""
    for key, value in parse_qsl(urlparse(url).query):
        if key == "c" and value.strip():
            return value.strip()
    return None


def tree_from_api2(node: Dict[str, Any]) -> Dict[str, Any]:
    """An api2 comment node (snake_case) -> the feed's tree shape that
    record_from_tree reads. Only the fields a record uses are kept."""
    post = node.get("post") if isinstance(node.get("post"), dict) else {}
    user = post.get("user") if isinstance(post.get("user"), dict) else {}
    meta = post.get("metadata") if isinstance(post.get("metadata"), dict) else {}
    return {
        "post": {
            "id": post.get("id"),
            "createdAt": post.get("created_at") or post.get("createdAt"),
            "metadata": {"content": meta.get("content")},
            "user": {"id": user.get("id") or post.get("user_id") or post.get("userId"),
                     "firstName": user.get("first_name") or user.get("firstName"),
                     "lastName": user.get("last_name") or user.get("lastName"),
                     "name": user.get("name")},
        },
        "children": [tree_from_api2(c) for c in (node.get("children") or []) if isinstance(c, dict)],
    }


def _add_nodes(dest: List[Dict[str, Any]], nodes: List[Dict[str, Any]],
               index: Dict[str, Dict[str, Any]]) -> None:
    """Append converted nodes once per comment id. A comment seen before (a
    pinned comment is also in the main tree) only adds children it lacked."""
    for node in nodes:
        key = str((node.get("post") or {}).get("id") or "")
        if key and key in index:
            _add_nodes(index[key]["children"], node.get("children") or [], index)
            continue
        fresh = {"post": node.get("post") or {}, "children": []}  # type: Dict[str, Any]
        if key:
            index[key] = fresh
        dest.append(fresh)
        _add_nodes(fresh["children"], node.get("children") or [], index)


def thread_from_api2(feed_tree: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """The full thread: the feed's root post over the pinned and main comment
    trees of an api2 comments payload, de-duplicated by comment id."""
    children = []  # type: List[Dict[str, Any]]
    index = {}  # type: Dict[str, Dict[str, Any]]
    for key in ("pinned_post_tree", "post_tree"):
        branch = payload.get(key) if isinstance(payload.get(key), dict) else {}
        converted = [tree_from_api2(c) for c in (branch.get("children") or []) if isinstance(c, dict)]
        _add_nodes(children, converted, index)
    return {"post": feed_tree.get("post") or {}, "children": children}


def payload_shape(props: Dict[str, Any]) -> Dict[str, Any]:
    """Keys only, never values: what `look` saves so a schema miss can be fixed
    without copying anyone's posts."""
    trees = trees_from_props(props)
    sample_post = trees[0].get("post") if trees else None
    return {
        "page_props_keys": sorted(props.keys()),
        "tree_count": len(trees),
        "post_keys": sorted(sample_post.keys()) if isinstance(sample_post, dict) else [],
        "post_metadata_keys": sorted((sample_post.get("metadata") or {}).keys())
        if isinstance(sample_post, dict) else [],
    }


# ---------------------------------------------------------------------- live
def _scraper():
    """execution/skool_scraper.py, imported only when a live walk starts."""
    exec_dir = str(BASE_DIR / "execution")
    if exec_dir not in sys.path:
        sys.path.insert(0, exec_dir)
    return importlib.import_module("skool_scraper")


def _async_playwright():
    """Playwright's entry point, imported only for a live walk (and swapped in tests)."""
    from playwright.async_api import async_playwright

    return async_playwright


async def _goto_props(page: Any, url: str, scraper: Any) -> Dict[str, Any]:
    await page.goto(url, timeout=scraper.TIMING["nav_timeout"])
    await asyncio.sleep(scraper.TIMING["page_load_wait"])
    return await scraper._page_props(page)


async def _pause(scraper: Any) -> None:
    await asyncio.sleep(random.uniform(*scraper.TIMING["between_pages"]))


async def look(group: str, headless: bool = False) -> Dict[str, Any]:
    """Log-in check, the group's categories, and the payload keys. Read-only."""
    scraper = _scraper()
    async_playwright = _async_playwright()

    async with async_playwright() as p:
        page, context = await scraper.setup_auth(p, group, headless)
        try:
            props = await scraper._page_props(page)
            labels = find_labels(props)
            result = {
                "group": group,
                "feed_url": "%s/%s" % (SKOOL_HOST, group),
                "logged_in_as": ((props.get("self") or {}).get("name") if isinstance(props.get("self"), dict)
                                 else None),
                "labels": labels,
                "wins_labels": wins_labels(labels),
                "shape": payload_shape(props),
                "looked_at": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            await context.close()
    files.write_json(files.root() / "look.json", result)
    return result


def _feed_record(tree: Dict[str, Any], group: str, stamp: str, since: Optional[datetime],
                 counts: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """The feed copy of one post, or None when unusable or older than ``since``."""
    record = record_from_tree(tree, group, stamp)
    if not record:
        return None
    counts["seen"] += 1
    created = parse_time(record.get("created_at"))
    if since and created and created < since:
        counts["skipped_old"] += 1
        return None
    return record


def _store(old: Optional[Dict[str, Any]], record: Dict[str, Any], counts: Dict[str, int]) -> None:
    files.save_raw(merge_records(old, record))
    counts["updated" if old else "new"] += 1


async def collect(category_url: str, max_pages: int = 3, max_posts: int = 40,
                  since: Optional[datetime] = None, threads: bool = True,
                  refresh_days: int = REFRESH_DAYS, headless: bool = False,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Walk the wins category page by page and save one raw record per post."""
    group = group_from_url(category_url)
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    scraper = _scraper()
    async_playwright = _async_playwright()

    counts = {"pages": 0, "seen": 0, "new": 0, "updated": 0, "threads_read": 0, "skipped_old": 0}
    status = "ok"
    async with async_playwright() as p:
        page, context = await scraper.setup_auth(p, group, headless)
        try:
            empty = old_pages = 0
            for page_num in range(1, max_pages + 1):
                if counts["new"] + counts["updated"] >= max_posts:
                    break
                try:
                    props = await _goto_props(page, page_url(category_url, page_num), scraper)
                except Exception as exc:  # noqa: BLE001 - a timeout ends the walk; saved posts stay saved
                    logger.warning("feed page %d failed (%s); stopping", page_num, exc.__class__.__name__)
                    status = "fetch_failed"
                    break
                counts["pages"] += 1
                if not props.get("self"):
                    status = "logged_out"
                    break
                trees = trees_from_props(props)
                if not trees:
                    empty += 1
                    if empty >= MAX_EMPTY_PAGES:
                        break
                    continue
                empty = 0
                fresh_on_page = 0
                for tree in trees:
                    if counts["new"] + counts["updated"] >= max_posts:
                        break
                    record = _feed_record(tree, group, stamp, since, counts)
                    if not record:
                        continue
                    fresh_on_page += 1
                    old = files.load_raw(record["post_id"])
                    if threads and record.get("url") and needs_thread(old, now, refresh_days):
                        await _pause(scraper)
                        try:
                            detail = await _goto_props(page, record["url"], scraper)
                        except Exception as exc:  # noqa: BLE001 - keep the feed copy, retry next run
                            logger.warning("post page %s failed (%s)", record["post_id"], exc.__class__.__name__)
                            detail = {}
                            counts["thread_errors"] = counts.get("thread_errors", 0) + 1
                        for full in trees_from_props(detail):
                            root = full.get("post") or {}
                            if str(root.get("id")) == record["post_id"]:
                                record = record_from_tree(full, group, stamp, thread_fetched=True) or record
                                counts["threads_read"] += 1
                                break
                    _store(old, record, counts)
                old_pages = old_pages + 1 if (since and fresh_on_page == 0) else 0
                if old_pages >= MAX_OLD_PAGES:
                    break
                await _pause(scraper)
        finally:
            await context.close()
    return {"status": status, "group": group, "category_url": category_url, "counts": counts}


# ------------------------------------------------------- live, via skool-mcp
class McpUnavailable(Exception):
    """node or the skool-mcp client is not on this machine."""


class McpError(Exception):
    """One skool_mcp_fetch.mjs call failed; carries its one-line stderr."""


def find_client() -> Optional[Path]:
    """SKOOL_MCP_CLIENT when set (and then nothing else), else the first
    existing Coding/skool-mcp/dist/client.js. From a worktree the first
    candidate is an empty submodule folder, so the Desktop copy is next."""
    override = os.environ.get("SKOOL_MCP_CLIENT")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    for path in (BASE_DIR.parent / "Coding" / "skool-mcp" / "dist" / "client.js",
                 Path.home() / "Desktop" / "AdveroSolutions" / "Coding" / "skool-mcp" / "dist" / "client.js"):
        if path.is_file():
            return path
    return None


def _node_version(path: Path) -> Tuple[int, ...]:
    """~/.nvm/versions/node/v24.13.1/bin/node -> (24, 13, 1)."""
    return tuple(int(x) for x in re.findall(r"[0-9]+", path.parent.parent.name)[:3])


def find_node() -> Optional[str]:
    """NODE_BIN when set, else node on PATH, else nvm's newest install."""
    override = os.environ.get("NODE_BIN")
    if override:
        return override if Path(override).expanduser().is_file() else None
    found = shutil.which("node")
    if found:
        return found
    installs = sorted(Path.home().glob(".nvm/versions/node/*/bin/node"), key=_node_version)
    return str(installs[-1]) if installs else None


class McpTransport(object):
    """Runs skool_mcp_fetch.mjs once per Skool read. Logs sizes only, never
    what came back."""

    def __init__(self, client: Optional[Path] = None, node: Optional[str] = None,
                 script: Path = MCP_SCRIPT, timeout: int = MCP_TIMEOUT) -> None:
        self.client = client or find_client()
        if not self.client:
            raise McpUnavailable("skool-mcp client not found (build Coding/skool-mcp or set SKOOL_MCP_CLIENT)")
        self.node = node or find_node()
        if not self.node:
            raise McpUnavailable("node not found (install it or set NODE_BIN)")
        self.script = script
        self.timeout = timeout

    def _run(self, args: List[str]) -> Dict[str, Any]:
        argv = [str(self.node), str(self.script), str(self.client)] + [str(a) for a in args]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            raise McpError("%s timed out after %ds" % (args[0], self.timeout))
        except OSError as exc:
            raise McpError("%s could not start node: %s" % (args[0], exc.__class__.__name__))
        if proc.returncode != 0:
            lines = (proc.stderr or "").strip().splitlines()
            raise McpError("%s exit %d: %s" % (args[0], proc.returncode, (lines[-1] if lines else "")[:300]))
        out = proc.stdout or ""
        try:
            data = json.loads(out)
        except ValueError:
            raise McpError("%s returned %d bytes that are not JSON" % (args[0], len(out)))
        if not isinstance(data, dict):
            raise McpError("%s returned JSON that is not an object" % args[0])
        logger.debug("%s: %d bytes", args[0], len(out))
        return data

    def feed(self, group: str, label: str, page: int) -> Dict[str, Any]:
        return self._run(["feed", group, label, str(page)])

    def comments(self, post_id: str, group_id: str) -> Dict[str, Any]:
        return self._run(["comments", post_id, group_id])


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def collect_mcp(category_url: str, max_pages: int = 3, max_posts: int = 40,
                since: Optional[datetime] = None, threads: bool = True,
                refresh_days: int = REFRESH_DAYS, now: Optional[datetime] = None,
                transport: Any = None, sleep: Callable[[float], Any] = time.sleep) -> Dict[str, Any]:
    """Walk the wins category through skool-mcp's client and save one raw
    record per post. Same stop rules and counts as ``collect``."""
    counts = {"pages": 0, "seen": 0, "new": 0, "updated": 0, "threads_read": 0, "skipped_old": 0,
              "threads_partial": 0}
    result = {"status": "ok", "group": None, "category_url": category_url, "via": "mcp",
              "counts": counts}  # type: Dict[str, Any]
    try:
        group = group_from_url(category_url)
    except ValueError as exc:
        result.update(status="bad_url", detail=str(exc))
        return result
    result["group"] = group
    label = label_from_url(category_url)
    if not label:
        result.update(status="bad_url", detail="no c=<category id> in the URL")
        return result
    if transport is None:
        try:
            transport = McpTransport()
        except McpUnavailable as exc:
            result.update(status="mcp_unavailable", detail=str(exc))
            return result
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    calls = [0]

    def pace() -> None:
        if calls[0]:
            sleep(random.uniform(*MCP_PACE))
        calls[0] += 1

    empty = old_pages = 0
    for page_num in range(1, max_pages + 1):
        if counts["new"] + counts["updated"] >= max_posts:
            break
        pace()
        try:
            props = transport.feed(group, label, page_num)
        except Exception as exc:  # noqa: BLE001 - a failed page ends the walk; saved posts stay saved
            logger.warning("feed page %d failed: %s", page_num, exc)
            result["status"] = "fetch_failed"
            break
        counts["pages"] += 1
        if not props.get("self"):
            result["status"] = "logged_out"
            break
        trees = trees_from_props(props)
        logger.info("feed page %d: %d posts", page_num, len(trees))
        if not trees:
            empty += 1
            if empty >= MAX_EMPTY_PAGES:
                break
            continue
        empty = 0
        fresh_on_page = 0
        for tree in trees:
            if counts["new"] + counts["updated"] >= max_posts:
                break
            record = _feed_record(tree, group, stamp, since, counts)
            if not record:
                continue
            fresh_on_page += 1
            old = files.load_raw(record["post_id"])
            group_id = (tree.get("post") or {}).get("groupId")
            if (threads and group_id and _as_int(record.get("comment_count")) > 0
                    and needs_thread(old, now, refresh_days)):
                pace()
                try:
                    payload = transport.comments(record["post_id"], str(group_id))
                except Exception as exc:  # noqa: BLE001 - keep the feed copy, retry next run
                    logger.warning("comments for %s failed: %s", record["post_id"], exc)
                    counts["thread_errors"] = counts.get("thread_errors", 0) + 1
                    payload = None
                if payload is not None:
                    record = record_from_tree(thread_from_api2(tree, payload), group, stamp,
                                              thread_fetched=True) or record
                    counts["threads_read"] += 1
                    if _as_int(payload.get("last")) != 0:
                        record["thread_partial"] = True
                        counts["threads_partial"] += 1
            _store(old, record, counts)
        old_pages = old_pages + 1 if (since and fresh_on_page == 0) else 0
        if old_pages >= MAX_OLD_PAGES:
            break
    return result
