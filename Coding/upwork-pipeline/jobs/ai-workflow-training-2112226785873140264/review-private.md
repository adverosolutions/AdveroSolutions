APPROVE — exact compact training generation reviewed independently on 2026-10-19.

Scope: original jd.txt, intake-private.json, content-private.md, deck-spec.json, generated page.html, recording-script.txt and build-report.json, against REVIEW_BRIEF.md and extension-contract.md. Browser review used only a hidden IAB tab through cua_repl. The reviewer changed only this private evidence file. No source, template, queue, proposal, Git or live-service writes were made.

Exact approved identities:

- Page SHA-256: `0dffb741854ca678af4313ef09d6aec6b58c37d3ea45313993a051ad888c206e`
- Content: `dbb91ba35bfda33c3bb1743e292f7579d63037824cd182f55e8b0471647844c9`
- Normalized spec: `c18b698e0a3dbe56b865c51e4ddd43b81a8028db66841c4e677e4601eb02478c`
- Template: `4dbfdc2ccb27f33075070264178cfdf993572c437c003fbbc5d866d0addd3806`
- Recording script: `64843c98828b8e68ca8906ea4039d91b9791355c9c43d8cb7f4ebb6331331895`

The page and script hashes were independently recomputed. There are no remaining blocking defects for this generation.

Observed visual evidence:

| View | Evidence |
| --- | --- |
| Desktop, verified 1440 × 900 | Bounded screenshots inspected for cover, native n8n workflow, four-lesson record, prompt/troubleshooting messages, sample result and close. Inter is the computed font; approved palette, opening caption and blue CTA are retained. Document scrollWidth was 1440. |
| Native n8n workflow | Four supported nodes are visible at canvasScale 1: Manual Trigger → Edit Fields → HTTP Request → Google Sheets Append Row. Labels and short details are unscaled and readable. The caption explicitly starts with supplied spreadsheet/CRM values and moves source API connection to lesson two. |
| Lesson record | Trial, four numbered lessons, learner actions and workflow/prompt/sample/checklist handover are visible. The trial exit check changes clicks from 48 to 60. |
| Prompt and troubleshooting | The full prompt and 401/empty-total/missing-qualified/new-period troubleshooting card are readable. The page supplies text to copy into n8n; it does not claim an in-page prompt editor. |
| Result | 4%, 37.5%, 5%, the source arithmetic, revised AI summary and visible sample proof are readable. The workbench is labelled a custom project workspace, with no GHL vendor chrome. |
| Mobile, verified 390 × 844 | Cover top and lower teach/do/rerun panel, workflow start and final node, prompt top and lower troubleshooting/reviewer content, close top and lower blue CTA were inspected in screenshots. All inspected scenes had document scrollWidth 390. Normal vertical scrolling reveals lower content. |
| Mobile native canvas | Canvas scale stays 1; its 912px graph scrolls inside a 348px frame. Observed canvas scrollLeft 564 while page scrollX remained 0. Final node is readable; there is no whole-page horizontal overflow. |

Observed behavior evidence:

- Quick, Standard and Detailed were selected through the real control. Each resets to the cover, retains six chapters, and reaches the required result with `48 / 1,200 = 4%` proof. The lesson record is intentionally required; there is no optional record in this job to omit.
- Talking points opens with the current scene and route timing. Present hides the controls and closes notes. Right arrow advances to lessons, left arrow returns to the workflow, and Escape exits Present and closes notes.
- Chapter buttons, Previous and Next work. Previous is disabled on the cover; Next is disabled on the close.
- Workflow entry and Replay expose step 0 immediately. Show result reaches the final workflow step 3. Natural playback reaches the final state and holds without chapter advance.
- Rapid Replay → Replay → Next → Next → Replay → Next finishes on the correct result, step 2, with Learner rerun and unchanged proof. Old workflow/message timers did not visibly mutate the result. A locator wait hit the tool's short wait deadline before the animation completed; the next observation at about 7.3 seconds showed the correct settled result. The exact source schedules the last state at 4500ms, and the shared runtime test covers the five-second bound; this review does not claim a browser stopwatch measurement below five seconds.
- Page scrolling stayed under user control; the mobile workflow pans only inside its native canvas. Browser console error query returned an empty list.
- The temporary viewport override was reset and the review tab was closed.

Content and integrity evidence:

- Teach/do/rerun, a trial as lesson one, four numbered lessons, hands-on learner action, 401 and missing-field troubleshooting, independent rerun, and workflow/prompt/sample/checklist handover are present.
- The revised AI summary shows clicks 48 / sent 1200 = 4%, qualified 9 / leads 24 = 37.5%, booked 3 and a reviewer question. It matches the prompt's arithmetic and source-field requirements. The 60-click rerun gives 5%.
- MKT-104, the October newsletter, Casey Brooks and Morgan Lee remain connected across the scenario. No numerical improvement, past client result or teaching-history claim was invented.
- Two private review entries support contact first name Yaffa, without inferring ownership. Public DATA retains only firstName; source metadata, client_reviews, reviewCount, jobUrl, intake-private and client financial/intake data are absent.
- Workbench output is explicitly custom. The workflow uses supported n8n actions, including HTTP Request for the model call, with no unsupported AI Agent node or GHL fallback. Source API construction and the 401 drill remain in lesson two.
- No remote src/href, fetch, XMLHttpRequest, WebSocket or sendBeacon primitives were found in the generated page. Font and runtime are embedded. No service writes are performed by the demo.

Reduced-motion evidence is exact-source and shared-test evidence, not an observed browser emulation. The embedded runtime immediately settles when motion.matches, cancels timers on preference change and disables CSS transitions/animations under the media query. The existing runtime test checks settled entry/replay and cancellation on media change; the coordinator reported 19 runtime checks passing on this exact template. This IAB exposes viewport but no media-emulation capability. The coordinator explicitly accepted this evidence distinction for the review.

Review history retained:

1. The original supplied page `cc6abfef6d1ac2d036117d05a1fb85ccad70c94650aa621c0332e1583816e089`, template `78ad7e70830cd39b240125f172cd49de9b9db709c2db93a2298d119ae8f1df3f`, initially returned Not found because the running queue invalidated the generation. Its on-disk hashes matched. The coordinator restarted the stale server and rebuilt. No approval attached to that generation.
2. Rebuilt page `5eda1cde5b5d1638e98a4ffc709aba59074ddde76c44e3d4473ccbb7f5bc54ba` was rejected after a 1440 × 900 native-workflow screenshot. Six nodes fit, but a 1376px canvas inside a 1095px viewport scaled to 0.7957848837209303. Labels rendered at about 9.55px and detail/action text at about 7.96px, too small for the recording. This was a native-text-scale defect, not page overflow. The coordinator recorded rejection before rebuilding.
3. The coordinator reduced only the job's workflow content to four supported core nodes and revised the caption, beat, status/context and private route note. The final page listed above renders the graph at scale 1 and passes the required screenshots and controls. The template hash stayed unchanged during this compacting repair.
