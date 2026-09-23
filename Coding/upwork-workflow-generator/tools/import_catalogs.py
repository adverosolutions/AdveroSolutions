"""Translate the harvested catalogs into this project's key scheme.

The harvesting agents keyed their output `kind:vendor:operation` using each
platform's own vendor names (`googlesheets`, `google-email`, `builtin`). This
project keys on `kind:app:op` using its own app vocabulary. Rather than rewrite
twenty archetypes to match theirs, the mapping lives here — so a re-harvest is
one command, not a migration.

Two rules make the merge forgiving:

* Every app entry is also registered under `kind:app:` (no operation). The
  resolver falls back to that, so an op the harvest did not cover — `gmail:draft`
  when only `gmail:send` was found — still lands on the right node type instead
  of degrading to a generic HTTP request.
* Anything not covered at all keeps its stub. The loader merges verified over
  stub, so this never subtracts coverage.

    python3 tools/import_catalogs.py ../n8n-node-catalog.json ../make_module_catalog.json
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_DIR = os.path.join(os.path.dirname(HERE), "upwork_gen", "catalog")

# ---------------------------------------------------------------------------
# n8n: harvested key -> one or more keys in our scheme
# ---------------------------------------------------------------------------

N8N_MAP: Dict[str, List[str]] = {
    "ai.agent:langchain:tools_agent":            ["ai.agent::"],
    "ai.llm:langchain:basic_llm_chain":          ["ai.llm::"],
    "ai.llm:openai:text_response":               ["app.action:openai:message", "app.action:openai:"],
    "ai.model:openai:chat":                      ["ai.model:openai:", "ai.model::"],
    "ai.model:anthropic:chat":                   ["ai.model:anthropic:"],
    "ai.memory:langchain:buffer_window":         ["ai.memory::"],
    "ai.tool:langchain:http_request":            ["ai.tool:http:"],
    "ai.tool:langchain:call_workflow":           ["ai.tool:workflow:", "ai.tool::"],
    "ai.embed:openai:embeddings":                ["ai.embed:openai:", "ai.embed::"],
    "ai.vectorstore:pinecone:retrieve_as_tool":  ["ai.vectorstore:pinecone:", "ai.vectorstore::"],
    "ai.parser:langchain:structured_output":     ["ai.parser::"],

    "trigger.webhook:webhook:post":              ["trigger.webhook::"],
    "trigger.schedule:schedule:every_hour":      ["trigger.schedule::"],
    "trigger.chat:langchain:chat_message":       ["trigger.chat::"],
    "trigger.app:calendly:invitee_created":      ["trigger.app::", "app.action:calendly:"],

    "data.transform:set:manual":                 ["data.transform::"],
    "data.code:code:javascript":                 ["data.code::"],
    "data.merge:merge:append":                   ["data.merge::"],
    "data.split:splitinbatches:loop":            ["data.split::"],
    "flow.branch:if:condition":                  ["flow.branch::"],
    "flow.switch:switch:rules":                  ["flow.switch::"],
    "flow.noop:noop:passthrough":                ["flow.noop::"],
    "net.http:http:post_json":                   ["net.http::"],
    "net.respond:webhook:respond_json":          ["net.respond::"],

    "app.action:googlesheets:append_or_update":  ["app.action:googleSheets:append", "app.action:googleSheets:"],
    "app.action:gmail:send_message":             ["app.action:gmail:send", "app.action:gmail:"],
    "app.action:slack:post_message":             ["app.action:slack:post", "app.action:slack:"],
    "app.action:airtable:create_record":         ["app.action:airtable:create", "app.action:airtable:"],
    "app.action:hubspot:upsert_contact":         ["app.action:hubspot:create_contact", "app.action:hubspot:"],
    "app.action:notion:create_page":             ["app.action:notion:create", "app.action:notion:"],
    "app.action:telegram:send_message":          ["app.action:telegram:send", "app.action:telegram:"],
    "app.action:whatsapp:send_message":          ["app.action:whatsapp:send", "app.action:whatsapp:"],
    "app.action:discord:send_message":           ["app.action:discord:send", "app.action:discord:"],
    "app.action:twilio:send_sms":                ["app.action:twilio:send", "app.action:twilio:"],
    "app.action:postgres:execute_query":         ["app.action:postgres:insert", "app.action:postgres:"],
    "app.action:stripe:create_charge":           ["app.action:stripe:get", "app.action:stripe:"],
    "app.action:shopify:create_order":           ["app.action:shopify:get", "app.action:shopify:"],
    "app.action:googledrive:upload_file":        ["app.action:googleDrive:upload", "app.action:googleDrive:"],
    "app.action:googledocs:create_document":     ["app.action:googleDocs:create", "app.action:googleDocs:"],
    "app.action:wordpress:create_post":          ["app.action:wordpress:create", "app.action:wordpress:"],
}

# ---------------------------------------------------------------------------
# Make: harvested key -> one or more keys in our scheme
# ---------------------------------------------------------------------------

MAKE_MAP: Dict[str, List[str]] = {
    # One webhook module serves every instant trigger shape we emit.
    "trigger.webhook:gateway:custom-web-hook": [
        "trigger.webhook::", "trigger.app::", "trigger.form::", "trigger.chat::",
    ],
    "trigger.email:email:trigger-new-email":   ["trigger.email::"],

    # No schedule module exists in Make — the cadence lives on the scenario
    # record, outside the blueprint. An HTTP poll is the honest stand-in, and
    # compile_make sets metadata.instant false for it.
    "net.http:http:action-send-data":          ["net.http::", "trigger.schedule::"],

    "data.transform:util:set-variable2":       ["data.transform::"],
    # Make has no native code module; a third-party one would fail to import
    # for anyone without that app installed. Set-variables is the safe built-in.
    "data.transform:util:set-variables":       ["data.code::"],
    "data.merge:builtin:basic-merge":          ["data.merge::"],
    "data.aggregate:builtin:basic-aggregator": ["data.aggregate::"],
    "data.split:builtin:basic-feeder":         ["data.split::"],
    "flow.wait:util:function-sleep":           ["flow.wait::"],
    "flow.noop:builtin:ignore":                ["flow.noop::"],
    "net.respond:gateway:webhook-respond":     ["net.respond::"],

    # Both fan-out kinds compile to a router. BasicIfElse uses a `branches`
    # shape this compiler does not emit, so mapping switch to it would produce
    # a blueprint the editor cannot render.
    "flow.branch:builtin:basic-router":        ["flow.branch::", "flow.switch::", "data.filter::"],

    "ai.llm:openai-gpt-3:create-completion":   ["ai.llm::", "ai.agent::", "app.action:openai:message", "app.action:openai:"],
    "ai.parser:openai-gpt-3:transform-text-to-structured-data": ["ai.parser::"],

    "app.action:google-sheets:add-row":            ["app.action:googleSheets:append", "app.action:googleSheets:"],
    "app.action:google-sheets:get-sheet-content":  ["app.action:googleSheets:read"],
    "app.action:google-sheets:update-row":         ["app.action:googleSheets:update"],
    "app.action:google-email:action-send-email":   ["app.action:gmail:send", "app.action:gmail:"],
    "app.action:slack:create-message":             ["app.action:slack:post", "app.action:slack:"],
    "app.action:airtable:action-create-record":    ["app.action:airtable:create", "app.action:airtable:"],
    "app.action:airtable:action-search-records":   ["app.action:airtable:search"],
    "app.action:airtable:action-update-records":   ["app.action:airtable:update"],
    "app.action:notion:create-a-page":             ["app.action:notion:create", "app.action:notion:"],
    "app.action:telegram:send-reply-message":      ["app.action:telegram:send", "app.action:telegram:"],
    "app.action:discord:create-message":           ["app.action:discord:send", "app.action:discord:"],
    "app.action:whatsapp-business-cloud:send-message": ["app.action:whatsapp:send", "app.action:whatsapp:"],
    "app.action:google-drive:upload-a-file":       ["app.action:googleDrive:upload", "app.action:googleDrive:"],
    "app.action:google-docs:create-a-document":    ["app.action:googleDocs:create", "app.action:googleDocs:"],
    "app.action:google-calendar:create-an-event":  ["app.action:googleCalendar:create", "app.action:googleCalendar:"],
    "app.action:quickbooks:make-api-call":         ["app.action:quickbooks:create", "app.action:quickbooks:"],
    "app.action:calendly:list-events":             ["app.action:calendly:get", "app.action:calendly:"],
    "app.action:pdf-co:htm-lto-pdf":               ["app.action:extractFile:pdf", "app.action:extractFile:"],
}

MAKE_SPECIAL = {
    "set_variable": "data.transform:util:set-variable2",
    "router": "flow.branch:builtin:basic-router",
}


def build_n8n(path: str) -> Dict[str, Any]:
    raw = json.load(open(path, "r", encoding="utf-8"))
    nodes = raw["nodes"]
    meta = raw.get("$meta", {})

    entries: Dict[str, Any] = {}
    unmapped: List[str] = []
    for source_key, node in nodes.items():
        targets = N8N_MAP.get(source_key)
        if not targets:
            if source_key != "flow.noop:sticky:note":
                unmapped.append(source_key)
            continue
        for target in targets:
            entries[target] = {
                "type": node["type"],
                "typeVersion": node["typeVersion"],
                "parameters": node.get("parameters", {}),
                "verified": True,
                "source": node.get("source", meta.get("method", "")),
            }

    out: Dict[str, Any] = {
        "_meta": {
            "status": "verified",
            "verified_against": meta.get("verifiedAgainst"),
            "verified_on": meta.get("verifiedOn"),
            "method": meta.get("method"),
            "unmapped_from_harvest": sorted(unmapped),
        },
        "entries": entries,
    }

    sticky = nodes.get("flow.noop:sticky:note")
    if sticky:
        out["sticky"] = {
            "type": sticky["type"],
            "typeVersion": sticky["typeVersion"],
            "verified": True,
        }
    return out


def build_make(path: str) -> Dict[str, Any]:
    raw = json.load(open(path, "r", encoding="utf-8"))

    entries: Dict[str, Any] = {}
    for source_key, module in raw.items():
        for target in MAKE_MAP.get(source_key, []):
            entries[target] = {
                "module": module["module"],
                "version": module["version"],
                "parameters": module.get("sample_parameters") or {},
                "verified": True,
                "source": module.get("source", ""),
            }

    special: Dict[str, Any] = {}
    for name, source_key in MAKE_SPECIAL.items():
        module = raw.get(source_key)
        if module:
            special[name] = {
                "module": module["module"],
                "version": module["version"],
                "verified": True,
                "source": module.get("source", ""),
            }

    return {
        "_meta": {
            "status": "verified",
            "harvest_entries": len(raw),
            "note": "Module ids and versions mined from real exported blueprints; "
                    "every source entry carries the URL it came from.",
        },
        "entries": entries,
        "special": special,
    }


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    n8n = build_n8n(argv[0])
    make = build_make(argv[1])

    for name, data in (("n8n_nodes.verified.json", n8n), ("make_modules.verified.json", make)):
        path = os.path.join(CATALOG_DIR, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print("wrote {:<32} {} entries".format(name, len(data["entries"])))

    unmapped = n8n["_meta"]["unmapped_from_harvest"]
    if unmapped:
        print("\nharvested but unmapped (no slot in our vocabulary yet):")
        for key in unmapped:
            print("  - {}".format(key))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
