**Update 2026-10-20 (Lorenzo): obsolete for judgement calls; Opus routing is automatic through the harness. Kept as reference.**

# How ask_opus reaches Claude (2026-09-25)

Lorenzo uses Claude Max on this shared computer via Claude Code.
`ask_opus.py` defaults to `claude -p` (transport `claude_code_cli`) when
`ANTHROPIC_API_KEY` is unset. Leave the key unset.

- Login: `claude auth login --claudeai` then hand the desktop for browser sign-in
- Check: `claude auth status` should show `"subscriptionType": "max"`
- Force CLI: `ASK_OPUS_TRANSPORT=cli`
- Force API (not wanted): set `ANTHROPIC_API_KEY` (bills Console separately)

Displayed `cost_usd` in decisions is Anthropic list-price accounting for logs.
It does not mean a separate API invoice while on Max via Claude Code.
