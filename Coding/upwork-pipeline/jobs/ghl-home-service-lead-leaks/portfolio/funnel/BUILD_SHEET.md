# Build sheet: Harlow Heating & Plumbing quote funnel (GHL native)

Sample funnel for a fictional HVAC and plumbing company in Fort Worth, TX. Two steps, built natively in the GoHighLevel funnel builder. Follow it top to bottom.

- Reference render: `design.html` (open `?page=1` or `?page=2`), `design-desktop.png`, `design-mobile.png`.
- Images: `assets/`. Every PNG is exported @2x, so display it at half its pixel width (listed below).
- Page CSS: `ghl-custom.css`. It goes into both pages after the ids are swapped in (Part 4).
- Form: `Get a Quote (Sample)`. It already exists, so do not add or rename fields. Part 3 lists the style settings it needs.

**Element budget: page 1 = 19, page 2 = 5, total 24 (cap 25).** Do not add spacers, dividers or extra headlines. Spacing comes from padding and margins.

---

## Part 0. Tokens (use these exact values)

| Token | Value | Use |
|---|---|---|
| Ink | `#16202e` | headlines, bold text, labels |
| Ink 2 | `#4d596b` | body text |
| Muted | `#5f6b7d` | footer, small print |
| Copper (accent) | `#b4501c` | buttons, second headline line, focus ring |
| Copper light | `#c9622a` | top of button gradient (CSS only) |
| Page | `#eef3f8` | page/body background, plain sections |
| Glass white | `rgba(255,255,255,0.86)` | form panel column |
| Hairline | `rgba(150,170,200,0.30)` | footer top border |
| Font | Figtree (Google Fonts): 600 headlines, 400/500 body | everything |

Radii: form panel 28, trust bar 24, fields 12, buttons pill (99). Shadows are handled by the custom CSS. Natively, pick the softest large shadow preset as a fallback, or none.

## Part 1. Funnel and page settings

1. Funnel name: `Harlow Quote Funnel (Sample)`.
2. Step 1: name `Get a quote`, path `/get-a-quote`. Step 2: name `Check your phone`, path `/check-your-phone`.
3. Each page > Settings:
   - SEO title: step 1 `Get a quote | Harlow Heating & Plumbing`, step 2 `Check your phone | Harlow Heating & Plumbing`. Meta description (step 1): `AC, heating, water heaters and drains across Fort Worth. Send the form and we text you back in seconds.`
   - Favicon: leave empty.
   - Typography: Headline font **Figtree**, Content font **Figtree**. Headline color `#16202e`, text color `#4d596b`, link color `#b4501c`.
   - Page background color: `#eef3f8`.
   - Custom CSS: paste `ghl-custom.css` **after** Part 4 step 1 (id swap).

Upload all 8 files from `assets/` to the media library first.

## Part 2. Layout conventions

- Every section: width **Full width**. Every row: **custom width 1160px** (if only presets exist, use the widest one that is at least 1140px). Row padding is 0 unless stated.
- Column split: drag the divider until the percentages match. If the builder only offers presets, 50/50 is acceptable. Spacing comes from column padding.
- "Mobile" rows below are overrides you set after switching the builder to the mobile device view. GHL stores font size, padding and margin per device. Columns stack automatically on mobile, in left-then-right order.
- Headlines with two lines: type line 1, press **Shift+Enter**, then type line 2. Select line 2 and set text color `#b4501c`.
- Paragraphs with a bold title: type the title, make it **bold**, press **Shift+Enter**, then type the body in regular weight.

---

## Part 3. PAGE 1 "Get a quote" (4 sections, 19 elements)

### Section 1: HERO (1 section, 3 rows, 7 elements)
- Background: image `bg-sky.jpg`, size **cover**, position **center top**, no repeat. Fallback color `#eef3f8`.
- Padding: desktop 28 top, 40 left/right, 72 bottom. Mobile: 20 / 16 / 48.

**Row 1.1 LOGO**: 1 column.
| # | Element | Settings |
|---|---|---|
| 1 | Image | `logo-harlow.png` (464x88), display width **232px**, align left, alt `Harlow Heating & Plumbing`, no link. Mobile width **190px**. |

**Row 1.2 HERO**: margin top 48 (mobile 32). 2 columns: **55% / 45%**.
- Column A (text): padding top **192**, right 56 (optical centre against the form). Mobile: padding 0 all round, bottom 28.

| # | Element | Settings |
|---|---|---|
| 2 | Headline (H1) | Line 1 `Tell us what's broken.` Shift+Enter, line 2 `We'll text your price.` in `#b4501c`. Figtree 600, **64px**, line height 1.04, color `#16202e`, align left. Mobile **40px**. |
| 3 | Paragraph | `AC, heating, water heaters and drains across Fort Worth. Send the form and we text you back in seconds.` Figtree 500, **20px**, line height 1.5, color `#4d596b`, margin top 24, padding right so the line length stays around 500px wide. Mobile 17px, margin top 16. |

- Column B (form panel): background `rgba(255,255,255,0.86)`, border 1px solid `#ffffff`, radius **28**, padding 34 top, 34 left/right, 28 bottom. Mobile padding 24 / 20 / 20, radius 24. The glass, edge light and layered shadow come from CSS (`col-FORMPANEL`).

| # | Element | Settings |
|---|---|---|
| 4 | Form | Embed `Get a Quote (Sample)`, full width. **On submit: go to the next step** (`/check-your-phone`). If the form element only offers "Open URL", use the full published URL of step 2. If the form's own On-submit setting overrides this, set it there to the same step-2 URL. Test once in preview and confirm it lands on step 2. |

Form Builder > Styles (set on the form itself; the funnel reuses it):
- Form background transparent, border 0, padding 0, width 100%.
- Font Figtree. Labels: 14px, 600, `#16202e`, shown above the fields.
- Fields: height 48, background `#ffffff`, border 1px `#d5deea`, radius 12, text 16px `#16202e`, placeholder color `#8792a3`, gap between fields 14.
- Placeholders: First Name `First name`, Phone `(817) 555-0142`, Email `you@example.com`, Service Needed `Choose a service`, ZIP code `76107`.
- Service Needed options, in this order: AC repair, Heating repair, Water heater, Drains and plumbing, New system estimate.
- Submit button: text `Get my quote`, full width, height 56, background `#b4501c`, text `#ffffff` 17px 600, radius 99 (pill), margin top 8.
- Consent text under the button, recommended for A2P/TCPA and shown in the design, 12px `#5f6b7d`, centred: `By sending this you agree to get texts from Harlow Heating & Plumbing about your request. Msg and data rates may apply. Reply STOP to opt out.` It is a Text/HTML item inside the form, not a page element. If whoever owns the form declines it, leave it out.

**Row 1.3 TRUST BAR**: margin top 72 (mobile 28). Row background `rgba(255,255,255,0.70)`, border 1px `#ffffff`, radius **24**, padding 6. 3 equal columns, each with padding 22 top/bottom and 28 left/right (mobile 18 / 20). The hairlines between columns come from CSS (`row-TRUSTBAR`).

| # | Element | Copy (bold title, Shift+Enter, body) | Style |
|---|---|---|---|
| 5 | Paragraph | **Price before we start** / You approve the full price before any work begins. | 15.5px, line height 1.5, `#4d596b`; bold `#16202e` |
| 6 | Paragraph | **Same-day slots** / Pick a time today, or any day that works for you. | same |
| 7 | Paragraph | **Text us anytime** / Questions before or after the visit? Reply to our text. | same |

### Section 2: THREE STEPS (1 section, 2 rows, 7 elements)
- Background: none (page color `#eef3f8` shows through).
- Padding: desktop 104 top, 40 sides, 64 bottom. Mobile 64 / 16 / 56.

**Row 2.1**: 1 column.
| # | Element | Settings |
|---|---|---|
| 8 | Headline (H2) | `Three steps. No phone tag.` Figtree 600, **48px**, line height 1.04, `#16202e`, align left. Mobile **34px**. |

**Row 2.2 STEPS**: margin top 56 (mobile 32). 3 equal columns. Columns 1 and 2 get padding right 48; column 3 gets 0. On mobile each column gets padding bottom 36 (the last one 0) and no right padding.

| # | Element | Settings |
|---|---|---|
| 9 | Image | `step-1.png` (128x128), width **64px**, align left, alt empty |
| 10 | Paragraph | **Tell us what's wrong** / Pick the service, add your ZIP code and send. It takes about 30 seconds. |
| 11 | Image | `step-2.png`, 64px, left |
| 12 | Paragraph | **Get a price by text in minutes** / A real person on our team prices the job and texts it to you. No callback to wait for. |
| 13 | Image | `step-3.png`, 64px, left |
| 14 | Paragraph | **Pick your time** / Reply with the slot that suits you. Your tech texts when they're on the way. |

Step paragraphs: 16.5px, line height 1.55, `#4d596b`, margin top 18, **padding left 8** (lines the text up with the icon tile, which sits 8px inside its PNG). CSS makes the bold title 20px on its own line (`row-STEPS`).

### Section 3: PHONE + CLOSING CTA (1 section, 1 row, 4 elements)
- Background: image `bg-soft.jpg`, **cover**, **center center**. Fallback `#eef3f8`. The image is flat `#eef3f8` at every edge, so there is no seam.
- Padding: desktop 40 top, 40 sides, 64 bottom. Mobile 48 / 16 / 64.

**Row 3.1**: 2 columns **56% / 44%**.
- Column A: padding right 24 (mobile 0, bottom 12).

| # | Element | Settings |
|---|---|---|
| 15 | Image | `phone-thread.png` (1200x1556), width **600px**, centred, alt `Text thread: Harlow confirms the request in seconds, texts a price, and books a 3 to 5 PM visit`. Mobile width **100%**. |

- Column B: padding top **228**, left 16 (mobile 0 all round).

| # | Element | Settings |
|---|---|---|
| 16 | Headline (H2) | `Your phone buzzes before you put it down.` 600, **48px**, line height 1.04, `#16202e`, left. Mobile **32px**. |
| 17 | Paragraph | `The first text lands seconds after you send the form. Your price follows a few minutes later, and you book by replying.` 19px, line height 1.55, `#4d596b`, margin top 20, max about 460px wide. Mobile 17px. |
| 18 | Button | Text `Get my quote`. Figtree 600 18px, text `#ffffff`, background `#b4501c`, radius 99, height 58 (padding about 18 top/bottom and 36 left/right), margin top 36, align left. **Action: Scroll to element / Go to section.** Target the **form** element (#4) if the list offers it, otherwise Row 1.2 or the hero section. Mobile: full width, margin top 28. No icon. |

### Section 4: FOOTER (1 section, 1 row, 1 element)
- Background none. Border top 1px `rgba(150,170,200,0.35)`. Padding 32 top, 40 sides, 40 bottom (mobile 28 / 16 / 32).

| # | Element | Settings |
|---|---|---|
| 19 | Paragraph | Line 1 `Harlow Heating & Plumbing, Fort Worth, TX`, Enter, line 2 `Sample funnel designed by Advero Solutions`. 13.5px, line height 1.7, `#5f6b7d`, centred. No links. |

---

## Part 3b. PAGE 2 "Check your phone" (2 sections, 5 elements)

### Section 1: THANKS
- Background: image `bg-sky.jpg`, cover, center top, fallback `#eef3f8`.
- Padding: desktop 28 top, 40 sides, 112 bottom. Mobile 20 / 16 / 48.

**Row 1.1 LOGO**: 1 column.
| # | Element | Settings |
|---|---|---|
| 1 | Image | `logo-harlow.png`, width 232 (mobile 190), left, alt `Harlow Heating & Plumbing` |

**Row 1.2**: margin top 40 (mobile 32). 2 columns **56% / 44%**.
- Column A: padding top 88, right 48 (mobile 0, bottom 12).

| # | Element | Settings |
|---|---|---|
| 2 | Headline (H1) | Line 1 `Check your phone.` Shift+Enter, line 2 `We just texted you.` in `#b4501c`. 600, **64px** (mobile **40px**), line height 1.04, `#16202e`. |
| 3 | Paragraph | Three lines, each on its own line with a **normal Enter** (not Shift+Enter), so each line becomes its own `<p>` and CSS can number it 01/02/03 with hairlines between:<br>**In a few minutes.** Your price arrives in this same thread.<br>**When it suits you.** Reply with a time and we book the visit.<br>**On the day.** Your tech texts when they're on the way.<br>17px (mobile 16px), line height 1.5, `#4d596b`, bold parts `#16202e`, margin top 40 (mobile 24), max about 540px wide. |

- Column B:

| # | Element | Settings |
|---|---|---|
| 4 | Image | `phone-received.png` (840x1008), width **420px**, centred, alt `Lock screen with a new text from Harlow Heating & Plumbing`. Mobile width **300px**. |

### Section 2: FOOTER
Same as page 1 section 4 (a copy of it is fine).
| # | Element | Settings |
|---|---|---|
| 5 | Paragraph | same two lines, same style |

---

## Part 4. Custom CSS: swap the ids, paste, verify

1. Open `ghl-custom.css` and replace these 4 placeholders with the real ids. Select the item and read its id in the Advanced tab, or inspect the live preview:

| Placeholder | Is |
|---|---|
| `col-FORMPANEL` | page 1, Row 1.2, right column (holds the form) |
| `row-TRUSTBAR` | page 1, Row 1.3 |
| `row-STEPS` | page 1, Row 2.2 |
| `paragraph-NEXTSTEPS` | page 2, element 3 |

2. Paste the same edited file into **both** pages' Custom CSS. Rules for items that are not on a page do nothing.
3. **Verify the CSS on the live preview DOM.** These selectors were written from GHL's usual output and have not been checked against this account:
   - Row and column settings sit on a child `> .inner`. If the background or radius sits on the `#col-...` node itself instead, drop ` > .inner` from those rules.
   - Headline, paragraph, button and form nodes carry id prefixes (`heading-`/`headline-`, `paragraph-`, `button-`, `form-`) or `c-*` classes. The CSS matches either.
   - The form renders inline, not in an iframe. If it is an iframe, the `form` rules do nothing and the Form Builder styles alone carry the look. That is acceptable.
   - Mobile breakpoint is 480px. If GHL stacks columns at a different width, change `@media (max-width:480px)` to match.
   - Page 2 paragraph: if the three lines come out as `<br>` instead of `<p>`, the 01/02/03 numbers will not show. Retype them with plain Enter, or delete the `#paragraph-NEXTSTEPS` rules. The bold leads still read fine without them.
4. Compare the preview against `design-desktop.png` at 1440 wide and `design-mobile.png` at 390 wide. Check the form panel glass edge and shadow, the trust-bar hairlines (vertical on desktop, horizontal on mobile), the step titles on their own line at 20px, the pill buttons with the copper gradient, and the page 2 numbers.

## Part 5. Final checks
- Page 1 has 19 elements and page 2 has 5. Count them before you publish.
- Submitting the form in preview lands on `/check-your-phone`.
- "Get my quote" (#18) scrolls to the form on desktop and on mobile.
- No emoji, no star ratings, no review counts, no licence numbers anywhere.
- The footer line `Sample funnel designed by Advero Solutions` is present on both pages.
