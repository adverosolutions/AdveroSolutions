
## Delegation (main session only)
If you are running as a subagent, ignore this entire section and follow only your own agent instructions.

### Roles
- Main session = orchestrator. Plans, splits work, briefs agents, reads reports, decides. On multi-step builds it does not do the implementation itself.
- scout (low effort): read-only context gathering. Use it instead of reading many files yourself or using the built-in Explore agent.
- worker (medium): default for small, clearly scoped implementation pieces.
- worker-heavy (high): multi-file or tricky pieces, debugging, and fixing anything the reviewer rejected.
- reviewer (xhigh): reviews every implementation result before it's accepted.
- reviewer-max (max): replaces reviewer ONLY for high-stakes changes (infrastructure, deployments, auth/security, payments, migrations, client production systems, data deletion, anything hard to undo).

### When to act directly (no agents)
Questions, explanations, small or single-file edits, config tweaks, and anything finishable in a few steps. Don't spin up agents for these.

### Build loop (multi-step builds)
1. If context is missing, send scout first.
2. Plan and split the work into pieces, each with a clear spec: goal, files in scope, acceptance criteria.
3. Send each piece to worker (small, clear) or worker-heavy (multi-file, tricky). Run independent pieces in parallel; keep dependent pieces in order.
4. Send each result plus the ORIGINAL spec to reviewer, or reviewer-max if high-stakes.
5. On REJECT, send the defect list to worker-heavy (even if a worker did the original), then review again.
6. Accept a piece only on APPROVE.

### Lanes (who backs off)
- Scouts read, workers build, reviewers judge. No agent does another's job.
- Only the main session delegates. Subagents never start other agents or workflows.
- The main session does not approve work itself. Every implementation result goes through reviewer or reviewer-max.
- Pass each agent only the context its piece needs.

### Escalation and limits
- If a piece fails review twice after worker-heavy, stop and tell me what's failing. I decide whether to switch effort to max. Never use max effort on your own except through reviewer-max for high-stakes changes.
- Workflows/ultracode: never start one unless I type "ultracode" or ask for a workflow.

## Writing (every session and every agent)
No Claudeisms in any copy you write for me or my clients (emails, Upwork proposals and messages, LinkedIn, DMs, and prompts that generate copy): never add a sentence or tacked-on clause that restates, sums up or sells the point you just made ("Nobody in the office has to remember to ask.", "No more chasing leads.", "That's the whole point.", "...which means you never lose a lead"). Say the thing and stop. Test: delete the line; if the reader loses no fact, question or next step, it goes. Details in the `claudeisms` skill. If a job looks too big for a handful of agents (codebase-wide audit, large migration, many-file refactor), suggest a workflow and wait for my go-ahead, recommending a small test slice first.
