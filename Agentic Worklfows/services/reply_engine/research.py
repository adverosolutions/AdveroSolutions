"""The E2 research step (section 1, P4): one line about the lead's own
business for E2, or NONE, in which case E2 uses the approved fallback line.

    fetch_pages(website, transport=None, resolver=None) -> List[Page]
    html_to_text(html) -> str
    confirm_identity(pages, phone=None, city=None, company_spoken=None) -> (identity | None, reason | None)
    write_line(context, pages, complete=None) -> {"line", "facts", "reasons"}
    check_excerpts(facts, pages) -> List[str]           # reason codes, [] when every excerpt is real
    research_context(state) -> (context, missing)       # research_rules.validate's context
    research_e2(state, now, store, dry_run=False, ...) -> dict

Order: read the lead's website (the home page plus at most two same-site
pages: about / services / areas / locations / contact), confirm by code that
the site is this lead's (the lead's phone on a page, else its city or metro
as a whole word, and the company name on the site), ask shared.llm role
"research" ONCE for strict JSON ``{"line", "facts"}``, check by code that
every excerpt is really on the page it names, then
``research_rules.validate``. Any failure is NONE and E2 uses the fallback
line; nothing here raises to the caller.

Safety of the fetch: read-only GETs, http(s) on the default ports only, the
host must resolve to public addresses only (the resolver is injectable), a
redirect is followed only inside the same registrable domain (at most
MAX_REDIRECTS), TIMEOUT_S per request and FETCH_BUDGET_S for the whole
read, MAX_BYTES per page, an honest
User-Agent, no cookies kept (a fresh client per request) and no proxy from
the environment (the address check is only meaningful on a direct
connection). With LLM_FAKE on and no transport injected nothing is fetched:
an offline rehearsal never reads a real site.

The cache: ``research:<lead email>`` in the engine store holds the outcome
(the model's line and evidence, or why there is none) with the rules_sha and
a hash of the inputs, so a held or retried E2 never pays twice. A cached
line is re-validated before use (pure, cheap); a record written under other
rules or other inputs is ignored. A dry run reads the cache but writes no
key. Nothing is cached when the lead data is missing or the site could not
be read (nothing was paid for; the next try may read it).

E2_RESEARCH_MODE in cadence.py decides whether this runs at all ("fallback",
the default, never calls it). Python 3.9.
"""
import dataclasses
import hashlib
import ipaddress
import json
import logging
import re
import socket
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from shared import llm

from services.reply_engine import research_rules

logger = logging.getLogger("reply_engine.research")

CACHE_PREFIX = "research:"
CACHE_VERSION = 1

# ------------------------------------------------------------ fetch limits
USER_AGENT = ("AdveroResearch/1.0 (+https://theadvero.com; reads a business's own public pages once, "
              "for a personal follow-up email)")
TIMEOUT_S = 6.0
MAX_BYTES = 400000               # per page, after decompression
MAX_REDIRECTS = 3
MAX_EXTRA_PAGES = 2
FETCH_BUDGET_S = 20.0            # for the whole read: no request starts, and no body read goes on, after this
ALLOWED_PORTS = (None, 80, 443)
REDIRECT_CODES = (301, 302, 303, 307, 308)
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
# Link text or path stems that pick the extra pages, in priority order.
LINK_STEMS = ("about", "service", "area", "location", "contact")
LINK_SKIP = ("privacy", "terms", "policy", "login", "log-in", "signin", "sign-in", "cart", "checkout",
             "account", "wp-admin", "feed", "careers")
# Hosts whose mail says nothing about the lead's website.
FREE_MAIL_DOMAINS = ("gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com", "outlook.com",
                     "hotmail.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com", "mac.com",
                     "comcast.net", "att.net", "sbcglobal.net", "verizon.net", "cox.net", "charter.net",
                     "bellsouth.net", "earthlink.net", "protonmail.com", "proton.me", "gmx.com", "mail.com",
                     "zoho.com", "yandex.com")
# When the lead record has no website, the lead's own email domain is read
# instead (B2B leads write from the company's domain). The identity check
# still has to pass on it, so a shared or hosted mail domain gives NONE.
USE_EMAIL_DOMAIN = True
# Second-level labels under a two-letter country code (co.uk, com.au): the
# registrable domain is then the last three labels.
_CC_SLD = ("co", "com", "net", "org", "gov", "edu", "ac")

# ------------------------------------------------------------ model limits
MAX_PROMPT_CHARS_PER_PAGE = 6000
MAX_TOKENS = 600
MAX_EXCERPT_CHARS = 400

_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")
_QUOTES = {"’": "'", "‘": "'", "“": '"', "”": '"'}


@dataclasses.dataclass
class Page(object):
    url: str                                   # the final URL, after redirects
    text: str                                  # visible text, whitespace collapsed
    links: List[Tuple[str, str]] = dataclasses.field(default_factory=list)   # (absolute url, link text)
    phones: List[str] = dataclasses.field(default_factory=list)              # 10-digit numbers on the page


# --------------------------------------------------------------- HTML to text
_SKIP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "object", "canvas", "select")
_BLOCK_TAGS = ("address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "fieldset",
               "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
               "li", "main", "nav", "ol", "p", "pre", "section", "table", "tbody", "td", "tfoot", "th",
               "thead", "title", "tr", "ul", "button", "label", "option")


class _PageParser(HTMLParser):
    """Visible text (scripts, styles and the like dropped), the links with
    their text, and tel: numbers. Block tags separate words."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts = []  # type: List[str]
        self.links = []  # type: List[Tuple[str, str]]
        self.tels = []  # type: List[str]
        self._skip = 0
        self._href = None  # type: Optional[str]
        self._link_text = []  # type: List[str]

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")
        if tag == "a":
            href = dict(attrs).get("href")
            if isinstance(href, str) and href.strip().lower().startswith("tel:"):
                self.tels.append(href.strip()[4:])
            self._href = href if isinstance(href, str) else None
            self._link_text = []

    def handle_startendtag(self, tag, attrs):
        if not self._skip and tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._link_text).split())))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._href is not None:
            self._link_text.append(data)


def _parse_html(html: str) -> _PageParser:
    parser = _PageParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception as exc:  # noqa: BLE001 - a page that does not parse is what was parsed so far
        logger.info("research: HTML parse stopped early: %s", type(exc).__name__)
    return parser


def html_to_text(html: str) -> str:
    """The visible text of ``html``: scripts, styles, templates and the like
    dropped, entities decoded, all whitespace collapsed to single spaces."""
    return " ".join("".join(_parse_html(html).parts).split())


def _phones_in(text: str, tels: List[str]) -> List[str]:
    out = []  # type: List[str]
    for raw in [m.group(0) for m in _PHONE_RE.finditer(text or "")] + list(tels or []):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10 and digits[-10:] not in out:
            out.append(digits[-10:])
    return out


def _page(url: str, body: str, is_html: bool) -> Page:
    if not is_html:
        text = " ".join((body or "").split())
        return Page(url=url, text=text, links=[], phones=_phones_in(text, []))
    parser = _parse_html(body)
    text = " ".join("".join(parser.parts).split())
    links = []  # type: List[Tuple[str, str]]
    for href, label in parser.links:
        try:
            absolute = urljoin(url, href.strip())
        except ValueError:
            continue
        links.append((absolute, label))
    return Page(url=url, text=text, links=links, phones=_phones_in(text, parser.tels))


# ------------------------------------------------------------ URL safety
def _bare(host: Optional[str]) -> str:
    host = (host or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _registrable(host: str) -> str:
    labels = _bare(host).split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _CC_SLD:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _system_resolver(host: str) -> List[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return []
    return sorted(set(str(info[4][0]) for info in infos))


def _public_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(text).split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(ip.is_global) and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                                       or ip.is_multicast or ip.is_unspecified)


def url_refusal(url: str, resolver: Callable[[str], List[str]], base: Optional[str] = None) -> Optional[str]:
    """Why ``url`` may not be fetched, or None. ``base``: the registrable
    domain the fetch started on; a URL outside it is refused (off_site)."""
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
    except ValueError:
        return "bad_url"
    if parts.scheme.lower() not in ("http", "https"):
        return "scheme"
    if parts.username or parts.password or "@" in parts.netloc:
        return "credentials_in_url"
    if port not in ALLOWED_PORTS:
        return "port"
    if not host:
        return "no_host"
    host = host.lower().rstrip(".")
    if base is not None and _registrable(host) != base:
        return "off_site"
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return None if _public_ip(host) else "private_address"
    if "." not in host or host.endswith((".local", ".localhost", ".internal", ".lan", ".home.arpa")):
        return "private_address"
    try:
        addresses = list(resolver(host) or [])
    except Exception:  # noqa: BLE001 - a resolver that fails resolves nothing
        addresses = []
    if not addresses:
        return "unresolved"
    if not all(_public_ip(a) for a in addresses):
        return "private_address"
    return None


def _start_urls(website: Any) -> List[str]:
    """The URLs to try for the home page: as given when it has a scheme,
    else https then http. [] when it is not a usable http(s) website."""
    if not isinstance(website, str) or not website.strip():
        return []
    text = website.strip()
    if "://" in text:
        return [text] if text.lower().startswith(("http://", "https://")) else []
    if text.startswith("//"):
        text = text[2:]
    return ["https://" + text, "http://" + text]


def website_domain(website: Any) -> Optional[str]:
    """"https://www.Example.com/about" -> "example.com"; None when unusable."""
    urls = _start_urls(website)
    if not urls:
        return None
    try:
        host = urlsplit(urls[0]).hostname
    except ValueError:
        return None
    host = _bare(host)
    if not host or "." not in host:
        return None
    try:
        ipaddress.ip_address(host)
        return None          # a bare address is not a business website
    except ValueError:
        return host


# ------------------------------------------------------------------ fetch
def _one_get(url: str, transport: Any, deadline: Optional[float] = None,
             clock: Callable[[], float] = time.monotonic) -> Tuple[int, Optional[str], str, Optional[str]]:
    """(status, location, content type, text) of one GET, no redirect
    followed. The body read stops at MAX_BYTES or at ``deadline``."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5"}
    with httpx.Client(transport=transport, timeout=TIMEOUT_S, follow_redirects=False, trust_env=False,
                      headers=headers) as client:
        with client.stream("GET", url) as resp:
            status = resp.status_code
            ctype = (resp.headers.get("content-type") or "").lower()
            if status in REDIRECT_CODES:
                return status, resp.headers.get("location"), ctype, None
            if status != 200 or not any(t in ctype for t in TEXT_TYPES):
                return status, None, ctype, None
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) >= MAX_BYTES or (deadline is not None and clock() > deadline):
                    break
            raw = bytes(buf[:MAX_BYTES])
            try:
                text = raw.decode(resp.charset_encoding or "utf-8", errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return status, None, ctype, text


def _get_page(url: str, transport: Any, resolver: Callable[[str], List[str]], base: str,
              deadline: Optional[float] = None, clock: Callable[[], float] = time.monotonic) -> Optional[Page]:
    for _hop in range(MAX_REDIRECTS + 1):
        if deadline is not None and clock() > deadline:
            logger.info("research: out of time before %s", _host_for_log(url))
            return None
        why = url_refusal(url, resolver, base)
        if why:
            logger.info("research: not fetching %s (%s)", _host_for_log(url), why)
            return None
        status, location, ctype, text = _one_get(url, transport, deadline, clock)
        if status in REDIRECT_CODES:
            if not location:
                return None
            url = urljoin(url, location.strip())
            continue
        if status != 200 or text is None:
            logger.info("research: %s answered %s (%s)", _host_for_log(url), status, ctype or "no type")
            return None
        return _page(_canonical(url), text, is_html="html" in ctype)
    logger.info("research: too many redirects from %s", _host_for_log(url))
    return None


def _host_for_log(url: str) -> str:
    try:
        return urlsplit(url).hostname or "?"
    except ValueError:
        return "?"


def _canonical(url: str) -> str:
    """Scheme and host lowercased, fragment dropped: how a page is named to
    the model and matched against the source_url it gives back."""
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def _url_key(url: Any) -> Optional[str]:
    """What two URLs are compared on: host without www, path without a
    trailing slash, the query; scheme and fragment ignored."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        p = urlsplit(url.strip())
        host = _bare(p.hostname)
    except ValueError:
        return None
    if not host or p.scheme.lower() not in ("http", "https"):
        return None
    return "%s%s%s" % (host, p.path.rstrip("/") or "", ("?" + p.query) if p.query else "")


def _pick_links(home: Page) -> List[str]:
    """At most MAX_EXTRA_PAGES same-site links, one per LINK_STEMS stem in
    that order, by the link's text or path."""
    home_host = _bare(urlsplit(home.url).hostname)
    home_key = _url_key(home.url)
    candidates = []  # type: List[Tuple[str, str]]
    for url, label in home.links:
        try:
            p = urlsplit(url)
        except ValueError:
            continue
        if p.scheme.lower() not in ("http", "https") or _bare(p.hostname) != home_host:
            continue
        clean = urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))
        if _url_key(clean) == home_key:
            continue
        hay = ("%s %s" % (p.path, label)).lower()
        if any(s in hay for s in LINK_SKIP):
            continue
        candidates.append((clean, hay))
    picked = []  # type: List[str]
    for stem in LINK_STEMS:
        for clean, hay in candidates:
            if stem in hay and clean not in picked and _url_key(clean) not in [_url_key(u) for u in picked]:
                picked.append(clean)
                break
        if len(picked) >= MAX_EXTRA_PAGES:
            break
    return picked


def fetch_pages(website: Any, transport: Any = None, resolver: Optional[Callable[[str], List[str]]] = None,
                clock: Callable[[], float] = time.monotonic) -> List[Page]:
    """Read-only GETs of the lead's own site: the home page, then at most
    MAX_EXTRA_PAGES same-site pages (about / services / areas / locations /
    contact). Never raises: returns what was fetched so far, possibly []."""
    pages = []  # type: List[Page]
    starts = _start_urls(website)
    if not starts:
        return pages
    if transport is None and llm.is_fake():
        logger.info("research: LLM_FAKE is on and no transport was given, so no page is read")
        return pages
    resolver = resolver or _system_resolver
    try:
        base = _registrable(urlsplit(starts[0]).hostname or "")
        deadline = clock() + FETCH_BUDGET_S
        home = None
        for url in starts:
            try:
                home = _get_page(url, transport, resolver, base, deadline, clock)
            except Exception as exc:  # noqa: BLE001 - a failed scheme tries the next one
                logger.info("research: %s failed: %s", _host_for_log(url), type(exc).__name__)
                home = None
            if home is not None:
                break
        if home is None:
            return pages
        pages.append(home)
        for url in _pick_links(home):
            if clock() > deadline:
                break
            page = _get_page(url, transport, resolver, base, deadline, clock)
            if page is not None and _url_key(page.url) not in [_url_key(p.url) for p in pages]:
                pages.append(page)
    except Exception as exc:  # noqa: BLE001 - what was read so far is the answer
        logger.info("research: fetch stopped: %s", type(exc).__name__)
    return pages


# --------------------------------------------------------------- identity
def _digits10(phone: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits[-10:] if len(digits) >= 10 else None


def _city_forms(city: Any) -> List[str]:
    text = " ".join(str(city or "").split())
    forms = [text] if len(text) >= 3 else []
    head = text.split(",", 1)[0].strip()
    if len(head) >= 3 and head not in forms:
        forms.append(head)
    return forms


def _whole_word(needle: str, text: str) -> bool:
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])", text or "", re.I) is not None


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _name_key(company_spoken: Any) -> Optional[str]:
    """The run of letters the company's name must show on its site: its
    first word when that has 4 or more characters, else its first two words
    ("cjsglobal"), "the" skipped. Punctuation and case are ignored."""
    words = re.findall(r"[a-z0-9]+", str(company_spoken or "").lower().replace("'", "").replace("’", ""))
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    if not words:
        return None
    key = words[0] if (len(words[0]) >= 4 or len(words) == 1) else words[0] + words[1]
    return key if len(key) >= 3 else None


def confirm_identity(pages: List[Page], phone: Any = None, city: Any = None,
                     company_spoken: Any = None) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """(identity, None) when the site is this lead's, else (None, reason).

    By code, never by the model: the lead's phone (last 10 digits) on a
    fetched page gives ``matched_on "phone"``; else the lead's city or metro
    as a whole word gives ``"city"``. And the company's name must be on the
    site (``name_not_on_site``). Nothing to match on is
    ``identity_unconfirmed``."""
    if not pages:
        return None, "site_unreadable"
    found = None  # type: Optional[Dict[str, str]]
    digits = _digits10(phone)
    if digits:
        for page in pages:
            if digits in page.phones:
                found = {"source_url": page.url, "matched_on": "phone"}
                break
    if found is None:
        for form in _city_forms(city):
            for page in pages:
                if _whole_word(form, page.text):
                    found = {"source_url": page.url, "matched_on": "city"}
                    break
            if found is not None:
                break
    if found is None:
        return None, "identity_unconfirmed"
    key = _name_key(company_spoken)
    if key is None or not any(key in _alnum(p.text) for p in pages):
        return None, "name_not_on_site"
    return found, None


# ------------------------------------------------------------- the model
def load_prompt() -> str:
    from services.reply_engine import cadence

    return cadence._load_template("research")


def _model_input(context: Dict[str, Any], pages: List[Page]) -> str:
    return json.dumps({
        "company": context.get("company_spoken"),
        "company_on_record": context.get("company"),
        "city": context.get("city"),
        "niche": context.get("niche"),
        "offer": context.get("offer_branch"),
        "pages": [{"url": p.url, "text": p.text[:MAX_PROMPT_CHARS_PER_PAGE]} for p in pages],
    }, ensure_ascii=False)


def parse_model_output(out: Any) -> Dict[str, Any]:
    """{"line": str or None, "facts": [...], "reasons": [...]} from what the
    model returned. Anything but the agreed shape is NONE (model_malformed);
    the word NONE is NONE (model_none)."""
    none = {"line": None, "facts": [], "reasons": ["model_malformed"]}
    if not isinstance(out, dict):
        return none
    line = out.get("line")
    if not isinstance(line, str):
        return none
    if re.fullmatch(r"\s*none\W*\s*", line, re.I) or not line.strip():
        return {"line": None, "facts": [], "reasons": ["model_none"]}
    raw = out.get("facts")
    if not isinstance(raw, list) or not 1 <= len(raw) <= research_rules.MAX_FACTS:
        return none
    facts = []  # type: List[Dict[str, str]]
    for item in raw:
        if not isinstance(item, dict):
            return none
        fact = {}
        for key in ("text", "source_url", "excerpt"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                return none
            fact[key] = value
        if len(fact["excerpt"]) > MAX_EXCERPT_CHARS:
            return none
        facts.append(fact)
    return {"line": line, "facts": facts, "reasons": []}


def write_line(context: Dict[str, Any], pages: List[Page], complete: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """One shared.llm role "research" call with prompts/cadence_research.md;
    the model returns strict JSON {"line": str or "NONE", "facts": [...]}.
    Returns parse_model_output's dict; a model error is NONE (model_error)."""
    fn = complete or llm.complete
    try:
        out = fn("research", load_prompt(), _model_input(context, pages), max_tokens=MAX_TOKENS, json_mode=True)
    except Exception as exc:  # noqa: BLE001 - no line is NONE, never an exception
        logger.warning("research: the model call failed: %s", type(exc).__name__)
        return {"line": None, "facts": [], "reasons": ["model_error"]}
    return parse_model_output(out)


def _norm(text: str) -> str:
    for a, b in _QUOTES.items():
        text = text.replace(a, b)
    return " ".join((text or "").split())


def check_excerpts(facts: List[Dict[str, str]], pages: List[Page]) -> List[str]:
    """Reason codes, [] when every fact's source_url is a fetched page and
    its excerpt is verbatim (whitespace and curly quotes normalised) in that
    page's text. The P1 validator trusts excerpts; this is what makes them real."""
    by_key = {}  # type: Dict[str, Page]
    for page in pages:
        by_key.setdefault(_url_key(page.url) or "", page)
    reasons = []  # type: List[str]
    for fact in facts:
        page = by_key.get(_url_key(fact.get("source_url")) or "\0")
        if page is None:
            reasons.append("source_not_fetched")
            continue
        excerpt = _norm(fact.get("excerpt") or "")
        if not excerpt or excerpt not in _norm(page.text):
            reasons.append("excerpt_not_on_page")
    return list(dict.fromkeys(reasons))


# ------------------------------------------------------- the lead's data
_DICT_ATTRS = ("payload", "custom_variables", "lead")


def _lead_value(state: Any, *names: str) -> Optional[str]:
    """The first non-empty ``names`` value on the state, else in a dict the
    state carries (payload / custom_variables / lead, one level deep plus a
    nested custom_variables). No network: only what the engine already has."""
    for name in names:
        value = getattr(state, name, None)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    for attr in _DICT_ATTRS:
        blob = getattr(state, attr, None)
        if not isinstance(blob, dict):
            continue
        for d in (blob, blob.get("custom_variables") if isinstance(blob.get("custom_variables"), dict) else {}):
            for name in names:
                value = d.get(name)
                if isinstance(value, (str, int)) and str(value).strip():
                    return str(value).strip()
    return None


def lead_inputs(state: Any) -> Dict[str, Any]:
    """What the step reads about the lead: the website (the record's, else
    the email domain when USE_EMAIL_DOMAIN and it is not a free-mail
    domain), its bare domain, the phone and the city (or metro)."""
    website = _lead_value(state, "website", "company_website", "company_domain")
    source = "record" if website_domain(website) else None
    if source is None:
        website = None
        email = str(getattr(state, "lead_email", "") or "").strip().lower()
        domain = email.rsplit("@", 1)[1] if "@" in email else ""
        if USE_EMAIL_DOMAIN and website_domain(domain) and domain not in FREE_MAIL_DOMAINS:
            website, source = domain, "email_domain"
    return {
        "website": website,
        "website_domain": website_domain(website) if website else None,
        "website_source": source,
        "phone": _lead_value(state, "phone", "company_phone", "phone_number"),
        "city": _lead_value(state, "city", "metro"),
    }


def research_context(state: Any) -> Tuple[Dict[str, Any], List[str]]:
    """(context, missing): research_rules.validate's context for this lead,
    and the required keys it lacks. ``company`` is the record's name,
    ``company_spoken`` the form E2 says (cadence.spoken_company); ``city`` is
    the lead's city or metro, or None."""
    from services.reply_engine import cadence

    company = cadence.known_company(state)
    spoken = cadence.spoken_company(company) if company else None
    inputs = lead_inputs(state)
    context = {
        "company": company,
        "company_spoken": spoken or None,
        "offer_branch": cadence.lead_offer(state),
        "niche": cadence.lead_niche(state),
        "website_domain": inputs["website_domain"],
        "city": inputs["city"],
    }
    missing = [k for k in ("company", "company_spoken", "offer_branch", "niche", "website_domain") if not context[k]]
    return context, missing


# ----------------------------------------------------------------- cache
def cache_key(state: Any) -> Optional[str]:
    email = str(getattr(state, "lead_email", "") or "").strip().lower()
    return (CACHE_PREFIX + email) if email else None


def _inputs_sha(context: Dict[str, Any], inputs: Dict[str, Any]) -> str:
    blob = json.dumps({"context": context, "website": inputs.get("website"),
                       "phone": _digits10(inputs.get("phone"))}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _usable_record(record: Any, sha: str, inputs_sha: str) -> bool:
    return (isinstance(record, dict) and record.get("v") == CACHE_VERSION and record.get("rules_sha") == sha
            and record.get("inputs_sha") == inputs_sha)


# ------------------------------------------------------------- the step
def _result(fallback: Optional[str], reasons: List[str], **extra: Any) -> Dict[str, Any]:
    out = {"line": fallback, "evidence": None, "verdict": None, "source": "fallback",
           "reasons": list(dict.fromkeys(reasons)), "context": None, "cached": False, "model_called": False,
           "model_line": None}  # type: Dict[str, Any]
    out.update(extra)
    return out


def _judge(line: Optional[str], evidence: Optional[Dict[str, Any]], context: Dict[str, Any],
           fallback: Optional[str], reasons: List[str], **extra: Any) -> Dict[str, Any]:
    """The verdict on a model line with its evidence: researched when it
    passes, else the fallback with the validator's reasons."""
    if not line or not isinstance(evidence, dict):
        return _result(fallback, reasons or ["model_none"], context=context, **extra)
    verdict = research_rules.validate(line, evidence, context)
    if not verdict.ok:
        return _result(fallback, list(reasons) + list(verdict.reasons), context=context, verdict=verdict,
                       evidence=evidence, **extra)
    return _result(verdict.line, [], context=context, verdict=verdict, evidence=evidence, source="researched",
                   **extra)


def research_e2(state: Any, now: Optional[datetime], store: Any, dry_run: bool = False, transport: Any = None,
                resolver: Optional[Callable[[str], List[str]]] = None,
                complete: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """E2's research line for ``state``. Never raises.

    Returns {"line", "evidence", "verdict", "source", "reasons", "context",
    "cached", "model_called", "model_line"}: ``source`` "researched" with
    ``line`` the validated line and ``evidence`` the facts and identity, or
    "fallback" with ``line`` the approved fallback line for the offer
    (cadence.fallback_research_line; None when the offer is unknown) and
    ``reasons`` saying why. ``verdict`` is research_rules.validate's, None
    when no line got that far."""
    from services.reply_engine import cadence

    offer = None
    fallback = None
    try:
        offer = cadence.lead_offer(state)
        fallback = cadence.fallback_research_line("", offer) if offer else None
        return _research(state, now, store, dry_run, transport, resolver, complete, fallback)
    except Exception as exc:  # noqa: BLE001 - research never blocks E2: the fallback goes instead
        logger.warning("research: unexpected failure, using the fallback line: %s", type(exc).__name__)
        return _result(fallback, ["research_error"])


def _research(state: Any, now: Optional[datetime], store: Any, dry_run: bool, transport: Any, resolver: Any,
              complete: Any, fallback: Optional[str]) -> Dict[str, Any]:
    context, missing = research_context(state)
    key = cache_key(state)
    if missing or key is None:
        return _result(fallback, ["missing_lead_data:%s" % ",".join(missing or ["lead_email"])], context=context)
    inputs = lead_inputs(state)
    sha = research_rules.rules_sha()
    inputs_sha = _inputs_sha(context, inputs)

    if store is not None:
        try:
            record = store.get(key)
        except Exception as exc:  # noqa: BLE001 - unknown whether it was paid for: do not pay again
            logger.warning("research: cache read failed for %s: %s", key, type(exc).__name__)
            return _result(fallback, ["cache_error"], context=context)
        if _usable_record(record, sha, inputs_sha):
            return _judge(record.get("line"), record.get("evidence"), context, fallback,
                          list(record.get("reasons") or []), cached=True,
                          model_called=bool(record.get("model_called")), model_line=record.get("line"))

    pages = fetch_pages(inputs["website"], transport=transport, resolver=resolver)
    if not pages:
        return _result(fallback, ["site_unreadable"], context=context)   # not cached: nothing was paid for

    record = {"v": CACHE_VERSION, "rules_sha": sha, "inputs_sha": inputs_sha,
              "at": now.isoformat() if isinstance(now, datetime) else None,
              "website_source": inputs["website_source"], "pages": [p.url for p in pages],
              "line": None, "evidence": None, "reasons": [], "model_called": False}
    identity, why = confirm_identity(pages, inputs["phone"], inputs["city"], context["company_spoken"])
    if identity is None:
        record["reasons"] = [why or "identity_unconfirmed"]
    else:
        written = write_line(context, pages, complete=complete)
        record["model_called"] = True
        record["reasons"] = list(written["reasons"])
        if written["line"]:
            problems = check_excerpts(written["facts"], pages)
            evidence = {"facts": written["facts"], "identity": identity}
            record["line"], record["evidence"] = written["line"], evidence
            if problems:
                record["reasons"] = problems
                record["line"] = None           # an invented excerpt is never re-judged
                record["model_line"] = written["line"]

    result = _judge(record["line"], record["evidence"], context, fallback, list(record["reasons"]),
                    model_called=record["model_called"], model_line=record.get("model_line") or record["line"])
    if store is not None and not dry_run:
        try:
            store.set(key, record)
        except Exception as exc:  # noqa: BLE001 - a line whose cache failed is not used (it could be paid again)
            logger.warning("research: cache write failed for %s: %s", key, type(exc).__name__)
            return _result(fallback, list(result["reasons"]) + ["cache_write_failed"], context=context,
                           model_called=record["model_called"], model_line=result.get("model_line"))
    return result
