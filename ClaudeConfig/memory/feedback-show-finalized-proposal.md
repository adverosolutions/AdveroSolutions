---
name: feedback-show-finalized-proposal
description: After finalize, show the full proposal in chat for Lorenzo to copy himself; never put it on his clipboard (use --no-copy)
metadata:
  type: feedback
---

After `upwork_gen.finalize`, show the full proposal in chat in a fenced block with the job link, and let Lorenzo copy it himself. Never put it on his clipboard: always pass `--no-copy` and never run `pbcopy` on a proposal.

**Why:** Lorenzo (2026-09-28): "I don't want you to put it on my thing. I want you to show me and let me copy it because then I can read through it and make any quick changes."

**How to apply:** finalize with `--no-copy`, `cat proposal.md` into a code block in the reply, then flag any unconfirmed lines. Related: [[feedback-show-copy-in-question]], [[upwork-visual-walkthrough-lane]].

**Every change, whole proposal (2026-09-30):** after any edit, even a one-line one like adding the client's name, show the entire proposal again, never just the changed line. He: "remember to send me the whole thing every time."
