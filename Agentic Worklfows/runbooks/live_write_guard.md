# Live-write guard (Claude Code hook)

A tripwire that stops Claude from going live **by hand**: setting the gate flags, deploying,
pushing, calling the write endpoints, or editing the files that control all of this. The real
protection is still in the code: `shared.settings.guard_write` (nothing writes unless the process
has `MODE=live` and `ALLOW_LIVE_WRITES=1`), `load_env()` ignoring both flags in any `.env`
file, and the test netguard.

Files: `.claude/hooks/guard_live_writes.py` (the rules), `guard_live_writes.sh` (fail-closed
wrapper), `guard_session_check.sh` (session-start check). Installed by
`changesets/claude_guard/` (see its README). Decision R1(a); findings SAF-1, SAF-3, GOL-15.

## What it blocks (deny, always)

| Rule | Blocks |
|---|---|
| a | Setting `ALLOW_LIVE_WRITES` (any value) or `MODE=live` in any form: a prefix, `export`, `env`, `declare`, `setenv`, `launchctl setenv`, `read`/`printf -v`, `${X:=}`, `os.environ[...]`, `update`, `putenv`, `setdefault`, a subprocess `env=`, inside `bash -c`, `eval`, heredocs and `python3 -c`. Brace words are read the way bash and zsh read them, nested groups and cross products included, and every alternative is checked (`export {ALLOW_LIVE_WRITES=1,MODE=live}`, `ALLOW_LIVE_WRITE{S..S}=1`, a flag behind 300 harmless alternatives). A brace word that stands for more than 256 words is scanned segment by segment and denied as too large to check if any of its words could hold a flag name or a secret path. Also, `echo`/`echo -e`/`printf` output piped or substituted into a shell or Python is decoded first (`\xHH`, octal, `\uHHHH`, `%b`, `%s` pieces, `$'...'`). Also writing shell startup files (`~/.zshrc` and similar). |
| b | Any `modal` / `python3 -m modal` command that is not read-only, and inline Python that imports `modal`. Read-only list: `--version`, `--help`, `app list`, `app logs`, `app history`, `secret list`, `profile current`, `profile list`, `environment list`, `dict list`, `volume list`, `queue list`. |
| c | `git push` in any form (`-C`, `-c alias`, quoted, through `bash -c`, `xargs`, subprocess), and the `gh` CLI's remote writes: `gh api` with a non-GET method or a body (`-f`/`-F`/`--input`), `gh secret`/`gh variable set/delete`, `gh repo sync/create/...`, `gh pr create/merge/...`, `gh release create/upload/...`, `gh workflow run`, `gh auth login/token`. Reads (`gh api` GET, `gh pr list`, `gh secret list`) are fine. |
| d | Writing `.env`, `.env.*`, `.envrc`, anything under `~/.advero/`, any `.claude/settings*.json`, `managed-settings.json`, or anything under `.claude/hooks/`. This covers the Write, Edit, MultiEdit and NotebookEdit tools and Bash (redirects, `tee`, `sed -i`, `cp`/`mv`/`ln`/`rm`, `dd of=`, Python writes). Also blocks a nested `claude --settings` / `--setting-sources`. Template approvals (below) are rule d too. |
| e | Reading `.env*` (except `.env.example`/`.sample`/`.template`), `~/.advero/**`, `credentials.json`, `token.json` and `~/.modal.toml`, through the Read tool, `cat`/`less`/`head`/`tail`/`grep`/`base64`/`xxd`/`strings`/`cp`, `source`/`.`, or `<` input, and git objects that name one (`git show :.env`, `git show HEAD:.env`, `git cat-file -p :.env`). The Grep tool on such a path or with a glob like `.env*` is blocked too. `ls`, `test -f`, `[ -f ]` and `stat` are fine. |
| f | Change-set scripts without their read-only flag (below). Write flags always block, including argparse short forms (`--ap` = `--apply`). |
| g | `launchctl load/bootstrap/kickstart/enable/start/submit` of `com.advero.*` (or a whole folder), installing a crontab, and copying a `com.advero` plist into `~/Library/LaunchAgents`. |
| h | curl/wget/httpie/Python/Node HTTP writes (`-d`, `--data*`, `--json`, `-F`, `-T`, `-X` other than GET/HEAD, `requests.post`, and so on) to `*.instantly.ai`, `*.leadconnectorhq.com`, `*.gohighlevel.com`, `*.modal.com` or `*.modal.run`. A body without `-X` counts as a POST. |
| i | Instantly MCP tools that change anything (reply, pause, activate, update, create/delete, move, interest status, subsequences, blocklist, webhooks, account pause/resume, warmup, bulk add, forward, and more). Tools are identified by name, not server id. A new tool in an Instantly family that is not on the read list is treated as a write. |
| j | `apply_claude_guard.py` without `--dry-run`. |

Change-set flags that are allowed (`--help` is always fine):

| Script | Allowed | Blocked |
|---|---|---|
| `capacity/apply_capacity.py`, `capacity/apply_promotion.py`, `inbox_actions/apply_inbox_actions.py`, `instantly_phase0/apply_instantly_phase0.py` | `--dry-run` | `--apply`, `--restore`, `--yes`, `--accept-interrupted`, `--override-later-changes` |
| `instantly_subsequences/apply_subsequences.py` | `--dry-run` | `--apply`, `--yes` |
| `instantly_webhooks.py` | `--dry-run` | `--apply`, `--rollback`, `--yes` |
| `onboarding/apply.py` | `--dry-run` | `--apply` |
| `deploy/cutover.py` | `--dry-run`, `--status` | `--apply` |
| `deploy/modal_secret.py` | no `--create` (plan only) | `--create` |
| `deploy/budget.py` | `status` | `reset` |
| `schedules/install_schedules.sh` | `--preflight`, with nothing piped in | `--deploy`, any piped or redirected input |
| `schedules/laptop_runner.py` | `--plan`, `--self-test` | running a job |
| `claude_guard/apply_claude_guard.py` | `--dry-run` | `--apply`, `--rollback` |

### Template approvals (rule d)

An approved template sends every cold email of its type on its own, so approvals come only from
Lorenzo, typed in his own terminal (`runbooks/template_approvals.md`). The CLI refuses without a
TTY, but a Claude session can fake one with `script -q /dev/null ...`, so the guard denies, with
the reason "template approvals come only from Lorenzo's own terminal
(runbooks/template_approvals.md)":

| Blocked | Forms |
|---|---|
| Writing `config/approved_templates.json` | Any spelling: absolute, relative, from the repo root or `Agentic Worklfows/`, through `..`, any letter case, through an existing symlink, or a bare `approved_templates.json` after a `cd` the guard cannot follow. Write, Edit, MultiEdit, NotebookEdit. Bash: `>`, `>>`, `>|`, `tee`, `cp`/`mv`/`install`/`rsync` targets, `sed -i`, `perl -pi`, `truncate`, `dd of=`, `ln` (either end), `rm`, `touch`, `sponge`, `json.tool` output, brace forms, and `rm`/`mv`/a recursive copy of the `config/` folder that holds it. `sed` in place (also on settings files and `.env*`): `-i` or BSD's `-I` anywhere in a short-option cluster (`-i ''`, `-i.bak`, `-ni`, `-I ''`, `-I.bak`, `-Ie`, `-nI`, `-EI`, `-I .bak`; `-e`/`-f` take the rest of their word), GNU's `--in-place` or any prefix of it (`--i`, `--in`, `--in-pl`, also `=.bak`), wherever it sits on the line, and the same spellings in a line the guard cannot parse and in code text. Git: on the file itself every subcommand except the reads (`diff`, `log`, `show`, `status`, `add`, ...). On a folder that holds it (`config`, `.`, the project folder, the repo root) only the forms that write working-tree files: `checkout`, `restore` (unless `--staged`/`-S` without `--worktree`/`-W`), `rm` (unless `--cached`), `clean` (unless `-n`/`--dry-run`), `stash`, `mv`, ... Index-only forms pass: `git restore --staged .`, `git reset HEAD -- config` (a reset with paths never touches files), `git rm -r --cached .`, `git clean -n .`. Options are read the way git reads them (`-SW`, `--work`, `--no-staged`, `-sS` as `--source=S`, `-en` as `--exclude=n`); an abbreviated switch (`--stag`), a computed word, an unquoted glob or `xargs`/`find -exec` arguments count as a write. |
| `jobs/approve_templates.py --approve`, `--approve-all-shown`, `--revoke` | These spellings: a path from any folder, `./`, `python3 -m jobs.approve_templates` (also `-mjobs...`, `-I -m`, `-m runpy`), `cd x && ...`, `env`/`sudo`/`nohup`/`timeout`/`uv run` wrappers, `bash -c`, `eval`, heredocs, `find -exec` naming the script, and `script [-q] <file> <cmd...>` (judged as `<cmd...>`; `script -c "<cmd>"` and piped input to a bare `script` are judged as shell). Also `--export` onto the registry, computed arguments (`"$@"`) and `xargs`-fed arguments. |
| Inline code | `python3 -c`, `python3 -`, `/dev/stdin` or `/dev/fd/0` heredocs, `node -e`, `osascript` that name the registry or `APPROVALS_PATH` and write, or call `template_approvals.approve` / `save_approvals` / `revoke` (also through `getattr`). `/dev/fd/0` is read like `/dev/stdin` for every rule, both as a `python3` script and after `source` and `.`. |
| Code that runs the CLI | Its `main`, `runpy.run_path`/`run_module`, `subprocess`, `exec(open(...))` or `os.system` from `python3 -c`, a `python3 -`/`/dev/stdin`/`/dev/fd/0` heredoc, or `python3 - ARGS < jobs/approve_templates.py`: denied when a write flag shows in the code or in the interpreter's trailing arguments (`python3 -c "...main()" --approve x`, which the code gets as `sys.argv`), and when no read mode (`--list`/`--show`/`--export`) is visible in either. Change-sets get the same trailing-argument and `python3 - < script` reading under rule f. |

Allowed: `--list`, `--show`, `--export <other path>`, `--help`; `cat`, `jq`, `grep`, `head`, the
Read and Grep tools on the registry; copying it elsewhere; `git diff`/`add`/`log` on it.

### The terminal MCP

`mcp__terminal__run_in_terminal` types its `command` into a new tab of Lorenzo's own login shell (a
real terminal, outside any sandbox). The guard gives that command exactly the Bash analysis, for every
rule above, so the same line gets the same decision either way. It is judged from the tool's `cwd`
(absolute, `~`, or relative to the session's directory; the session's directory when left out, JSON
null or empty, and null gets exactly the decision a missing `cwd` gets). A `cwd` of any other type
that is not a string (number, list, object, boolean) is denied under `[guard]`. A `cwd` with shell
syntax in it (a glob, `;`, `$`, backticks, a newline, quotes, `~user`)
is judged as the literal folder, from the session's directory and as an unknown directory, and the
stricter decision wins. Reasons read `[x] in a terminal tab: ...`; a template approval deny reads
`[d] template approvals come only from Lorenzo's own terminal (runbooks/template_approvals.md): in a
terminal tab: ...`.
`mcp__terminal__open_terminal_tab` types nothing and gets no decision.

### Shells that read their program from stdin

`bash`, `sh`, `zsh` (and `dash`, `ksh`, ...) run their stdin as the program with no script, with `-s` (the
other words are its `$1 $2 ...`, so `bash -s x` counts), and when the script operand is stdin:
`/dev/stdin` or `/dev/fd/N` however spelled (`/dev/fd/0`, `//dev/stdin`, `/DEV/stdin`, `/dev/fd/00`,
`/dev/fd/3 3<&0`, a heredoc on fd 3, a relative path, an existing symlink), `<(cat)`, or a computed
word. The heredoc, here-string or piped `echo`/`printf` text is then analyzed for every rule, exactly
as for `bash -s`. When a plain shell, `-s` or a stdin script operand is fed text the guard cannot see
(a file, another program's output, a heredoc whose unquoted delimiter lets `$...` expand, or the
keyboard), the line is denied if it names the template approvals (`approved_templates`, `approve_templates`,
`template_approvals`, `APPROVALS_PATH`, also in a variable set earlier on the line), a protected file
(`.claude` settings or hooks, `.env*`, `~/.advero`) or a live gate flag; otherwise it passes.

Anything the guard cannot make sense of is denied: empty, unparseable or unexpected hook input,
an internal error, a command over 200,000 characters, or a run longer than 5 seconds.

## What it asks about (best-effort)

Rule k: Gmail send/reply/forward/trash/delete/spam (drafts are fine), Calendar
create/update/delete/respond, GHL `execute_operation` writes (reads and `dryRun` are fine), and Skool
posts, comments, member approve/reject and raw non-GET requests. Rule h also asks about HTTP writes
to any host other than the revenue systems and loopback. In bypass-permissions mode Claude Code may
not prompt for these, so treat them as unguarded.

## What it leaves alone

Upwork MCP tools get no decision (the application flow has its own permission modes), and neither does
`open_terminal_tab`. Also allowed:
normal `git status/diff/add/commit/log`, `pytest`, every change-set with `--dry-run`,
`grep -rn ALLOW_LIVE_WRITES`, GET requests to Instantly, Write/Edit of normal repo files (test files
that mention the flags included), memory files, `.claude/agents/*.md`, and MCP reads.

## Install, verify, roll back

1. From your own terminal: `python3 changesets/claude_guard/apply_claude_guard.py` (dry-run), read
   the diffs, then `--apply` and type APPLY.
2. Open a fresh Claude Code session from `Coding/`. No line starting `LIVE-WRITE GUARD WARNING`
   should appear. Ask it to run `git push --dry-run`: it must be blocked with a `[c]` reason.
3. Any time: `python3 ../.claude/hooks/guard_live_writes.py --self-test` must end in
   "N/N cases passed".
4. Roll back: `apply_claude_guard.py --rollback <timestamp>` (printed by `--apply`; backups are in
   `AdveroSolutions/.tmp/claude_guard_backup/`).

## Residual risks

- A hook that times out lets the call through (the guard denies itself at 5 s; the hook timeout is 15 s).
- `ask` may not prompt in bypass mode.
- A script file Claude writes and then runs can set the flags or call the APIs from inside it. The
  guard reads command text only. `guard_write`, `load_env` and the netguard cover that case.
- `disableAllHooks` in a project settings file turns every hook off. Claude cannot write one, and
  the session check warns if one exists, but it cannot block.
- Opaque code is not decoded: `base64 -d`, `xxd -r`, `openssl enc -d`, `tr`/`rev`/`sed`/`awk` output, or
  anything computed at run time, piped or `eval`'d into a shell or Python. Only `echo`, `printf` and
  `$'...'` escapes are decoded.
- Brace words: every segment of every comma list and sequence is scanned, whatever the word's size.
  Up to 256 words are expanded and checked one by one. A bigger word is denied ("brace expansion too
  large to check") when any of its words could hold a live flag name, a secret or protected path or
  a glob, or when the working directory is `~/.advero` or a `.claude` folder; otherwise it passes
  (`touch file{1..300}.txt`). Words that bash and zsh expand differently (unmatched braces, a
  `..step`, a non-letter range) are denied on the same text. A big word that reaches a secret only
  through a symlink is not followed. Quoted braces are treated as unquoted, so they can over-block.
- Brace words with `$` in them: `$NAME`, `${...}`, `$(...)` and backticks are kept whole and the
  rest is expanded and scanned as above, so `export {ALLOW_LIVE_WRITES=$X,B=1}` and
  `cat {$D,.env}` are denied. `${VAR:-default}`, `${#arr[@]}` and `"${files[@]}"` are parameter
  expansion, not brace expansion, and pass.
- A brace in the command word: unquoted brace groups are split into words the way the shell does
  before the command is judged, so `{git,push} origin` and `sudo {git,push} origin` are denied as
  `git push`. `{ cmd; }` grouping is unchanged. A command word too big to split is denied, and so is
  a too-big argument on a git, gh, modal, curl, python, shell or wrapper command line.
- A brace in a URL: curl, wget, httpie, xh and nc operands are expanded (curl expands URL braces
  itself, even quoted), and any variant with an Instantly, GHL or Modal host is denied under rule h.
- `gh` subcommands outside the modelled list (extensions, aliases defined earlier) are not judged.
  The repo has no remote, so a push has nowhere to go today.
- `git archive`/`git bundle` of a whole tree, or `git log -p` with no path, can still print a secret
  if one was ever committed. Only operands that name a secret file are caught.
- `grep -r` over a folder that holds a `.env` can print its lines. The Grep tool is in the matcher and
  blocks a secret path or a `.env*` glob; on a plain folder it relies on ripgrep skipping hidden
  and git-ignored files (`.env`, `credentials.json` and `token.json` are ignored here). Glob is not
  in the matcher (the guard has no Glob check, and Glob only lists names).
- Template approvals: the guard reads command text, so arbitrary or obfuscated code cannot be
  caught. A script file Claude writes and then runs, code decoded at run time, an unknown module
  alias, a copy of the CLI under another name, `find -exec python3 {}`, a symlink created in the
  same command as the write, and git commands with no path (`git stash`, `git reset --hard`,
  `git checkout <branch>`) can all still change the registry. The real protection is that approvals live
  in a committed file Lorenzo reviews: check `git diff -- config/approved_templates.json` before
  every commit and treat any approval record he did not make himself as an incident. Every path
  ending in `config/approved_templates.json` is protected, so a test fixture at that path and
  `dd if=` reading it are over-blocked.
- The git folder rule judges each operand from the folder the command runs in. It does not follow
  `git -C <dir>` (`git -C 'Agentic Worklfows' checkout -- config` from the repo root passes) and does
  not read pathspec magic or quoted globs, which git expands itself (`git checkout -- ':/'`,
  `':(glob)**/approved_templates.json'`, `'*approved_templates.json'`, `git restore -- 'config/*'`
  pass). An operand that itself ends in `config/approved_templates.json` is still caught by that
  suffix, under `-C` or `:/` too; a bare `approved_templates.json` under `git -C config` is not. The
  commit review of the registry covers these.
- `sed` in place judges every positional word as a file, because BSD sed (this Mac) reads
  `sed -i '' SCRIPT FILE` with `''` as the suffix while GNU sed reads `''` as the script and every
  later word as a file. A script that reads as a protected path is therefore denied:
  `sed -i '' 's/API_KEY/.env/' README.md` ("sed on a .env file"). Left failing closed on purpose;
  pass the script with `-e` (`sed -i '' -e 's/API_KEY/.env/' README.md` passes).
- `--pathspec-from-file` is not read: git takes those paths from the file, so
  `git checkout --pathspec-from-file=list.txt` passes whatever the list names.
- Git over-blocks, left failing closed: index-only forms that name the registry itself
  (`git restore --staged config/approved_templates.json`, `git reset -- config/approved_templates.json`),
  `git rm -n` on a folder that holds it, an abbreviated switch (`--stag`, `git rm --c`, `git clean --dry`)
  and a `~` inside a word (`git restore -s HEAD~1 -S config`) are denied.
- The keyword check for text the guard cannot see covers a plain shell, `-s` and a stdin script operand,
  not `<(cat)` or a computed operand (their visible text is still analyzed). Process-substitution input
  (`bash < <(...)`) is not analyzed (the keyword check still applies), a group
  `(a; b) | bash /dev/stdin` is read as its last command, `python3` and `source` read `/dev/stdin` and
  `/dev/fd/0` only as spelled, stdin handed on through an outer `bash -c '...'` is not followed into the
  inner command (`bash -c 'bash /dev/stdin' <<< 'git push'`), and `xargs ... bash /dev/stdin` is
  over-blocked (the piped text is an argument there, not the program).
- Claude may edit `template_approvals.py`, `jobs/approve_templates.py` and the send paths that read
  the registry; that is allowed by design. A change there could weaken what an approval means without
  touching the registry, so Lorenzo's commit review must cover those files as well as the registry.
- Known gaps shared by every rule: `find config -delete`, `pathlib.Path.replace` and Node
  `appendFileSync`/`renameSync` (even naming the registry), `python3 -m cProfile`/`trace`/`pdb`
  running a script, `tmux`/`screen`/`expect`/`at`/`launchctl submit` running a command later or
  elsewhere, glob sources copied into `config/`, `ditto` of a folder onto `config`, and
  `tar -C config`.
- The terminal tab runs Lorenzo's interactive login zsh, so his rc files and aliases apply. An alias or
  function from `~/.zshrc` could hide a command name behind a harmless word, and the guard cannot see
  rc files. Only `run_in_terminal` is judged; a terminal-typing tool under another name is not.
- `mcp__ccd_session_mgmt__send_message` and other cross-session messages can ask another session to
  run something. The guard only protects sessions launched where the hook is registered, and judges
  each session's own tool calls.
- Scheduled tasks start new sessions. On this Mac with the user-level hook they are guarded like any
  other session; a remote or cloud session is not.
- Managed settings would be stronger (a project could not disable them). They need admin rights, so
  that is Lorenzo's call.
