"""DESIGN boundary 1: the engine never writes to Upwork.

Every ``.py`` under ``services/upwork_followup/`` (and ``jobs/upwork_followup.py``
once it exists) is parsed, and none may reference a write-shaped Upwork tool
name as a whole word in code: an identifier, an attribute, an import, a
keyword argument, or a string constant that is not a docstring. Comments and
docstrings may name them (the collect instructions must, to forbid them).

Test files are held to the identifier rule only, so a test can still assert
that a draft or an instruction text does not contain one of these names.
"""
import ast
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent
REPO = PACKAGE.parent.parent
CLI = REPO / "jobs" / "upwork_followup.py"

FORBIDDEN = ("send_message", "manage_proposals", "respond_to_offer", "manage_meetings",
             "submit_milestones", "boost_profile", "manage_offers", "update_profile")
_WORD_RE = re.compile(r"(?<![A-Za-z0-9_])(%s)(?![A-Za-z0-9_])" % "|".join(FORBIDDEN))


def _docstring_nodes(tree):
    """The Constant nodes that are module, class or function docstrings."""
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None),
                                                                      ast.Constant) \
                    and isinstance(body[0].value.value, str):
                nodes.add(id(body[0].value))
    return nodes


def references(source, include_strings=True):
    """Forbidden names this source references in code, as (line, name) pairs."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    hits = []
    for node in ast.walk(tree):
        words = []
        if isinstance(node, ast.Name):
            words.append(node.id)
        elif isinstance(node, ast.Attribute):
            words.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            words.append(node.name)
        elif isinstance(node, ast.arg):
            words.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            words.append(node.arg)
        elif isinstance(node, ast.alias):
            words.extend([node.name, node.asname or ""])
        elif isinstance(node, ast.ImportFrom):
            words.append(node.module or "")
        elif include_strings and isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            words.append(node.value)
        for word in words:
            # "upwork__send_message" is the MCP tool name: the "__" prefix must not hide it
            for match in _WORD_RE.finditer((word or "").replace("upwork__", "upwork ")):
                hits.append((getattr(node, "lineno", 0), match.group(1)))
    return hits


def engine_files():
    files = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)
    if CLI.exists():
        files.append(CLI)
    return files


def _is_test_file(path):
    return "tests" in path.relative_to(REPO).parts


def test_there_is_something_to_scan():
    names = {p.name for p in engine_files()}
    assert "collect.py" in names


@pytest.mark.parametrize("path", engine_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_no_module_references_an_upwork_write_tool(path):
    source = path.read_text(encoding="utf-8")
    hits = references(source, include_strings=not _is_test_file(path))
    assert hits == [], "%s references Upwork write tools in code: %s" % (path.relative_to(REPO), hits)


# ---------------------------------------------------------- the scanner works
def test_scanner_catches_code_and_ignores_comments_and_docstrings():
    clean = (
        '"""Module doc: never call send_message or manage_offers."""\n'
        "# a comment about respond_to_offer\n"
        "def f():\n"
        '    """Docstring naming boost_profile."""\n'
        "    return 'send_messages is a different word'\n"
    )
    assert references(clean) == []

    dirty = (
        "import upwork\n"
        "from upwork import manage_proposals\n"
        "client.send_message(room, text)\n"
        "tool = 'upwork__respond_to_offer'\n"
        "call(name='update_profile')\n"
        "run(submit_milestones=True)\n"
        "def manage_meetings():\n"
        "    pass\n"
        "x = getattr(api, 'boost_profile')\n"
        "manage_offers = None\n"
    )
    found = {name for _, name in references(dirty)}
    assert found == set(FORBIDDEN)


def test_test_files_are_held_to_identifiers_only():
    source = "assert 'send_message' not in draft\n"
    assert references(source, include_strings=False) == []
    assert references("api.send_message()\n", include_strings=False) != []


# ------------------------------------------------------- the watch task prompt
WATCH_PROMPT = PACKAGE / "watch_task_prompt.md"


def test_the_watch_prompt_names_no_upwork_write_tool():
    """The watch runs up to 23 times a day from a scheduled task: its prompt
    allows only the read tools by name and never spells out a write tool."""
    text = WATCH_PROMPT.read_text(encoding="utf-8")
    hits = [m.group(1) for m in _WORD_RE.finditer(text.replace("upwork__", "upwork "))]
    assert hits == [], "watch_task_prompt.md names Upwork write tools: %s" % hits
