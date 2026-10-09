# Ten designs, one build (Lorenzo, 2026-09-28)

Lorenzo wants 10 gorgeous design directions for the same build. He'll pick the best, and it becomes the formula for every job from then on. He records a Loom while scrolling the page, narrating it, and the client watches that. The page has to make a client stop and think "this person is world class, and this was made for me."

## The build (identical content in all 10)
Job: `jobs/hubspot-real-estate-lead-automation/`. Read `jd.txt` (the post), `dossier.md` and `beats.md`. `page.html` is the current version: take its **story and content** from it, but **never its look**. It is the dark aurora/glass style he has already seen, so do not use dark aurora, glass cards, bokeh or grain unless your direction says so.

The story (sample data, a fictional brokerage):
1. **Opening:** a lead arrives at 9:42 PM. Maya Chen asks about 214 Linden Ave, pre-approved, and gets handled in 38 seconds.
2. **01 Clean up:** her three duplicate records become one, and CRM health goes from 58 to 97. The duplicate count is 412, dropping to 0.
3. **02 Capture:** five sources flow into HubSpot: website form, portal inquiry, open house, home valuation, and calls and texts. Her contact record is created with no duplicate. "29 new leads today" is labelled Illustrative.
4. **03 Qualify:** an SMS conversation asks her timeline, budget and area. Her lead score rises to 86 and she's sales-ready.
5. **04 Assign:** the Northside buyer agent Jordan Reyes gets her, with a 5-minute call SLA. He calls her in 2:14.
6. **05 The automation:** the live workflow runs: trigger, set type and lifecycle, qualifying SMS, score ≥ 80 branch, rotate to agent, task, wait 1 day, similar-listings email that stops on reply, and the showing booked Sat 11:00.
7. **06 "This is what it will look like in your HubSpot":** a HubSpot-style workflow builder. Use HubSpot's layout conventions and colour feel, but no HubSpot logo or wordmark, and the label "Your workflow in HubSpot · illustrative".
8. **Close:** Captured. Qualified. Assigned. Booked.

Words stay minimal: a headline of 6 words or fewer per section, plus the product's own words on the UI. No paragraphs of explanation.

## Hard rules
- One self-contained HTML file with no doctype/html/head/body tags. Start with `<title>`, then the Google Fonts `<link>`, then `<style>`. Scripts may come only from cdnjs.cloudflare.com or cdn.jsdelivr.net/npm, with a pinned version. There are no external images: build everything from type, CSS, SVG and canvas, or use inline data URIs.
- **Title:** "HubSpot Lead System · <Direction name>". It must never contain "reel", "film", "video", "prototype" or "mock", anywhere in visible text either.
- **Format:** a normal page he scrolls. There's no video frame, Play button, slide dots or Next button. Animations trigger as each section scrolls into view (IntersectionObserver or CSS scroll-driven animation), run once and hold. Ambient motion can keep going.
- **Width:** it must look stunning at 1440x900 desktop, where he records. At 390 wide there must be no sideways scroll. Where you can, make it actually readable on a phone (real responsive layout, not one tiny shrunken stage).
- **Content:** "Sample data" is shown once. Don't invent facts about the client beyond the post. Show no prices. No clip-art illustrations: Lorenzo hated triangle-and-circle houses. Beauty comes from type, layout, colour, UI craft and motion.
- **Avoid the AI look:** no cream + terracotta + serif, no purple-to-blue gradient hero, and no Inter/Space Grotesk as the safe choice. Commit fully to your direction; it must look nothing like the other nine.
- **Speed:** aim to finish in about 20 minutes. Quality beats quantity. If time is short, cut sections 02 and 03 into one rather than shipping anything ugly.

## Check before handing back
Render it with headless Chrome or Playwright (python3) at 1440x900, scrolling section by section and screenshotting after each section settles, then check once at 390 wide. There must be no console errors, overlaps or clipped text. Fix what's off and look again.

## Report (short)
The file path, the direction in one line, what makes it special, and anything uncertain. Write only your own file, `jobs/hubspot-real-estate-lead-automation/designs/dNN-<slug>.html`. No git, no publishing, and no other files except scratch files in your scratchpad.
