"""End-to-end generation: job description in, platform JSON out.

Two engines share everything downstream of the spec:

* **vault** — retrieve a hand-verified archetype and swap in the apps the post
  actually names. No model call, so it runs in milliseconds.
* **compiler** — the spec is authored by Claude in-session and handed here as
  a file or a dict.

Both paths converge on the same validate -> layout -> compile pipeline, which
is what keeps the two arms of the split test comparable.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import warnings as _warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .catalog import get_catalog
from .classify import Classification, classify
from .compile_make import compile_make
from .compile_excalidraw import (compile_excalidraw, excalidraw_command,
                                 render, render_async)
from .compile_mockup import compile_mockup, theme_for_platform
from .compile_flow import compile_flow_markdown
from .compile_n8n import compile_n8n
from .layout import check, layout
# The ASCII fold lives in params (node references are built from the folded
# name); ascii_safe is re-exported here for everything that already imports it.
from .params import ascii_safe, ascii_safe_obj  # noqa: F401
from .spec import DIAGRAM_ONLY_PLATFORMS, SpecError, WorkflowSpec, slugify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_DIR = os.path.join(ROOT, "vault", "archetypes")
SUBSTITUTIONS_PATH = os.path.join(ROOT, "vault", "substitutions.json")
OUT_DIR = os.path.join(ROOT, "out")


@dataclass
class Result:
    spec: WorkflowSpec
    workflow: Dict[str, Any]
    platform: str
    engine: str
    classification: Optional[Classification] = None
    warnings: List[str] = field(default_factory=list)
    layout_problems: List[str] = field(default_factory=list)
    elapsed_ms: int = 0
    path: Optional[str] = None
    flow_path: Optional[str] = None
    dsl_path: Optional[str] = None
    excalidraw_target: Optional[str] = None
    excalidraw_path: Optional[str] = None
    ghl_prompt_path: Optional[str] = None
    ghl_json_path: Optional[str] = None
    mockup_path: Optional[str] = None
    copied: bool = False

    @property
    def node_count(self) -> int:
        if not self.workflow:
            return len(self.spec.nodes)
        if self.platform == "n8n":
            return len([n for n in self.workflow.get("nodes", []) if "stickyNote" not in n["type"]])
        return _count_modules(self.workflow.get("flow", []))


def ascii_json(value: Any, indent: Optional[int] = 2) -> str:
    """A JSON file's text, pure ASCII. Every string is folded on the object
    first and only then serialised, so a curly quote in a label or a sample
    can never end a JSON string early (folding the serialised text did)."""
    return json.dumps(ascii_safe_obj(value), indent=indent, ensure_ascii=False)


def _count_modules(flow: List[Dict[str, Any]]) -> int:
    total = 0
    for module in flow:
        total += 1
        for route in module.get("routes", []):
            total += _count_modules(route["flow"])
    return total


# --------------------------------------------------------------------------
# Vault engine
# --------------------------------------------------------------------------


def _load_substitutions() -> Dict[str, Any]:
    with open(SUBSTITUTIONS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def available_archetypes() -> List[str]:
    if not os.path.isdir(VAULT_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(VAULT_DIR) if f.endswith(".json") and not f.startswith("_")
    )


def load_archetype(archetype_id: str) -> WorkflowSpec:
    path = os.path.join(VAULT_DIR, "{}.json".format(archetype_id))
    if not os.path.exists(path):
        raise SpecError(
            "no vault archetype {!r}; have: {}".format(archetype_id, ", ".join(available_archetypes()))
        )
    return WorkflowSpec.load(path)


def apply_substitutions(spec: WorkflowSpec, named_apps: List[str]) -> List[str]:
    """Swap default apps for ones the post names, within the same group.

    Returns a list of human-readable swaps for the CLI to report.
    """
    if not named_apps:
        return []

    subs = _load_substitutions()
    groups: Dict[str, List[str]] = subs["groups"]
    display: Dict[str, str] = subs["display"]
    op_for: Dict[str, Dict[str, str]] = subs.get("op_for", {})

    # A node's group comes from the app it already uses, so a CRM node stays a
    # CRM node. Apps that belong to several groups (Airtable is both a CRM and
    # a store) are resolved per group rather than pinned to one.
    group_of: Dict[str, str] = {}
    for group, members in groups.items():
        for app in members:
            group_of.setdefault(app, group)

    # Per group, the earliest-mentioned candidate wins. `named_apps` arrives in
    # order of appearance, so "push to Salesforce, log the rest in Airtable"
    # gives the CRM slot to Salesforce and the store slot to Airtable.
    wanted: Dict[str, str] = {}
    for group, members in groups.items():
        for app in named_apps:
            if app in members:
                wanted[group] = app
                break

    swaps: List[Tuple[str, str]] = []
    for node in spec.nodes:
        if not node.app:
            continue
        group = group_of.get(node.app)
        if not group or group not in wanted:
            continue
        target = wanted[group]
        if target == node.app:
            continue

        old_display = display.get(node.app, node.app)
        new_display = display.get(target, target)
        node.label = _replace_ci(node.label, old_display, new_display)
        node.app = target
        # Ops are pinned per app: Slack posts, Discord sends, Airtable creates.
        node.op = op_for.get(group, {}).get(target, node.op)
        swaps.append((old_display, new_display))

    # The title usually names the apps too, and a headline still reading
    # "-> Slack" over a Discord node is the kind of detail a client notices.
    for old_display, new_display in swaps:
        spec.title = _replace_ci(spec.title, old_display, new_display)
        for section in spec.sections:
            section.note = _replace_ci(section.note, old_display, new_display)

    return sorted({"{} → {}".format(old, new) for old, new in swaps})


def _replace_ci(text: str, old: str, new: str) -> str:
    """Case-insensitive replace-all, preserving everything around the match."""
    if not text or not old:
        return text
    needle = old.lower()
    haystack = text.lower()
    out: List[str] = []
    cursor = 0
    while True:
        index = haystack.find(needle, cursor)
        if index < 0:
            out.append(text[cursor:])
            return "".join(out)
        out.append(text[cursor:index])
        out.append(new)
        cursor = index + len(old)


# --------------------------------------------------------------------------
# Shared pipeline
# --------------------------------------------------------------------------


def build(spec: WorkflowSpec, platform: str, engine: str,
          classification: Optional[Classification] = None) -> Result:
    started = time.time()
    warnings = spec.validate()

    placement = layout(spec)
    problems = check(spec, placement)

    if platform in DIAGRAM_ONLY_PLATFORMS:
        # Nothing to compile — no import format exists for these. The layout
        # still runs, because the diagram is laid out from the same placement.
        workflow = {}
        if platform == "gohighlevel":
            warnings.append(
                "gohighlevel: the workflow compiles to import JSON (<slug>.ghl.json, one "
                "file per independent trigger, for the Backup & Audit extension) plus "
                "<slug>.ghl-prompt.txt, <slug>.ghl-prompt-oneline.txt and "
                "<slug>.ghl-prereqs.txt; the diagram is drawn from the same spec"
            )
        else:
            warnings.append(
                "{} has no importable workflow format — the diagram is the "
                "deliverable".format(platform)
            )
    else:
        catalog = get_catalog(platform, fresh=True)
        if platform == "n8n":
            workflow = compile_n8n(spec, catalog)
        elif platform == "make":
            workflow = compile_make(spec, catalog)
        else:
            raise SpecError("unknown platform {!r}".format(platform))
        warnings.extend(catalog.report())
    return Result(
        spec=spec,
        workflow=workflow,
        platform=platform,
        engine=engine,
        classification=classification,
        warnings=warnings,
        layout_problems=problems,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def generate_from_vault(job_text: str, platform: Optional[str] = None,
                        archetype: Optional[str] = None) -> Result:
    started = time.time()
    found = classify(job_text)
    target_platform = platform or found.platform
    archetype_id = archetype or found.archetype

    if not archetype_id:
        raise SpecError(
            "classifier found no confident archetype (best {:.1f}, threshold clears at 3.0) — "
            "this posting belongs on the compiler path".format(found.confidence)
        )

    spec = load_archetype(archetype_id)
    spec.platform = target_platform
    swaps = apply_substitutions(spec, found.apps)

    result = build(spec, target_platform, "vault", found)
    if swaps:
        result.warnings.insert(0, "app swaps applied: {}".format("; ".join(swaps)))
    result.elapsed_ms = int((time.time() - started) * 1000)
    return result


def generate_from_spec(spec_source: Any, platform: Optional[str] = None) -> Result:
    """Engine B entry point. Accepts a path, a JSON string, or a dict."""
    if isinstance(spec_source, WorkflowSpec):
        spec = spec_source
    elif isinstance(spec_source, dict):
        spec = WorkflowSpec.from_dict(spec_source)
    elif os.path.exists(str(spec_source)):
        spec = WorkflowSpec.load(str(spec_source))
    else:
        spec = WorkflowSpec.from_json(str(spec_source))
    return build(spec, platform or spec.platform, "compiler")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def write_output(result: Result, out_dir: Optional[str] = None, copy: bool = True,
                 mockup: Optional[str] = None, account: str = "") -> Result:
    out_dir = out_dir or OUT_DIR
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    slug = slugify(result.spec.title)
    payload = None
    if result.workflow:
        suffix = "n8n" if result.platform == "n8n" else "make"
        path = os.path.join(out_dir, "{}.{}.json".format(slug, suffix))
        # Keep the importable file pure ASCII. The middle dot and em dash in
        # labels showed up as mojibake ("Â·") on the n8n canvas after a paste,
        # so they are swapped for plain hyphens here, in the file only, on
        # each string before it is serialised (see ascii_json).
        payload = ascii_json(result.workflow)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload)
        result.path = path

    # The flowchart is a third target on the same spec, so it costs a few
    # milliseconds and can never disagree with the workflow it describes.
    if result.spec.platform == "gohighlevel":
        # GHL: the import JSON (compile_ghl) plus the builder prompt and prereqs.
        from .compile_ghl_prompt import render_prompt, render_prerequisites
        from .compile_ghl import GHLCompileWarning, GHLCompiler, split_ghl_spec
        import re as _re
        # A spec whose triggers start separate chains is several GHL
        # workflows: one prompt and one import file per trigger. A single
        # workflow keeps the plain <slug>.* names.
        parts = split_ghl_spec(result.spec)
        stems = ([slug] if len(parts) == 1 else
                 ["{}--{}-{}".format(slug, i + 1, slugify(suffix, 40)) for i, (suffix, _s) in enumerate(parts)])
        loc = os.environ.get("UPWORK_GHL_LOCATION", "ebyNANPagaK7ycf1pfge")
        ids_path = os.path.join(ROOT, "upwork_gen", "catalog", "ghl_ids_{}.json".format(loc))
        ids = json.load(open(ids_path)) if os.path.exists(ids_path) else {}
        prompt_paths: List[str] = []
        json_paths: List[str] = []
        unresolved: List[str] = []
        checks: List[str] = []
        for stem, (_suffix, sub) in zip(stems, parts):
            prompt, pre = render_prompt(sub)
            ghl_path = os.path.join(out_dir, "{}.ghl-prompt.txt".format(stem))
            with open(ghl_path, "w", encoding="utf-8") as fh:
                fh.write(ascii_safe(prompt))
            with open(ghl_path.replace(".ghl-prompt.txt", ".ghl-prompt-oneline.txt"), "w", encoding="utf-8") as fh:
                fh.write(_re.sub(r"\s*\n\s*", " | ", ascii_safe(prompt).strip()))
            with open(os.path.join(out_dir, "{}.ghl-prereqs.txt".format(stem)), "w", encoding="utf-8") as fh:
                fh.write(ascii_safe(render_prerequisites(pre)))
            prompt_paths.append(ghl_path)
            # The importable file: same spec, GHL's own node format, for the
            # "GHL Workflow Backup & Audit" extension (open an empty workflow,
            # pick this file). Pipeline/stage ids come from the per-location map.
            compiler = GHLCompiler(sub, ids, loc)
            # GHLCompiler._warn also raises each check as a GHLCompileWarning.
            # They reach the notes below via compiler.warnings, so the raised
            # copies are swallowed here (else the first spec of a process shows
            # each one twice: once on stderr, once in the notes). Any other
            # warning type is passed on unchanged, as compile_ghl.main() does.
            with _warnings.catch_warnings(record=True) as caught:
                _warnings.simplefilter("always", GHLCompileWarning)
                ghl_wf = compiler.compile()
            for w in caught:
                if not issubclass(w.category, GHLCompileWarning):
                    _warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
            ghl_json = os.path.join(out_dir, "{}.ghl.json".format(stem))
            with open(ghl_json, "w", encoding="utf-8") as fh:
                fh.write(ascii_json(ghl_wf))
            json_paths.append(ghl_json)
            unresolved.extend(u for u in compiler.unresolved if u not in unresolved)
            # Copied from compiler.warnings (this compile's own deduped list),
            # so every spec of a batch gets its "check after import" lines.
            checks.extend(w for w in compiler.warnings if w not in checks)
        result.ghl_prompt_path = prompt_paths[0]
        result.ghl_json_path = json_paths[0]
        # Result has no list field for this; a plain attribute keeps every path.
        setattr(result, "ghl_json_paths", json_paths)
        if len(json_paths) > 1:
            result.warnings.append("ghl: {} workflows, one per trigger; import each file into its own empty workflow: {}".format(
                len(json_paths), ", ".join(os.path.basename(p) for p in json_paths)))
        missing = [u for u in unresolved if u.split(":", 1)[0] not in ("condition", "go_to")]
        by_hand = [u for u in unresolved if u.split(":", 1)[0] in ("condition", "go_to")]
        if missing:
            result.warnings.append("ghl: create these in the sub-account, then refresh the id map: " + ", ".join(missing))
        if by_hand:
            result.warnings.append("ghl: set these by hand after import: " + "; ".join(by_hand))
        for check in checks:
            result.warnings.append("ghl: check after import: " + check)

    flow_path = os.path.join(out_dir, "{}.mmd.md".format(slug))
    with open(flow_path, "w", encoding="utf-8") as fh:
        fh.write(ascii_safe(compile_flow_markdown(result.spec)))
    result.flow_path = flow_path

    # Same ASCII rule for the diagram: the middle dot pasted into
    # excalidraw.com as a stray accented character.
    dsl = ascii_safe(compile_excalidraw(result.spec))
    dsl_path = os.path.join(out_dir, "{}.excalidraw.dsl".format(slug))
    with open(dsl_path, "w", encoding="utf-8") as fh:
        fh.write(dsl)
    result.dsl_path = dsl_path
    result.excalidraw_target = os.path.join(out_dir, "{}.excalidraw".format(slug))
    # Every run gets a scene, no flag to forget. The scene is now built
    # natively (tinted stage bands, coloured shapes, labelled arrows) straight
    # from the layout, synchronously, so `flow` never has to wait on a render.
    from .compile_excalidraw_native import compile_excalidraw_scene
    scene_json = ascii_json(compile_excalidraw_scene(result.spec), indent=None)
    with open(result.excalidraw_target, "w", encoding="utf-8") as fh:
        fh.write(scene_json)
    result.excalidraw_path = result.excalidraw_target

    # The builder mockup. Written whenever it is asked for, and always on a
    # platform with no import format — there it is not an extra, it is the only
    # thing the client can be shown.
    # Only the two real builders get a mockup. A generic "diagram" spec has no
    # product to imitate, and rendering it as GoHighLevel would put a brand on
    # screen that has nothing to do with the job.
    if mockup or result.platform in ("gohighlevel", "zapier"):
        theme = (mockup if mockup in ("ghl", "zapier")
                 else theme_for_platform(result.platform))
        mockup_path = os.path.join(out_dir, "{}.{}.html".format(slug, theme))
        with open(mockup_path, "w", encoding="utf-8") as fh:
            fh.write(compile_mockup(result.spec, theme, account=account))
        result.mockup_path = mockup_path

    if copy:
        # Whatever is primary goes to the clipboard. On a diagram-only platform
        # that is the diagram, because there is nothing else to paste.
        if payload is None:
            # Diagram-only platform: the scene is the deliverable, so it is
            # worth rendering here rather than behind --excalidraw. If the CLI
            # is unavailable the DSL goes to the clipboard instead — still
            # usable, just one more step.
            if not os.path.exists(result.excalidraw_target):
                if render(dsl, result.excalidraw_target):
                    result.excalidraw_path = result.excalidraw_target
            source = (result.excalidraw_target
                      if os.path.exists(result.excalidraw_target) else dsl_path)
            with open(source, "r", encoding="utf-8") as fh:
                payload = fh.read()
        result.copied = copy_to_clipboard(payload)
    return result


def copy_to_clipboard(text: str) -> bool:
    """macOS pbcopy. n8n accepts workflow JSON pasted straight onto the canvas,
    which skips the save-then-import round trip entirely."""
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
