# Reference kit brief (one finished-product page per platform)

Goal: a library of approved pages, one per platform, so a real job only swaps the content (business, names, records, headline copy) instead of rebuilding screens and canvases.

## Read first
1. `jobs/_REEL_BRIEF.md`. UPDATE 4 wins over everything above it; the Spatial rules in UPDATE 3, the Words rule and the builder accuracy check still apply.
2. The approved references: `jobs/_examples/finished-ghl.html`, `finished-make.html` and `finished-clickup.html`. Copy the CSS/JS engine and the section structure from the one closest to your platform. Don't rebuild the engine.

## Page shape
Keep the approved order:
1. A hero naming the outcome.
2. 3 to 5 finished screens of the live system, in the order the client would use it.
3. The platform screen: "This is what it will look like in your <Platform>", labelled "Your <thing> in <Platform> · illustrative".
4. Close with 4 words on pills.

Each screen gets a headline of 6 words or fewer and one `.sub` sentence. "Sample data" goes in the top bar. The platform screen follows the platform's real layout conventions and colour feel, with no vendor logos (generic icons only).

## Plug-and-play rules (the point of this kit)
- Wrap each section in `<!-- SCREEN: <name> -->` … `<!-- /SCREEN -->` comments.
- Keep all sample content (names, company, records, numbers, headline copy) in one `const DATA = {...}` object near the top of the script, where you can. The markup and runners read from it, so a real job mostly edits DATA and the headlines.
- Components are reusable: a platform canvas takes its nodes and steps from DATA, not hard-coded markup, where that's practical.

## Hard rules
- `<title>` is 2 to 4 words and never contains reel, film, video, prototype or mock. Those words don't appear anywhere on the page.
- One self-contained file with no doctype/html/head/body tags.
- A real responsive layout at 390 wide, with no sideways scroll.
- Numbers are labelled Illustrative.
- Write ONLY your own output file. No git, no publishing.
- Put render scripts and screenshots in the scratchpad subfolder named in your prompt. Other agents share the scratchpad.

## Check
Render with Playwright pointed at the installed Google Chrome (its bundled browser isn't installed):
- at 1440x900, section by section after each settles
- at 390 wide

There must be no console errors, overlaps or clipped text. Screenshot the platform screen on its own and verify it the way the builder accuracy check describes.

Report briefly: the screens, and the platform-screen screenshot path.
