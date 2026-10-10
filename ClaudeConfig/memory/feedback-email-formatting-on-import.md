---
name: feedback-email-formatting-on-import
description: "When pushing email copy into Instantly, formatting (line breaks, blank lines, sign-off lines) must survive exactly; Lorenzo says Claude tends to lose it on import"
metadata:
  node_type: memory
  type: feedback
  originSessionId: a91002dd-9f2a-48b8-ba2d-00e8d95c3d7d
  modified: 2026-09-28T02:14:44.512Z
---

When importing or pushing emails into Instantly (new campaigns, variants, PATCHes), keep his formatting exactly: one `<div>` per line, one `<div><br /></div>` per blank line, "Thanks," and "Lorenzo" on consecutive lines, step-2 bullets directly under "Quick version:". Read back after the write and compare byte for byte, then show him the raw HTML in the dry-run.

**Why:** Lorenzo, 2026-09-27: "make sure to not lose formatting you tend to lose it when you import emails." Earlier plain-text PATCHes left three bodies empty (see [[instantly-2026-campaigns]]).

**How to apply:** every change-set that writes copy gets a structural check (the line and blank-line pattern equals the source text) plus a read-back verify. Also: when he says "identical email, just replace the offer", keep every other line of his template verbatim, and make the "I build X" line, the proof and the guarantee all match the new offer.
