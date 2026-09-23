#!/usr/bin/env python3
"""Every store key the SCHEDULED laptop jobs can read or write in .tmp/store.json,
found by reading the code (D1 round 3, defect 8).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/schedules/laptop_store_keys.py            # key prefixes, read or write, and where

The laptop keeps one store file for shadow and live, so runbooks/deployment.md
step 7 lists every key in it. A hand-kept list drifts; this scan is what
changesets/tests/test_schedules.py compares that table with.

How it scans: starting from the module of every laptop schedule
(modal_app.LAPTOP_SCHEDULES), it follows the repo's own imports (jobs.*,
services.*, shared.*) except the reply engine and the store implementation
(SKIP_MODULES says why), and finds every call of a store method (get, set,
set_if_absent, mutate, delete, keys, items, add_once, append,
compare_and_set) on something that is a store (a name or attribute containing
"store", or ``st``). The key argument is resolved through string constants,
module constants (also imported ones), ``+``, ``%`` and f-string prefixes and
one level of key-building helper functions. A key it cannot resolve is
reported as unresolved, so a new, opaque key fails the test instead of
slipping past it. OTHER_FILES lists stores that are not .tmp/store.json.

Reads source files only. Python 3.9.
"""
import ast
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(HERE))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

STORE_METHODS = frozenset(["get", "set", "set_if_absent", "mutate", "delete", "keys", "items", "add_once",
                           "append", "compare_and_set"])
# The methods that change the store; get, keys and items only read it.
WRITE_METHODS = frozenset(["set", "set_if_absent", "mutate", "delete", "add_once", "append", "compare_and_set"])
REPO_PACKAGES = ("jobs", "services", "shared")
# Modules the scan does not follow, and why.
SKIP_MODULES = {
    "services.reply_engine": "the reply engine runs on Modal with its own Dict; a laptop job that imports a "
                             "helper from it does not run the engine",
    "shared.store": "the store implementation itself (its keys are the ones passed in)",
    "shared.job_log": "writes the evidence Dict only on Modal (RUNTIME=modal), never .tmp/store.json",
}
# Store calls on a store that is NOT .tmp/store.json: (module, key) -> the file.
OTHER_FILES = {
    ("services.list_factory.state", "state"): "the list factory's own run-state file (state.json per run), "
                                              "through its own JsonFileStore",
}
# Store calls whose key is built at run time from a key already listed (the
# probe the retro writes and deletes at once to prove the claim is writable).
DERIVED = {
    ("jobs.retro_packet", "_probe_store"): "writes and deletes '<claim key>:probe' before the paid call",
}


def _module_path(name: str) -> Optional[str]:
    base = os.path.join(BASE_DIR, *name.split("."))
    for path in (base + ".py", os.path.join(base, "__init__.py")):
        if os.path.isfile(path):
            return path
    return None


def _skipped(name: str) -> bool:
    return any(name == s or name.startswith(s + ".") for s in SKIP_MODULES)


class _Module(object):
    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        with open(path, "r", encoding="utf-8") as fh:
            self.tree = ast.parse(fh.read(), filename=path)
        self.consts = {}  # type: Dict[str, str]
        self.funcs = {}  # type: Dict[str, ast.FunctionDef]
        self.aliases = {}  # type: Dict[str, str]        # local name -> module
        self.imported = {}  # type: Dict[str, Tuple[str, str]]   # local name -> (module, attr)
        for node in self.tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.consts[target.id] = node.value.value
            elif isinstance(node, ast.FunctionDef):
                self.funcs[node.name] = node
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname \
                        else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    full = "%s.%s" % (node.module, alias.name)
                    if _module_path(full):
                        self.aliases[alias.asname or alias.name] = full
                    else:
                        self.imported[alias.asname or alias.name] = (node.module, alias.name)

    def imports(self) -> Set[str]:
        out = set()  # type: Set[str]
        for node in ast.walk(self.tree):
            names = []  # type: List[str]
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module] + ["%s.%s" % (node.module, a.name) for a in node.names]
            for name in names:
                if name.split(".")[0] in REPO_PACKAGES and _module_path(name):
                    out.add(name)
        return out


class Scanner(object):
    def __init__(self):
        self.modules = {}  # type: Dict[str, _Module]
        self._enclosing = {}  # type: Dict[int, Any]

    def module(self, name: str) -> Optional[_Module]:
        if name not in self.modules:
            path = _module_path(name)
            self.modules[name] = _Module(name, path) if path else None
        return self.modules[name]

    def closure(self, roots: List[str]) -> List[str]:
        seen = set()  # type: Set[str]
        todo = list(roots)
        while todo:
            name = todo.pop()
            if name in seen or _skipped(name):
                continue
            mod = self.module(name)
            if mod is None:
                continue
            seen.add(name)
            todo.extend(sorted(mod.imports() - seen))
        return sorted(seen)

    # -------------------------------------------------------- resolution
    def const(self, mod: _Module, name: str, depth: int = 0) -> Optional[str]:
        if name in mod.consts:
            return mod.consts[name]
        if name in mod.imported and depth < 4:
            other = self.module(mod.imported[name][0])
            if other is not None:
                return self.const(other, mod.imported[name][1], depth + 1)
        return None

    def resolve(self, mod: _Module, node: ast.AST, fn: Optional[ast.FunctionDef] = None,
                depth: int = 0) -> Set[str]:
        """Every key (or fixed prefix + '*') ``node`` can be. Empty: unknown."""
        if depth > 8 or node is None:
            return set()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Name):
            value = self.const(mod, node.id)
            if value is not None:
                return {value}
            if fn is not None:
                return self._local(mod, fn, node.id, depth)
            return set()
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in mod.aliases:
            other = self.module(mod.aliases[node.value.id])
            value = self.const(other, node.attr) if other is not None else None
            return {value} if value is not None else set()
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            out = set()  # type: Set[str]
            for left in self.resolve(mod, node.left, fn, depth + 1):
                rights = self.resolve(mod, node.right, fn, depth + 1) or {"*"}
                out.update(left.rstrip("*") + r if not left.endswith("*") else left for r in rights)
            return out
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant):
            args = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
            return self._format(mod, str(node.left.value), [self.resolve(mod, a, fn, depth + 1) for a in args])
        if isinstance(node, ast.JoinedStr):
            fmt, parts = "", []  # type: Tuple[str, List[Set[str]]]
            for part in node.values:
                if isinstance(part, ast.Constant):
                    fmt += str(part.value).replace("%", "%%")
                elif isinstance(part, ast.FormattedValue):
                    fmt += "%s"
                    parts.append(self.resolve(mod, part.value, fn, depth + 1))
            return self._format(mod, fmt, parts)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in mod.funcs:
            helper = mod.funcs[node.func.id]
            returns = [n.value for n in ast.walk(helper) if isinstance(n, ast.Return) and n.value is not None]
            out = set()
            for ret in returns:
                out |= self.resolve(mod, ret, helper, depth + 1)
            return out
        return set()

    @staticmethod
    def _format(mod: _Module, fmt: str, parts: List[Set[str]]) -> Set[str]:
        """A %-format with each %s filled from ``parts``; stops at the first unknown."""
        heads = {""}
        i = k = 0
        while i < len(fmt):
            if fmt[i] == "%" and i + 1 < len(fmt):
                if fmt[i + 1] == "%":
                    heads = set(h + "%" for h in heads)
                    i += 2
                    continue
                values = parts[k] if k < len(parts) else set()
                k += 1
                i += 2
                if not values:
                    return set(h + "*" for h in heads if h)
                new = set()  # type: Set[str]
                done = set()  # type: Set[str]
                for h in heads:
                    for v in values:
                        (done if v.endswith("*") else new).add(h + v)
                if done:
                    return set(d for d in done if d != "*") | set(h + "*" for h in new if h)
                heads = new
                continue
            heads = set(h + fmt[i] for h in heads)
            i += 1
        return heads

    def _local(self, mod: _Module, fn: ast.FunctionDef, name: str, depth: int) -> Set[str]:
        """A local variable (every value assigned to it in ``fn``), or a
        parameter (every value the module's own callers pass for it)."""
        values = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
        if values:
            out = set()  # type: Set[str]
            for value in values:
                got = self.resolve(mod, value, fn, depth + 1)
                if not got:
                    return set()
                out |= got
            return out
        params = [a.arg for a in fn.args.args]
        if name not in params:
            return set()
        index = params.index(name)
        out = set()
        callers = [n for n in ast.walk(mod.tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == fn.name]
        for call in callers:
            arg = call.args[index] if index < len(call.args) else next(
                (kw.value for kw in call.keywords if kw.arg == name), None)
            got = self.resolve(mod, arg, self._enclosing.get(id(call)), depth + 1)
            if not got:
                return set()
            out |= got
        return out

    # -------------------------------------------------------------- scan
    @staticmethod
    def _is_store(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return "store" in node.id.lower() or node.id == "st"
        if isinstance(node, ast.Attribute):
            return "store" in node.attr.lower()
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            return "store" in str(name).lower()
        return False

    def _map_enclosing(self, mod: _Module) -> None:
        def visit(node, current):
            for child in ast.iter_child_nodes(node):
                inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else current
                self._enclosing[id(child)] = inner
                visit(child, inner)

        visit(mod.tree, None)

    def scan(self, names: List[str]) -> Tuple[Dict[str, Set[str]], List[str], Dict[str, str]]:
        """({key or 'prefix*': {module:function}}, [unresolved sites], {other-file key: why}).

        self.written holds the keys some call site WRITES (WRITE_METHODS)."""
        self.written = set()  # type: Set[str]
        found = {}  # type: Dict[str, Set[str]]
        unresolved = []  # type: List[str]
        elsewhere = {}  # type: Dict[str, str]
        for name in names:
            mod = self.module(name)
            if mod is None:
                continue
            self._enclosing = {}  # type: Dict[int, Any]
            self._map_enclosing(mod)
            for node in ast.walk(mod.tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in STORE_METHODS and self._is_store(node.func.value)):
                    continue
                fn = self._enclosing.get(id(node))
                fname = fn.name if fn is not None else "<module>"
                where = "%s:%s" % (name, fname)
                if (name, fname) in DERIVED:
                    continue
                if not node.args:
                    if node.func.attr in ("keys", "items"):
                        unresolved.append("%s line %d: %s() over the whole store" % (where, node.lineno,
                                                                                    node.func.attr))
                    continue
                keys = self.resolve(mod, node.args[0], fn)
                other = [k for k in keys if (name, k) in OTHER_FILES]
                for k in other:
                    elsewhere[k] = OTHER_FILES[(name, k)]
                keys = set(k for k in keys if (name, k) not in OTHER_FILES)
                if not keys and not other or any(k in ("", "*") for k in keys):
                    unresolved.append("%s line %d: %s(%s)" % (where, node.lineno, node.func.attr,
                                                              ast.dump(node.args[0])[:80]))
                    continue
                for k in keys:
                    found.setdefault(k, set()).add(where)
                    if node.func.attr in WRITE_METHODS:
                        self.written.add(k)
        return found, sorted(set(unresolved)), elsewhere


def laptop_roots() -> List[str]:
    from services.reply_engine import modal_app

    return sorted(set(modal_app.SCHEDULE_JOB_MODULE[n] for n in modal_app.LAPTOP_SCHEDULES))


def laptop_store_keys() -> Dict[str, Any]:
    scanner = Scanner()
    modules = scanner.closure(laptop_roots())
    found, unresolved, elsewhere = scanner.scan(modules)
    return {"keys": dict((k, sorted(v)) for k, v in sorted(found.items())), "unresolved": unresolved,
            "other_files": elsewhere, "modules": modules, "written": sorted(scanner.written)}


def key_prefix(key: str) -> str:
    """'retro:proposal:*' and 'retro:proposal:<week>' both -> 'retro:proposal:'."""
    for mark in ("*", "<"):
        if mark in key:
            key = key[:key.index(mark)]
    return key


def main() -> int:
    out = laptop_store_keys()
    for key, where in out["keys"].items():
        print("%-32s %-6s %s" % (key, "write" if key in out["written"] else "read", ", ".join(where)))
    for key, why in out["other_files"].items():
        print("%-32s NOT .tmp/store.json: %s" % (key, why))
    for line in out["unresolved"]:
        print("UNRESOLVED %s" % line)
    return 1 if out["unresolved"] else 0


if __name__ == "__main__":
    sys.exit(main())
