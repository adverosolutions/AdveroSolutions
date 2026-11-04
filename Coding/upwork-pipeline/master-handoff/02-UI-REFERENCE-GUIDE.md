# Native UI reference and readiness guide

Compiled on 2026-10-20 from saved research checked 19 October 2026 and the later repaired desktop review. No new web/account inspection is implied.

Read this product selectively: do not load every image into every worker context. The source board is [the saved visual library](sources/pipeline/templates/sales-deck/visual-reference/index.html).

## Readiness hierarchy

The dated research catalog has 29 product plans and productionReady:false throughout. Its older no-adapter descriptions predate the four native candidates. The candidate overlay below records that later implementation without granting production approval. Current review: [whole-walkthrough findings](sources/pipeline/templates/sales-deck/native-templates/SALES-REVIEW-2026-10-19.md).

A saved image, technical action catalog, implemented screen and accepted exact generation are four different states. Do not collapse them into supported/ready. Product-specific remaining evidence is mandatory.

## Historical prioritization evidence

The selected local corpus contained 149 deduplicated original posts with genuine Upwork URLs. This is Lorenzo’s historical selection, not all Upwork. Mentions overlap; conservative Make aliases can undercount. No fresh counts were collected for this handoff.

| Tool | Posts in that selected corpus |
| --- | --- |
| GoHighLevel | 54 |
| n8n | 47 |
| Zapier | 32 |
| Claude | 31 |
| OpenAI API | 18 |
| ChatGPT | 14 |
| HubSpot | 13 |
| Google Sheets | 10 |
| Claude Code | 9 |
| Make | 8 |
| Zoho | 8 |
| Gmail | 6 |

Public search-index signals have mixed crawl dates and category overlap; see the saved research for its limitations. Do not present them as live market share.

## Product-by-product saved knowledge

### GoHighLevel (`ghl`)

- Product category: CRM & automation
- Surface plan: Workflow Builder; Opportunities pipeline; Contact detail / overlay; Conversations; Calendar / booking; Funnel or form builder
- Current implementation/readiness: Desktop sales candidate; not blanket production parity
- Research snapshot adapter note (dated, not approval): Existing ghl renderer: visually rejected
- Rebuilt scope: Builder, Conversations, Opportunities
- Current boundary: Exact current account/settings and other GHL surfaces remain unverified.
- Candidate preview: [GoHighLevel](previews/ghl/page.html)
- Seed spec: [JSON](sources/pipeline/templates/sales-deck/native-templates/ghl.json)

**Visual anchors to reproduce**

- Account/sub-account context and native navigation
- Dotted infinite builder with compact action cards, plus controls and native builder tabs
- Opportunities as stage columns with opportunity cards and actual deal values
- Conversations as inbox list, thread, composer and contact details

**Sales evidence to make visible**

- A real sample enquiry enters the correct workflow
- One contact moves through the named pipeline stages
- The promised SMS/email appears in Conversations with the same name and details

**Do not substitute:** Do not place invented contact-context cards permanently inside the workflow canvas. Do not use fake reply-trigger nodes or a generic CRM interior.

**Research snapshot remaining work:** Rebuild the rejected workflow/CRM/message interiors against current references; add action setup and execution views only where needed. Capture the open contact/opportunity overlay; the selected Appointments image shows only its entry point. Verify account navigation, action labels and the exact builder generation before acceptance.

**Saved image evidence** (inspect the full image, including its qualification):

- [ghl-workflow-a40574215114](sources/pipeline/templates/sales-deck/visual-reference/assets/ghl-workflow-a40574215114.png): Workflow builder; Vendor-published UI reference; target account/version still needs confirmation. Source: [ghl-workflow](https://help.gohighlevel.com/support/solutions/articles/155000001254-workflow-builder-walkthrough). SHA-256 `a40574215114e89e69deb0fe965f6a284e4e6e52811abcba9a838c7b62e5f2a1`.
- [ghl-contact-2beadb770b86](sources/pipeline/templates/sales-deck/visual-reference/assets/ghl-contact-2beadb770b86.png): Appointments list — contact overlay entry point; The image shows Calendars > Appointments with a contact link highlighted. No contact or opportunity overlay is open; this is an entry-point reference only. Capture the open overlay before implementing that surface. Source: [ghl-contact](https://help.gohighlevel.com/support/solutions/articles/155000008627-how-to-use-the-contact-overlay-in-highlevel). SHA-256 `2beadb770b86a6326be2a78f7cc84c6dbce223c8f8328a854b1e5582a2686995`.
- [ghl-conversations-30e383a67a3b](sources/pipeline/templates/sales-deck/visual-reference/assets/ghl-conversations-30e383a67a3b.png): Conversations; Vendor-published UI reference; target account/version still needs confirmation. Source: [ghl-conversations](https://help.gohighlevel.com/support/solutions/articles/155000001321-right-panel-expandable-sidebar-in-conversations). SHA-256 `30e383a67a3b6570ad9ff6f18838fd7b8f59700691156151b4e7825cb0f30002`.
- [ghl-conversations-862e469c1971](sources/pipeline/templates/sales-deck/visual-reference/assets/ghl-conversations-862e469c1971.png): Conversations; Vendor-published UI reference; target account/version still needs confirmation. Source: [ghl-conversations](https://help.gohighlevel.com/support/solutions/articles/155000001321-right-panel-expandable-sidebar-in-conversations). SHA-256 `862e469c197142f31caf467a82fc1fd35088d5e3e141d2bb9a2cbc66b4964f2e`.

**Supplemental current-rebuild references**

- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/ghl-pipeline-3.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `a7e240ccbf8f2bfcb90a6d3c3fe71838c659150d84c8360831ff89a11a450446`.
- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/ghl-pipeline-4.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `f065b7c1a7b98fb7a73adc8791f5cf1ebc37e61a50e7c0b1f9c2d0d315bcdc0c`.
- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/ghl-card-config-3.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `7ea732eac4d11422cdc57347d0ea8963ce6ccec90b4a8d053e172fae7048e9af`.
- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/ghl-card-config-6.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `8d7f931de03eb96bfdd39f9e6a0fbee1280798425bf4826e4afe3dc250ee696c`.

### n8n (`n8n`)

- Product category: Workflow automation
- Surface plan: Workflow canvas; Node editor with input / parameters / output; Execution history and run detail; AI Agent cluster with model/tool connectors
- Current implementation/readiness: Desktop sales candidate; bounded editor/node scope
- Research snapshot adapter note (dated, not approval): Existing n8n renderer: visual rebuild; AI cluster unsupported
- Rebuilt scope: Editor canvas and returned-node output table
- Current boundary: Literal sample requests; no executed API/dynamic-expression proof. Mobile whole-flow entry limited. Typed AI Agent/model/tool support and current 2026 references added on 20 October; approval remains exact-generation only.
- Candidate preview: [n8n](previews/n8n/page.html)
- Seed spec: [JSON](sources/pipeline/templates/sales-deck/native-templates/n8n.json)

**Visual anchors to reproduce**

- Native canvas controls and workflow header
- App-icon nodes with real ports and connection geometry
- Separate input / parameters / output panes when a node is opened
- AI subnodes connect through the correct typed ports

**Sales evidence to make visible**

- The triggering payload enters the actual first node
- The selected branch and item count match the sample
- Node output and the destination record agree

**Do not substitute:** Do not invent native nodes or show AI Agent as an ordinary node with arbitrary main-line model links. Do not squeeze a large graph to illegible text.

**Research snapshot remaining work:** Replace generic node/context layout. Current adapter lacks AI cluster/subnode schema and a native execution inspector; these are explicit missing capabilities, not content-only repairs.

**Saved image evidence** (inspect the full image, including its qualification):

- [n8n-current-editor-f118523d2bb0](sources/pipeline/templates/sales-deck/visual-reference/assets/n8n-current-editor-f118523d2bb0.png): Current repository editor screenshots; Vendor-published UI reference; target account/version still needs confirmation. Source: [n8n-current-editor](https://github.com/n8n-io/n8n-docs/tree/main/docs/build/.gitbook/assets). SHA-256 `f118523d2bb0001d88e27b3068d2a4c1ec7d4b882232587d4b3cd64768f7dcbb`.
- [n8n-current-editor-d82393bef07f](sources/pipeline/templates/sales-deck/visual-reference/assets/n8n-current-editor-d82393bef07f.png): Current repository editor screenshots; Vendor-published UI reference; target account/version still needs confirmation. Source: [n8n-current-editor](https://github.com/n8n-io/n8n-docs/tree/main/docs/build/.gitbook/assets). SHA-256 `d82393bef07ff561134cfda4dba34672568906b931dd71be3346548c3dcda3e3`.

### Make (`make`)

- Product category: Workflow automation
- Surface plan: Scenario canvas; Module configuration and mapping; Route filter; Run inspector / bundles; Scenario history
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Existing make renderer: visual rebuild required

**Visual anchors to reproduce**

- Circular app modules with the real app and operation label
- Dotted connections, router routes and inline filters
- Native Run once and scheduling toolbar
- Bundle inspector stays distinct from the scenario canvas

**Sales evidence to make visible**

- The correct trigger produces the sample bundle
- Filters select the intended route
- The output bundle creates the promised result in its destination app

**Do not substitute:** A router can run multiple matching routes. Do not present it as a universal first-match if/else. Do not invent Make module identifiers or reuse a GHL action card.

**Research snapshot remaining work:** Rebuild scenario chrome and module geometry, add configuration/filter/bundle views, and verify actual operations. Keep JSON/module authenticity separate from visual correctness.

**Saved image evidence** (inspect the full image, including its qualification):

- [make-router-31817cc15a9d](sources/pipeline/templates/sales-deck/visual-reference/assets/make-router-31817cc15a9d.webp): Email module / Add another module — detail; Email module and Add another module control only; no router or filter is visible. This detail does not establish the full scenario layout. Source: [make-router](https://help.make.com/router). SHA-256 `31817cc15a9d8b9c2f22b20c85d1c4651468a379c42f60f36e2bed73d84fcce4`.
- [make-router-1b634a50c20a](sources/pipeline/templates/sales-deck/visual-reference/assets/make-router-1b634a50c20a.webp): Router and filters; Vendor-published UI reference; target account/version still needs confirmation. Source: [make-router](https://help.make.com/router). SHA-256 `1b634a50c20aea06ea8f4533286a6558619158f25d3f59423d8311cad118323d`.
- [make-router-9e0abcb55098](sources/pipeline/templates/sales-deck/visual-reference/assets/make-router-9e0abcb55098.webp): Router and filters; Vendor-published UI reference; target account/version still needs confirmation. Source: [make-router](https://help.make.com/router). SHA-256 `9e0abcb55098216bf64d9d6f6c5154438f2e834897c39080a1808420077789f5`.
- [make-router-e3054f5b5bf4](sources/pipeline/templates/sales-deck/visual-reference/assets/make-router-e3054f5b5bf4.webp): Router and filters; Vendor-published UI reference; target account/version still needs confirmation. Source: [make-router](https://help.make.com/router). SHA-256 `e3054f5b5bf4d8cdf1ef2ed1d8ef2848e01d09537028df4faea6992792ff7a86`.

### Zapier (`zapier`)

- Product category: Workflow automation
- Surface plan: Zap visual editor; Step Setup / Configure / Test panel; Paths and filters; Zap run detail; Next Gen Workflow Manager (only when specified)
- Current implementation/readiness: Desktop sales candidate; current native evidence incomplete
- Research snapshot adapter note (dated, not approval): Reference examples only; no reusable native adapter
- Rebuilt scope: Visual Zap editor, row test and acknowledgement test
- Current boundary: Current full editor/test-panel reference gap. Paths/Next Gen not implemented.
- Candidate preview: [Zapier](previews/zapier/page.html)
- Seed spec: [JSON](sources/pipeline/templates/sales-deck/native-templates/zapier.json)

**Visual anchors to reproduce**

- Zap name, draft/published state and native top controls
- App/event steps and native path geometry
- Step configuration in the actual right panel
- Next Gen components and code view belong to that distinct surface

**Sales evidence to make visible**

- A test trigger returns a useful sample
- The configured step maps real fields
- A successful run and downstream record demonstrate the outcome

**Do not substitute:** Classic Zap editor, current visual editor and Next Gen are not interchangeable. Do not label a GHL workflow Zapier or assume JSON export/import availability across plans.

**Research snapshot remaining work:** Implement separate classic visual-editor and Next Gen modes only as demanded. Native step setup/run inspector and current variant confirmation are required.

**Saved image evidence** (inspect the full image, including its qualification):

- [zapier-nextgen-8ad0653e41d0](sources/pipeline/templates/sales-deck/visual-reference/assets/zapier-nextgen-8ad0653e41d0.png): Next Gen Workflow Manager; Vendor-published UI reference; target account/version still needs confirmation. Source: [zapier-nextgen](https://help.zapier.com/hc/en-us/articles/49005047515021-Use-the-Workflow-Manager-to-build-and-view-your-Next-Gen-Zaps). SHA-256 `8ad0653e41d0f7239182ce46cc4a179ea1c9d4dcc45b18cda15c036380ad5f73`.
- [zapier-nextgen-37f210954feb](sources/pipeline/templates/sales-deck/visual-reference/assets/zapier-nextgen-37f210954feb.png): Next Gen Workflow Manager; Vendor-published UI reference; target account/version still needs confirmation. Source: [zapier-nextgen](https://help.zapier.com/hc/en-us/articles/49005047515021-Use-the-Workflow-Manager-to-build-and-view-your-Next-Gen-Zaps). SHA-256 `37f210954febf69d66975b75d12bdce161d86434928f4603b3194836ff0233cd`.
- [zapier-nextgen-1719b98f3fe4](sources/pipeline/templates/sales-deck/visual-reference/assets/zapier-nextgen-1719b98f3fe4.png): Next Gen Workflow Manager; Vendor-published UI reference; target account/version still needs confirmation. Source: [zapier-nextgen](https://help.zapier.com/hc/en-us/articles/49005047515021-Use-the-Workflow-Manager-to-build-and-view-your-Next-Gen-Zaps). SHA-256 `1719b98f3fe485ddea958e169da4fb1226bec0c652fbc6ee68e063129e1bb3ad`.
- [zapier-quickstart-4d70d16cfc8f](sources/pipeline/templates/sales-deck/visual-reference/assets/zapier-quickstart-4d70d16cfc8f.png): Zap editor overview; Vendor-published UI reference; target account/version still needs confirmation. Source: [zapier-quickstart](https://help.zapier.com/hc/en-us/articles/22234847450893-Zap-workflows-quick-start-guide). SHA-256 `4d70d16cfc8f8f60f0bc51be134f9d7d3d773744f3781d9f9942efcbb02de1dd`.

### Claude (`claude`)

- Product category: AI workspaces
- Surface plan: Claude chat; Customize > Skills; Project knowledge / instructions; Artifact or generated file; Cowork task workspace
- Current implementation/readiness: Desktop sales candidate; Skills/chat evidence bounded
- Research snapshot adapter note (dated, not approval): No Claude-app adapter; Code transcript is not a substitute
- Rebuilt scope: Claude app Skills and source-linked document/chat result
- Current boundary: Current Contents and populated chat/artifact references incomplete; no Cowork/Code substitution.
- Candidate preview: [Claude](previews/claude/page.html)
- Seed spec: [JSON](sources/pipeline/templates/sales-deck/native-templates/claude.json)

**Visual anchors to reproduce**

- Chat sidebar and composer, with Claude's actual warm/neutral surface and response typography
- Skills library, enable state and genuine skill menu
- Project instructions and knowledge files are separate from skills
- Artifact/document output uses the correct pane or file card

**Sales evidence to make visible**

- Show the relevant skill configured in its actual library
- Give Claude the client's representative input
- Show the source-grounded output and the missing-information case in chat or the actual artifact

**Do not substitute:** Claude Skills is not a CRM pipeline, a node builder, or automatically Claude Code. Do not invent a native attorney-approval button; show the review in the actual document/chat process.

**Research snapshot remaining work:** Highest-priority rebuild: add Claude-app Skills, Projects, chat and output surfaces. The current 2025 launch screenshots are historical and current help offers only a small menu crop; capture the current full workspace before implementation acceptance. Cowork is a separate surface.

**Saved image evidence** (inspect the full image, including its qualification):

- [claude-skills-9d1ac6cfdd04](sources/pipeline/templates/sales-deck/visual-reference/assets/claude-skills-9d1ac6cfdd04.png): Skill overflow menu — detail crop; Small skill overflow-menu crop only; it does not show the full Skills library or upload workspace. A current full-workspace capture is required before acceptance. Source: [claude-skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude). SHA-256 `9d1ac6cfdd046e5248eb55b7eb68978474c9c4c206c51f6cd4dfcf102d6e5e08`.
- [claude-skills-launch-55e2cd935aae](sources/pipeline/templates/sales-deck/visual-reference/assets/claude-skills-launch-55e2cd935aae.webp): Historical Skills UI; date-sensitive reference; Historical vendor UI; use only for structure, not current production layout. Historical capture. Source: [claude-skills-launch](https://www.anthropic.com/research/skills). SHA-256 `55e2cd935aae711df16d8adb14513ac3cc6e01a571172a1780a161546437cea5`.
- [claude-projects-launch-c9d6f79d1a58](sources/pipeline/templates/sales-deck/visual-reference/assets/claude-projects-launch-c9d6f79d1a58.webp): Historical project workspace; date-sensitive reference; Historical vendor UI; use only for structure, not current production layout. Historical capture. Source: [claude-projects-launch](https://www.anthropic.com/news/projects). SHA-256 `c9d6f79d1a58cad6e9eca2dbc0d8637d7a4d50d42c4a25e4e722911c042d3e84`.
- [claude-projects-launch-935d6d76e03d](sources/pipeline/templates/sales-deck/visual-reference/assets/claude-projects-launch-935d6d76e03d.webp): Historical project workspace; date-sensitive reference; Historical vendor UI; use only for structure, not current production layout. Historical capture. Source: [claude-projects-launch](https://www.anthropic.com/news/projects). SHA-256 `935d6d76e03d81d6f6ec7119eb3ea6712f657d4c0bcbbad4d461e804d1dd07fe`.
- [claude-projects-launch-ec2e9db1f89f](sources/pipeline/templates/sales-deck/visual-reference/assets/claude-projects-launch-ec2e9db1f89f.webp): Historical project workspace; date-sensitive reference; Historical vendor UI; use only for structure, not current production layout. Historical capture. Source: [claude-projects-launch](https://www.anthropic.com/news/projects). SHA-256 `ec2e9db1f89f2c935d5decd915016e695c71d93f9ca3e97a72c15698fa2d0f4d`.

**Supplemental current-rebuild references**

- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/claude-skills-current.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `87eb61c0a5a84c0876900f3f5846623aa1fef34ac2320045219e6ab81f62eb60`.
- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/claude-skill-detail-current.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `8d24675633cd57bab772b60bef89d9508a5b3710f766042209f835b51a28b9bd`.
- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/claude-project-current.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `cc8e02493e743a4419a27482fabb678fe4751bde4c843a1b3a04bbf30c034bd8`.
- [Saved capture](sources/pipeline/templates/sales-deck/native-templates/references/claude-project-wide-current.png); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `f1174c3a86da9ccd54dcd924848e1b943f6d72e25b99c7b2485febbf58c514e7`.

### Claude Code (`claude-code`)

- Product category: Coding agents & IDEs
- Surface plan: Terminal / TUI; IDE agent integration; Web or desktop coding task; Diff and test result; Skill files in project context
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Existing claude-code transcript: conceptual, not visually accepted

**Visual anchors to reproduce**

- Actual terminal or IDE framing for the requested surface
- Prompt, tool activity and changed files in native arrangement
- Review uses real diff/test output rather than CRM status cards

**Sales evidence to make visible**

- The original task and relevant skill/files are visible
- A concrete change is made
- The changed artifact and relevant check are shown

**Do not substitute:** Do not assume every Claude request means Claude Code. A conceptual transcript is not proof of a native UI or a completed backend.

**Research snapshot remaining work:** Capture target terminal/IDE version, then replace conceptual transcript formatting. No current full native screenshot in this reference pack yet.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Codex (`codex`)

- Product category: Coding agents & IDEs
- Surface plan: Desktop app conversation / project; CLI TUI; IDE extension; Files and diff review; Cloud task (when specified)
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Existing codex transcript: conceptual, not visually accepted

**Visual anchors to reproduce**

- Correct surface: desktop sidebar and panels versus terminal TUI
- Native task messages, tool activity and file/diff views
- Code outputs and tests retain their actual formatting

**Sales evidence to make visible**

- A specific task starts in its repository
- The implementation and diff are visible
- A real sample artifact or meaningful check closes the demonstration

**Do not substitute:** Desktop Codex is not merely a terminal inside a generic CRM shell. Do not represent a CLI splash screenshot as the current desktop UI.

**Research snapshot remaining work:** Current desktop capture is missing. The official repository CLI splash is a historical structural reference; it cannot certify a current app or model selector. Implement desktop and CLI separately.

**Saved image evidence** (inspect the full image, including its qualification):

- [codex-cli-repo-15b86fa9c079](sources/pipeline/templates/sales-deck/visual-reference/assets/codex-cli-repo-15b86fa9c079.png): Codex CLI repository screenshot; Historical vendor UI; use only for structure, not current production layout. Historical capture. Source: [codex-cli-repo](https://github.com/openai/codex). SHA-256 `15b86fa9c0790a779ecdd84f1e7dee029ab79bfb093bd3c4876998696925b013`.

### Hermes Agent (`hermes`)

- Product category: AI workspaces
- Surface plan: Hermes Desktop chat / skills / messaging / artifacts; Terminal CLI / TUI; Web Dashboard sessions / config / skills; Messaging gateway such as Telegram
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Reference example only; no accepted adapter

**Visual anchors to reproduce**

- Desktop is chat-first with its own sidebar and working panes
- Web Dashboard has a distinct admin navigation and session/config/skills views
- CLI and external messenger use their own native layouts

**Sales evidence to make visible**

- An agent receives the representative task
- Its relevant skill/context and tool activity are visible
- The requested artifact or action result is shown in the proper destination

**Do not substitute:** Do not collapse Desktop, CLI, Dashboard and Telegram into one invented Hermes dashboard. The delivery surface must be named.

**Research snapshot remaining work:** Choose the surface from the post. Desktop video and dashboard screenshots provide separate baselines; implement them separately and capture target-version states before acceptance.

**Saved image evidence** (inspect the full image, including its qualification):

- [hermes-dashboard-41c7c136d9db](sources/pipeline/templates/sales-deck/visual-reference/assets/hermes-dashboard-41c7c136d9db.png): Web dashboard; Vendor-published UI reference; target account/version still needs confirmation. Source: [hermes-dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard). SHA-256 `41c7c136d9dba87f975dace7f2be9d082d7195a48c3086b5c26a879aa9f9d43e`.
- [hermes-dashboard-5b997c10c5fc](sources/pipeline/templates/sales-deck/visual-reference/assets/hermes-dashboard-5b997c10c5fc.png): Web dashboard; Vendor-published UI reference; target account/version still needs confirmation. Source: [hermes-dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard). SHA-256 `5b997c10c5fc811f62f92c91f2c4f4e75d71a3d7f4618ad32b59dc2fad86ee9a`.
- [hermes-desktop-frame-15](sources/pipeline/templates/sales-deck/visual-reference/assets/hermes-desktop-frame-15.png): Desktop chat and sidebar, video at 15 seconds; Official product video frame; desktop surface only, not the web dashboard. Target version/theme still needs confirmation. Source: [hermes-desktop-product](https://hermes-agent.nousresearch.com/desktop). SHA-256 `34280f8fc0c2ca4a1c745d08cb274df4b383431bbaba834b9d95134e69c08ab9`.

### Grok (`grok`)

- Product category: AI workspaces
- Surface plan: Grok web chat; Workspace selector; Files / connected tools; Shared conversation; Build mode (only if requested)
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Reference example only; no accepted adapter

**Visual anchors to reproduce**

- Actual chat navigation and composer
- Workspace/profile menu distinct from conversation body
- Source/file cards and responses match the selected feature

**Sales evidence to make visible**

- The representative prompt and attached context are shown
- The response uses the relevant evidence or tool
- The output answers the business requirement

**Do not substitute:** Grok chat is not Grok Bot, the API console, or a GHL workflow. Workspace-selector screenshots alone do not establish full chat layout.

**Research snapshot remaining work:** Capture a complete current chat. Existing references cover workspace/sharing details only; implement chat/build modes separately as needed.

**Saved image evidence** (inspect the full image, including its qualification):

- [grok-chat-d49110e3b69c](sources/pipeline/templates/sales-deck/visual-reference/assets/grok-chat-d49110e3b69c.webp): Chat and workspaces; Vendor-published UI reference; target account/version still needs confirmation. Source: [grok-chat](https://docs.x.ai/grok/user-guide). SHA-256 `d49110e3b69c1104d135ad57d60fbe2f810edc2c11990965cb36c9ab5b5fba7c`.

### Grok Bot (`grok-bot`)

- Product category: AI workspaces
- Surface plan: Bot list and creation; Bot conversation; Computer / apps; Skills and routines; Files and task results
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No adapter; native capture required

**Visual anchors to reproduce**

- A named Bot and task conversation, not a workflow graph
- Persistent computer/app context belongs to the Bot workspace
- Skills/routines and approval states use the real product controls

**Sales evidence to make visible**

- Assign a concrete job to the named Bot
- Show relevant work in the actual connected application
- Return the finished result and any real review checkpoint

**Do not substitute:** Do not infer Grok Bot's layout from ordinary Grok, Cursor IDE, or Lorenzo's internal operator instructions. They are different references.

**Research snapshot remaining work:** Official docs establish the separate product and task model, but the public product page returned 403 and full native screenshots are absent. A genuine app capture is required before its renderer can be built or approved.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Cursor (`cursor`)

- Product category: Coding agents & IDEs
- Surface plan: IDE editor and Agent pane; File explorer; Diff / review; Terminal and checks; Projects or cloud agents (when specified)
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Editor tabs and activity/file navigation
- Agent composer and tool events in the actual sidepane
- Changed files and diff remain native editor surfaces

**Sales evidence to make visible**

- A concrete issue and relevant files are visible
- The Agent edits the implementation
- The diff plus working result or test demonstrate completion

**Do not substitute:** Do not substitute Codex Desktop, Orca or a generic terminal. The official queued-message video is a pane detail, not a full current IDE capture.

**Research snapshot remaining work:** Implement the editor/agent split and native diff. Capture current full IDE and any requested cloud/project surface; do not use marketing wallpapers as references.

**Saved image evidence** (inspect the full image, including its qualification):

- [cursor-agent-video](sources/pipeline/templates/sales-deck/visual-reference/assets/cursor-agent-video.png): Agent sidepane detail, video at 3 seconds; Official documentation video detail; shows an older model label and is not proof of the current full IDE. Historical capture. Source: [cursor-agent](https://cursor.com/docs/agent/overview). SHA-256 `615d93970b245e2d4323d13bb6a03b77bd7b6fe9dcf465f1bf7405307179e836`.

### Orca IDE (`orca`)

- Product category: Coding agents & IDEs
- Surface plan: Workspace / worktree list; Parallel agent terminals; Editor / browser split; Diff annotation and review; Rich repo preview
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No adapter; product identified by user clarification

**Visual anchors to reproduce**

- Worktree/project navigation and isolated terminal panes
- Native split boundaries and tabs
- Diff annotation and file/browser previews shown in actual Orca arrangement

**Sales evidence to make visible**

- A task is isolated in the correct worktree
- The chosen agent performs the relevant work
- Its diff and running result are reviewed

**Do not substitute:** Lorenzo clarified Orca as an IDE like Antigravity. Do not use Orca Security, orcapods.ai, or another similarly named product.

**Research snapshot remaining work:** Use onorca.dev as the identified product. Product posters show real features but some are cropped; capture the complete target workspace before implementation acceptance.

**Saved image evidence** (inspect the full image, including its qualification):

- [orca-ide-f5d2c9fee6ee](sources/pipeline/templates/sales-deck/visual-reference/assets/orca-ide-f5d2c9fee6ee.jpg): Agent IDE worktrees, terminals and review; Vendor-published UI reference; target account/version still needs confirmation. Source: [orca-ide](https://www.onorca.dev/). SHA-256 `f5d2c9fee6ee0b82fc893ed1a8eb54ff5bc32cd983d7083a3e6e7083ccec8a7e`.
- [orca-ide-7f03154e7dfe](sources/pipeline/templates/sales-deck/visual-reference/assets/orca-ide-7f03154e7dfe.jpg): Agent IDE worktrees, terminals and review; Vendor-published UI reference; target account/version still needs confirmation. Source: [orca-ide](https://www.onorca.dev/). SHA-256 `7f03154e7dfe456b1fdf4029449bf09f12171fcf1c637818f0071e8e0369e06d`.
- [orca-ide-7e333e573b0c](sources/pipeline/templates/sales-deck/visual-reference/assets/orca-ide-7e333e573b0c.jpg): Agent IDE worktrees, terminals and review; Vendor-published UI reference; target account/version still needs confirmation. Source: [orca-ide](https://www.onorca.dev/). SHA-256 `7e333e573b0c6a2f5e416d359f8b8060f6fe4cb617ccec30824d21329fd065a0`.
- [orca-ide-9d33395b9d56](sources/pipeline/templates/sales-deck/visual-reference/assets/orca-ide-9d33395b9d56.jpg): Agent IDE worktrees, terminals and review; Vendor-published UI reference; target account/version still needs confirmation. Source: [orca-ide](https://www.onorca.dev/). SHA-256 `9d33395b9d561531ddd731a1c759489eeb91e1cfecb76b68ba69308db9817e25`.

### Google Antigravity (`antigravity`)

- Product category: Coding agents & IDEs
- Surface plan: IDE editor / Agent pane; Agent Manager; App task conversation; CLI (when specified)
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Editor and Agent Manager are distinct views
- Workspace switcher, editor navigation and native agent composer
- Review and browser/test artifacts use the requested surface

**Sales evidence to make visible**

- A concrete task starts in the correct project
- Agent work and artifact evidence are shown
- A working preview or check establishes the result

**Do not substitute:** Do not substitute Orca or Cursor because all are coding tools. The documentation screenshots do not establish the account's current model/version.

**Research snapshot remaining work:** Confirm IDE versus app/CLI and actual version. Reference screenshots establish editor/manager structure only; implement the selected surface with current target evidence.

**Saved image evidence** (inspect the full image, including its qualification):

- [antigravity-ide-current-ac2c2d67a029](sources/pipeline/templates/sales-deck/visual-reference/assets/antigravity-ide-current-ac2c2d67a029.png): Editor and Agent Manager; Vendor-published UI reference; target account/version still needs confirmation. Source: [antigravity-ide-current](https://www.antigravity.google/docs/getting-started?tab=ide). SHA-256 `ac2c2d67a02971734adc05cda0022344308e2bae0bfc9ecf9aa91ca3c550a45d`.
- [antigravity-ide-current-ae664ecd19b7](sources/pipeline/templates/sales-deck/visual-reference/assets/antigravity-ide-current-ae664ecd19b7.png): Editor and Agent Manager; Vendor-published UI reference; target account/version still needs confirmation. Source: [antigravity-ide-current](https://www.antigravity.google/docs/getting-started?tab=ide). SHA-256 `ae664ecd19b7fa48f24b71f70ea2d12f5903c5bafb7f0991582562bf16ed737e`.

### HubSpot (`hubspot`)

- Product category: CRM & automation
- Surface plan: CRM contact / deal record; Deal pipeline; Workflow editor; Activity timeline
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Reference only; no accepted adapter

**Visual anchors to reproduce**

- HubSpot navigation, record properties and activity timeline
- Actual enrollment/action panels and workflow controls
- Native deal cards and pipeline stages

**Sales evidence to make visible**

- A contact is enrolled under the intended rule
- The correct property/activity changes
- The expected deal or follow-up appears

**Do not substitute:** Do not recolor the GHL contact page and call it HubSpot.

**Research snapshot remaining work:** Build a real HubSpot adapter; collected sources include record and workflow-panel details, not full coverage of pipeline and all record states.

**Saved image evidence** (inspect the full image, including its qualification):

- [hubspot-workflows-3b0696514fae](sources/pipeline/templates/sales-deck/visual-reference/assets/hubspot-workflows-3b0696514fae.png): Workflow editor; Vendor-published UI reference; target account/version still needs confirmation. Source: [hubspot-workflows](https://knowledge.hubspot.com/workflows/create-workflows). SHA-256 `3b0696514faec96c00854b1f336790f58949c34a2e753bd74cd00080a13a7c63`.
- [hubspot-workflows-144c8ec3c6c3](sources/pipeline/templates/sales-deck/visual-reference/assets/hubspot-workflows-144c8ec3c6c3.png): Workflow editor; Vendor-published UI reference; target account/version still needs confirmation. Source: [hubspot-workflows](https://knowledge.hubspot.com/workflows/create-workflows). SHA-256 `144c8ec3c6c31cfdc9496d9447aaa1861ecbab28221c3097d714a36b70d1baa1`.
- [hubspot-workflows-e19767b546de](sources/pipeline/templates/sales-deck/visual-reference/assets/hubspot-workflows-e19767b546de.png): Workflow editor; Vendor-published UI reference; target account/version still needs confirmation. Source: [hubspot-workflows](https://knowledge.hubspot.com/workflows/create-workflows). SHA-256 `e19767b546de585bd1b1274ffa163e9288a2bf854d3c5294c8cf3ccb95f7d87b`.

### ChatGPT (`chatgpt`)

- Product category: AI workspaces
- Surface plan: Chat; Project; GPT configuration; Artifact/file output; Codex / Work only if named
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Actual sidebar, composer and response controls
- Project instructions/files distinct from GPT configuration
- Output cards use actual ChatGPT behavior

**Sales evidence to make visible**

- Provide a representative input and context
- Show the useful output and one validation
- Make the business result visible

**Do not substitute:** Do not substitute Codex or a generic CRM. A Project is not a custom GPT.

**Research snapshot remaining work:** Current references cover project navigation details. Capture full chat and the specific requested Project/GPT surface before creating an adapter.

**Saved image evidence** (inspect the full image, including its qualification):

- [chatgpt-projects-95f0b11b22fb](sources/pipeline/templates/sales-deck/visual-reference/assets/chatgpt-projects-95f0b11b22fb.webp): Projects; Vendor-published UI reference; target account/version still needs confirmation. Source: [chatgpt-projects](https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt). SHA-256 `95f0b11b22fbfa929d5693bc1321b13c887fa1f75397aadb790653e79ce4667e`.
- [chatgpt-projects-c8c898bc45ca](sources/pipeline/templates/sales-deck/visual-reference/assets/chatgpt-projects-c8c898bc45ca.webp): Projects; Vendor-published UI reference; target account/version still needs confirmation. Source: [chatgpt-projects](https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt). SHA-256 `c8c898bc45cabe4b800d62caa902282d750ff8dd1031c341a40b1863be114646`.

### OpenAI API (`openai-api`)

- Product category: AI workspaces
- Surface plan: API request/response; Developer logs or evaluation results; Agent's actual application UI
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No general native adapter

**Visual anchors to reproduce**

- Real API/tool names and request fields
- Structured response and meaningful validation
- Destination application shown when the deliverable is customer-facing

**Sales evidence to make visible**

- A sample input reaches the intended API
- A grounded response passes a useful check
- The client's app displays the result

**Do not substitute:** The API does not imply ChatGPT or Codex UI. Do not invent a native OpenAI workflow canvas.

**Research snapshot remaining work:** Resolve whether the job needs API implementation, an agent framework, a developer console or a custom product. Create a visual reference for that exact surface.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Google Sheets (`google-sheets`)

- Product category: Data & operations
- Surface plan: Spreadsheet grid; Formula bar; Filter / sort; Integration output / audit rows
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Sheet tabs, column/row headers and formula bar
- Readable typed cells and native selection
- Realistic dates, currency and formulas

**Sales evidence to make visible**

- The original row is visible
- A validated field or row changes
- The formula/report reflects the same sample data

**Do not substitute:** Do not render a generic web table as the Google Sheets app.

**Research snapshot remaining work:** Capture native sheet chrome and representative formula/edit states. A custom summary table can be used only as explicitly custom output.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Zoho CRM (`zoho`)

- Product category: CRM & automation
- Surface plan: Lead / contact record; Deal pipeline; Workflow rule configuration; Activity
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Zoho module navigation and record header
- Native criteria and instant/scheduled action sections
- Actual pipeline and activity layouts

**Sales evidence to make visible**

- A lead meets the specified criteria
- The intended action updates the record
- The result is visible to the responsible user

**Do not substitute:** Zoho CRM, Creator and Flow are different products. Never choose by brand name alone.

**Research snapshot remaining work:** Confirm CRM/Flow/Creator and edition, collect full screenshots and implement product-specific screens. Current rule documentation has insufficient full UI imagery.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Instantly (`instantly`)

- Product category: Outreach
- Surface plan: Campaign sequence editor; Leads / campaign status; Unibox conversation; Campaign analytics
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Native campaign tabs and step/delay sequence
- Lead status and sending-account context
- Unibox inbox and thread
- Actual analytics metric names

**Sales evidence to make visible**

- A sample lead enters the intended sequence
- A reply appears in Unibox
- Follow-up stops or changes under the intended condition

**Do not substitute:** Do not use generic email bubbles, a CRM conversation screen, or a lead-finder screenshot as evidence of the sequence editor.

**Research snapshot remaining work:** Obtain current sequence, Unibox and lead screenshots. Some public help routes are unavailable and collected homepage art is excluded from UI evidence.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Airtable (`airtable`)

- Product category: Data & operations
- Surface plan: Base grid; Automation trigger/actions; Run history; Interface Designer
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Base/table/view navigation and typed fields
- Actual automation test/run history panels
- Interfaces are separate from the base grid

**Sales evidence to make visible**

- A record is created or corrected
- A rule runs against that record
- The status and related output appear

**Do not substitute:** A generic table or form is not the Airtable grid or Interface Designer.

**Research snapshot remaining work:** Collected automation/history references need a matching grid and Interface Designer capture when those are required by a post.

**Saved image evidence** (inspect the full image, including its qualification):

- [airtable-automation-36c222f5600d](sources/pipeline/templates/sales-deck/visual-reference/assets/airtable-automation-36c222f5600d.png): Automations; Vendor-published UI reference; target account/version still needs confirmation. Source: [airtable-automation](https://support.airtable.com/docs/getting-started-with-airtable-automations). SHA-256 `36c222f5600db40420a278025b8c704b722b8ddcb009ec442ec14cfe1a4424f4`.

### Notion (`notion`)

- Product category: Data & operations
- Surface plan: Page with blocks; Database table / board; Properties and filters; Database automation
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Reference only; no accepted adapter

**Visual anchors to reproduce**

- Workspace navigation and breadcrumb
- Actual block/page hierarchy
- Database views, properties and row/page opening behavior

**Sales evidence to make visible**

- A record/page enters the proper database
- Relevant fields or content are updated
- The requested view/report reflects the update

**Do not substitute:** Do not present a Kanban-style CRM with Notion written above it.

**Research snapshot remaining work:** Use actual database-view screenshots; cover full workspace navigation and edit states before implementing the adapter.

**Saved image evidence** (inspect the full image, including its qualification):

- [notion-database-3550bd3cd5dc](sources/pipeline/templates/sales-deck/visual-reference/assets/notion-database-3550bd3cd5dc.webp): Database views; Vendor-published UI reference; target account/version still needs confirmation. Source: [notion-database](https://www.notion.com/help/views-filters-and-sorts). SHA-256 `3550bd3cd5dc086eb2f7bc06172644bd3ce7829ddf3e617cf4a58a17cf87c5fe`.
- [notion-database-b419b8206516](sources/pipeline/templates/sales-deck/visual-reference/assets/notion-database-b419b8206516.webp): Database views; Vendor-published UI reference; target account/version still needs confirmation. Source: [notion-database](https://www.notion.com/help/views-filters-and-sorts). SHA-256 `b419b820651631e13aae15f6218e7071708c71dd59ee3ec5a7443b3e20178dd5`.

### Clay (`clay`)

- Product category: Outreach
- Surface plan: Table and enrichment columns; Enrichment configuration; Row/cell details; Run results
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Reference only; no accepted adapter

**Visual anchors to reproduce**

- Native table navigation and typed/enrichment columns
- Configuration panel and row-level execution state
- Sources and validated output in the relevant cell

**Sales evidence to make visible**

- A sample company/contact is researched
- The enrichment returns supported values
- Qualified output is handed to the intended destination

**Do not substitute:** Decorative enrichment icons are not evidence of Clay's table UI.

**Research snapshot remaining work:** Acquire actual table/configuration references; homepage artwork is excluded. Verify provider/operation names and row-result states.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Pipedrive (`pipedrive`)

- Product category: CRM & automation
- Surface plan: Deal pipeline; Deal/contact detail; Automation editor; Activity scheduling
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Reference only; no accepted adapter

**Visual anchors to reproduce**

- Native pipeline cards and stage totals
- Record activities and detail layout
- Actual automation builder and trigger/action labels

**Sales evidence to make visible**

- A deal enters the right stage
- The intended activity is created
- The same deal moves with consistent values

**Do not substitute:** Do not substitute GHL or HubSpot pipeline styling.

**Research snapshot remaining work:** Resolve the current official pipeline documentation route, capture pipeline/detail/editor and implement the matching views.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Vapi (`vapi`)

- Product category: Voice agents
- Surface plan: Assistant configuration; Test call; Call logs / transcript; Tool invocation detail
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): Voice-agent example is not a Vapi adapter

**Visual anchors to reproduce**

- Assistant list and native configuration sections
- Prompt, voice/model and tool controls
- Call/transcript and extracted fields in their actual views

**Sales evidence to make visible**

- The assistant receives a representative call
- It handles one important edge case
- Transcript/tool result and the destination record agree

**Do not substitute:** Do not show a made-up phone waveform and imply a verified live call.

**Research snapshot remaining work:** Collect complete assistant and call-log views beyond the current detail crops; implement native transcript and call outcome states.

**Saved image evidence** (inspect the full image, including its qualification):

- [vapi-dashboard-76e8c8f6cb9a](sources/pipeline/templates/sales-deck/visual-reference/assets/vapi-dashboard-76e8c8f6cb9a.webp): Voice assistant dashboard; Vendor-published UI reference; target account/version still needs confirmation. Source: [vapi-dashboard](https://docs.vapi.ai/quickstart/dashboard). SHA-256 `76e8c8f6cb9ab84294f9c55024d40069f36b5e6ea5bf1912705726468f71d191`.
- [vapi-dashboard-8a1c1af7f0bb](sources/pipeline/templates/sales-deck/visual-reference/assets/vapi-dashboard-8a1c1af7f0bb.webp): Voice assistant dashboard; Vendor-published UI reference; target account/version still needs confirmation. Source: [vapi-dashboard](https://docs.vapi.ai/quickstart/dashboard). SHA-256 `8a1c1af7f0bb83c2db15d4f5119afe51e7cabda78943e858c9e50096bcb38a53`.

### Retell AI (`retell`)

- Product category: Voice agents
- Surface plan: Agent configuration; Conversation flow if selected; Test call; Call history / transcript
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Actual agent mode and configuration sections
- Real conversation-flow node types when applicable
- Call detail and transcript layout

**Sales evidence to make visible**

- A realistic sample call follows the intended path
- An exception is handled
- The extracted result reaches the destination

**Do not substitute:** Retell prompt agents and flow agents are not interchangeable; do not use a Vapi skin.

**Research snapshot remaining work:** Resolve current create-agent documentation and capture target agent type, tests and call detail. No accepted imagery yet.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Twilio (`twilio`)

- Product category: Voice agents
- Surface plan: Studio flow canvas; Widget configuration; Execution logs; Messaging/call logs
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Native Studio widgets, transition ports and right configuration panel
- Trigger and widget-specific transitions
- Actual log tables and execution detail

**Sales evidence to make visible**

- The incoming event reaches the intended widget
- Correct transitions execute
- The message/call result and logs are consistent

**Do not substitute:** Twilio Studio is not n8n. Do not claim a message was sent from a purely visual sample.

**Research snapshot remaining work:** Implement Studio and log surfaces independently; references cover trigger/widget configuration details, not all log views.

**Saved image evidence** (inspect the full image, including its qualification):

- [twilio-studio-4d3d9c3ac7ae](sources/pipeline/templates/sales-deck/visual-reference/assets/twilio-studio-4d3d9c3ac7ae.webp): Studio canvas; Vendor-published UI reference; target account/version still needs confirmation. Source: [twilio-studio](https://www.twilio.com/docs/studio/user-guide). SHA-256 `4d3d9c3ac7ae91768b09bcd79106e9aa132c462d140e2da6506b4d96d746a0d1`.
- [twilio-studio-12e77564b260](sources/pipeline/templates/sales-deck/visual-reference/assets/twilio-studio-12e77564b260.webp): Studio canvas; Vendor-published UI reference; target account/version still needs confirmation. Source: [twilio-studio](https://www.twilio.com/docs/studio/user-guide). SHA-256 `12e77564b260d40b98dd1158b36bef551fe9ab687141b0efb55237d06ff43821`.

### Supabase (`supabase`)

- Product category: Data & operations
- Surface plan: Table Editor; SQL Editor; Auth users; Edge Function / logs
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Project navigation and table/schema selection
- Actual grid or query/result split
- Relevant auth/function/log detail

**Sales evidence to make visible**

- A sample input is stored correctly
- Validation/query behavior is visible
- The consuming application shows the intended result

**Do not substitute:** An ERD illustration is not the Table Editor, and a generic table is not Supabase.

**Research snapshot remaining work:** Acquire native dashboard screenshots; conceptual database illustrations have been excluded from UI evidence.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Apify (`apify`)

- Product category: Data & operations
- Surface plan: Actor input; Run progress/log; Dataset output; Schedule or integration
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Actor/run navigation and native input form
- Actual run status/log
- Dataset table/export controls

**Sales evidence to make visible**

- A specific input starts the relevant actor
- The run result is inspected
- Structured records reach the requested destination

**Do not substitute:** Do not substitute a custom scraping dashboard or invent actor IDs.

**Research snapshot remaining work:** Collect the actual Actor/Run/Dataset interface; console docs alone currently provide insufficient visual coverage.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

### Shopify (`shopify`)

- Product category: Commerce
- Surface plan: Admin product/order; Flow editor; Run history; Storefront (when relevant)
- Current implementation/readiness: Research/reference plan only; no accepted native renderer.
- Research snapshot adapter note (dated, not approval): No accepted adapter

**Visual anchors to reproduce**

- Admin navigation and real order/product detail
- Flow trigger/condition/action arrangement
- Run history and storefront are distinct views

**Sales evidence to make visible**

- A sample order meets the condition
- The correct Flow action occurs
- Order/customer/storefront output matches

**Do not substitute:** A custom storefront is not Shopify Admin. Shopify Flow must use its own builder.

**Research snapshot remaining work:** Capture admin plus Flow/editor/run states for the specific task; add only the surfaces the post actually needs.

**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.

## If a platform is not in this guide

Identify the exact product/surface first. Collect current full-workspace and relevant detail images from primary sources or an authorized actual workspace. Record provenance/date/hash/theme/version and the needed state map. Implement a bounded adapter separately, preserve the outer identity, compare pixels and semantics, test behavior and obtain whole-walkthrough review. Do not improvise a generic native UI while the recording queue waits.

This guide preserves the known UI knowledge. It does not claim every product/version has already been implemented or that captured software can never change.
