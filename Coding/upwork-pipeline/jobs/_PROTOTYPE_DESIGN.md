# Prototype design standard

Lorenzo, 2026-09-28: "It needs to be gorgeous, elegant, almost like a $15,000 custom build." The first prototypes (cold email, GHL + Pipedrive) were judged **not good enough**. They were busy, card-heavy dashboards in a generic SaaS style. Do not use them as a style reference. The goal is the calm confidence of a boutique studio's product work: Linear, Stripe, Vercel, Mercury, Arc. Not a Bootstrap admin panel.

## The reference build (approved by Lorenzo, 2026-09-28)
`jobs/_reference/voice-agent-film.html` is the approved base: "this is really good... a good enough base to where you can understand and go from there." Open it before building any prototype and match its format:
- presenter film with scenes in a fixed order
- a description card on each still frame, then Play
- an animated agent presence with states
- speech bubbles that hold for 3 seconds or more
- rich motion, minimal words
- held end frames and cinematic transitions

His last note on it: "make sure that we're putting as many beautiful visuals on the screen as possible". Every scene should be visually rich (illustrated records, animated connectors, charts, avatars, product surfaces in the client's world), never text on a plain background.

## Keep the system, cut the words (Lorenzo, 2026-09-28, overrides anything below)
Calibration from three rounds on 2026-09-28:
- The detailed prototypes had the right screens and the right system ("the overall system architecture is phenomenal"), but too many words to follow.
- A 6-step slideshow was still too wordy.
- A wordless 5-node flow was too thin: "it gives me nothing to talk through."
- The target, on the voice agent prototype: "Just slightly simplify... not as one-on-one on the screen as the last one, but remove a lot of the fluff words that are unnecessary. Make it look beautiful, animated, automated, all these moving parts and beauty that I can just talk over easily with minimal words on the screen."

So:
- **Keep the structure.** Keep the screens, the live moments, the real records (a call transcript, a CRM card, an SMS, a booked slot) and the integrations. These are what Lorenzo talks over.
- **Cut the fluff words.** Remove ledes, explanatory paragraphs, "why it's built this way" blocks, captions that restate what the visual already shows, helper text, and repeated labels. Headlines stay short (8 words or fewer). The words that remain are the product's own words: record content, field labels, statuses, short tags.
- **More motion, more polish.** Every screen should have something that moves on its own or on one click: data flowing, records filling in, statuses flipping, connectors lighting up. The system should feel alive and automated, and every frame should look beautiful.
- **Show the ideal outcome.** Each screen lands on the finished result in the client's world, so the prototype reads as "this is what your business looks like when it's done right".
- **A film Lorenzo narrates live (2026-09-28).** "Think of it as a YouTube video that we send to a board of directors to get them to close, without narration, where I can trigger parts of the video at different points." Scenes come in a fixed order. Nothing auto-plays on arrival: each scene opens on a composed still frame and waits. One presenter bar at the bottom centre holds the scene number, a progress line, Play for the scene's action and Next scene. Space plays, the right arrow moves to the next scene, the left arrow goes back. Each action runs 6 to 15 seconds with a clear rhythm, then holds on a finished frame worth pausing on. Scene transitions are cinematic (a 400 to 600ms eased crossfade or slide). Every frame should be board-of-directors quality.
- **Produced-explainer feel (2026-09-28).** An animated presence for the system's agent sits on screen, an elegant orb or avatar that idles, listens, talks, thinks and hands off, reacting in every scene. Motion is rich throughout. Each scene's still frame carries a short description block (1 to 2 lines, 15 to 25 words) saying what's about to happen, which Lorenzo reads before pressing Play. Nothing flashes past: any in-action subtitle, such as spoken dialogue, stays up for at least 2.5 to 3 seconds, and actions can run to about 20 seconds.
- **Easy to walk.** The primary live moment is obvious on each screen, and Lorenzo can move through the whole thing in 2 minutes or less.

## The one test
Ask whether a founder who paid a design studio $15,000 would be proud to show this to their board. If any screen looks like a template, a Dribbble shot from 2019, or "AI made this", redo that screen.

## Direction before code
Before writing HTML, write a 6-line design plan at the top of your report:
- **Subject world:** what the client's business actually looks and feels like, and one detail only this subject would have (its units, documents, vocabulary).
- **Palette:** 4 to 6 named hex values. One restrained accent. Neutrals with a hue bias toward that accent, never pure mid-grey.
- **Type:** a characterful display face used sparingly, a refined text face, and a mono or tabular face for data. All from Google Fonts, with fallback stacks. Never Inter, Space Grotesk or Plus Jakarta Sans as the lead face. Good starting points: Instrument Serif, Fraunces, Newsreader, or Gloock for display; Geist, Manrope, Figtree, Onest, or Instrument Sans for text; Geist Mono, JetBrains Mono, or IBM Plex Mono for data.
- **Layout concept:** one or two sentences.
- **Signature moment:** the single animated or interactive moment the whole page is built around.
- **What you changed** from your first instinct because it was generic.

## Elegance rules
1. **Restraint over quantity.** Fewer, larger, better screens. One idea per screen. Cut any card, chip or badge that doesn't carry information. Chips everywhere is the #1 sign of a cheap build.
2. **Whitespace is the luxury.** Use an 8px spacing scale with generous section padding (48 to 96px on desktop). Line length for prose stays around 60 to 70 characters.
3. **Typography does the work.** Use a clear type scale (for example 12 / 14 / 16 / 20 / 28 / 44 / 64). Display headings get tight letter-spacing and `text-wrap: balance`. Uppercase labels get letter-spacing, used sparingly. Use tabular numbers wherever digits line up.
4. **Hierarchy through weight and size, not boxes.** Borders, fills, shadows and radii each mean "separate object", so spend them only where that's true. Prefer hairline dividers and alignment over nested cards. Keep one radius family and one shadow recipe, soft and low.
5. **Color is quiet.** Mostly neutrals, one accent that means "action or live", and semantic colors (success, warning, error) only for state. No rainbow chip palettes. No gradients except one deliberate, subtle one if it serves the signature moment.
6. **Icons are drawn, not typed.** Use inline SVG line icons with a consistent stroke width. No emoji, no unicode glyphs (✓ ⚡ ▥ ◎) as icons, no letter-in-a-square icons.
7. **Motion is choreographed.** Use one orchestrated sequence for the signature moment, with eased (cubic-bezier) timing and staggered reveals of 150 to 400ms. Micro-interactions on hover and press. Nothing loops forever to get attention. Respect `prefers-reduced-motion`.
8. **The system looks finished.** The page should look like the shipped product running: realistic sample data in the client's world, believable timestamps, real-looking records, and considered empty, running and done states. Every requirement in the post is answered (see the 90-second rule for grouping). Nothing reads as "coming soon" or as a placeholder.
9. **Craft details:** a visible focus ring, crisp 1px hairlines in a neutral with alpha, consistent alignment edges, no orphaned single items in a row, and no text clipping. Use `font-feature-settings` where the font supports it (for example `"ss01"` or `"cv11"`).
10. **Navigation is elegant.** Prefer a slim top bar or a refined left rail with a small wordmark. Section switching should feel like an app, not tabs on a form. A persistent, quiet "Reset" and a theme toggle go in a corner, not in the hero.

## Both themes, done properly
Put light tokens on bare `:root`. Put dark overrides under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`, with `color-scheme` set in each. Design the dark theme on its own terms (deep tinted neutrals, not pure black, and the accent adjusted for contrast) rather than inverting the light one. Give `body` an explicit token background.

## Honesty
Sample data is labelled as sample in one quiet place, not stamped on every card. Illustrative numbers carry a small "illustrative" note. Don't use real people or real client data, and don't imitate a vendor's UI.

## Before you hand it back
Open it at 1440x900 and at 390px wide. Check the first still frame, since that's the thumbnail and the first thing the client sees. Check every live moment, then Reset. Fix anything that looks generic, then look once more. Report your design plan, the signature moment and the screens.
