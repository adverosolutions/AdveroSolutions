"""Strict, data-only sales demonstration schema (Python 3.9+)."""
import base64
import binascii
import copy
import math
import re

OPENING = "I've already put this workflow together for you. Let me walk you through how it works."
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s*\}\}")
MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>|javascript\s*:|data\s*:\s*(?:text|application)/", re.I)


class ValidationError(ValueError):
    pass


def fail(path, message):
    raise ValidationError("{}: {}".format(path, message))


def obj(value, path, required, optional=()):
    if not isinstance(value, dict):
        fail(path, "expected object")
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    if missing:
        fail(path, "missing " + ", ".join(sorted(missing)))
    if extra:
        fail(path, "unknown fields " + ", ".join(sorted(extra)))
    return value


def text(value, path, empty=False, private=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        fail(path, "expected nonempty text")
    limit = 20000 if private else 240 if path in ("title", "systemName") else 800 if path.endswith((".body", ".definition", ".beat")) else 120 if path.endswith((".title", ".accent", ".name", ".subject")) else 80 if path.endswith(".label") else 240 if path.endswith(".value") else 600
    if len(value) > limit or "\x00" in value:
        fail(path, "text exceeds {} characters or contains NUL".format(limit))
    if not private and MARKUP.search(value):
        fail(path, "markup and executable URLs are not permitted")
    return value.strip()


def texts(value, path, minimum=0, maximum=50):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail(path, "expected list with {}..{} entries".format(minimum, maximum))
    return [text(v, "{}[{}]".format(path, i)) for i, v in enumerate(value)]


def rows(value, path, keys, optional=(), minimum=0, maximum=50):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail(path, "expected list with {}..{} entries".format(minimum, maximum))
    result = []
    for i, row in enumerate(value):
        p = "{}[{}]".format(path, i)
        obj(row, p, keys, optional)
        result.append({k: text(v, p + "." + k) for k, v in row.items()})
    return result


def slug(value, path):
    if not isinstance(value, str) or len(value) > 80 or not SLUG.fullmatch(value):
        fail(path, "expected safe lowercase slug, at most 80 characters")
    return value


def entity_tree(value, path="entities", depth=0):
    if depth > 12 or not isinstance(value, dict):
        fail(path, "expected nested object, maximum depth 12")
    for k, v in value.items():
        if not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z0-9_]+", k):
            fail(path, "invalid entity key")
        if isinstance(v, dict):
            entity_tree(v, path + "." + k, depth + 1)
        elif isinstance(v, str):
            text(v, path + "." + k)
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            fail(path + "." + k, "entity must be text or finite number")
        elif isinstance(v, int):
            # Compare integers directly: converting a huge JSON integer to float
            # can raise OverflowError before the job's validation can finish.
            if abs(v) > 2 ** 53 - 1:
                fail(path + "." + k, "entity integer exceeds the exact browser number range")
        elif not math.isfinite(v):
            fail(path + "." + k, "entity must be text or finite number")


def resolve(data, entities):
    def lookup(match, trail):
        key = match.group(1)
        if key in trail:
            fail("entities", "cyclic reference " + key)
        value = entities
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                fail("entities", "unresolved token " + key)
            value = value[part]
        if isinstance(value, dict):
            fail("entities", "token points to an object: " + key)
        return render(str(value), trail + (key,))

    def render(value, trail=()):
        value = TOKEN.sub(lambda m: lookup(m, trail), value)
        if "{{" in value or "}}" in value:
            fail("text", "unresolved or malformed entity token")
        return value

    def walk(value):
        if isinstance(value, str):
            return render(value).strip()
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value
    return walk(data)


def validate(spec, catalog):
    """Return normalized private spec; reject all unrecognized fields."""
    obj(spec, "job", ("schemaVersion", "id", "title", "systemName", "account", "source", "entities", "cover", "scenes", "close"), ("personalization",))
    if type(spec["schemaVersion"]) is not int or spec["schemaVersion"] != 1:
        fail("schemaVersion", "only version 1 is supported")
    entity_tree(spec["entities"])
    s = resolve(copy.deepcopy(spec), spec["entities"])
    slug(s["id"], "id")
    for k in ("title", "systemName"):
        s[k] = text(s[k], k)
    obj(s["account"], "account", ("name", "initials", "operatorInitials"))
    for k, v in s["account"].items():
        s["account"][k] = text(v, "account." + k)
    obj(s["source"], "source", ("jobUrl", "facts"))
    text(s["source"]["jobUrl"], "source.jobUrl", private=True)
    if not isinstance(s["source"]["facts"], list):
        fail("source.facts", "expected list")
    for v in s["source"]["facts"]:
        text(v, "source.facts", private=True)
    if "personalization" in s:
        p = s["personalization"]
        obj(p, "personalization", ("firstName", "source", "reviewCount"))
        text(p["firstName"], "personalization.firstName")
        if not re.fullmatch(r"[^\W\d_]+(?:['-][^\W\d_]+)*", p["firstName"], re.U):
            fail("personalization.firstName", "expected one person's first name")
        if p["source"] not in ("supplied", "post", "client_reviews"):
            fail("personalization.source", "expected supplied, post or client_reviews")
        if type(p["reviewCount"]) is not int or p["reviewCount"] < 0:
            fail("personalization.reviewCount", "expected nonnegative integer")
        if p["source"] == "client_reviews" and p["reviewCount"] < 2:
            fail("personalization", "requires at least two unambiguous separate review entries")
    c = s["cover"]
    obj(c, "cover", ("eyebrow", "title", "accent", "caption", "anchors", "previewSteps", "footer", "beat"))
    for k in ("eyebrow", "title", "accent", "caption", "footer", "beat"):
        c[k] = text(c[k], "cover." + k)
    if c["caption"] != OPENING:
        fail("cover.caption", "must match the approved opening exactly")
    c["anchors"] = texts(c["anchors"], "cover.anchors", 1, 5)
    c["previewSteps"] = rows(c["previewSteps"], "cover.previewSteps", ("title", "detail"), minimum=1, maximum=5)
    c = s["close"]
    obj(c, "close", ("eyebrow", "title", "accent", "caption", "metrics", "baselineNote", "ctaTitle", "ctaCopy", "beat"))
    for k in ("eyebrow", "title", "accent", "caption", "baselineNote", "ctaTitle", "ctaCopy", "beat"):
        c[k] = text(c[k], "close." + k)
    c["metrics"] = rows(c["metrics"], "close.metrics", ("name", "direction", "aim", "definition"), minimum=3, maximum=3)
    for m in c["metrics"]:
        if m["direction"] not in ("up", "down"):
            fail("close.metrics.direction", "expected up or down")
        if re.search(r"\d|%", m["aim"]):
            fail("close.metrics.aim", "use directional aims, not numerical improvement promises")
    scenes = s["scenes"]
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 20:
        fail("scenes", "expected 2..20 scenes")
    ids = set()
    for i, scene in enumerate(scenes):
        p = "scenes[{}]".format(i)
        obj(scene, p, ("id", "kind", "platform", "title", "caption", "beat", "details", "optional", "content", "statuses"))
        sid = slug(scene["id"], p + ".id")
        if sid in ids or sid in ("cover", "close"):
            fail(p + ".id", "duplicate or reserved scene id")
        ids.add(sid)
        if type(scene["optional"]) is not bool:
            fail(p + ".optional", "expected boolean")
        for k in ("title", "caption", "beat"):
            scene[k] = text(scene[k], p + "." + k)
        scene["details"] = texts(scene["details"], p + ".details", 1)
        scene["statuses"] = texts(scene["statuses"], p + ".statuses", 1, 12)
        text(scene["kind"], p + ".kind")
        text(scene["platform"], p + ".platform")
        platform = catalog.get("platforms", {}).get(scene["platform"])
        if not platform or platform.get("status") != "supported":
            fail(p + ".platform", "requires_adapter: unsupported platform " + str(scene["platform"]))
        content(scene, platform, p)
    if scenes[0]["kind"] != "workflow" or scenes[0]["optional"]:
        fail("scenes", "first scene must be a required workflow")
    results = [x for x in scenes if x["kind"] in ("outcome", "workshop", "carousel") and not x["optional"]]
    if not results:
        fail("scenes", "requires a visible result/proof scene on every route")
    return s


def content(scene, platform, path):
    c, kind = scene["content"], scene["kind"]
    p = path + ".content"
    shared = ("name", "subtitle")
    compatible = {
        "ghl": ("workflow", "record", "messages", "outcome", "workshop"),
        "n8n": ("workflow",), "make": ("workflow",),
        "workbench": ("record", "messages", "outcome", "carousel"),
        "claude-code": ("workflow", "record", "messages", "outcome"),
        "codex": ("workflow", "record", "messages", "outcome"),
    }
    if kind not in compatible.get(scene["platform"], ()):
        fail(path, "requires_adapter: unsupported scene/platform combination")
    if kind == "workflow":
        obj(c, p, ("name", "nodes", "edges", "runOrder", "context", "related"))
        text(c["name"], p + ".name")
        nodes = rows(c["nodes"], p + ".nodes", ("id", "type", "label", "detail"), minimum=2, maximum=12)
        ids = [n["id"] for n in nodes]
        if len(set(ids)) != len(ids):
            fail(p + ".nodes", "duplicate node ids")
        for n in nodes:
            slug(n["id"], p + ".nodes.id")
            action = platform.get("actions", {}).get(n["type"])
            if not action or action.get("available") is not True:
                fail(p + ".nodes.type", "unsupported action " + n["type"] + ": " + (action or {}).get("reason", "requires_adapter"))
        edges = rows(c["edges"], p + ".edges", ("from", "to"), ("label",), minimum=1, maximum=30)
        adjacency = {n: [] for n in ids}
        pairs = set()
        for e in edges:
            pair = (e["from"], e["to"])
            if any(n not in adjacency for n in pair) or pair in pairs:
                fail(p + ".edges", "invalid or duplicate edge")
            pairs.add(pair)
            adjacency[pair[0]].append(pair[1])
        visiting, visited = set(), set()
        def visit(n):
            if n in visiting:
                fail(p + ".edges", "graph must be acyclic")
            if n in visited:
                return
            visiting.add(n)
            for nxt in adjacency[n]:
                visit(nxt)
            visiting.remove(n)
            visited.add(n)
        for n in ids:
            visit(n)
        for n in nodes:
            if scene["platform"] == "n8n" and n["type"] == "if":
                outgoing = [e for e in edges if e["from"] == n["id"]]
                if len(outgoing) > 2 or any(e.get("label", "").lower() not in ("true", "false") for e in outgoing) or len({e.get("label", "").lower() for e in outgoing}) != len(outgoing):
                    fail(p + ".edges", "n8n If requires at most two distinct true/false output labels")
        indegree = {n: 0 for n in ids}
        for a, b in pairs:
            indegree[b] += 1
        starts = [n for n in ids if indegree[n] == 0]
        triggers = [n["id"] for n in nodes if platform["actions"][n["type"]]["kind"] == "trigger"]
        if len(starts) != 1 or triggers != starts:
            fail(p + ".nodes", "requires one trigger at the graph root")
        reachable = set()
        def reach(n):
            if n in reachable:
                return
            reachable.add(n)
            for nxt in adjacency[n]:
                reach(nxt)
        reach(starts[0])
        if reachable != set(ids):
            fail(p + ".nodes", "all nodes must be reachable from the trigger")
        order = texts(c["runOrder"], p + ".runOrder", 2, 12)
        if order[0] != starts[0]:
            fail(p + ".runOrder", "sample path must start at the trigger")
        if adjacency.get(order[-1]):
            fail(p + ".runOrder", "sample path must end at a terminal result")
        if len(set(order)) != len(order) or any(n not in adjacency for n in order):
            fail(p + ".runOrder", "must contain unique existing node ids")
        if any((a, b) not in pairs for a, b in zip(order, order[1:])):
            fail(p + ".runOrder", "sample path must follow edges")
        if scene["platform"] in ("claude-code", "codex"):
            if len(order) != len(ids) or len(edges) != len(ids) - 1 or any(len(adjacency[n]) > 1 for n in ids):
                fail(p, "agent transcript requires one linear chain containing every task stage")
        if len(scene["statuses"]) != len(order):
            fail(path + ".statuses", "one status required per runOrder step")
        ctx = c["context"]
        obj(ctx, p + ".context", ("name", "subtitle", "fields", "states"))
        for k in shared:
            text(ctx[k], p + ".context." + k)
        rows(ctx["fields"], p + ".context.fields", ("label", "value"))
        texts(ctx["states"], p + ".context.states", 1, 12)
        if len(ctx["states"]) != len(order):
            fail(p + ".context.states", "one state required per runOrder step")
        rows(c["related"], p + ".related", ("title", "detail"))
    elif kind == "record":
        obj(c, p, shared + ("sourceTitle", "sourceFields", "fields", "events", "notice"))
        rows(c["sourceFields"], p + ".sourceFields", ("label", "value"))
        rows(c["fields"], p + ".fields", ("label", "value"))
        rows(c["events"], p + ".events", ("title", "detail"), minimum=1)
        text(c["sourceTitle"], p + ".sourceTitle")
        text(c["notice"], p + ".notice")
    elif kind == "messages":
        obj(c, p, shared + ("fields", "items", "notice"))
        rows(c["fields"], p + ".fields", ("label", "value"))
        items = rows(c["items"], p + ".items", ("channel", "direction", "sender", "time", "body"), ("subject",), minimum=1, maximum=12)
        for item in items:
            if item["channel"] not in ("sms", "email", "internal") or item["direction"] not in ("incoming", "outgoing"):
                fail(p + ".items", "invalid channel or direction")
        if len(items) != len(scene["statuses"]):
            fail(path + ".statuses", "one status required per message")
        text(c["notice"], p + ".notice")
    elif kind == "outcome":
        obj(c, p, shared + ("fields", "stages", "stageSequence", "metrics", "note"), ("proof",))
        rows(c["fields"], p + ".fields", ("label", "value"))
        stages = texts(c["stages"], p + ".stages", 2, 8)
        seq = c["stageSequence"]
        if not isinstance(seq, list) or len(seq) != len(scene["statuses"]) or any(type(n) is not int or not 0 <= n < len(stages) for n in seq):
            fail(p + ".stageSequence", "requires one valid stage index per status")
        rows(c["metrics"], p + ".metrics", ("label", "value", "note"), minimum=1, maximum=6)
        text(c["note"], p + ".note")
        if "proof" in c:
            rows([c["proof"]], p + ".proof", ("label", "value", "description", "sourceNote"))
    elif kind == "carousel":
        obj(c, p, shared + ("slides", "caption", "fields"))
        c["caption"] = text(c["caption"], p + ".caption")
        c["fields"] = rows(c["fields"], p + ".fields", ("label", "value"))
        slides = c["slides"]
        if not isinstance(slides, list) or not 2 <= len(slides) <= 5:
            fail(p + ".slides", "expected 2..5 slides")
        if len(scene["statuses"]) != len(slides):
            fail(path + ".statuses", "one status required per carousel slide")
        total_bytes = 0
        for i, slide in enumerate(slides):
            sp = p + ".slides[{}]".format(i)
            obj(slide, sp, ("title", "body", "imageData", "alt"))
            for k in ("title", "body", "alt"):
                slide[k] = text(slide[k], sp + "." + k)
            value = slide["imageData"]
            if not isinstance(value, str) or len(value) > 2800000:
                fail(sp + ".imageData", "image exceeds inline image size limit")
            match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})", value)
            if not match:
                fail(sp + ".imageData", "expected inline base64 JPEG, PNG or WebP image")
            try:
                raw = base64.b64decode(match.group(2), validate=True)
            except (binascii.Error, ValueError):
                fail(sp + ".imageData", "invalid image base64")
            mime = match.group(1)
            valid = (mime == "jpeg" and raw.startswith(b"\xff\xd8\xff")) or (mime == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or (mime == "webp" and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
            if not raw or not valid:
                fail(sp + ".imageData", "image MIME signature mismatch")
            total_bytes += len(raw)
            if total_bytes > 2 * 1024 * 1024:
                fail(p + ".slides", "decoded carousel images exceed 2 MiB total")
    elif kind == "workshop":
        obj(c, p, shared + ("current", "next", "events", "followup", "reusable", "historyNote"))
        for k in ("current", "next"):
            rows([c[k]], p + "." + k, ("id", "title", "date", "time"))
        if c["current"]["id"] == c["next"]["id"]:
            fail(p, "next workshop must have a distinct event id")
        rows(c["events"], p + ".events", ("title", "detail"), minimum=1)
        rows([c["followup"]], p + ".followup", ("subject", "body"))
        texts(c["reusable"], p + ".reusable", 1)
        text(c["historyNote"], p + ".historyNote")
        if len(scene["statuses"]) != 3:
            fail(path + ".statuses", "workshop requires attendance, followup and next-event states")
    else:
        fail(path + ".kind", "unsupported scene kind")
    if kind != "workflow":
        for k in shared:
            text(c[k], p + "." + k)


def public_job(normalized):
    result = copy.deepcopy(normalized)
    result.pop("source", None)
    if "personalization" in result:
        result["personalization"] = {"firstName": result["personalization"]["firstName"]}
    return result
