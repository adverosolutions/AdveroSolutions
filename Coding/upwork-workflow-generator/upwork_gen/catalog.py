"""Catalog loading and node resolution.

Two jobs:

1. Merge the harvested/verified catalogs over the hand-seeded stubs, so the
   external agents' output drops in as a file rather than a code change.
2. Resolve a spec node to a concrete platform entry, and *never fail*. An
   uncatalogued app degrades to a labelled HTTP request node, which reads on
   canvas as a deliberate custom-API call. A compile that dies because the job
   post mentioned some niche CRM is worth more lost time than a slightly
   generic node.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .spec import Node

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog")

_STUB_FILES = {"n8n": "n8n_nodes.json", "make": "make_modules.json"}
_VERIFIED_FILES = {"n8n": "n8n_nodes.verified.json", "make": "make_modules.verified.json"}


class Resolution(object):
    """One resolved node, plus how confident we are in it."""

    __slots__ = ("entry", "key", "matched", "exact", "verified", "fallback")

    def __init__(
        self,
        entry: Dict[str, Any],
        key: str,
        matched: Optional[str],
        exact: bool,
        verified: bool,
        fallback: bool,
    ) -> None:
        self.entry = entry
        self.key = key
        self.matched = matched
        self.exact = exact
        self.verified = verified
        self.fallback = fallback


class Catalog(object):
    def __init__(self, platform: str) -> None:
        if platform not in _STUB_FILES:
            raise ValueError("unknown platform {!r}".format(platform))
        self.platform = platform
        self._data = self._load(platform)
        self.entries: Dict[str, Any] = self._data.get("entries", {})
        self.fallbacks: Dict[str, Any] = self._data.get("fallback", {})
        self.meta: Dict[str, Any] = self._data.get("_meta", {})
        self.special: Dict[str, Any] = self._data.get("special", {})
        self.sticky: Dict[str, Any] = self._data.get("sticky", {})
        # Populated as nodes resolve, so the CLI can warn about weak spots.
        self.unverified_used: List[str] = []
        self.fallback_used: List[str] = []

    # -- loading -----------------------------------------------------------

    @staticmethod
    def _load(platform: str) -> Dict[str, Any]:
        stub_path = os.path.join(CATALOG_DIR, _STUB_FILES[platform])
        with open(stub_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        verified_path = os.path.join(CATALOG_DIR, _VERIFIED_FILES[platform])
        if os.path.exists(verified_path):
            with open(verified_path, "r", encoding="utf-8") as fh:
                verified = json.load(fh)
            # Verified entries win outright; anything the harvest missed keeps
            # its stub so the compiler still has something to emit.
            for section in ("entries", "fallback", "special", "sticky"):
                incoming = verified.get(section)
                if not incoming:
                    continue
                merged = dict(data.get(section, {}))
                for key, value in incoming.items():
                    if isinstance(value, dict):
                        value = dict(value)
                        value.setdefault("verified", True)
                    merged[key] = value
                data[section] = merged
            data.setdefault("_meta", {})["verified_overlay"] = verified.get("_meta", {})

        # Every `kind:app:op` also answers to `kind:app:`. Without this, asking
        # for an operation nobody catalogued — salesforce:get when only
        # salesforce:create_contact exists — falls all the way through to a
        # generic HTTP node, even though the right app node is sitting right
        # there. The app is what the canvas shows; the operation is a dropdown.
        entries = data.get("entries", {})
        for key in list(entries):
            parts = key.split(":", 2)
            if len(parts) != 3:
                continue
            kind, app, op = parts
            if not app or not op:
                continue
            app_level = "{}:{}:".format(kind, app)
            if app_level not in entries:
                entries[app_level] = entries[key]
        return data

    @property
    def is_verified(self) -> bool:
        return bool(self.meta.get("verified_overlay"))

    # -- resolution --------------------------------------------------------

    def resolve(self, node: Node) -> Resolution:
        """Exact -> kind:app: -> kind:: -> group fallback. Always returns."""
        candidates = [
            "{}:{}:{}".format(node.kind, node.app or "", node.op or ""),
            "{}:{}:".format(node.kind, node.app or ""),
            "{}::".format(node.kind),
        ]
        for index, key in enumerate(candidates):
            entry = self.entries.get(key)
            if entry:
                resolution = Resolution(
                    entry=copy.deepcopy(entry),
                    key=candidates[0],
                    matched=key,
                    exact=(index == 0),
                    verified=bool(entry.get("verified")),
                    fallback=False,
                )
                self._record(node, resolution)
                return resolution

        group = node.kind.split(".")[0]
        entry = (
            self.fallbacks.get(node.kind)
            or self.fallbacks.get(group)
            or self.fallbacks.get("app.action" if node.app else "default")
            or self.fallbacks["default"]
        )
        resolution = Resolution(
            entry=copy.deepcopy(entry),
            key=candidates[0],
            matched=None,
            exact=False,
            verified=False,
            fallback=True,
        )
        self._record(node, resolution)
        return resolution

    def _record(self, node: Node, resolution: Resolution) -> None:
        if resolution.fallback:
            self.fallback_used.append("{} ({})".format(node.label, node.catalog_key))
        elif not resolution.verified:
            self.unverified_used.append("{} ({})".format(node.label, resolution.matched))

    # -- reporting ---------------------------------------------------------

    def report(self) -> List[str]:
        """Warnings worth showing before a recording, not blockers."""
        out: List[str] = []
        if not self.is_verified:
            out.append(
                "{} catalog is still the hand-seeded stub — type names and versions "
                "are unverified".format(self.platform)
            )
        if self.fallback_used:
            out.append(
                "fell back to a generic node for: {}".format(", ".join(sorted(set(self.fallback_used))))
            )
        return out


_CACHE: Dict[str, Catalog] = {}


def get_catalog(platform: str, fresh: bool = False) -> Catalog:
    """Cached per platform. `fresh` resets the per-run usage tracking."""
    if fresh or platform not in _CACHE:
        _CACHE[platform] = Catalog(platform)
    return _CACHE[platform]
