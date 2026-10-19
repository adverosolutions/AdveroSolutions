# MapleSpark independent review

Verdict: **APPROVE** for the final generation below, reviewed independently on 2026-10-19. No blocking defects found. This note is evidence for the coordinator; the reviewer did not write a queue receipt.

## Approved final generation

- Page SHA-256: `60179a8cd4a83664526d698de8e85d66f8df37988dabe12f78a493d5a3f31930`.
- Template hash: `4dbfdc2ccb27f33075070264178cfdf993572c437c003fbbc5d866d0addd3806`.
- Content hash: `789b36bfd7836979bb452a2a9882bde2d5fc233b54f6efc92ea5f39203bfdd85`.
- Spec hash: `b1e12982acfc1d19ecfc6cc10b84a3fed5132b4018c8db649d0c5902fc89609b`.
- Recording script SHA-256: `2c92ffe57b570b18664389f67e13f836e9175d2141cb663cdecb72b849a177da`.

Page and script hashes were independently computed and matched build-report.json and the coordinator's assigned final generation. All template-lock files matched. The approved artifact is the canonical `.local/recording-queue/public/jobs/maplespark-agent-operations-2112199267713547296/page.html`, served at the original supplied URL after the coordinator restarted the server and rebuilt it.

The final source retains the content checks below. Both Claude Code and Codex are actual transcript interiors. The issue and result screens clearly use Custom project workspace. There is no GHL scene or vendor-functionality substitution. All four scenes remain required; each route keeps both tools, failure/recovery, internal notes, human verification, and the proof outcome. No private source/review history appears in browser DATA or public recording notes.

## Final browser evidence

Used only hidden IAB tabs through mcp__cua_repl. Viewed screenshots at **1440 × 900** and a documented viewport override of **390 × 844**. Screenshots were inspected in the tool conversation; this Markdown file is the saved evidence. No standalone browser script was used.

Desktop screenshots: cover; Claude Code at initial and settled states; settled Codex; settled issue notes; settled result; close. The cover, approved opening caption, Inter font, blue accent and blue 15-minute CTA were intact. Both transcript bodies were readable at 12px without horizontal scaling. Result metric values were 33px and the proof was the short `3/4 = 9/12`. No clipped headline or whole-document horizontal overflow was seen. Transcript content scrolls within its own frame; earlier stages remain available there. The context label “Checkpoints” wraps tightly on desktop, but its value is readable and it is not a blocker.

390px screenshots: cover; both settled agent transcripts; issue notes; result; close, plus a separate scrolled proof capture. The terminal and project contexts stack, all content remains readable, and navigation/CTA are reachable. Measured document clientWidth/scrollWidth were 390/390 for cover, Claude workflow, messages, result, and close. The Claude transcript was 348/348 client/scroll width. Desktop document width was 1440/1440.

The mobile result uses an internally scrolling content area. Its first view shows KPI cards and worked answers; I scrolled inside that frame and verified the full proof, human check, revised-prompt note, and source-file list. At contentScrollTop 424, the proof rectangle was x=33 to 357, y=343 to 618 in the viewport. The proof is accessible; it is not omitted or horizontally clipped.

Observed controls and behavior:

- Quick, Standard, and Detailed each reset to the cover with six chapters. This job has no optional record, so optional-record omission is not applicable to this specimen; the shared test covers that renderer behavior.
- See the workflow, Next, Previous, chapter buttons, left/right arrow keys, Talking points, Present, and Escape worked. Present hid the control bar and notes; Escape restored normal view and closed notes. The close disabled Next and the cover disabled Previous.
- Initial Claude workflow state was immediately step 0, “Brief and acceptance checks set.” It naturally settled to step 5, “Draft handed to Codex,” and held that scene. Show result set Codex to step 5 and result to step 3 immediately.
- Rapid repeated Replay reset the result to step 0. Rapid Previous/Next/Replay/Next navigation produced the correct later scenes; no stale scene content appeared in subsequent screenshots. Shared source additionally cancels timers and checks both a generation token and scene identity.
- Both keyboard directions were verified again in a fresh hidden tab: Right moved cover to claude-code-task; Left returned to cover. That tab's warning/error log was empty.
- Scrolling the result's internal frame worked. No automatic chapter advance or wheel/scroll interception was observed. Navigation resets page position intentionally; replay does not.

Reduced-motion limitation: the exposed CUA browser/tab capabilities have no reduced-motion emulator. I did not claim to observe the operating-system media setting or change it. I reviewed the exact final runtime and its `reduced motion shows settled state immediately and media change cancels animation` test: reduced mode skips timers, Replay remains settled, and switching to reduced cancels pending animation. The coordinator reported **34 build tests and 19 runtime tests passed** on this exact shared template and explicitly accepted shared runtime/source evidence for this check. This is code/test evidence, separate from the browser observations above.

Static final-page inspection found no remote resource src/href, CSS import, fetch, XMLHttpRequest, WebSocket, or sendBeacon call. Inter is embedded. This is source evidence rather than a browser network trace. No service writes were performed.

The viewport override was reset and both reviewer-created hidden tabs were closed. Only this private review file was written. No source, template, proposal, queue, Git, or live-system writes were made by the reviewer.

## Superseded initial assigned generation

- Page SHA-256: `311596ff1f476eaf5e9a925f5c2b7349995d396446513244d8946db607c304d3` (independently computed; matches build report and assignment).
- Template hash: `78ad7e70830cd39b240125f172cd49de9b9db709c2db93a2298d119ae8f1df3f`.
- Content hash: `bcde309684b52446003c358c506ae27bdeda87e4b6c8e448c63ed8f6e4a04008`.
- Spec hash: `e2dfe8daffc3797d07c64731c32d526949a6fa89bae6517a0c2ecfd78640d691`.
- Recording script SHA-256: `df1fa1ac798add9827b5a00507983d21c3a63e5d6ffd77ba8949b29d93c275d3` (independently computed).

Read original jd.txt, intake-private.json, content-private.md, deck-spec.json, generated page and script, build-report.json, REVIEW_BRIEF.md, extension-contract.md, and pipeline instructions. All current template files matched template-lock.json at the first check.

## Source checks on the initial generation

- Required Claude Code and Codex transcript scenes are both present. All six stages in each scene form one prompt-first linear chain. No GHL scene or fallback interior is selected.
- The original requirements and S1 rule are visible source material. The sample retains MS-014, the same two fraction questions, source note, two fixtures, operator Alex Morgan, and separate reviewer Maya Chen.
- The sample shows task subdivision, hourly checks during working hours, a stalled attempt, narrowing the prompt, reproducing the incorrect `3/4 = 6/12` answer, correcting it to `3/4 = 9/12`, and rerunning the same fixtures.
- Human verification names the actual files and original brief, recounts both questions, recalculates both answers, and checks source references. It is not based on the agent completion claim.
- All four scenes have `optional: false`. Quick, Standard, and Detailed source routes all contain both agent scenes, issue notes, the proof outcome, cover, and close. There is no optional record scene to omit in this job.
- Illustrative names, data, checks, and results are labelled. No personal accomplishment, rate, availability, start date, or MapleSpark project access is invented. Chang is supported as a contact first name by two separate reviews; no account-ownership inference appears.
- Public DATA contains no source block, review text, review counts, private intake, or client history. Public personalization contains only firstName. No private review-title tokens were found in the page.
- No remote src/href attributes, CSS imports, or fetch/XMLHttpRequest/WebSocket/sendBeacon calls were found in the standalone page. Inter is embedded. This is static-source evidence, not a browser network trace.
- Timer code cancels prior timers and uses both a generation token and scene ID. Replay starts at step 0 and schedules its last step at 4500 ms. Reduced motion applies the final step immediately and finishes on a matching media-query change. These are source checks; runtime behavior is still awaiting browser review.

## Browser evidence so far

Hidden IAB only. The supplied canonical URL returned a plain “Not found.” page, confirmed by AX text and a 1280 × 720 screenshot. The registry was `needs_build` with “Spec or artifacts changed; rebuild and review required.” The coordinator diagnosed the running server's cached schema and is handling restart/rebuild after template changes. No queue or template edits were made by this reviewer.

The IAB advertises a documented viewport override, so the required 390px check can be performed once the page is served. Browser and tab capability inventories do not advertise a reduced-motion override. No OS preference was changed.

## Copy shortening sent to coordinator

- Result metrics: “Checks passed”; “1/2 → 2/2” with “Same fixtures before and after repair”; “3 hourly checks” with the schedule in its note.
- Proof value: “3/4 = 9/12”; retain the multiplier and S1 explanation in proof description.
- Remove repeated defensive clauses about no scheduler, no curriculum claims, no completion approval, no real performance claim, and no transmission where the shared sample label and actual project-output context establish the boundary.
- Retain the prominent illustrative label, initial sample/people identification, original brief/source evidence, both tools, hourly rule, failure/repair, same-fixture comparison, separate human review, and baseline agreement.

No approval was issued for this earlier generation. The final approval above applies only to the final hashes listed at the top of this file. Any later changed generation needs fresh hashes and rendered-page checks.
