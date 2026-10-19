# Adapter extension contract

Maintenance scope, 19 October 2026. All scenes remain illustrative samples. The outer deck, palette, font, controls and timing are unchanged.

- `workbench`: custom project workspace; `record`, `messages`, `outcome`, `carousel`. Never call it a native vendor screen. Use this for project deliverables outside supported native apps.
- `claude-code`, `codex`: terminal task transcript for `workflow`; project output panels for `record`, `messages`, `outcome`. Output panels explicitly say project output. These do not claim native CRM or messaging functionality.
- `ghl`: existing workflow, record, messages, outcome, workshop unchanged.
- `n8n`, `make`: workflow only. Their project result screens use `workbench`.

Existing scene fields remain unchanged; carousel has the additional content structure documented below. Specs contain no raw HTML, CSS or coordinates. The first scene is still a required workflow; every route needs a required outcome, workshop or carousel proof scene.

Agent workflow keys: `prompt` (the single root trigger), `read`, `edit`, `command`, `review`, `result`. These are conceptual task stages, not importable nodes or API tool identifiers. Use `label` for the concrete task and `detail` for sample input/output. Use a single linear chain with every node in `runOrder`, 2–12 stages; first is `prompt`. Each stage requires one `statuses` and `context.states` entry. Context fields describe the project; related rows describe project files/artifacts. Do not invent connectors, a scheduler or autonomous legal decisions.

Example sequences: Claude legal intake: prompt → read source → edit structured draft → review citations → result. Claude/Codex QA: prompt → read project → command test suite → review failures → result. Separate agent scenes can distinguish the two tools. Native n8n document/technical workflows: `manual_trigger` or `webhook` → `http_request` → `edit_fields` → supported delivery action. LLM calls can use `http_request`; `ai_agent`/`chat_model` remain unavailable. Make/Claude Instagram: existing Make `custom_webhook`/`http_request` actions for the API orchestration, followed by a workbench messages/outcome scene for drafts/review; never a fictitious Claude Make module or unsupported native Instagram screen.

Nonworkflow schemas are unchanged: record uses sourceFields/fields/events/notice; messages uses fields/items/notice (`sms`, `email`, `internal` remain channel values); outcome uses fields/stages/stageSequence/metrics/note and optional proof. For agent output messages, use `internal` for project notes, or label email/SMS as drafts. No scene transmits anything.

Vendor references checked: [Claude Code overview](https://code.claude.com/docs/en/overview), [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [n8n Manual Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.manualworkflowtrigger/). Agent interiors show the shared terminal concepts (prompt, task transcript, project context); they do not promise a pixel-identical vendor release.

## Carousel content approval preview

Frozen addition: `kind: "carousel"`, `platform: "workbench"` only. A required carousel counts as visible proof. Content is exactly `{name, subtitle, slides: [{title, body, imageData, alt}], caption, fields: [{label, value}]}`. Supply 2–5 slides and exactly one scene status per slide. Existing plain text limits apply: name/title 120 characters, body 800, caption/alt/subtitle 600, field label 80 and value 240. `imageData` must be `data:image/jpeg;base64,...`, `data:image/png;base64,...` or `data:image/webp;base64,...`, with strict base64, nonempty bytes and matching file signature. Total decoded imagery is at most 2 MiB per scene. No SVG, remote URL, file URI or extra image metadata fields. Embed only supplied/approved photographs; alt text describes each image. This is a custom content approval preview, never a native Instagram screen. It publishes nothing. Existing replay advances photos and copy, Show result selects the final slide, Replay returns to the first; the full social caption remains visible alongside/below the preview.
