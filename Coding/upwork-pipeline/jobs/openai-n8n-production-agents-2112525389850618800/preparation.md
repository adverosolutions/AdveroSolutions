# Private preparation: OpenAI + n8n production agents

Prepared 20 October 2026. Research/content only. Initial research status was requires_adapter; bounded AI adapter candidate is now implemented and awaits whole-walkthrough review. Subsequent main authorization added the assigned deck-spec.json and bounded native adapter maintenance; no live system or queue writes were performed by this worker. This is a proposed illustrative sales sample, not evidence of a production deployment or past delivery.

## Job facts and boundaries

Source: https://www.upwork.com/jobs/~022112525389850618800
The client asks for reliable/scalable OpenAI + n8n agents, multiple connected tools, performance optimization and production experience. No business workflow, destination application, account version, workload or SLA is supplied. Use “Prepared for your team”; do not invent a company or client name. The proposal keyword is Aether. Actual hours/week, start date and qualifying production examples must come from Lorenzo; do not manufacture them. Preserve the locked proposal process and resolve its keyword placement with main.

## Two-minute story

Opening caption, verbatim: I've already put this workflow together for you. Let me walk you through how it works.

Opening outcome: “Handle an operations request and leave a traceable result.” One outer label: “Illustrative sample”. The example is deliberately an operations task, not an asserted client industry.

Sample contract: request REQ-1042; requester Alex Morgan, alex.morgan@example.com; assigned person Maya Chen; original text “Please check order ORD-1042 and create a follow-up for Maya if delivery is still pending.” Read-only order tool returns ORD-1042, delivery pending, expected 22 October 2026. Write tool returns task TASK-1042, assigned Maya Chen, due 22 October, status open. No email is sent. These IDs and dates must be shared across every scene.

| Time | Stop/purpose | New fact and visible evidence | Spoken cue |
| --- | --- | --- | --- |
| 0–10s | Opening | Specific request → traceable task | “I used one request to show the agent checking a source before it takes an action.” |
| 10–35s | n8n workflow Editor | Webhook → Edit Fields → AI Agent. OpenAI Chat Model attaches to Chat Model port; HTTP Request Tool “Get order” and HTTP Request Tool “Create follow-up” attach to Tool port. Read and write capabilities are separately named. | “This tool checks ORD-1042. This one can create the task. The model connection is here.” |
| 35–75s | Native execution/node inspection | Actual-shaped tool output table for Get order, then Create follow-up: same order, task ID, owner, due date and open status. Readable final agent response: “ORD-1042 is pending. Created TASK-1042 for Maya Chen, due 22 October.” Required proof is in the route, not hidden in Detailed. | “The order lookup is the source for the pending status. The task tool returns the record ID and Maya as owner.” |
| 75–100s | Same native run surface, failure state | A controlled alternative for REQ-1042: read tool returns timeout; execution visibly errors and the write tool is not executed. No TASK-1042 success or final success response in this alternative. “Failure sample” is a state, not a second unrelated person. | “If the lookup fails, this path stops before creating the task. I would test that alongside the successful case.” |
| 100–120s | Goal/close | Three definitions below, baseline note and blue reply CTA | “Reply and we can use a 15-minute call to choose your first workflow and agree the failure cases.” |

The timeout state is a proposed requirement: implement real supported error semantics and native failure styling before depicting it. Do not claim a green execution proves a timeout, retry, idempotency, load testing or production scale. Do not draw an Error Trigger on the happy path or imply native Retry On Fail eliminates duplicate writes. A separate deterministic idempotency guard and an error workflow are later implementation scope; neither is proven by the minimal sample.

## Directional goals

- Increase validated completions: requests with a confirmed expected tool result / eligible requests attempted. A model saying “done” does not qualify.
- Reduce manual touches: count of operator interventions per completed request, including exception recovery.
- Reduce recovery time: elapsed time from failed execution detection to a correct terminal result, with unresolved failures retained in the denominator/report.

Baseline note: “We’ll agree the baseline, workload and acceptance cases using your workflow.” No invented uplift, current rate, cost saving or response-time guarantee.

## Native research and fidelity

Checked 20 October 2026. Existing library inspected before new research:
- templates/sales-deck/visual-reference/assets/n8n-current-editor-d82393bef07f.png, source https://raw.githubusercontent.com/n8n-io/n8n-docs/main/docs/build/.gitbook/assets/canvas-groups-overview.png. Visually inspected: light dotted canvas, real node/port geometry, grouped canvas and labels. Does not show the AI cluster or full application chrome.
- templates/sales-deck/visual-reference/assets/n8n-current-editor-f118523d2bb0.png, source https://raw.githubusercontent.com/n8n-io/n8n-docs/main/docs/build/.gitbook/assets/dirty-node-editor.png. Visually inspected: Parameters/Settings/Docs, Test step, table output and stale-output warning. It is an Edit Fields detail crop, not AI Agent configuration.

Current official technical sources:
- https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/ — chat model plus tool subnodes; at least one tool required; legacy agent-type selector is deprecated. Do not copy an old “Tools Agent” dropdown as a current control.
- https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.lmchatopenai/ — Model is account-loaded; Use Responses API and model options exist. Use a neutral available-model field until target version/account is known; do not invent a selected model. Bound requests to one item because subnode expressions resolve to the first item.
- https://docs.n8n.io/workflows/executions/ — native execution review source; match actual list/detail layout and success/error states before implementation approval.
- https://blog.n8n.io/how-to-build-ai-agent/ — official article includes AI cluster and node configuration imagery. Candidate canvas asset: https://storage.ghost.io/c/0d/78/0d78b34c-0c5f-4975-900e-61d00ccb1c2d/content/images/2025/04/Screenshot-2025-04-13-110742.png ; configuration candidate: https://storage.ghost.io/c/0d/78/0d78b34c-0c5f-4975-900e-61d00ccb1c2d/content/images/2025/04/Screenshot-2025-04-14-073414.png . Both explicitly date from April 2025, so historical geometry reference only. URLs retrieved; pixels not independently accepted in this preparation.
- https://n8n.io/ai-agents/ — current product distinguishes workflow AI Agent node from standalone Agent Builder. This sample chooses workflow Editor, not the new standalone-agent surface. Do not blend the two.
- The catalog’s https://docs.n8n.io/advanced-ai/intro-tutorial/ now redirects to https://learn.n8n.io/ . It no longer supplies the intended AI-cluster screenshot.

Required matching: target n8n workflow Editor version/theme; sidebar/header/Editor versus Executions navigation; rectangular AI Agent root with bottom typed Chat Model/Memory/Tool ports, appropriate subnode geometry and attachment wires; straight main-flow edges separate from AI edges; vendor icons; current node parameter labels; native INPUT/OUTPUT and Table/JSON tabs; execution selection and error details. No blue generic CRM interior, invented agent approval card or OpenAI dashboard. Retain approved outer shell.

## Minimal compiler/adapter contract for main

Current supported n8n keys webhook/edit_fields/http_request cannot express this job. Extend through explicit template maintenance, not per-job skinning:
1. Root ai_agent, subnodes openai_chat_model and http_request_tool; typed connection kinds main/ai_languageModel/ai_tool (plus ai_memory only if actually used). Reject tools wired as main-flow nodes and agent roots without model/tool.
2. A native AI node inspector and execution result state carrying input, tool call, tool result and agent final output. Tool-call data must reference the same entity IDs. The top-level agent final output alone is insufficient proof.
3. Success/error branch states with a truthful “not executed” downstream result; deterministic replay reset and Show result for both. Do not fabricate successful write output during the error alternative.
4. One coherent sample entity object and three directional goal definitions. Required result scenes on all routes; controls and native parameters can be optional details inside a scene.
5. Template needs current full-workspace AI cluster + detail screenshot evidence, same-viewport comparison and independent acceptance. This preparation self-review is not that gate.

Recommendation: keep this entry unapproved until the AI-cluster candidate and exact job page pass the native/sales gate. Do not compile a webhook/HTTP-only “agent” or claim production performance. Self-review checked post fit, continuity, visible output, distinct scenes, directional metrics and source limitations; no independent review performed.

## Implementation addendum (20 October 2026)

The executable spec uses two native stops: actual n8n workflow Editor with Webhook → AI Agent and typed OpenAI/tool subnodes, then the node output with order status, task ID, owner and due date. It does not use the earlier custom architecture concept. The failure alternative remains private rollout acceptance scope; no fake failure execution or retry claim is rendered.

Implemented action keys: ai_agent, openai_chat_model, http_request_tool. AI subnodes are separate content.aiNodes with content.aiConnections typed ai_languageModel/ai_tool. They do not enter the main-flow graph or runOrder. Inspectors cover main nodes and attached subnodes. Main owns catalog/build/runtime integration, lock, generated pages and exact-generation review.

Reference images now downloaded and visually inspected in reference-evidence/ with source URLs and SHA256 in sources.json: ai-cluster-2025.png and ai-agent-settings-2025.png. The inspected cluster establishes rectangular agent root, lower diamond Chat Model/Memory/Tool ports, circular tool/model subnodes, dashed typed connections and separate main-flow edge. It is dark theme April 2025; our light theme follows the existing inspected vendor light references. No claim of target-account pixel parity or 2026 full-workspace screenshot is made. The vendor root subtitle “Tools Agent” is dated and intentionally not copied as a current configuration selector. Native OpenAI icon is embedded from n8n’s official repository: https://raw.githubusercontent.com/n8n-io/n8n/master/packages/%40n8n/nodes-langchain/nodes/llms/LMChatOpenAi/openAiLight.svg . Model gpt-4.1-mini is an illustrative configuration, not a claim of account availability.

Self-check evidence: both assigned specs pass current integrated schema/catalog; negative checks reject wrong model port, tool attachment to a non-agent, and missing model. JavaScript syntax checks pass; Python compile() passes without bytecode writes. Isolated DOM harness contains typed-port, visible-task-output and subnode/main-port checks. Headless Chrome launch in worker sandbox failed SIGABRT/EPERM; main was sent /private/tmp/agent-native-harness.html and /private/tmp/agent-native-qa.cjs to run with its approved browser environment. No browser-result or screenshot pass is claimed here. This is self-review, not independent review.

## Final focused proof correction (20 October 2026)

The result scene now selects Create follow-up, so its native OUTPUT shows the actual-shaped tool response: TASK-1042, Maya Chen, 22 October and open. INPUT shows ORD-1042, the prior pending delivery status, owner and due date. The agent’s flattened summary is not the default visible proof. Replay opens the initial main-path node first, then settles on content.selectedNode (the tool) at the final step. No third duplicate inspector scene was added.

Shared runtime changes authorized by main in this focused pass: final node-state selection respects selectedNode; current AI Agent glyph uses overlapping rounded person outlines following the official July/August 2026 images; header now shows Saved + Publish (unpublished sample), with no false active/Published claim.

Self-checks passed: spec validates; wrong typed port, missing model and unknown selected node are rejected; node --check passes. A jsdom harness executed the actual runtime and verified final Create follow-up selection, pending status in INPUT, TASK-1042/open in OUTPUT, draft Publish header, typed model/tool connections and absence of main-flow subnode ports. It also checked the existing Gmail draft edit/replay/disabled-send states. This DOM test is not a screenshot comparison; main retains browser and independent review.
