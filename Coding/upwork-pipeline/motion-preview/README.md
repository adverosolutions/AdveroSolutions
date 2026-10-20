# Animated sales presentation — comparison preview

Requested by Lorenzo on 20 October 2026 before the next production batch.
This is a separate motion direction, not a change to the accepted/default deck.

Build:

```sh
/usr/bin/python3 build_preview.py
```

Output: `../.local/animated-sales-preview/index.html`.
The page embeds its assets and runs locally. Open it and click **Replay entrance**
to repeat the opening; use Next/Previous or chapter buttons to inspect transitions.
**Motion on/off** compares presentation movement; native workflow replay is a
separate control. Present hides the preparation toolbar for recording.

The preview retains the invented Northstar GHL example and its reviewed sales
sequence. The personalization badge, headline reveal, overview-card entrance,
chapter transitions, closing-card reveal and subtle ambient drift are presentation
chrome. Native app states and replay logic are not rewritten. No production
CSS/runtime/font/catalog/lock changes or recording-queue commands are involved.

The builder compiles an exact base page, applies an explicit preview-only go()
hook, then injects this folder’s CSS/JS. The hook refuses to patch a runtime whose
expected source shape has changed. `motion-build-report.json` identifies the
base and new candidate page separately; old native review hashes do not approve
the changed animated page. The existing native-reference boundaries still apply.

Browser checks: `check_preview.cjs` with Node and Playwright available. They cover
chapter transitions, repeated navigation, old replay cancellation, entrance replay,
presentation toggle, 1440/1280/390px opening containment, reduced motion and no
remote requests/page errors. Screenshots and exact checks stay with the generated
preview. The check is bounded; it does not certify every native surface or every
small-screen result pane. Independent motion review is in `REVIEW.md`.

User review is required before integrating this direction into the production
runtime or refreshing the master handbook’s default template. Do not start a
saved-job batch merely by building or opening this preview.

## Cinematic v2 — deliberate maximal direction

Lorenzo requested a substantially more animated presentation after rejecting the
restrained first study. Build this separate comparison with:

```sh
/usr/bin/python3 build_preview.py --cinematic
```

Open `../.local/cinematic-sales-preview/index.html`. **Replay opening** repeats
the full company-name intro. The intro holds until **Start presentation** is clicked.
The client-name entrance plays on the intro screen, then holds indefinitely.
Only clicking Start presentation triggers the curtain and presentation reveal.
Returning to the cover does not force the prelude again unless replay is requested.

V2 adds a full-screen personalized title, moving perspective grid and expanding
rings, a curtain reveal, large kinetic type, floating glass overview panels,
animated SVG paths/orbits, perspective chapter transitions and a swept closing CTA.
The floating panels are explicitly a conceptual system overview, not invented GHL
software. Native scenes, sample causality, Inter and the outer blue/light palette
remain. Ongoing decorative effects stop with the presentation toggle or reduced
motion; the native workflow simulation’s replay remains separate.

Run `node check_preview.cjs --cinematic` with Playwright available for the bounded
motion test. It additionally checks the manually started intro and responsive animation
handoff. `CINEMATIC-REVIEW.md` contains the final independent comparison review.
This is still a preview awaiting Lorenzo’s direction, not the production default.
