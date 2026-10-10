---
name: advero-website
description: "Advero Solutions website (Website/): design approved, AI-agents positioning, LIVE on adverosolutions.com via Vercel since 2026-09-30; DNS at Namecheap; redeploy + rollback steps"
metadata:
  node_type: memory
  type: project
  originSessionId: d85ce730-9f79-4487-bb04-71786c0bfd1c
  modified: 2026-09-30T20:02:34.834Z
---

The Advero Solutions website lives in `Website/` (static HTML; styles only from `Brand/tokens/brand.css`, logos from `Brand/logo/svg/`, `build.sh` makes `dist/`).

Lorenzo on the design (2026-09-30): "absolutely beautiful and perfect". Keep the look: sky background, glass panels and the live inbox → calendar hero mockup.

Positioning (2026-09-30): Advero is in a "spray and taste test" phase and works with all industries (3 niches growing to about 12-15). The site is "a one-stop shop for AI agents", not niche pages, and must not read as "we specialize in everything". The framing is to specialize in how a business sells, with proof from past builds. It sells six agent cards: reply and booking, lead research, follow-up and win-back, receptionist (text and chat, no voice), ops, and custom. The guarantee copy is generic: "a written guarantee for your market".

**Hosting (live since 2026-09-30, about 20:02 UTC):**
- Vercel project `adverosolutions` in team `lorenzo-villarreals-projects` (Vercel CLI login `adverosolutions-7119`). It serves https://adverosolutions.com, and www returns a 308 redirect to the apex. Let's Encrypt certificates are auto-renewed by Vercel.
- DNS is at Namecheap Advanced DNS (account "AdveroAdvertising"): A `@` 76.76.21.21 (TTL 5 min) and CNAME `www` cname.vercel-dns.com. (TTL 5 min). Two `_vercel` TXT verification records must be kept. The `_acme-challenge` and `_acme-challenge.www` TXT records can be deleted.
- Don't touch: MX `smtp.google.com` (Custom MX), TXT google-site-verification, `_dmarc`, `default._domainkey` (DKIM), and A `view` 76.76.21.21 (another Vercel team, unused 404).
- **Redeploy:** run `Website/build.sh`, copy `dist/` without `CNAME` into a folder linked to the project (`.vercel/project.json`), then `npx vercel deploy --prod --yes`.
- **Rollback to the old site:** set A `@` to 75.2.60.5 and CNAME `www` to heartfelt-wisp-c86f5b.netlify.app. This only works while the old Netlify certificate is valid (to Dec 27 2026).
- The old site ("AI-Powered Lead Automation", a Vite app with Supabase and Calendly) is Netlify `heartfelt-wisp-c86f5b` in an unknown Netlify account (not lorenzovillarreal@adverosolutions.com). Netlify won't release the domain without support.
- A spare Netlify site `adverosolutions` (adverosolutions.netlify.app) exists in his Netlify team from the first attempt and is unused.
- Open items: Vercel Hobby terms bar commercial use (Pro is needed for a business site); the apex has no SPF record.
- Chrome-extension quirk: closing a tab can dissolve the MCP tab group. Don't close tabs mid-task.

**Why:** hosting moved off Netlify because the domain was locked to that unknown account.

**How to apply:** redeploy to Vercel for any site change, and never touch the email records above.

Related: [[advero-brand-2026]], [[ops-agent-demo]], [[lorenzo-case-studies]].
