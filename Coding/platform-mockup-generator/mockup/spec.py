"""The contract: a linear, branching list of steps.

Deliberately *not* the graph model the n8n generator uses. GoHighLevel and
Zapier both render automations as a vertical stack of cards that occasionally
splits in two — there is no free-form 2-D canvas to lay out, so a nested list
is the honest shape. Modelling it as a graph and flattening it back would be
work in service of a similarity that does not exist.

A step's `type` comes from a closed vocabulary. Anything outside it is rejected
at parse time rather than rendering as a card that looks subtly wrong on camera.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

PLATFORMS = ("ghl", "zapier")

# What a card can be. Each maps to a distinct treatment in the renderer, so
# adding one here without teaching render.py about it is a visible bug — the
# tests assert the two stay in step.
STEP_TYPES = ("action", "ai", "branch", "wait", "filter", "code")

_MAX_DEPTH = 2  # Neither builder nests branches deeper than this legibly.


class SpecError(ValueError):
    """Raised with a message meant to be read at speed, mid-application."""


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


class Step:
    __slots__ = ("type", "app", "label", "note", "yes", "no", "branch_labels")

    def __init__(self, type: str, app: str, label: str, note: str = "",
                 yes: Optional[List["Step"]] = None,
                 no: Optional[List["Step"]] = None,
                 branch_labels: Optional[List[str]] = None) -> None:
        self.type = type
        self.app = app
        self.label = label
        self.note = note
        self.yes = yes or []
        self.no = no or []
        self.branch_labels = branch_labels or ["Yes", "No"]

    @property
    def is_branch(self) -> bool:
        return self.type == "branch"

    @classmethod
    def from_dict(cls, data: Dict[str, Any], depth: int = 0) -> "Step":
        if not isinstance(data, dict):
            raise SpecError("each step must be an object, got {!r}".format(data))

        step_type = _clean(data.get("type", "action")).lower()
        if step_type not in STEP_TYPES:
            raise SpecError(
                "unknown step type {!r} — use one of: {}".format(
                    step_type, ", ".join(STEP_TYPES))
            )

        label = _clean(data.get("label", ""))
        if not label:
            raise SpecError("every step needs a label; {!r} has none".format(data))

        if step_type == "branch":
            if depth >= _MAX_DEPTH:
                raise SpecError(
                    "branch {!r} nests too deep — neither builder reads clearly "
                    "past {} levels".format(label, _MAX_DEPTH)
                )
            yes = [cls.from_dict(s, depth + 1) for s in data.get("yes", [])]
            no = [cls.from_dict(s, depth + 1) for s in data.get("no", [])]
            if not yes and not no:
                raise SpecError(
                    "branch {!r} has no steps on either side — an empty split "
                    "reads as a mistake on camera".format(label)
                )
            labels = data.get("branch_labels") or ["Yes", "No"]
            return cls("branch", _clean(data.get("app", "")), label,
                       _clean(data.get("note", "")),
                       yes, no, [_clean(x) for x in labels][:2])

        app = _clean(data.get("app", ""))
        if step_type in ("action", "ai") and not app:
            raise SpecError(
                "step {!r} is an {} but names no app — the app tile is the "
                "thing that makes the card look real".format(label, step_type)
            )
        return cls(step_type, app, label, _clean(data.get("note", "")))

    def walk(self):
        """Every step in this subtree, in reading order."""
        yield self
        for child in list(self.yes) + list(self.no):
            for item in child.walk():
                yield item


class Trigger:
    __slots__ = ("app", "label", "note")

    def __init__(self, app: str, label: str, note: str = "") -> None:
        self.app = app
        self.label = label
        self.note = note

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trigger":
        if not isinstance(data, dict):
            raise SpecError("`trigger` must be an object")
        label = _clean(data.get("label", ""))
        app = _clean(data.get("app", ""))
        if not label or not app:
            raise SpecError("the trigger needs both an `app` and a `label`")
        return cls(app, label, _clean(data.get("note", "")))


class MockupSpec:
    __slots__ = ("title", "platform", "trigger", "steps",
                 "input_sample", "output_sample", "account")

    def __init__(self, title: str, platform: str, trigger: Trigger,
                 steps: List[Step], input_sample: Dict[str, Any],
                 output_sample: Dict[str, Any], account: str = "") -> None:
        self.title = title
        self.platform = platform
        self.trigger = trigger
        self.steps = steps
        self.input_sample = input_sample
        self.output_sample = output_sample
        self.account = account

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MockupSpec":
        platform = _clean(data.get("platform", "ghl")).lower()
        if platform in ("gohighlevel", "highlevel"):
            platform = "ghl"
        if platform not in PLATFORMS:
            raise SpecError(
                "platform must be one of {}, got {!r}".format(
                    " / ".join(PLATFORMS), platform)
            )

        title = _clean(data.get("title", ""))
        if not title:
            raise SpecError("the mockup needs a `title` — it goes in the top bar")

        steps = [Step.from_dict(s) for s in data.get("steps", [])]
        if not steps:
            raise SpecError("a trigger with no steps is not an automation")

        spec = cls(
            title=title,
            platform=platform,
            trigger=Trigger.from_dict(data.get("trigger", {})),
            steps=steps,
            input_sample=data.get("input_sample") or {},
            output_sample=data.get("output_sample") or {},
            account=_clean(data.get("account", "")),
        )
        spec.validate()
        return spec

    @classmethod
    def load(cls, path: str) -> "MockupSpec":
        with open(path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except ValueError as exc:
                raise SpecError("{} is not valid JSON: {}".format(path, exc))
        return cls.from_dict(data)

    def walk(self):
        for step in self.steps:
            for item in step.walk():
                yield item

    @property
    def card_count(self) -> int:
        return 1 + sum(1 for _ in self.walk())

    def validate(self) -> List[str]:
        """Warnings, not errors — things that read badly rather than break.

        Returned rather than printed so the caller decides how loud to be.
        """
        warnings: List[str] = []
        count = self.card_count
        if count < 4:
            warnings.append(
                "only {} cards — a short stack reads as a trivial build".format(count))
        if count > 16:
            warnings.append(
                "{} cards — the stack will scroll past one screen at recording "
                "zoom".format(count))
        if not self.input_sample:
            warnings.append("no input_sample — the trigger card has nothing to show")
        if not self.output_sample:
            warnings.append("no output_sample — the last card has nothing to show")

        # A branch whose arms are both empty is caught at parse time; a branch
        # that is the very last step leaves the automation ending mid-question.
        if self.steps and self.steps[-1].is_branch:
            both = self.steps[-1].yes and self.steps[-1].no
            if not both:
                warnings.append(
                    "the automation ends on a one-sided branch — the empty arm "
                    "will look unfinished")
        return warnings
