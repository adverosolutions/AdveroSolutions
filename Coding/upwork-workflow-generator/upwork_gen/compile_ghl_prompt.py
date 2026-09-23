"""GoHighLevel builder prompt — the "import format" for a platform that has none.

GHL cannot import a workflow and its API cannot create one, but its workflow
builder has a prompt box ("Build Using AI") that draws a complete, configured
workflow from a paragraph. So for GHL the prompt *is* the JSON: this module
renders a WorkflowSpec into an exhaustive, numbered instruction sheet with
every field spelled out, so the builder has nothing to guess and the canvas
needs no hand edits afterwards (hand edits through a browser cost ten minutes
each; a second prompt costs thirty seconds).

Spec vocabulary for GHL: `app: "ghl"` with `op` from OPS below and the fields
in `params`. Unknown ops and missing required fields are errors, on purpose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .params import for_wait
from .spec import SpecError, WorkflowSpec, Node

# op -> (required params, optional params). Names match the GHL action picker.
OPS: Dict[str, Tuple[List[str], List[str]]] = {
    # triggers
    "form_submitted": ([], ["form"]),
    "survey_submitted": ([], ["survey"]),
    "customer_replied": ([], ["channels"]),
    "contact_created": ([], []),
    "contact_tag_added": (["tag"], []),
    "contact_tag_removed": (["tag"], []),
    "pipeline_stage_changed": (["pipeline", "stage"], []),
    "opportunity_created": (["pipeline"], []),
    "opportunity_status_changed": (["status"], ["pipeline"]),
    "appointment_status": (["status"], ["calendar"]),
    "inbound_webhook": ([], []),
    "missed_call": ([], []),
    "invoice_paid": ([], []),
    "order_submitted": ([], []),
    "birthday": ([], []),
    "task_completed": ([], []),
    # actions
    "add_tag": (["tag"], []),
    "remove_tag": (["tag"], []),
    "send_sms": (["message"], []),
    "send_email": (["subject", "body"], ["from_name"]),
    "wait": ([], ["amount", "unit"]),
    "create_opportunity": (["pipeline", "stage"], ["name", "value", "status"]),
    "update_opportunity": (["pipeline", "stage"], ["status"]),
    "internal_notification": (["type", "message"], ["to", "subject"]),
    "if_else": (["condition"], []),
    "goal": (["goal_type"], ["tag", "form", "status", "if_not_met"]),
    "assign_user": ([], ["user"]),
    "create_task": (["title"], ["due_in_days", "assign_to"]),
    "update_contact_field": (["field", "value"], []),
    "add_to_workflow": (["workflow"], []),
    "remove_from_workflow": (["workflow"], []),
    "send_review_request": ([], []),
    "webhook": (["url"], ["method"]),
    # model and temperature: optional, default to the export's gpt-5-mini and 0.2
    # (compile_ghl.AI_DEFAULT_MODEL / AI_DEFAULT_TEMPERATURE).
    "ai_step": (["prompt"], ["output_field", "model", "temperature"]),
    "call": (["whisper"], ["to", "timeout_seconds"]),
    "manual_action": (["type"], ["title", "instructions"]),
    "go_to": (["target"], []),
    "end": ([], []),
}

TRIGGER_OPS = {
    "form_submitted", "survey_submitted", "customer_replied", "contact_created",
    "contact_tag_added", "contact_tag_removed", "pipeline_stage_changed",
    "opportunity_created", "opportunity_status_changed", "appointment_status",
    "inbound_webhook", "missed_call", "invoice_paid", "order_submitted", "birthday",
    "task_completed",
}

GOAL_TYPES = {
    "tag_added": "Added a contact Tag",
    "tag_removed": "Removed a contact Tag",
    "form_submitted": "Form Submitted",
    "appointment_status": "Appointment status",
    "payment_received": "Payment Received",
    "email_event": "Received an Email Event",
    "trigger_link": "Clicked a trigger link",
    "invoice_paid": "Invoice paid",
}


@dataclass
class Prerequisites:
    tags: List[str] = field(default_factory=list)
    pipelines: Dict[str, List[str]] = field(default_factory=dict)
    forms: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    workflows: List[str] = field(default_factory=list)
    calendars: List[str] = field(default_factory=list)

    def add(self, bucket: str, value: Optional[str], stage: Optional[str] = None) -> None:
        if not value:
            return
        if bucket == "pipelines":
            stages = self.pipelines.setdefault(value, [])
            if stage and stage not in stages:
                stages.append(stage)
            return
        lst: List[str] = getattr(self, bucket)
        if value not in lst:
            lst.append(value)


def _q(value: object) -> str:
    return '"{}"'.format(str(value).replace('"', "'"))


def _strip_step(label: str) -> str:
    return re.sub(r"^\d+[a-z]?\s*[·.:-]\s*", "", label).strip()


def _node_op(node: Node) -> str:
    if node.kind == "flow.wait":
        return "wait"
    if node.kind == "flow.branch":
        return "if_else"
    if node.kind == "flow.noop":
        return "end"
    if node.kind in ("ai.llm", "ai.agent"):
        return "ai_step"
    if node.app == "ghl" and node.op:
        return node.op
    raise SpecError(
        "node {!r}: GHL specs need app \"ghl\" and an op from the closed list, got "
        "kind={!r} app={!r} op={!r}".format(node.key, node.kind, node.app, node.op)
    )


def _check_params(node: Node, op: str) -> None:
    if op not in OPS:
        raise SpecError("node {!r}: unknown GHL op {!r}; allowed: {}".format(
            node.key, op, ", ".join(sorted(OPS))))
    required, optional = OPS[op]
    missing = [p for p in required if p not in node.params or node.params[p] in ("", None)]
    if missing:
        raise SpecError("node {!r} ({}): missing required params {}".format(
            node.key, op, missing))
    if op == "goal" and node.params["goal_type"] not in GOAL_TYPES:
        raise SpecError("node {!r}: goal_type must be one of {}".format(
            node.key, sorted(GOAL_TYPES)))
    if op == "goal" and node.params["goal_type"] in ("tag_added", "tag_removed") \
            and not node.params.get("tag"):
        raise SpecError("node {!r}: goal on a tag needs params.tag".format(node.key))
    if op == "internal_notification" and node.params["type"] not in ("sms", "email", "in_app"):
        raise SpecError("node {!r}: internal_notification.type must be sms, email or in_app".format(node.key))


def _describe(node: Node, op: str, pre: Prerequisites, spec: WorkflowSpec) -> str:
    p = node.params
    name = _strip_step(node.label)
    if op == "form_submitted":
        form = p.get("form")
        pre.add("forms", form)
        return "Trigger \"Form submitted\". Filter: form is {}.".format(
            _q(form) if form else "any form (no filter)")
    if op == "survey_submitted":
        return "Trigger \"Survey submitted\". Filter: survey is {}.".format(
            _q(p.get("survey")) if p.get("survey") else "any survey (no filter)")
    if op == "customer_replied":
        ch = p.get("channels") or ["all channels"]
        return "Trigger \"Customer replied\". Reply channel: {}. No other filters.".format(
            ", ".join(ch) if isinstance(ch, list) else ch)
    if op == "contact_created":
        return "Trigger \"Contact created\". No filters."
    if op in ("contact_tag_added", "contact_tag_removed"):
        pre.add("tags", p["tag"])
        return "Trigger \"Contact tag\". Tag {}: {}.".format(
            "added" if op.endswith("added") else "removed", _q(p["tag"]))
    if op == "pipeline_stage_changed":
        pre.add("pipelines", p["pipeline"], p["stage"])
        return "Trigger \"Pipeline stage changed\". Pipeline {}, stage moved to {}.".format(
            _q(p["pipeline"]), _q(p["stage"]))
    if op == "opportunity_created":
        pre.add("pipelines", p["pipeline"])
        return "Trigger \"Opportunity created\". Pipeline {}.".format(_q(p["pipeline"]))
    if op == "opportunity_status_changed":
        if p.get("pipeline"):
            pre.add("pipelines", p["pipeline"])
        return "Trigger \"Opportunity status changed\". Status changed to {}{}.".format(
            _q(p["status"]), ", pipeline {}".format(_q(p["pipeline"])) if p.get("pipeline") else "")
    if op == "appointment_status":
        if p.get("calendar"):
            pre.add("calendars", p["calendar"])
        return "Trigger \"Appointment status\". Status is {}{}.".format(
            _q(p["status"]), ", calendar {}".format(_q(p["calendar"])) if p.get("calendar") else "")
    if op == "inbound_webhook":
        return "Trigger \"Inbound webhook\". No mapping needed for this build."
    if op == "missed_call":
        return "Trigger \"Call status\": missed call."
    if op == "invoice_paid":
        return "Trigger \"Invoice\": invoice paid."
    if op == "order_submitted":
        return "Trigger \"Order submitted\". No filters."
    if op == "birthday":
        return "Trigger \"Birthday reminder\". On the birthday."
    if op == "task_completed":
        return "Trigger \"Task completed\". No filters."

    if op == "add_tag":
        pre.add("tags", p["tag"])
        return "Action \"Add contact tag\". Tag: {}.".format(_q(p["tag"]))
    if op == "remove_tag":
        pre.add("tags", p["tag"])
        return "Action \"Remove contact tag\". Tag: {}.".format(_q(p["tag"]))
    if op == "send_sms":
        return "Action \"Send SMS\". Message text, exactly: {}".format(_q(p["message"]))
    if op == "send_email":
        extra = " From name: {}.".format(_q(p["from_name"])) if p.get("from_name") else ""
        return "Action \"Send email\". Subject: {}. Body, exactly: {}{}".format(
            _q(p["subject"]), _q(p["body"]), extra)
    if op == "wait":
        amount, unit = p.get("amount"), p.get("unit")
        if amount is None or not unit:
            parsed = for_wait(node)
            amount = parsed.get("amount", amount or 1)
            unit = parsed.get("unit", unit or "days")
        unit_word = str(unit).rstrip("s") if int(amount) == 1 else str(unit)
        return "Action \"Wait\". Wait for a set time: {} {}.".format(amount, unit_word)
    if op == "create_opportunity":
        pre.add("pipelines", p["pipeline"], p["stage"])
        bits = ["Action \"Create/Update opportunity\". Pipeline: {}. Stage: {}.".format(
            _q(p["pipeline"]), _q(p["stage"]))]
        if p.get("name"):
            bits.append("Opportunity name: {}.".format(_q(p["name"])))
        if p.get("value") is not None:
            bits.append("Lead value: {}.".format(p["value"]))
        bits.append("Status: {}.".format(p.get("status", "open")))
        return " ".join(bits)
    if op == "update_opportunity":
        pre.add("pipelines", p["pipeline"], p["stage"])
        return "Action \"Create/Update opportunity\" (update the existing one). Pipeline: {}. Move to stage: {}. Status: {}.".format(
            _q(p["pipeline"]), _q(p["stage"]), p.get("status", "open"))
    if op == "internal_notification":
        kind = {"sms": "SMS", "email": "Email", "in_app": "Notification"}[p["type"]]
        to = p.get("to", "assigned user")
        s = "Action \"Send internal notification\". Type: {}. Send to: {}.".format(kind, to)
        if p["type"] == "email" and p.get("subject"):
            s += " Subject: {}.".format(_q(p["subject"]))
        s += " Message, exactly: {}".format(_q(p["message"]))
        return s
    if op == "if_else":
        return "Action \"If/Else\". Branch name: {}. Condition: {}.".format(_q(name), p["condition"])
    if op == "goal":
        gt = GOAL_TYPES[p["goal_type"]]
        s = "Action \"Goal event\". Type of goal: {}.".format(_q(gt))
        if p.get("tag"):
            pre.add("tags", p["tag"])
            s += " Tag: {}.".format(_q(p["tag"]))
        if p.get("form"):
            pre.add("forms", p["form"])
            s += " Form: {}.".format(_q(p["form"]))
        if p.get("status"):
            s += " Status: {}.".format(_q(p["status"]))
        s += " If the contact reaches this goal without meeting its conditions: {}.".format(
            {"end": "End this workflow", "continue": "Continue anyway"}.get(
                p.get("if_not_met", "end"), p.get("if_not_met")))
        return s
    if op == "assign_user":
        return "Action \"Assign to user\". User: {}.".format(p.get("user", "round robin across all users"))
    if op == "create_task":
        s = "Action \"Create task\". Title: {}.".format(_q(p["title"]))
        if p.get("due_in_days") is not None:
            s += " Due in {} days.".format(p["due_in_days"])
        s += " Assign to: {}.".format(p.get("assign_to", "the contact's assigned user"))
        return s
    if op == "update_contact_field":
        pre.add("fields", p["field"])
        return "Action \"Update contact field\". Field: {}. Value: {}.".format(_q(p["field"]), _q(p["value"]))
    if op == "add_to_workflow":
        pre.add("workflows", p["workflow"])
        return "Action \"Add to workflow\". Workflow: {}.".format(_q(p["workflow"]))
    if op == "remove_from_workflow":
        pre.add("workflows", p["workflow"])
        return "Action \"Remove from workflow\". Workflow: {}.".format(_q(p["workflow"]))
    if op == "send_review_request":
        return "Action \"Send review request\"."
    if op == "webhook":
        return "Action \"Webhook\". Method: {}. URL: {}.".format(p.get("method", "POST"), p["url"])
    if op == "ai_step":
        from .compile_ghl import AI_DEFAULT_MODEL, AI_DEFAULT_TEMPERATURE
        s = "Action \"GPT powered\" (AI step). Prompt, exactly: {} Model: {}. Temperature: {}.".format(
            _q(p["prompt"]), p.get("model", AI_DEFAULT_MODEL), p.get("temperature", AI_DEFAULT_TEMPERATURE))
        if p.get("output_field"):
            pre.add("fields", p["output_field"])
            s += " Save the answer to custom field {}.".format(_q(p["output_field"]))
        return s
    if op == "call":
        return ("Action \"Call\" (the automated call). Call the user first: {}. Play this whisper message to the user before connecting to the contact, exactly: {}. "
                "Then connect the call to the contact. Ring timeout: {} seconds.").format(
            p.get("to", "the contact's assigned user"), _q(p["whisper"]), p.get("timeout_seconds", 30))
    if op == "manual_action":
        kind = {"call": "Manual Call", "sms": "Manual SMS"}[p["type"]]
        s = "Action \"Manual action\". Type: {}.".format(kind)
        if p.get("title"):
            s += " Title: {}.".format(_q(p["title"]))
        if p.get("instructions"):
            s += " Instructions for the rep, exactly: {}".format(_q(p["instructions"]))
        return s
    if op == "go_to":
        return "Action \"Go To\". Jump to the step named {}.".format(_q(p["target"]))
    if op == "end":
        return "End of this branch. Nothing else runs here."
    raise SpecError("unhandled op {!r}".format(op))


def render_prompt(spec: WorkflowSpec) -> Tuple[str, Prerequisites]:
    """Return (prompt_text, prerequisites)."""
    if spec.platform != "gohighlevel":
        raise SpecError("GHL prompt needs platform \"gohighlevel\", got {!r}".format(spec.platform))

    nodes = {n.key: n for n in spec.nodes if not n.is_ai_sub}
    outgoing: Dict[str, List[Tuple[str, Optional[str], bool]]] = {}
    for e in spec.edges:
        outgoing.setdefault(e.src, []).append((e.dst, e.branch, e.loop))

    # compile_ghl imports this module, so its shared name check is imported
    # here, where it is used.
    from .compile_ghl import name_param_problem

    ops = {k: _node_op(n) for k, n in nodes.items()}
    for k, n in nodes.items():
        _check_params(n, ops[k])
        # The refusal compile_ghl makes, word for word, before a prompt could
        # name a pipeline, stage, tag or field after a dict, list or number
        # (Prerequisites.add would otherwise fail on an unhashable dict).
        problem = name_param_problem(ops[k], n.params)
        if problem:
            raise SpecError("node {!r} ({}): {}".format(k, _strip_step(n.label), problem))

    triggers = [n for n in nodes.values() if n.is_trigger or ops[n.key] in TRIGGER_OPS]
    if not triggers:
        raise SpecError("GHL spec has no trigger node")

    pre = Prerequisites()
    lines: List[str] = []
    counter = [0]
    visited: Set[str] = set()

    def walk(key: str, indent: str) -> None:
        # Follow the main line; branches recurse with their own numbering.
        while key:
            if key in visited:
                lines.append("{}Then continue at the step named {}.".format(
                    indent, _q(_strip_step(nodes[key].label))))
                return
            visited.add(key)
            node = nodes[key]
            op = ops[key]
            counter[0] += 1
            n = counter[0]
            desc = _describe(node, op, pre, spec)
            lines.append("{}Step {} - name this step exactly {}. {}".format(
                indent, n, _q(_strip_step(node.label)), desc))
            if node.notes:
                lines.append("{}  (Purpose: {})".format(indent, node.notes))
            outs = outgoing.get(key, [])
            loops = [o for o in outs if o[2]]
            for dst, _b, _l in loops:
                lines.append("{}  After this step, add action \"Go To\" pointing at the step named {}.".format(
                    indent, _q(_strip_step(nodes[dst].label))))
            outs = [o for o in outs if not o[2]]
            if op == "if_else":
                yes = [o for o in outs if (o[1] or "").lower() in ("true", "yes")]
                no = [o for o in outs if (o[1] or "").lower() in ("false", "no")]
                lines.append("{}  YES branch (condition is true):".format(indent))
                if yes:
                    walk(yes[0][0], indent + "    ")
                else:
                    lines.append("{}    End.".format(indent))
                lines.append("{}  NO branch (condition is false, the \"None\" branch):".format(indent))
                if no:
                    walk(no[0][0], indent + "    ")
                else:
                    lines.append("{}    End.".format(indent))
                return
            if not outs:
                if op != "end":
                    lines.append("{}  End of the workflow after this step.".format(indent))
                return
            key = outs[0][0]

    # Triggers first (GHL lists them side by side), then the single main line.
    for t in triggers:
        visited.add(t.key)
        lines.append("Trigger - name it exactly {}. {}".format(_q(_strip_step(t.label)), _describe(t, ops[t.key], pre, spec)))
    starts: List[str] = []
    for t in triggers:
        for dst, _b, _l in outgoing.get(t.key, []):
            if dst not in starts:
                starts.append(dst)
    if not starts:
        raise SpecError("no edge leaves the trigger")
    if len(starts) > 1:
        raise SpecError("triggers fan out to different first steps; GHL has one main line")
    lines.append("")
    lines.append("Actions, in this exact order:")
    walk(starts[0], "")

    header = [
        "Build this GoHighLevel workflow exactly as specified. Name the workflow exactly {}.".format(_q(spec.title)),
        "Rules: create every step listed below, in the order given, with the exact step names and field values given. "
        "Do not add steps, do not remove steps, do not merge steps, do not reorder them, do not rename anything, "
        "do not ask me questions. Where a tag, pipeline, stage, form or field is named, use that exact name. "
        "Leave the workflow as a draft; do not publish.",
        "",
    ]
    footer = [
        "",
        "Checklist before you finish: {} trigger(s), {} action steps, workflow name {}. "
        "Every Send SMS, Send email and internal notification contains the exact message text above. "
        "Every Wait has the duration above. Every If/Else has both branches. Nothing is left unconfigured.".format(
            len(triggers), counter[0], _q(spec.title)),
    ]
    text = "\n".join(header + lines + footer)
    return text, pre


def render_prerequisites(pre: Prerequisites) -> str:
    out: List[str] = ["Create these in the sub-account BEFORE pasting the prompt, with these exact names:"]
    if pre.tags:
        out.append("Tags: " + ", ".join(pre.tags))
    for pipe, stages in pre.pipelines.items():
        out.append("Pipeline {}: stages in order: {}".format(_q(pipe), ", ".join(stages) if stages else "(any)"))
    if pre.forms:
        out.append("Forms: " + ", ".join(pre.forms))
    if pre.fields:
        out.append("Custom fields: " + ", ".join(pre.fields))
    if pre.workflows:
        out.append("Other workflows referenced: " + ", ".join(pre.workflows))
    if pre.calendars:
        out.append("Calendars: " + ", ".join(pre.calendars))
    if len(out) == 1:
        out.append("(nothing)")
    return "\n".join(out)
