---
name: feedback-push-every-change
description: From 2026-09-23 every change gets committed and pushed to GitHub (private adverosolutions/AdveroSolutions); only refs rooted at the fresh-start commit
metadata:
  node_type: memory
  type: feedback
  originSessionId: 3dc944a4-c8ec-45c0-9c77-dfcacd50c4da
  modified: 2026-09-24T01:25:18.462Z
---

Lorenzo, 2026-09-23: "any changes that we make need to be pushed to the GitHub repo as well, because I will be running out of usage here shortly." This replaces the earlier "no git push" rule for the revenue build.

**Why:** he runs out of usage mid-build and wants every change safe on GitHub so a new chat can pick up. **How to apply:** after each reviewed piece, commit by path and push (section branch, then main). Before any push, `git rev-list --max-parents=0 HEAD` must print only fe95263; never push `--all`, `--mirror`, `--tags` or `archive/*` (see [[committed-live-credentials]]). Pushing is not deploying: live-write rules in [[no-live-changes-until-tested]] still hold. Also split long builds into parallel chats early instead of one marathon session ([[sections-split-2026-09-23]]).

He repeated it later the same day ("pushing everything... extremely frequently... about to hit our usage limits, then I'll move to the cloud"). So don't wait for review to get work onto GitHub: push unreviewed work in progress to the **section branch** as a WIP commit as soon as a worker finishes, and keep `STATUS.md` on the branch current with what is in flight, so a cloud chat can resume. Only reviewed, full-suite-green work goes to `main`. When agents are still editing files in the worktree, snapshot them without touching the worktree: a temporary `GIT_INDEX_FILE`, `git read-tree HEAD`, `git add <paths>`, `git write-tree`, `git commit-tree -p HEAD`, then push that commit to `wip/section-<n>-inprogress` (section 4 did this on 2026-09-23). In zsh write `"${C}:refs/heads/..."`: `"$C:refs/..."` makes zsh apply the `:r` modifier and the push fails with "src refspec ...efs/heads does not match". Keep the hash in a file, because a `commit-tree` commit is unreferenced until pushed.

In a worktree session the live-write guard blocks `git push` (rule c; see [[no-live-changes-until-tested]]). There, commit by path, run the fresh-root check, and hand Lorenzo the exact push command in a bash block.

Squashing WIP onto a main that moved: never `git reset --soft origin/main` (the index keeps the old tree and silently reverts every other section's newer files; happened twice in section 1). Instead: back up the branch, `git reset --hard origin/main`, then `git checkout <backup> -- <only this section's paths>`, check `git diff --stat <backup>` shows only main's new files, and commit by path.
