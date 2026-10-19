# Upwork operating policy — 19 October 2026

Lorenzo's later instructions supersede the earlier Astra-heavy batch setup. This
is repository-local guidance, not a change to global app/model settings.

| Work | Default |
| --- | --- |
| Coordination, research, planning, proposals, queue and Loom finalization | GPT-6.1 Sol · Medium · Standard |
| Daily content from an accepted visual template | GPT-6.1 Sol · Medium; Fast when production is explicitly time constrained |
| A difficult implementation defect | Sol · High for that bounded repair |
| Final independent sales, behavior and visual review | One Astra · High review with exact sources and screenshots |

The app's speed selection and an agent's model/effort are separate. Use the
controls actually exposed. If a dispatch tool cannot set or confirm speed, say
so; never claim Standard was enforced by a tool that has no speed field.

One coordinator owns intake, proposals, queue and Git. Do not multiply Astra
coordinator chats by default. Use task-specific workers with `fork_turns: none`
only when delegation is requested; their briefs contain the assigned job,
specific relevant references, and acceptance criteria. Do not copy the entire
conversation, unrelated jobs, or a whole research library into every worker.

Separate native-template research and implementation from job production. A
content run fills an accepted template. It does not create an unfamiliar
software interface while a recording queue waits. Missing product identity,
reference evidence, adapter coverage or native behavior blocks that screen.

Run mechanical checks before Astra review. Follow `SALES_ACCEPTANCE.md`; visual-only review never clears a recording. The reviewer inspects the original
requirements, the exact generated page, the relevant vendor screenshots and
the changed behavior. Carry unchanged verified evidence forward transparently.
A source-code check must not be described as a browser check. After a repeated
failure, stop the production item and repair the shared template separately.

Before another volume run, use one representative corrected demo and record:
model/effort, selected speed, agent count, elapsed time, allowance used before
and after, repairs and final visual verdict. The allowance delta is account-wide
and is only a run estimate if other sessions were idle. Do not promise a fixed
number of daily jobs from API token prices or an unmeasured model switch.

Official guidance checked 19 October 2026: [Codex/Work pricing and limits](https://learn.chatgpt.com/docs/pricing)
documents Fast at 2.5× included subscription usage relative to Standard, shared
usage between chats, and the effects of context, reasoning, tools and caching.
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
is the lower-cost complex-work option. These facts do not establish a fixed
weekly savings ratio for this pipeline.
