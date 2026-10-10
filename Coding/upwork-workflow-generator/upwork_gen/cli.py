"""Command line entry point.

    python3 -m upwork_gen classify  "<job description>"
    python3 -m upwork_gen vault     "<job description>" [--platform n8n|make]
    python3 -m upwork_gen spec      path/to/spec.json   [--platform n8n|make]
    python3 -m upwork_gen check                          # self-test the vault
    python3 -m upwork_gen batch     <job_dir>... | --order N   # compile, copy, verify
    python3 -m upwork_gen nearest   path/to/jd.txt [--k 3]     # param-rich style refs

The output JSON lands in out/ and on the clipboard, because n8n takes a workflow
pasted straight onto the canvas.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
import sys
from typing import List, Optional

from .classify import classify
from .generate import (
    OUT_DIR,
    ROOT,
    Result,
    available_archetypes,
    build,
    generate_from_spec,
    generate_from_vault,
    load_archetype,
    slugify,
    write_output,
)
from .layout import check as layout_check
from .layout import layout
from .handoff import (
    copy as clip_copy,
    warm,
    load_config,
    newest,
    open_canvases,
    save_config,
)
from .learn import promote
from .maintain import (
    archive_source,
    autocommit,
    corpus_stats,
    record_corpus,
    selfcheck,
    vault_is_dirty,
)
from .spec import SpecError

# A vault hit clears the MISS threshold but can still be thin. Observed
# self-matches (an archetype scored against the post that produced it) land
# between 12 and 19; a hit well under that is usually one scope of a
# multi-scope posting, which reads generic to a client who wrote out four
# specifics. Not a hard rule — a signal, printed so the choice is deliberate.
WEAK_MATCH = 8.0

RUNS_CSV = os.path.join(ROOT, "runs.csv")
RUNS_HEADER = [
    "timestamp", "job_ref", "engine", "platform", "archetype", "confidence",
    "nodes", "gen_ms", "import_clean", "loom_takes", "submitted_at", "replied",
]


def _read_job_text(value: Optional[str]) -> str:
    """Accept an argument, a file path, or piped stdin — long job posts are
    easier to pipe than to quote."""
    if value and os.path.exists(value):
        with open(value, "r", encoding="utf-8") as fh:
            return fh.read()
    if value:
        # A string that looks like a path but is not one is a typo or a stale
        # temp file, never a job post. Silently classifying the path text scores
        # ~0 and reports "no archetype matched", which sends you debugging the
        # classifier instead of the filename.
        if value.startswith(("/", "./", "~/")) or value.endswith((".txt", ".md", ".json")):
            raise SystemExit(
                "no such file: {}\n(pass the job text directly, or a path that exists)".format(value)
            )
        return value
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("no job description given (pass a string, a file path, or pipe stdin)")


def _log_run(result: Result, job_ref: str) -> None:
    exists = os.path.exists(RUNS_CSV)
    with open(RUNS_CSV, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if not exists:
            writer.writerow(RUNS_HEADER)
        found = result.classification
        writer.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            job_ref,
            result.engine,
            result.platform,
            (found.archetype if found else result.spec.archetype) or "",
            "{:.1f}".format(found.confidence) if found else "",
            result.node_count,
            result.elapsed_ms,
            "", "", "", "",
        ])


def _report(result: Result) -> None:
    print()
    print("  {}".format(result.spec.title))
    print("  {} · {} engine · {} nodes · {} ms".format(
        result.platform, result.engine, result.node_count, result.elapsed_ms))
    if result.classification:
        found = result.classification
        print("  matched: {} (confidence {:.1f}) — {}".format(
            found.archetype_label or "none", found.confidence, found.platform_reason))
    if result.path:
        print("  wrote:   {}".format(os.path.relpath(result.path, ROOT)))
    for ghl_path in _ghl_json_paths(result):
        print("  ghl:     {}".format(os.path.relpath(ghl_path, ROOT)))
    if result.flow_path:
        print("  flow:    {}".format(os.path.relpath(result.flow_path, ROOT)))
    if result.dsl_path:
        print("  flowchart: rendering — run ./flow when you want it")
    if result.mockup_path:
        print("  mockup:  {}  (opens in the browser)".format(
            os.path.relpath(result.mockup_path, ROOT)))
    if result.copied:
        # The clipboard holds whatever is primary, which on a diagram-only
        # platform is the scene rather than a workflow file.
        if not result.workflow:
            print("  clipboard: ready — paste onto the excalidraw.com canvas")
        elif result.platform == "n8n":
            print("  clipboard: ready — paste onto the n8n canvas with Cmd+V")
        else:
            print("  clipboard: ready — paste into Make's Import Blueprint dialog")

    found = result.classification
    if result.engine == "vault" and found and found.confidence < WEAK_MATCH:
        print("\n  WEAK MATCH ({:.1f}) — the archetype fits, but loosely. If the post"
              "\n  names specifics this workflow does not show, the compiler will"
              "\n  land harder: python3 -m upwork_gen spec <spec.json> --jd <post>"
              .format(found.confidence))

    if result.layout_problems:
        print("\n  LAYOUT PROBLEMS (the canvas will look wrong):")
        for problem in result.layout_problems:
            print("    ! {}".format(problem))
    if result.warnings:
        print("\n  notes:")
        for warning in result.warnings:
            print("    - {}".format(warning))
    print()


def _ghl_json_paths(result: Result) -> List[str]:
    """Every GHL import file a compile wrote: a spec with several triggers is
    split into `<slug>--<n>-<trigger>.ghl.json`, one per workflow."""
    paths = getattr(result, "ghl_json_paths", None)
    if paths:
        return list(paths)
    single = getattr(result, "ghl_json_path", None)
    return [single] if single else []


def cmd_classify(args: argparse.Namespace) -> int:
    text = _read_job_text(args.job)
    found = classify(text)
    print()
    print("  platform:   {}  ({})".format(found.platform, found.platform_reason))
    print("  archetype:  {}".format(found.archetype_label or "no confident match"))
    print("  confidence: {:.1f}   engine: {}".format(found.confidence, found.engine_hint))
    print("  apps:       {}".format(", ".join(found.apps) or "none named"))
    print("\n  top matches:")
    for name, score in found.scores:
        print("    {:<28} {:.1f}".format(name, score))
    print()
    return 0


def cmd_vault(args: argparse.Namespace) -> int:
    text = _read_job_text(args.job)
    if not getattr(args, "no_open", False):
        warm()  # wake a sleeping instance while we generate
    try:
        result = generate_from_vault(text, platform=args.platform, archetype=args.archetype)
    except SpecError as exc:
        print("\n  {}\n".format(exc), file=sys.stderr)
        return 2
    write_output(result, copy=not args.no_copy,
                 mockup=getattr(args, 'mockup', None),
                 account=getattr(args, 'account', '') or '')
    _report(result)
    _render_excalidraw(result, args)
    _handoff(result, args)
    _maintain(result, text, args)
    if not args.no_log:
        _log_run(result, args.job_ref or "")
    return 1 if result.layout_problems else 0


def _handoff(result: Result, args: argparse.Namespace) -> None:
    """Open the canvases. On by default — the whole point is not touching files."""
    if getattr(args, "no_open", False):
        return

    # The mockup opens even when canvas-opening is off. That setting exists
    # because the n8n and Excalidraw tabs are already open and a second copy is
    # friction; a mockup is a file on disk with no other way to be seen.
    if result.mockup_path:
        from .handoff import open_url
        open_url("file://" + result.mockup_path,
                 str(load_config().get("browser") or "") or None)
        print("  opened the mockup — full-screen the tab before recording")

    if not load_config().get("open_on_run", True):
        return
    for line in open_canvases(result.platform, bool(result.excalidraw_path)):
        print("  open:  {}".format(line))


def latest_run_dsl(out_dir: Optional[str] = None) -> Optional[str]:
    """The .dsl of the most recent run. Written on every run, so it — and not
    the artifact being asked for — is what identifies which run is current."""
    return newest(".excalidraw.dsl", out_dir)


def run_slug(dsl_path: str) -> str:
    return os.path.basename(dsl_path)[: -len(".excalidraw.dsl")]


def cmd_ghl(args: argparse.Namespace) -> int:
    """Spec -> exhaustive GoHighLevel "Build Using AI" prompt (+ prerequisites)."""
    from .compile_ghl_prompt import render_prompt, render_prerequisites
    from .generate import ascii_safe
    from .spec import WorkflowSpec
    spec = WorkflowSpec.load(args.path)
    prompt, pre = render_prompt(spec)
    prompt = ascii_safe(prompt)
    slug = slugify(spec.title)
    out_dir = os.path.join(ROOT, "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "{}.ghl-prompt.txt".format(slug))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prompt)
    # Enter submits the builder's prompt box, so the browser lane types this
    # single-line variant instead (line breaks become " | ").
    with open(path.replace(".ghl-prompt.txt", ".ghl-prompt-oneline.txt"), "w", encoding="utf-8") as fh:
        fh.write(re.sub(r"\s*\n\s*", " | ", prompt.strip()))
    print("  ghl prompt: {} ({} chars, {} lines)".format(os.path.relpath(path, ROOT), len(prompt), prompt.count("\n") + 1))
    print("  " + ascii_safe(render_prerequisites(pre)).replace("\n", "\n  "))
    if not args.no_copy:
        import subprocess
        subprocess.run(["pbcopy"], input=prompt.encode("utf-8"), check=False)
        print("  clipboard: prompt ready to paste into Create workflow -> Build Using AI")
    return 0


# write_output writes a run's GHL files a moment before its .dsl (the Mermaid
# and DSL compiles come last), so "from the latest run" means: no older than
# the .dsl minus this slack. A leftover from an earlier run is minutes or hours
# older and falls outside it.
GHL_RUN_SLACK = 10.0


def latest_run_ghl(out_dir: str, slug: str, dsl_path: str):
    """([current GHL import files in workflow order], [ignored older ones]).

    out/ is never cleaned, so `<slug>.ghl.json` from a single-workflow run can
    sit next to the `<slug>--<n>-<trigger>.ghl.json` files of a later split
    run (or the reverse, or a `--3-` part the spec no longer has). Only files
    at least as new as the run's .dsl (less GHL_RUN_SLACK) count. If both
    shapes are that new, two runs happened seconds apart and the one that
    wrote last wins."""
    from .verify_job import ghl_part
    floor = os.path.getmtime(dsl_path) - GHL_RUN_SLACK
    plain = os.path.join(out_dir, slug + ".ghl.json")
    plain_group = [plain] if os.path.exists(plain) else []
    parts = sorted((ghl_part(name, slug), name) for name in os.listdir(out_dir)
                   if name.endswith(".ghl.json") and ghl_part(name, slug) is not None)
    split_group = [os.path.join(out_dir, name) for _, name in parts]
    fresh_plain = [p for p in plain_group if os.path.getmtime(p) >= floor]
    fresh_split = [p for p in split_group if os.path.getmtime(p) >= floor]
    if fresh_plain and fresh_split:
        if max(os.path.getmtime(p) for p in fresh_split) >= os.path.getmtime(fresh_plain[0]):
            fresh_plain = []
        else:
            fresh_split = []
    current = fresh_plain or fresh_split
    ignored = [p for p in plain_group + split_group if p not in current]
    return current, ignored


def cmd_clip(args: argparse.Namespace) -> int:
    """Swap the clipboard between the workflow and the diagram.

    Everything here resolves against **the latest run**, never "the newest file
    of this type anywhere". Those differ whenever a run does not produce every
    artifact, and the old behaviour silently handed over a diagram of a
    different job — which looks exactly like success until it is on camera.
    """
    kind = args.what
    suffix = {
        "flow": ".excalidraw",
        "ghl": ".ghl.json",
        "n8n": ".n8n.json",
        "make": ".make.json",
        "mermaid": ".mmd.md",
    }[kind]

    latest = latest_run_dsl()
    if not latest:
        print("\n  nothing generated yet\n", file=sys.stderr)
        return 2
    slug = run_slug(latest)
    path = os.path.join(OUT_DIR, slug + suffix)

    ghl_paths: List[str] = []
    ghl_ignored: List[str] = []
    if kind == "ghl":
        # A spec with several triggers compiles to several GHL workflows,
        # `<slug>--<n>-<trigger>.ghl.json`, and no plain `<slug>.ghl.json`.
        # Only the latest run's own files count; see latest_run_ghl.
        ghl_paths, ghl_ignored = latest_run_ghl(OUT_DIR, slug, latest)
        if not ghl_paths:
            print("\n  the latest run ({}) produced no .ghl.json file.".format(slug),
                  file=sys.stderr)
            if ghl_ignored:
                print("  older runs' GHL files, not handed over: {}".format(
                    ", ".join(os.path.basename(p) for p in ghl_ignored)), file=sys.stderr)
            print("  refusing to hand over an older run's artifact.\n", file=sys.stderr)
            return 2
        path = ghl_paths[0]

    if kind == "flow" and not os.path.exists(path):
        # The background render from the run is usually done by now. If it is
        # still going or never started, finish it here.
        from .compile_excalidraw import render
        with open(latest, "r", encoding="utf-8") as fh:
            rendered = render(fh.read(), path)
        if not rendered:
            # Never leave the recording without a diagram. excalidraw.com can
            # import Mermaid directly, and Mermaid is compiled from the same
            # spec — so the fallback is the same picture by another door.
            mermaid = os.path.join(OUT_DIR, slug + ".mmd.md")
            if os.path.exists(mermaid):
                with open(mermaid, "r", encoding="utf-8") as fh:
                    body = fh.read()
                body = body.split("```mermaid", 1)[-1].split("```", 1)[0].strip()
                if clip_copy(body):
                    print("\n  the scene renderer is unavailable, so the clipboard"
                          "\n  holds the Mermaid instead — same diagram, same spec."
                          "\n  In excalidraw.com: Menu -> Mermaid to Excalidraw, paste there.\n")
                    return 0
            print("\n  could not produce a diagram for {}\n".format(slug),
                  file=sys.stderr)
            return 2

    if not os.path.exists(path):
        print("\n  the latest run ({}) produced no {} file."
              "\n  refusing to hand over an older run's artifact.\n".format(
                  slug, suffix), file=sys.stderr)
        return 2
    with open(path, "r", encoding="utf-8") as fh:
        payload = fh.read()
    if not clip_copy(payload):
        print("\n  could not reach the clipboard (pbcopy)\n", file=sys.stderr)
        return 2
    where = {
        "flow": "excalidraw.com", "n8n": "the n8n canvas",
        "make": "Make's Import Blueprint dialog", "mermaid": "any Markdown editor",
        "ghl": "GHL: open an empty workflow, Backup & Audit extension, Import",
    }[kind]
    print("\n  clipboard: {}\n             Cmd+V into {}".format(
        os.path.basename(path), where))
    if len(ghl_paths) > 1:
        print("\n  {} GHL workflows, import each into its own empty workflow:".format(
            len(ghl_paths)))
        for ghl_path in ghl_paths:
            print("    {}".format(ghl_path))
    if ghl_ignored:
        print("\n  ignored (older runs of this title): {}".format(
            ", ".join(os.path.basename(p) for p in ghl_ignored)))
    print()
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    updates = {}
    if args.n8n_url is not None:
        updates["n8n_url"] = args.n8n_url.strip()
    if args.browser is not None:
        updates["browser"] = args.browser.strip()
    if args.open_on_run is not None:
        updates["open_on_run"] = args.open_on_run == "on"
    config = save_config(updates) if updates else load_config()
    print()
    for key in ("n8n_url", "browser", "make_url", "open_on_run"):
        value = config.get(key)
        # `or` would print False as "(unset)" — a booleanly-false setting is
        # set, and reading it as unset is how you re-enable something twice.
        print("  {:<14} {}".format(key, "(unset)" if value in (None, "") else value))
    print()
    return 0


def _render_excalidraw(result: Result, args: argparse.Namespace) -> None:
    """Deprecated. Rendering now starts automatically on every run."""
    return


def _render_excalidraw_unused(result: Result, args: argparse.Namespace) -> None:
    """Opt-in: the CLI is a network round trip, so it never runs by default."""
    if not getattr(args, "excalidraw", False) or not result.dsl_path:
        return
    from .compile_excalidraw import render
    with open(result.dsl_path, "r", encoding="utf-8") as fh:
        dsl = fh.read()
    rendered = render(dsl, result.excalidraw_target)
    if rendered:
        result.excalidraw_path = rendered
        print("  excalidraw: rendered {}".format(os.path.relpath(rendered, ROOT)))
    else:
        print("  excalidraw: render failed — the .dsl is still written; run the "
              "CLI manually (needs npx)")


def _maintain(result: Result, job_text: str, args: argparse.Namespace) -> None:
    """Everything that keeps the system current, on every run, unprompted.

    Deliberately not behind a flag. The whole value of the vault compounding is
    that it happens whether or not anyone remembers to ask for it.
    """
    found = result.classification
    archetype = (found.archetype if found else None) or result.spec.archetype
    record_corpus(
        job_text,
        archetype=archetype,
        engine=result.engine,
        platform=result.platform,
        confidence=found.confidence if found else 0.0,
    )
    if archetype:
        archive_source(archetype, job_text)

    problems = selfcheck()
    if problems:
        print("  health:")
        for problem in problems:
            print("    ! {}".format(problem))

    if not getattr(args, "no_commit", False):
        committed = autocommit("{} via {} engine".format(
            archetype or result.spec.title, result.engine))
        if committed:
            print("  git:   vault committed {}".format(committed))


def cmd_spec(args: argparse.Namespace) -> int:
    if not getattr(args, "no_open", False):
        warm()  # wake a sleeping instance while we generate
    try:
        result = generate_from_spec(args.path, platform=args.platform)
    except SpecError as exc:
        print("\n  {}\n".format(exc), file=sys.stderr)
        return 2
    write_output(result, copy=not args.no_copy,
                 mockup=getattr(args, 'mockup', None),
                 account=getattr(args, 'account', '') or '')
    _report(result)

    job_text = _read_job_text(args.jd) if args.jd else ""

    # Promotion runs after the generation is safely on disk and on the
    # clipboard. A failure to learn must never cost a workflow that worked.
    if not args.no_promote:
        if not job_text:
            print("  vault: NOT LEARNING — no --jd given. The archetype would be "
                  "written but unreachable, so promotion was skipped.")
        else:
            try:
                report = promote(result.spec, job_text=job_text,
                                 archetype_id=args.archetype_id, force=args.force,
                                 job_dir=os.path.dirname(os.path.abspath(args.jd)))
            except Exception as exc:  # promotion is a nice-to-have, never fatal
                print("  vault: promotion failed ({})".format(exc))
            else:
                _report_promotion(report)

    _render_excalidraw(result, args)
    _handoff(result, args)
    _maintain(result, job_text, args)
    if not args.no_log:
        _log_run(result, args.job_ref or "")
    return 1 if result.layout_problems else 0


def _report_promotion(report: dict) -> None:
    if not report.get("promoted"):
        print("  vault: not promoted — {}".format(report.get("reason", "unknown")))
        return
    verb = "updated" if report.get("replaced") else "added"
    print("  vault: {} {!r}".format(verb, report["archetype"]))
    if report.get("reachable"):
        print("         classifier now matches: {}".format(", ".join(report["keywords"][:6])))
    else:
        print("         NO KEYWORDS — pass --jd so the classifier can reach it; "
              "without them this archetype is unreachable")


def cmd_next_engine(args: argparse.Namespace) -> int:
    """Which arm of the split test this job belongs to.

    Alternates to keep the A/B balanced, but a posting the classifier cannot
    place has to go to the compiler regardless — forcing a vault archetype onto
    a job it does not fit would poison the comparison with a result neither
    engine would produce in real use.
    """
    text = _read_job_text(args.job)
    found = classify(text)

    if found.is_miss:
        print("compiler")
        print("  reason: no confident archetype (best {:.1f}) — vault cannot serve this one"
              .format(found.confidence), file=sys.stderr)
        return 0

    counts = {"vault": 0, "compiler": 0}
    if os.path.exists(RUNS_CSV):
        with open(RUNS_CSV, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                engine = row.get("engine")
                if engine in counts:
                    counts[engine] += 1

    engine = "vault" if counts["vault"] <= counts["compiler"] else "compiler"
    print(engine)
    print("  reason: balancing split test (vault {}, compiler {}) · matched {}".format(
        counts["vault"], counts["compiler"], found.archetype), file=sys.stderr)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Everything the system knows about its own state, in one read."""
    from .catalog import get_catalog
    from .learn import load_learned

    print()
    problems = selfcheck()
    archetypes = available_archetypes()
    learned = load_learned()

    print("  vault        {} archetypes ({} seed, {} learned)".format(
        len(archetypes), len(archetypes) - len(learned), len(learned)))

    for platform in ("n8n", "make"):
        catalog = get_catalog(platform, fresh=True)
        state = "verified" if catalog.is_verified else "STUB — unverified"
        print("  catalog {:<4} {} entries, {}".format(
            platform, len(catalog.entries), state))

    stats = corpus_stats()
    print("  corpus       {} runs recorded".format(stats["runs"]))
    if stats["by_engine"]:
        print("               {}".format(", ".join(
            "{} {}".format(v, k) for k, v in sorted(stats["by_engine"].items()))))
    if stats["runs"]:
        top = sorted(stats["by_archetype"].items(), key=lambda kv: -kv[1])[:5]
        print("               most matched: {}".format(
            ", ".join("{} ({})".format(k, v) for k, v in top)))

    print("  git          vault {}".format(
        "has uncommitted changes" if vault_is_dirty() else "clean"))

    if problems:
        print("\n  {} problem{}:".format(len(problems), "" if len(problems) == 1 else "s"))
        for problem in problems:
            print("    ! {}".format(problem))
    else:
        print("\n  no problems found")
    print()
    return 1 if problems else 0


def cmd_archetypes(args: argparse.Namespace) -> int:
    """Inspect what the vault has learned, and drop anything matching badly."""
    from .learn import KEYWORDS_PATH, VAULT_DIR, load_learned, _save_learned

    learned = load_learned()

    if args.forget:
        if args.forget not in learned:
            print("\n  nothing learned under {!r}\n".format(args.forget), file=sys.stderr)
            return 2
        del learned[args.forget]
        _save_learned(learned)
        path = os.path.join(VAULT_DIR, "{}.json".format(args.forget))
        if os.path.exists(path):
            os.remove(path)
        print("\n  forgot {!r} — spec removed and classifier no longer matches it\n".format(
            args.forget))
        return 0

    seed = sorted(set(available_archetypes()) - set(learned))
    print("\n  {} seed archetypes (hand-tuned)".format(len(seed)))
    for archetype_id in seed:
        print("    {}".format(archetype_id))

    if not learned:
        print("\n  nothing learned yet — run `spec --jd <post>` to promote one\n")
        return 0

    print("\n  {} learned".format(len(learned)))
    for archetype_id, entry in sorted(learned.items()):
        terms = [re.sub(r"\\(.)", r"\1", str(k)) for k, _ in entry.get("kw", [])]
        print("    {}  ({})".format(archetype_id, entry.get("learned_at", "?")))
        print("      {}".format(entry.get("label", "")))
        print("      matches: {}".format(", ".join(terms) if terms
                                         else "NOTHING — unreachable, re-promote with --jd"))
    print("\n  keywords file: {}\n".format(os.path.relpath(KEYWORDS_PATH, ROOT)))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Compile every archetype on both platforms and report anything unclean."""
    archetypes = available_archetypes()
    if not archetypes:
        print("no archetypes in vault/archetypes/")
        return 2

    failures = 0
    print()
    for archetype_id in archetypes:
        line = "  {:<32}".format(archetype_id)
        try:
            spec = load_archetype(archetype_id)
            warnings = spec.validate()
            problems = layout_check(spec, layout(spec))
            for platform in ("n8n", "make"):
                build(spec, platform, "check")
            if problems:
                failures += 1
                print(line + "LAYOUT: {}".format("; ".join(problems)))
            else:
                flag = "  ({} notes)".format(len(warnings)) if warnings else ""
                print(line + "ok · {} nodes{}".format(len(spec.flow_nodes), flag))
            if args.verbose and warnings:
                for warning in warnings:
                    print("      - {}".format(warning))
        except Exception as exc:  # surfacing the archetype that broke matters more than the trace
            failures += 1
            print(line + "FAILED: {}".format(exc))
    print("\n  {}/{} clean\n".format(len(archetypes) - failures, len(archetypes)))
    return 1 if failures else 0


# --------------------------------------------------------------------------
# batch: compile + copy into the job folder + verify, for several jobs
# --------------------------------------------------------------------------

# Everything a job folder holds from a compile (verify_job.BUILD_SUFFIXES).
# `.excalidraw.dsl` is left in out/ on purpose: it is the renderer's input,
# not something anyone opens.
from .verify_job import BUILD_SUFFIXES as BATCH_SUFFIXES  # noqa: E402
from .verify_job import build_suffix, is_current_build  # noqa: E402

STALE_DIR = ".stale"


def _produced_files(out_dir: str, slug: str, since: float) -> List[str]:
    """Files this compile wrote for `slug`: `<slug><suffix>`, plus
    `<slug>--<n>-<trigger>.ghl*` when one spec yields several GHL workflows.
    The mtime floor keeps stale files from older runs out of the job folder;
    the name rule keeps other slugs that merely share this prefix out."""
    found = []
    for name in sorted(os.listdir(out_dir)):
        if not is_current_build(name, slug):
            continue
        path = os.path.join(out_dir, name)
        if os.path.getmtime(path) >= since:
            found.append(path)
    return found


def _retire_stale(job_dir: str, keep: List[str]) -> List[str]:
    """Move every build file in the job folder that this compile did not
    produce into `<job>/.stale/`, so verify and ./job only ever see the
    current spec's builds. Moved, not deleted: nothing is lost. Returns the
    new paths."""
    import shutil
    import time

    keep_names = {os.path.basename(p) for p in keep}
    moved = []
    for name in sorted(os.listdir(job_dir)):
        path = os.path.join(job_dir, name)
        if not os.path.isfile(path) or not build_suffix(name) or name in keep_names:
            continue
        stale_dir = os.path.join(job_dir, STALE_DIR)
        os.makedirs(stale_dir, exist_ok=True)
        target = os.path.join(stale_dir, name)
        if os.path.exists(target):
            target = os.path.join(stale_dir, "{}.{}".format(
                time.strftime("%Y%m%d-%H%M%S"), name))
            n = 2
            while os.path.exists(target):
                target = os.path.join(stale_dir, "{}.{}.{}".format(
                    time.strftime("%Y%m%d-%H%M%S"), n, name))
                n += 1
        shutil.move(path, target)
        moved.append(target)
    return moved


class BatchCompileError(Exception):
    """A job's compile step failed; the batch records it and moves on."""


def _batch_compile(job_dir: str, args: argparse.Namespace,
                   out_dir: Optional[str] = None) -> List[str]:
    """The manual step, in-process: `spec <job>/spec.json --jd <job>/jd.txt
    --excalidraw --no-open --no-copy`, then copy the outputs into the job.

    --force is deliberately never passed. In `promote` it only unlocks
    overwriting one of the 20 hand-tuned seed archetypes; an already-learned
    archetype is replaced without it. So forcing buys nothing for a job spec
    and risks silently replacing a curated seed. Returns the copied paths.
    Raises BatchCompileError when the spec is missing or does not compile;
    any other exception propagates to cmd_batch, which isolates the job.
    """
    import shutil
    import time

    from .learn import promote as learn_promote

    out_dir = out_dir or OUT_DIR
    spec_path = os.path.join(job_dir, "spec.json")
    jd_path = os.path.join(job_dir, "jd.txt")
    if not os.path.exists(spec_path):
        raise BatchCompileError("no spec.json")
    started = time.time() - 0.01
    result = generate_from_spec(spec_path)
    write_output(result, out_dir=out_dir, copy=False)
    _report(result)

    job_text = _read_job_text(jd_path) if os.path.exists(jd_path) else ""
    if not args.no_learn:
        if not job_text:
            print("  vault: NOT LEARNING - no jd.txt in the job folder")
        else:
            try:
                report = learn_promote(result.spec, job_text=job_text, force=False,
                                       job_dir=job_dir)
            except Exception as exc:  # promotion is never fatal, same as `spec`
                print("  vault: promotion failed ({})".format(exc))
            else:
                _report_promotion(report)
        _maintain(result, job_text, args)
    if not args.no_log:
        from .verify_job import jd_fields
        _log_run(result, jd_fields(job_dir)[0])

    produced = _produced_files(out_dir, slugify(result.spec.title), started)
    # Stage every copy inside the job folder first (same filesystem, so the
    # swap below is a rename). A failed copy removes the staging folder and
    # leaves the job's previous build set exactly as it was, never a mix.
    import tempfile
    staging = tempfile.mkdtemp(prefix=".batch-", dir=job_dir)
    try:
        for path in produced:
            shutil.copyfile(path, os.path.join(staging, os.path.basename(path)))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    moved = _retire_stale(job_dir, produced)
    if moved:
        print("  moved stale builds to {}/: {}".format(
            STALE_DIR, ", ".join(os.path.basename(p) for p in moved)))
    copied = []
    try:
        for path in produced:
            name = os.path.basename(path)
            target = os.path.join(job_dir, name)
            os.replace(os.path.join(staging, name), target)
            copied.append(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("  copied into job: {}".format(
        ", ".join(os.path.basename(p) for p in copied) or "nothing"))
    return copied


def _compile_failed_report(job_dir: str, error: str):
    """The table row for a job whose compile step failed. verify() is not run:
    the folder still holds the previous compile's files, and checking those
    would pass off an old build as this one."""
    from .verify_job import JobReport, jd_fields
    report = JobReport(job_dir=job_dir, slug=os.path.basename(job_dir.rstrip("/")))
    report.url, _ = jd_fields(job_dir)
    report.fails.append("compile failed: {}".format(error))
    return report


def cmd_batch(args: argparse.Namespace) -> int:
    from .verify_job import _table, order_slugs, print_reports, verify

    jobs = [os.path.abspath(j) for j in args.jobs]
    not_listed: List[str] = []
    if args.order:
        jobs.extend(order_slugs(args.order, missing=not_listed))
    if not jobs:
        print("\n  give job folders or --order N\n", file=sys.stderr)
        return 2
    missing = [j for j in jobs if not os.path.isdir(j)]
    if missing:
        print("\n  not a folder: {}\n".format(", ".join(missing)), file=sys.stderr)
        return 2

    reports = []
    compile_failed = []
    for job in jobs:
        print("\n== {}".format(os.path.basename(job.rstrip("/"))))
        try:
            _batch_compile(job, args, out_dir=args.out_dir)
        except Exception as exc:  # one broken job must never stop the batch
            error = str(exc).replace("\n", " ")
            if not isinstance(exc, (BatchCompileError, SpecError)):
                error = "{}: {}".format(type(exc).__name__, error)
            print("  COMPILE FAILED: {}".format(error))
            compile_failed.append(os.path.basename(job))
            reports.append(_compile_failed_report(job, error))
            continue
        reports.append(verify(job))

    print("\n== verification")
    print_reports(reports)
    rows = [[r.slug, r.platform, str(r.nodes),
             "-" if r.preview_len is None else str(r.preview_len),
             "{}/{}".format(len(r.fails), len(r.warns)), r.url or "-"] for r in reports]
    print(_table(["job", "platform", "nodes", "preview", "FAIL/WARN", "upwork url"], rows))
    if compile_failed:
        print("\n  did not compile: {}".format(", ".join(compile_failed)))
    for slug in not_listed:
        print("\n  slug {} listed in _ORDER.txt has no folder".format(slug))
    print()
    return 1 if compile_failed or any(r.fails for r in reports) else 0


# --------------------------------------------------------------------------
# nearest: which param-rich specs to read as a style reference
# --------------------------------------------------------------------------


def _spec_text(data: dict) -> str:
    parts = [str(data.get("title", ""))]
    for section in data.get("sections", []) or []:
        parts.append("{} {}".format(section.get("label", ""), section.get("note", "")))
    for node in data.get("nodes", []) or []:
        parts.append("{} {} {}".format(node.get("label", ""), node.get("notes") or "",
                                       node.get("app") or ""))
    return "\n".join(parts)


def _param_coverage(data: dict):
    from .spec import AI_SUB_KINDS
    flow = [n for n in data.get("nodes", []) or [] if n.get("kind") not in AI_SUB_KINDS]
    with_params = [n for n in flow if n.get("params")]
    return len(with_params), len(flow)


def _nearest_candidates(own_title: str, own_dir: Optional[str]):
    """(kind, id, path, data) for every vault archetype and job-folder spec."""
    import glob
    import json

    from .verify_job import JOBS_DIR

    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "vault", "archetypes", "*.json"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if str(data.get("title", "")).strip().lower() == own_title:
            continue  # the post's own spec, already promoted
        out.append(("vault", os.path.basename(path)[:-5], path, data))
    # A job spec already promoted into the vault is the same spec twice.
    vault_titles = {str(d.get("title", "")).strip().lower() for _, _, _, d in out}
    for path in sorted(glob.glob(os.path.join(JOBS_DIR, "*", "spec.json"))):
        if own_dir and os.path.abspath(os.path.dirname(path)) == own_dir:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        title = str(data.get("title", "")).strip().lower()
        if title == own_title or title in vault_titles:
            continue
        out.append(("job", os.path.basename(os.path.dirname(path)), path, data))
    return out


def nearest(jd_text: str, k: int = 3, own_dir: Optional[str] = None):
    """Rank param-rich specs by idf-weighted word overlap with the post body.

    Returns (vault_hits, job_hits): each a list of (score, id, path, with, total).
    Job-folder specs are only returned when fewer than k archetypes qualify.
    """
    import json
    import math

    from .learn import _STOP, _describes_the_work, _strip_jd_header, _tokens

    def words(text: str) -> set:
        return {w for w in _tokens(text) if w not in _STOP and len(w) > 2}

    post = words(_describes_the_work(_strip_jd_header(jd_text)))
    own_title = ""
    if own_dir and os.path.exists(os.path.join(own_dir, "spec.json")):
        try:
            with open(os.path.join(own_dir, "spec.json"), "r", encoding="utf-8") as fh:
                own_title = str(json.load(fh).get("title", "")).strip().lower()
        except (OSError, ValueError):
            pass

    candidates = [(kind, cid, path, data, words(_spec_text(data)))
                  for kind, cid, path, data in _nearest_candidates(own_title, own_dir)]
    if not candidates or not post:
        return [], []
    df: dict = {}
    for *_, toks in candidates:
        for tok in toks:
            df[tok] = df.get(tok, 0) + 1
    total_docs = float(len(candidates))
    idf = {tok: math.log(1.0 + total_docs / n) for tok, n in df.items()}
    post_norm = math.sqrt(sum(idf.get(t, math.log(1.0 + total_docs)) ** 2 for t in post))

    scored = {"vault": [], "job": []}
    for kind, cid, path, data, toks in candidates:
        with_params, flow = _param_coverage(data)
        if not flow or with_params / float(flow) < 0.3:
            continue
        shared = post & toks
        doc_norm = math.sqrt(sum(idf[t] ** 2 for t in toks)) or 1.0
        score = 100.0 * sum(idf[t] ** 2 for t in shared) / (post_norm * doc_norm)
        scored[kind].append((score, cid, path, with_params, flow))
    for kind in scored:
        scored[kind].sort(key=lambda h: (-h[0], h[1]))
    vault_hits = scored["vault"][:k]
    job_hits = scored["job"][: k - len(vault_hits)] if len(vault_hits) < k else []
    return vault_hits, job_hits


def cmd_nearest(args: argparse.Namespace) -> int:
    if not os.path.exists(args.jd):
        print("\n  no such file: {}\n".format(args.jd), file=sys.stderr)
        return 2
    with open(args.jd, "r", encoding="utf-8") as fh:
        text = fh.read()
    own_dir = os.path.abspath(os.path.dirname(args.jd))
    vault_hits, job_hits = nearest(text, args.k, own_dir)

    def show(hits) -> None:
        for rank, (score, cid, path, with_params, flow) in enumerate(hits, 1):
            print("    {}. {:5.1f}  {}  ({}/{} nodes with params)".format(
                rank, score, cid, with_params, flow))
            print("       {}".format(path))

    print("\n  nearest vault archetypes with node params:")
    if vault_hits:
        show(vault_hits)
    else:
        print("    none qualify (needs params on at least 30% of flow nodes)")
    if len(vault_hits) < args.k:
        print("\n  fewer than {} qualify, job-folder specs with params:".format(args.k))
        if job_hits:
            show(job_hits)
        else:
            print("    none")
    print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="upwork_gen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_classify = sub.add_parser("classify", help="show what the classifier sees")
    p_classify.add_argument("job", nargs="?")
    p_classify.set_defaults(func=cmd_classify)

    p_vault = sub.add_parser("vault", help="generate from a vault archetype (engine A)")
    p_vault.add_argument("job", nargs="?")
    p_vault.add_argument("--platform", choices=["n8n", "make"])
    p_vault.add_argument("--archetype", help="force a specific archetype")
    p_vault.add_argument("--job-ref", help="url or note recorded in runs.csv")
    p_vault.add_argument("--mockup", nargs="?", const="auto",
                        choices=["auto", "ghl", "zapier"],
                        help="also render the builder mockup (automatic on "
                             "gohighlevel/zapier, where nothing is importable)")
    p_vault.add_argument("--account",
                        help="client business name for the mockup's top bar")
    p_vault.add_argument("--excalidraw", action="store_true",
                        help=argparse.SUPPRESS)  # now automatic; kept so the
                        # old flag does not error mid-application
    p_vault.add_argument("--no-open", action="store_true",
                        help="do not open the canvases in a browser")
    p_vault.add_argument("--no-copy", action="store_true")
    p_vault.add_argument("--no-log", action="store_true")
    p_vault.add_argument("--no-commit", action="store_true",
                         help="skip the automatic vault commit")
    p_vault.set_defaults(func=cmd_vault)

    p_spec = sub.add_parser("spec", help="compile an authored spec (engine B)")
    p_spec.add_argument("path")
    p_spec.add_argument("--platform", choices=["n8n", "make"])
    p_spec.add_argument("--jd", help="the job post this spec was written for; its "
                                     "keywords are what make the archetype reachable")
    p_spec.add_argument("--archetype-id", help="vault id (defaults to a slug of the title)")
    p_spec.add_argument("--job-ref", help="url or note recorded in runs.csv")
    p_spec.add_argument("--force", action="store_true",
                        help="allow replacing a hand-tuned seed archetype")
    p_spec.add_argument("--no-promote", action="store_true", help="compile without learning")
    p_spec.add_argument("--mockup", nargs="?", const="auto",
                        choices=["auto", "ghl", "zapier"],
                        help="also render the builder mockup (automatic on "
                             "gohighlevel/zapier, where nothing is importable)")
    p_spec.add_argument("--account",
                        help="client business name for the mockup's top bar")
    p_spec.add_argument("--excalidraw", action="store_true",
                        help="also render the .excalidraw file via npx (network on first use)")
    p_spec.add_argument("--no-open", action="store_true",
                        help="do not open the canvases in a browser")
    p_spec.add_argument("--no-copy", action="store_true")
    p_spec.add_argument("--no-log", action="store_true")
    p_spec.add_argument("--no-commit", action="store_true",
                        help="skip the automatic vault commit")
    p_spec.set_defaults(func=cmd_spec)

    p_next = sub.add_parser("next-engine", help="which split-test arm this job belongs to")
    p_next.add_argument("job", nargs="?")
    p_next.set_defaults(func=cmd_next_engine)

    # Named `archetypes`, not `vault` — `vault` is the generation command above,
    # and registering it twice silently replaced it.
    p_arch = sub.add_parser("archetypes", help="list what the vault holds and has learned")
    p_arch.add_argument("--forget", metavar="ARCHETYPE_ID",
                        help="delete a learned archetype and its keywords")
    p_arch.set_defaults(func=cmd_archetypes)

    p_ghl = sub.add_parser("ghl", help="render a GoHighLevel builder prompt from a spec")
    p_ghl.add_argument("path")
    p_ghl.add_argument("--no-copy", action="store_true")
    p_ghl.set_defaults(func=cmd_ghl)

    p_clip = sub.add_parser("clip", help="put an artifact on the clipboard")
    p_clip.add_argument("what", choices=["flow", "n8n", "make", "mermaid", "ghl"])
    p_clip.set_defaults(func=cmd_clip)

    p_config = sub.add_parser("config", help="set the n8n URL and open-on-run behaviour")
    p_config.add_argument("--n8n-url")
    p_config.add_argument("--browser", help='app name, e.g. "Arc" (empty = system default)')
    p_config.add_argument("--open-on-run", choices=["on", "off"])
    p_config.set_defaults(func=cmd_config)

    p_doctor = sub.add_parser("doctor", help="full health read: vault, catalogs, corpus, git")
    p_doctor.set_defaults(func=cmd_doctor)

    p_check = sub.add_parser("check", help="compile every archetype and report problems")
    p_check.add_argument("-v", "--verbose", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_batch = sub.add_parser("batch", help="compile, copy into the job folder and verify, "
                                           "for several jobs")
    p_batch.add_argument("jobs", nargs="*", help="job folders")
    p_batch.add_argument("--order", type=int, metavar="N",
                         help="the first N slugs of jobs/_ORDER.txt")
    p_batch.add_argument("--no-learn", action="store_true",
                         help="compile and verify only: no vault promotion, corpus or commit")
    p_batch.add_argument("--no-commit", action="store_true",
                         help="skip the automatic vault commit")
    p_batch.add_argument("--no-log", action="store_true", help="do not append to runs.csv")
    p_batch.add_argument("--out-dir", help=argparse.SUPPRESS)
    p_batch.set_defaults(func=cmd_batch)

    p_near = sub.add_parser("nearest", help="the k param-rich specs closest to a post, "
                                            "as style references")
    p_near.add_argument("jd", help="path to the job's jd.txt")
    p_near.add_argument("--k", type=int, default=3)
    p_near.set_defaults(func=cmd_nearest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
