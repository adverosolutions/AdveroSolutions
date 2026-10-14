# Workflow platform catalog

This template produces local, illustrative sales demonstrations. The software interiors follow the repository's established examples and documented workflow concepts. They are not live software, importable automation exports, or a claim of pixel-identical current vendor interfaces. Every workflow frame displays “Illustrative sample.” Icons are semantic interface symbols; they are not vendor logos.

## Supported adapters

| Key | Interior | Available visual action keys |
| --- | --- | --- |
| `ghl` | Vertical action cards, condition branches, contact context | `facebook_lead`, `assign_user`, `opportunity`, `sms`, `email`, `notification`, `contact_tag`, `event_date`, `wait`, `condition` |
| `n8n` | Horizontal rectangular nodes, main input/output ports, true/false branches | `webhook`, `edit_fields`, `if`, `http_request`, `slack`, `gmail`, `google_sheets` |
| `make` | Circular modules, green routers, dotted route connections | `custom_webhook`, `google_sheets_add_row`, `router`, `gmail_send_email`, `slack_create_message`, `http_request` |

`n8n.ai_agent` and `n8n.chat_model` remain in the catalog with `available: false`. This schema does not describe cluster subnodes or their separate AI connectors, so the compiler and adapter reject these actions. Supporting them requires a reviewed template and schema change.

`contact_tag` represents the HighLevel **Contact Tag** trigger, configured for a tag being added. It does not mean an Add Contact Tag action. `google_sheets` represents n8n's append-row operation; the other application keys above likewise use the operation named in the catalog. Job labels describe the sample's purpose; the catalog's action label remains visible separately.

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

The compiler and renderer require 2–12 unique nodes, one root trigger, reachable acyclic edges, and a `runOrder` beginning at that trigger and following one connected sample path. Each adapter uses the same topological rank calculation. Cards or modules are placed in lanes derived from graph depth and branch count. Text length increases reserved node height. Longer edges use an outer corridor rather than passing through intermediate node boxes. No scene or job specifies pixel coordinates.

For n8n `if`, outgoing edges correspond to the **true** then **false** port in edge order; literal `true` or `false` labels select that port explicitly. There are at most two outputs. Other edge labels describe the sample condition or route. Make router routes are shown as a sample selected by `runOrder`; other routes remain inactive. This demonstration does not simulate every bundle or every router route of a real scenario.

`applyStep(scene, index)` updates only the mounted workflow frame matching that scene ID and platform under `#stage`. Nodes visited through the supplied index remain active; only consecutive edges in the sample path become active. Off-path branches stay inactive. Calling index `0` resets to the trigger. Context state advances through `scene.content.context.states`, holding its last entry if it has fewer entries than the path. Runtime separately displays `scene.statuses` below the frame.

Canvas overflow is contained inside a focusable scroll region. The canvas pans internally if the current sample node leaves its visible area; no page scrolling or timers are created by the adapter. Mobile keeps a 400px canvas viewport and places context below it. Labels retain their font size instead of shrinking a large graph to fit a phone. Reduced-motion settling is controlled by runtime; platform transitions also respect the media preference.

## Reference-only platforms

These existing examples are preserved as references. They have no reusable adapter in this version. Paths are relative to this template directory.

| Catalog key | Example |
| --- | --- |
| `airtable` | `../../jobs/_examples/finished-airtable.html` |
| `clay` | `../../jobs/_examples/finished-clay.html` |
| `clickup` | `../../jobs/_examples/finished-clickup.html` |
| `claude-code` | `../../jobs/_examples/finished-claude-code.html` |
| `cold-email` | `../../jobs/_examples/finished-cold-email.html` |
| `grok` | `../../jobs/_examples/finished-grok.html` |
| `hermes` | `../../jobs/_examples/finished-hermes.html` |
| `hubspot` | `../../jobs/_examples/finished-hubspot.html` |
| `notion` | `../../jobs/_examples/finished-notion.html` |
| `pipedrive` | `../../jobs/_examples/finished-pipedrive.html` |
| `voice-agent` | `../../jobs/_examples/finished-voice-agent.html` |
| `zapier` | `../../jobs/_examples/finished-zapier.html` |

## Evidence and review limits

The interior references are [GHL](../../jobs/_examples/finished-ghl.html), [n8n](../../jobs/_examples/finished-n8n.html) and [Make](../../jobs/_examples/finished-make.html). GHL also follows the approved V4 vertical-card/context layout. Those references are illustrations, not evidence of the vendors' current pixel layout.

Vendor documentation checked on 14 October 2026 supports the action families and graph concepts:

- HighLevel: [workflow actions](https://help.gohighlevel.com/support/solutions/articles/155000002294-what-are-workflow-actions-complete-list-), [workflow triggers](https://help.gohighlevel.com/support/solutions/articles/48001229927-workflows-vs-campaigns-triggers-deprecated-features-), [Assign To User](https://help.gohighlevel.com/support/solutions/articles/155000003300-workflow-action-assign-to-user), [Set Event Start Date](https://help.gohighlevel.com/support/solutions/articles/48001202723-workflow-action-set-event-start-date).
- n8n: [Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [Edit Fields](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.set/), [If](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.if/), [Slack](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.slack/), [Gmail](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/), [Google Sheets](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.googlesheets/).
- Make: [Webhooks](https://help.make.com/webhooks), [Router](https://help.make.com/router), [Gmail modules](https://apps.make.com/gmail-modules), [Google Sheets](https://apps.make.com/google-sheets), [Slack](https://apps.make.com/slack), [HTTP](https://apps.make.com/http). The local established example also supplies the module shapes and app/action captions.

Syntax and DOM checks cover the adapters' generated text, sample state and bounded node geometry. Desktop and 390px browser inspection and independent reviewer approval are still required for template acceptance. These checks do not certify real automation imports or service execution.
