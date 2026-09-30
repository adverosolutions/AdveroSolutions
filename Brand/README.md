# Advero Solutions brand

The brand for Advero Solutions, in the Spatial look used on the Upwork pages. The logo is Direction B, "Depth": three rounded glass planes rising up and to the right. It was chosen and refined on 2026-09-30.

- Canvas with every design: https://claude.ai/artifact/QWWP6kuStm58D1u8sUG1wL (private to Lorenzo). Pages: Brand, Banners, Profile photos & icons, Templates, Round 1 directions.
- Reference page for the look: `Coding/upwork-pipeline/jobs/_examples/finished-ghl.html`

## Which file goes where

| Platform | Slot | File |
|---|---|---|
| LinkedIn (you) | Profile photo | `social/avatars/headshot-lorenzo-1080x1080.png` (your headshot on the brand sky; `headshot-background-1080x1080.png` is the empty background for future photos) |
| LinkedIn (you) | Background banner | `social/linkedin/linkedin-banner-1584x396.png` (the 3168x792 is a sharper 2x copy) |
| LinkedIn company page | Logo | `social/avatars/linkedin-company-logo-400x400.png` |
| LinkedIn company page | Cover | `social/linkedin/linkedin-company-cover-1512x256.png` (or the 2x copy) |
| X | Profile photo | `social/avatars/headshot-lorenzo-400x400.png`, or `social/avatars/x-avatar-400x400.png` for a brand account |
| X | Header | `social/x/x-header-1500x500.png` (or the 2x copy) |
| YouTube | Profile picture | `social/avatars/youtube-profile-800x800.png` |
| YouTube | Channel banner | `social/youtube/youtube-banner-2560x1440.png` |
| YouTube | Watermark | `social/youtube/youtube-watermark-300x300.png` |
| YouTube | Thumbnail template | `templates/youtube-thumbnail-*.png` (upload the 3840x2160 JPG; it's under 2 MB) |
| YouTube | End screen background | `social/youtube/youtube-endscreen-1920x1080.png` |
| Skool | Group icon | `social/avatars/skool-group-icon-128x128.png` (the 512 is a sharper copy) |
| Skool | Group cover | `social/skool/skool-cover-1084x576.png` (or the 2x copy) |
| Skool | Course cover template | `templates/skool-course-cover-1460x752.png` |
| Skool (you) | Member photo | `social/avatars/headshot-lorenzo-400x400.png` |
| Upwork (you) | Freelancer photo | `social/avatars/headshot-lorenzo-1080x1080.png` (no logo or text, which Upwork requires) |
| Upwork agency | Logo | `social/avatars/upwork-agency-logo-800x800.png` |
| Upwork agency | Banner | `social/upwork/upwork-agency-banner-3200x320.png` |
| Upwork | Portfolio / Project Catalog cover | `templates/upwork-portfolio-cover-1000x750.png`, or the `-blank` version to drop a screenshot on. Keep text minimal and no other platforms' logos. |
| Instagram | Profile photo | `social/avatars/instagram-avatar-1080x1080.png` |
| Instagram | Highlight covers | `social/instagram/instagram-highlight-{results,systems,about,book}-1080x1920.png` |
| Facebook page | Profile photo | `social/avatars/facebook-avatar-1080x1080.png` |
| Facebook page | Cover | `social/facebook/facebook-cover-1702x630.png` (the 851x315 JPG is under Facebook's 100 KB guideline). Preview it on the live page, because Facebook's crop guidance contradicts itself. |
| TikTok | Profile photo | `social/avatars/tiktok-avatar-1080x1080.png` |
| Threads | Profile photo | `social/avatars/threads-avatar-1080x1080.png` |
| Posts (LinkedIn, X, Instagram, Facebook) | Templates | `templates/template-*.png`: statement, carousel cover / slide / end, result, square, story, wide. Bracketed text is placeholder. |
| Email | Signature | `email/signature.html` and `email/HOW-TO-INSTALL.md`. Host `email/email-mark-128x128.png` at a public https URL first. |
| Website | Icons and share image | `web/` (favicon.ico, favicon-16/32/96.png, favicon.svg, apple-touch-icon, icon-192/512, maskable icons, site.webmanifest, web-og-1200x630.png, web-xcard-1200x600.png) |

The source artboards for everything are in `source/` (`.dc.html`, self-contained). Re-render any of them at exact size with `python3 source/render.py <file> <out.png> <w> <h> [scale]` (needs Playwright and Chrome).

## For the website

- Colours, type, shadows, radii and motion are in `tokens/brand.css`. The same values are in `tokens/tokens.json`.
- Font: Figtree from Google Fonts (weights 300-800).
- Logos: `logo/svg/` and `logo/png/`. Text is outlined, so no font is needed.
  - `lockup-horizontal-glass.svg`: site header, on light backgrounds.
  - `lockup-horizontal-white.svg`: on dark sections.
  - `lockup-stacked-glass.svg`: centred layouts.
  - `mark-glass.svg`: the mark alone at 64px and up.
  - `mark-flat.svg`: the mark alone under 64px.
  - `mark-ink.svg`, `mark-white.svg`: one colour.
- Glass versions are for light backgrounds only; on dark backgrounds use the `white` files. The grid, clear space and minimum sizes are in `logo/GEOMETRY.md`.
- Head tags: link `web/favicon.ico`, `web/favicon.svg`, `web/apple-touch-icon-180x180.png` and `web/site.webmanifest`. Set `og:image` to `web-og-1200x630.png` and `twitter:image` to `web-xcard-1200x600.png`. Add `"start_url": "/"` and `"id": "/"` to the manifest when the site's paths are fixed.

## Rules

- Light pages on the sky gradient (`--sky`) with white glass panels. No dark page backgrounds; dark ink panels are fine as sections.
- One accent, blue. Mint only for success and "done" states.
- Small blue text (eyebrows, links) uses `--blue-deep` (#1f5fd6), because `--blue` fails contrast at small sizes.
- Headlines: weight 600, letter-spacing -.035em. The second half can use `--text-gradient`.
- Logo: clear space is half the front plane's height. Don't stretch, recolour, rotate or add effects, don't use glass on dark, and don't place it on busy backgrounds (see `guidelines/`).
- Copy used across the kit: eyebrow "AI automation for service businesses", headline "Leads in. Calls booked.", and the proof numbers $750M+ annual bid volume routed, $5M loan applications in 30 days, +35% qualified leads.
