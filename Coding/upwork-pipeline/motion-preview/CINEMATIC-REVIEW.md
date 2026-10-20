> Manual-start amendment (20 October 2026): the current page now holds the personalized intro until Start presentation is clicked, including motion-off and reduced-motion modes. Replay opening restores that waiting state; underlying navigation is inert while waiting. This bounded behavior change is main-session self-reviewed; the independent review below applies to the earlier cinematic page, not this new hash. Current page: `7ab431b5b6d4fe0b2c69ff766d514a9181d9d40a292c3e7c6dd20f4063ad8d3b`. See the generated checks.json for current browser evidence.

# Cinematic comparison review — 20 October 2026

Scope: the intentionally maximal v2 presentation requested by Lorenzo. Review covers concrete source, lifecycle and readability defects; intensity or restraint is not an acceptance criterion.

Verdict: acceptable for Lorenzo’s cinematic comparison preview. No remaining blocking concrete defect was found within this bounded scope. This is not production or daily-batch acceptance.

Final page SHA-256: `1ca8f353713d5d0c21cd58694bd122d3588be8c3ab04c3cb933ca2157f43560b`, independently recomputed and matching `checks.json`.

One source defect was found and repaired: the 761–1250px overview used a base scale of `.86`, while its entrance ended at scale `1`. Ending the animation would restore the smaller base scale abruptly. The revised code reads the computed base transform and uses it for the final keyframe. Source inspection confirms that correction; main reports a passing 1024px browser assertion comparing width one millisecond before completion and after completion, with a permitted difference below 0.5px.

No other blocking defect was found in the supplied sample. The prepared-for name, complete headline, approved opening caption and CTA remain legible in the 1440, 1280, 1024 and 390px cover captures. The overview cards fit the frames inspected; their “System overview” and “Sample enquiry” labels distinguish the conceptual opening from the subsequent native GHL builder. The blue/light identity and prominent blue call CTA remain intact.

The intro is explicitly skippable. Source inspection shows Skip intro cancels pending presentation animations and reveals the settled cover. Navigation cancels the intro and previous entrance effects; transition generation checks discard obsolete callbacks. Motion off and reduced motion disable both JS entrance effects and the added perpetual CSS effects. The native replay is separate.

Timing from source: the full-screen intro exits by 2.9 seconds, and the last overview card finishes its entrance around 4.23 seconds from opening. Normal chapter entry settles around 1.23 seconds; the closing CTA settles around 1.82 seconds. Those are intentional presentation timings, with presenter-controlled chapter navigation.

Evidence inspected independently: `cinematic.js`, `cinematic.css`, `build_preview.py`, and `.local/cinematic-sales-preview/qa/{intro,cover,workflow,close,cover-1280,cover-1024,cover-390}.png`. This reviewer did not operate a browser or watch a recording. Still captures do not independently establish frame pacing, all phases of the looping sheen, or motion taste.

Main’s completed `checks.json` for the final hash reports passing opening/repeated entrance, chapter transitions, replay cancellation, rapid navigation, motion toggle, desktop/mobile containment, reduced motion, skippable intro and responsive scale handoff checks, with empty error and remote-request arrays. These are main’s operated checks. Final cover and 1024px screenshots were reinspected after the last change removed the redundant overview footer copy.

This remains a comparison preview using the invented Northstar sample. Long or different client names, other job content, every native chapter at smaller widths, daily batch adoption and native-product parity are outside this bounded pass. Existing native-fidelity limitations remain. The production runtime, lock and queue are outside the preview builder’s mutation paths.
