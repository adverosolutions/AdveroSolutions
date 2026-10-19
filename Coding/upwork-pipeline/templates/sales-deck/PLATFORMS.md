# Workflow platform catalog

> **Visual status, 19 October 2026:** This file describes technical renderer support, not accepted native visual fidelity. Lorenzo rejected the current batch. Start with [the native screen library](visual-reference/README.md) and its product/surface plans. Existing illustrations and conceptual transcripts cannot serve as proof of the current vendor UI. No replacement native template is accepted yet.

This template produces local, illustrative sales demonstrations. The software interiors follow the repository's established examples and documented workflow concepts. They are not live software, importable automation exports, or a claim of pixel-identical current vendor interfaces. Every workflow frame displays “Illustrative sample.” Icons are semantic interface symbols; they are not vendor logos.

## Supported adapters

| Key | Interior | Available visual action keys |
| --- | --- | --- |
| `ghl` | Vertical action cards, condition branches, contact context | `facebook_lead`, `assign_user`, `opportunity`, `sms`, `email`, `notification`, `contact_tag`, `event_date`, `wait`, `condition` |
| `n8n` | Horizontal rectangular nodes, main input/output ports, true/false branches | `webhook`, `manual_trigger`, `edit_fields`, `if`, `http_request`, `slack`, `gmail`, `google_sheets` |
| `make` | Circular modules, green routers, dotted route connections | `custom_webhook`, `google_sheets_add_row`, `router`, `gmail_send_email`, `slack_create_message`, `http_request` |
| `claude-code` | Terminal task transcript and project context | `prompt`, `read`, `edit`, `command`, `review`, `result` |
| `codex` | Terminal task transcript and project context | `prompt`, `read`, `edit`, `command`, `review`, `result` |
| `workbench` | Custom project workspace for records, drafts and results | No workflow actions |

`n8n.ai_agent` and `n8n.chat_model` remain in the catalog with `available: false`. This schema does not describe cluster subnodes or their separate AI connectors, so the compiler and adapter reject these actions. Supporting them requires a reviewed template and schema change.

`contact_tag` represents the HighLevel **Contact Tag** trigger, configured for a tag being added. It does not mean an Add Contact Tag action. `google_sheets` represents n8n's append-row operation; the other application keys above likewise use the operation named in the catalog. Job labels describe the sample's purpose; the catalog's action label remains visible separately.

## Scene compatibility

The compiler and runtime enforce this exact matrix. Adding a supported catalog entry alone never creates an adapter.

| Platform | Scene kinds |
| --- | --- |
| `ghl` | `workflow`, `record`, `messages`, `outcome`, `workshop` |
| `n8n`, `make` | `workflow` |
| `claude-code`, `codex` | `workflow`, `record`, `messages`, `outcome` |
| `workbench` | `record`, `messages`, `outcome`, `carousel` |

Agent workflows reuse existing graph fields as a strictly linear ordered task transcript: every node appears in `runOrder`, the chain starts with one `prompt`, and no branches or off-path stages are allowed. Action keys name conceptual task operations, not native importable nodes or API tool identifiers. `label` names the concrete task; `detail` shows its sample input or output. Context is project context; `related` rows describe project files/artifacts. Both terminal adapters display “Illustrative sample” and “Conceptual task stages · sample output.” Their shared terminal concepts follow vendor documentation; they do not reproduce a specific vendor version pixel for pixel.

`workbench` always says “Custom project workspace.” Nonworkflow agent scenes say “Claude Code · project output” or “Codex · project output”; they depict project artifacts and drafts, not a vendor CRM, email inbox or execution log. Their content schemas and replay behavior are unchanged. No non-GHL scene uses GHL navigation or tabs. A named but unsupported vendor such as HubSpot still requires its own adapter if a native screen is requested. Never relabel the custom workspace as that vendor.

n8n `manual_trigger` depicts the documented Manual Trigger (start by selecting Execute Workflow, with no automatic trigger). Use existing `http_request` for supported HTTP/API orchestration, including LLM API requests; this does not enable AI cluster connectors. None of these adapters runs commands, calls APIs or sends messages.

See [extension-contract.md](extension-contract.md) for the frozen content-worker contract and example sequences.

## Visual carousel proof

Workbench `carousel` scenes are a custom content approval preview with supplied inline photographs, slide title/body overlays, thumbnail sequence and the full social caption. They do not imitate native Instagram UI or publish content. They use the existing `statuses`/replay timer lifecycle: entry and Replay show slide one, Show result settles on the last slide, and reduced motion shows the final result immediately. A required carousel qualifies as visible proof on every route.

`content` requires `name`, `subtitle`, `slides`, `caption` and `fields`. Slides are 2–5 objects, each exactly `{title, body, imageData, alt}`; statuses must match their count. Existing plain text limits apply. Images must be strict inline base64 JPEG, PNG or WebP with matching binary signatures and at most 2 MiB decoded total per scene. SVG, remote/file URIs, additional fields, invalid encoding and mismatched signatures are rejected. Text and alt attributes are escaped. The compiler remains unchanged; image bytes are contained in the public standalone page. Source image provenance belongs in private job evidence.

## Catalog contract

`platforms.json` is loaded as the global `PLATFORM_CATALOG` before the runtime scripts. Its structure is:

```json
{
  "schemaVersion": 1,
  "platforms": {
    "ghl": {
      "name": "GoHighLevel",
      "status": "supported",
      "layout": "vertical",
      "sceneKinds": ["workflow", "record", "messages", "outcome", "workshop"],
      "referencePath": "../../jobs/_examples/finished-ghl.html",
      "sources": ["https://help.gohighlevel.com/..."],
      "actions": {
        "sms": {
          "label": "Send SMS",
          "kind": "action",
          "icon": "chat",
          "color": "#155eef",
          "available": true
        }
      }
    }
  },
  "referenceOnly": {}
}
```

Action `kind` values used by supported adapters are `trigger`, `action`, and `branch`. Unavailable AI entries use `cluster` and `subnode`. Application actions may include `app` for a visible app-and-operation caption. Unavailable entries include a `reason`. The icon key selects a local semantic SVG; color must be a six-digit hexadecimal value. These are visual catalog keys, not native import/module identifiers.

Only `platforms[key].status === "supported"` with `actions[type].available === true` is renderable. Unknown or reference-only platforms never fall back to GHL. Unknown and unavailable actions fail explicitly. Adding another platform is template maintenance, including an adapter, catalog, schema validation, fixtures and visual review.

## Rendering and graph behavior

`window.SalesPlatforms.renderWorkflow(scene, job)` returns only the `.native.sales-workflow` frame. Runtime owns the surrounding `.demo.panel`, replay controls and timers. Platform functions look up `window.SalesUI` at call time, allowing the platform script to precede the application script. Shared helper signatures are `esc(value)`, `icon(key)`, `avatar(jobOrInitials)`, and `fields([{label,value}])`.

All sample names, labels, details, context fields, context state and related paths come from `scene.content`; account information comes from `job.account`. Rendered strings are escaped. Node IDs are stored as escaped data attributes and compared as values, never interpolated into selectors.

The compiler and renderer require 2–12 unique nodes, one root trigger, reachable acyclic edges, and a `runOrder` beginning at that trigger and following one connected sample path. Canvas adapters use the same topological rank calculation. Cards or modules are placed in lanes derived from graph depth and branch count. Text length increases reserved node height. Longer edges use an outer corridor rather than passing through intermediate node boxes. No scene or job specifies pixel coordinates.

For n8n `if`, outgoing edges correspond to the **true** then **false** port in edge order; literal `true` or `false` labels select that port explicitly. There are at most two outputs. Other edge labels describe the sample condition or route. Make router routes are shown as a sample selected by `runOrder`; other routes remain inactive. This demonstration does not simulate every bundle or every router route of a real scenario.

`applyStep(scene, index)` updates only the mounted workflow frame matching that scene ID and platform under `#stage`. Nodes visited through the supplied index remain active; only consecutive edges in the sample path become active. Off-path branches stay inactive. Calling index `0` resets to the trigger. Context state advances through `scene.content.context.states`, holding its last entry if it has fewer entries than the path. Runtime separately displays `scene.statuses` below the frame.

Agent transcript overflow is contained in its own focusable scroll region. Replay resets its scroll position and task highlights; Show result settles the final stage and project state. Agent transcripts introduce no timers or external requests. On mobile the transcript keeps a 400px viewport with project context below it.

Canvas overflow is contained inside a focusable scroll region. The canvas pans internally if the current sample node leaves its visible area; no page scrolling or timers are created by the adapter. Mobile keeps a 400px canvas viewport and places context below it. Labels retain their font size instead of shrinking a large graph to fit a phone. Reduced-motion settling is controlled by runtime; platform transitions also respect the media preference.

## Reference-only platforms

These existing examples are preserved as references. They have no reusable adapter in this version. Paths are relative to this template directory.

| Catalog key | Example |
| --- | --- |
| `airtable` | `../../jobs/_examples/finished-airtable.html` |
| `clay` | `../../jobs/_examples/finished-clay.html` |
| `clickup` | `../../jobs/_examples/finished-clickup.html` |
| `cold-email` | `../../jobs/_examples/finished-cold-email.html` |
| `grok` | `../../jobs/_examples/finished-grok.html` |
| `hermes` | `../../jobs/_examples/finished-hermes.html` |
| `hubspot` | `../../jobs/_examples/finished-hubspot.html` |
| `notion` | `../../jobs/_examples/finished-notion.html` |
| `pipedrive` | `../../jobs/_examples/finished-pipedrive.html` |
| `voice-agent` | `../../jobs/_examples/finished-voice-agent.html` |
| `zapier` | `../../jobs/_examples/finished-zapier.html` |

## Agent and Manual Trigger evidence

Checked on 19 October 2026: [Claude Code overview](https://code.claude.com/docs/en/overview) documents reading code, editing files and running commands in terminal/project context; [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) documents the same terminal task loop and shows a prompt transcript. The local [Claude Code example](../../jobs/_examples/finished-claude-code.html) supplies the established terminal/project-files reference. [n8n Manual Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.manualworkflowtrigger/) documents manual workflow starts. No vendor documentation is needed for the explicitly custom workbench.

## Evidence and review limits

The interior references are [GHL](../../jobs/_examples/finished-ghl.html), [n8n](../../jobs/_examples/finished-n8n.html) and [Make](../../jobs/_examples/finished-make.html). GHL also follows the approved V4 vertical-card/context layout. Those references are illustrations, not evidence of the vendors' current pixel layout.

Vendor documentation checked on 14 October 2026 supports the action families and graph concepts:

- HighLevel: [workflow actions](https://help.gohighlevel.com/support/solutions/articles/155000002294-what-are-workflow-actions-complete-list-), [workflow triggers](https://help.gohighlevel.com/support/solutions/articles/48001229927-workflows-vs-campaigns-triggers-deprecated-features-), [Assign To User](https://help.gohighlevel.com/support/solutions/articles/155000003300-workflow-action-assign-to-user), [Set Event Start Date](https://help.gohighlevel.com/support/solutions/articles/48001202723-workflow-action-set-event-start-date).
- n8n: [Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [Edit Fields](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.set/), [If](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.if/), [Slack](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.slack/), [Gmail](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/), [Google Sheets](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.googlesheets/).
- Make: [Webhooks](https://help.make.com/webhooks), [Router](https://help.make.com/router), [Gmail modules](https://apps.make.com/gmail-modules), [Google Sheets](https://apps.make.com/google-sheets), [Slack](https://apps.make.com/slack), [HTTP](https://apps.make.com/http). The local established example also supplies the module shapes and app/action captions.

Syntax and DOM checks cover the adapters' generated text, sample state and bounded node geometry. Desktop and 390px browser inspection and independent reviewer approval are still required for template acceptance. These checks do not certify real automation imports or service execution.
