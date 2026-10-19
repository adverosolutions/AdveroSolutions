# Native template rebuild, 19 October 2026

Four isolated, reusable native-screen fixtures. This maintenance does not register
jobs, reopen the rejected batch, send messages, import a workflow or connect accounts.
The outer palette, Inter font file, approved opening and blue closing CTA are unchanged.

## Review locally

From `templates/sales-deck`:

```sh
/usr/bin/python3 build.py lock
/usr/bin/python3 native-templates/build_preview.py
```

The persistent review hub is `../../.local/native-template-review/index.html`.
Each standalone page embeds its font, styles, data and vendor icons. The hub is
outside the recording queue. Rebuild after any source/spec change; old page review
hashes do not transfer. `build_examples.py` maintains the four JSON fixtures.
They are invented acceptance scenarios, never real saved Upwork posts.

## Implemented surfaces

| Product | Native scene surfaces | Useful proof |
| --- | --- | --- |
| GoHighLevel | `builder`, `conversations`, `pipeline` | Avery's SMS/reply/email; one $8,450 opportunity moves through the supplied stages |
| n8n | `editor`, `node`, `execution` | Input / Parameters / Output; the sample HTTP result returns matching contact/opportunity IDs |
| Zapier | `editor`, `test` | The visual Zap and the selected step's mapped Data in / Data out |
| Claude app | `skills`, `project`, `chat` | Current skill list/detail/Contents; project context; readable visit brief with source references and missing-address case |

Use `kind: "native"` with the exact `platform` and `content.surface`. See the
fixtures and `../native_schema.py`. Every graph has an inspector for each node;
its IDs must match the graph. Graph nodes/actions are from the platform catalog.
Claude Skills/Projects can begin the mechanism route and Claude chat counts as
result proof; there is no forced CRM/workflow wrapper. Finalization recognizes
native graph metadata and leaves the node-count cell blank for assistant work.

All native chapters enter in a useful settled state. Replay resets only that
chapter, settles within 4.5 seconds and holds. Next/Previous and route changes
cancel obsolete timers. Show result settles immediately. Reduced motion settles
immediately. The native pipeline card moves between columns, conversation items
appear in order, and Claude replay progresses from input through output to the
missing-field exception. Controls live in the demo footer and never follow scroll.

## References and boundaries

The source image inventory is `../visual-reference/references.json`. Additional
GHL opportunity-board references and current installed Claude captures are in
`references/supplement.json`. Native screenshots were inspected, not inferred
from the article title. The Claude list now follows Customize > Skills > Yours;
toggles appear on the skill detail, not invented on the list. The current example
project captures establish a narrow left-aligned composer/context column at both
narrow and wide window sizes.
No account contents were copied into the public demo fixtures.

The explicit review surface is GHL's documented compact Workflow Builder and
classic CRM board/inbox; n8n's light editor and node data; Zapier's visual Zap
editor (not Next Gen Workflow Manager); and Claude's inspected dark app variant.
The Zapier quickstart canvas screenshot is older: current official documentation
confirms the visual-editor and Setup/Configure/Test concepts, but its account-
specific current chrome still needs comparison before claiming exact release parity.
The n8n source set establishes canvas/node geometry, not every current execution-
header control. Claude's current populated chat/artifact capture is also still a
reference gap: the new chat/document renderer is a candidate pending that comparison.
These limits must remain in the independent review verdict; a native-looking
candidate is not blanket production approval for all releases or all screens.

Not implemented here: n8n AI clusters/subnodes, Zapier Paths/Next Gen, GHL calendar,
contact overlay/action-setup parity, Claude Cowork/Code, arbitrary destinations,
or a tested import/snapshot. Unsupported catalog actions remain blocked. The old
`workflow`/`messages`/`outcome` renderers remain for legacy compatibility and remain
visually rejected; new native scenes do not confer approval on them.

## Checks and exact acceptance

`tests/test_native.py` checks product/surface isolation, meaningful result presence,
inspector IDs, blocked AI nodes, invalid stage/value data and markup rejection.
`tests/native_browser.cjs` checks all routes, settled entry, repeat replay, Show
result, stale timers, native skill/node controls, sample values, mobile overflow,
reduced motion and absence of runtime network calls. Browser screenshots and
exact page hashes are in `qa/`. Same-size comparison sheets preserve the source
image's aspect ratio; they are visual layout comparisons, not pixel-diff claims.

Independent review belongs in `REVIEW-2026-10-19.md`. Its verdict must distinguish
implemented candidates, visually reviewed surface variants, missing evidence and
any remaining blockers. Lorenzo's visual acceptance is separate from this report.
