# Change-set: the Claude Code live-write guard at user level

Decision R1(a) of the 2026-09-22 re-review (findings SAF-1, SAF-3, the hook half of GOL-15).
Until this is applied, the guard does **not** run in sessions started from `Coding/` or any
other folder, and `.claude/settings.local.json` pre-approves every `curl` and `python3` command.

## What it changes

| File | Change |
|---|---|
| `~/.claude/settings.json` | Adds a PreToolUse hook (`Bash\|Read\|Grep\|Write\|Edit\|MultiEdit\|NotebookEdit\|mcp__.*`, timeout 15 s) that runs `.claude/hooks/guard_live_writes.sh` by absolute path, and a SessionStart check (`startup\|resume\|clear\|compact`). Every other key stays as it is. |
| repo `.claude/settings.local.json` | Removes `Bash(curl:*)` and `Bash(python3:*)` only. |
| repo `.claude/settings.json` | Removes the old project-level guard entry (so it does not run twice). The Stop hook stays. |

Both hook commands check the script file exists first. If the guard script is missing, the
PreToolUse command exits 2, which blocks every tool call, rather than letting calls through.

## How to run it (Lorenzo, from your own terminal)

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/claude_guard/apply_claude_guard.py            # dry-run: read the three diffs
python3 changesets/claude_guard/apply_claude_guard.py --apply    # type APPLY
```

`--apply` refuses unless stdin is a terminal, the hook scripts exist and
`python3 ../.claude/hooks/guard_live_writes.py --self-test` passes. It backs the three files up
to `AdveroSolutions/.tmp/claude_guard_backup/<UTC timestamp>/` and then writes each one
atomically. Running it a second time changes nothing.

Then **open a fresh Claude Code session from `Coding/`** and check that no line starting
`LIVE-WRITE GUARD WARNING` appears at the start. To prove the guard is live, ask that session
to run `git push --dry-run`. It should be blocked with a reason starting `[c]`.

Roll back (same terminal rule):

```bash
python3 changesets/claude_guard/apply_claude_guard.py --rollback <timestamp printed by --apply>
```

Claude cannot run `--apply` or `--rollback`. The guard denies them (rule j), and they refuse
without an interactive terminal anyway.

## Template approvals (rule d)

An approved template will send every cold email of its type without a per-email Approve, so an
approval must only ever come from Lorenzo, typed in his own terminal
(`runbooks/template_approvals.md`). The CLI's TTY check alone is not enough: a Claude session can
fake a terminal with `script -q /dev/null ...`. So the guard denies, with the reason "template
approvals come only from Lorenzo's own terminal (runbooks/template_approvals.md)":

- **Any write to `config/approved_templates.json`**, however the path is spelled: absolute,
  relative, from the repo root or from `Agentic Worklfows/`, through `..`, in any letter case, or
  through a symlink that already exists. This covers Write, Edit, MultiEdit and NotebookEdit, and
  in Bash: redirects (`>`, `>>`, `>|`), `tee`, `cp`/`mv`/`install`/`rsync` targets, `sed -i`,
  `perl -pi`, `truncate`, `dd of=`, `ln` (either end, so no hard link can be made to edit later),
  `rm`, `touch`, `sponge`, `python3 -m json.tool` output, brace forms
  (`config/{approved_templates,x}.json`), and `rm`/`mv`/a recursive copy of the `config/` folder
  that holds it. `sed` counts as in place (the same for settings files and `.env*`) with `-i` or
  BSD's `-I` anywhere in a short-option cluster (`-i ''`, `-i.bak`, `-ni`, `-I ''`, `-I.bak`,
  `-Ie`, `-nI`, `-EI`, and `-I .bak` with the suffix as its own word; `-e` and `-f` take the rest
  of their word, so `-eI...` is a script), with GNU's `--in-place` or any prefix of it GNU accepts
  (`--i`, `--in`, `--in-pl`, also with `=.bak`), and wherever the option sits on the line (GNU
  also reads options after the files). The same spellings are caught in a line the guard cannot
  parse and in code text (`execSync("sed -nI ...")`). Git: on the file itself every subcommand
  except the reads (`diff`, `log`, `show`, `status`, `add`, ...) is denied. On a folder that
  holds it (`config`, `.`, the project folder or the repo root) only the forms that write
  working-tree files are denied: `checkout`,
  `restore` (unless `--staged`/`-S` without `--worktree`/`-W`), `rm` (unless `--cached`), `clean`
  (unless `-n`/`--dry-run`), `stash`, `mv`, ... (`git checkout HEAD~1 -- config`,
  `git restore --source X config`, `git checkout -- .`). Index-only forms pass:
  `git restore --staged .`, `git reset HEAD -- config` (a reset with paths never touches files;
  git refuses `--hard` with paths), `git rm -r --cached .`, `git clean -n .`. Their options are
  read the way git reads them (`-SW`, `--work`, `--no-staged`, `-sS` as `--source=S`, `-en` as
  `--exclude=n`). An abbreviated switch (`--stag`) counts as a write, and so does a line with a
  computed word, an unquoted glob or arguments added by `xargs` or `find -exec`. A bare
  `approved_templates.json` written after a `cd` the guard cannot follow is denied too.
- **`jobs/approve_templates.py` with `--approve`, `--approve-all-shown` or `--revoke`**, in these
  spellings: a path from any folder, `./`,
  `python3 -m jobs.approve_templates` (also `-mjobs...`, `-I -m`, `-m runpy`), `cd x && ...`,
  `env`/`sudo`/`nohup`/`timeout`/`uv run` and other wrappers, `bash -c`, `eval`, heredocs,
  `find -exec` that names the script, and `script`, which is now read explicitly:
  `script [-q] [-F] [-t time] <file> <cmd...>` is judged as `<cmd...>`, util-linux
  `script -c "<cmd>"` as shell, and a bare `script <file>` fed from a pipe or heredoc as shell
  input. `--export` onto the registry itself, computed arguments
  (`"$@"`) and arguments fed through `xargs` are denied as well. `--list`, `--show`, `--export`
  and `--help` pass.
- **Inline Python or other code** (`python3 -c`, `python3 -`, `/dev/stdin` or `/dev/fd/0` heredocs,
  `node -e`, `osascript`) that names the registry (or `APPROVALS_PATH`) and writes, or that calls
  `template_approvals.approve`, `save_approvals` or `revoke` (also `getattr(ta, "approve")`).
  `/dev/fd/0` is read like `/dev/stdin` (the same file on macOS) for every rule, both as a
  `python3` script and after `source` and `.`.
- **Code that runs the CLI** (its `main`, `runpy.run_path`, `runpy.run_module`, `subprocess`,
  `exec(open(...))`, `os.system`) from `python3 -c`, a `python3 -`, `/dev/stdin` or `/dev/fd/0`
  heredoc, or
  `python3 - ARGS < jobs/approve_templates.py`. It is denied when a write flag shows in the code
  or in the interpreter's trailing arguments (which the code receives as `sys.argv`, as in
  `python3 -c "...main()" --approve x`), and also when no read mode (`--list`, `--show`,
  `--export`) is visible in either. Change-sets get the same trailing-argument and
  `python3 - < script` reading under rule f, which also keeps its old rule: the read-only flag
  must be visible in the code itself.

Reading stays allowed: `cat`, `jq`, `grep`, `head` and the Read and Grep tools on the registry, a
copy of it elsewhere, `git diff`/`add`/`log`, and the CLI's read modes.

## The terminal MCP (every rule)

`mcp__terminal__run_in_terminal` types its `command` into a new tab of Lorenzo's own login shell:
a real terminal, outside any sandbox, where the CLI's TTY check passes. The guard gives that
command exactly the Bash analysis, for every rule (a to j, and the h asks), so it denies what
Bash would deny for the same line and nothing more. The command is judged from the tool's `cwd`:
absolute, `~` (Lorenzo's home) or relative to the session's working directory, and the session's
directory when `cwd` is left out, JSON null or empty (null gets exactly the decision a missing
`cwd` gets). A `cwd` of any other type that is not a string (a number, list, object or boolean)
is denied under `[guard]`. A `cwd` with shell syntax in it (a glob,
`;`, `$`, backticks, a newline, quotes, `~user`) is judged three ways, as the literal folder, from
the session's directory, and as an unknown directory (the way Bash is after `cd "$X"`), and the
stricter decision wins, in case the tool ever puts it into shell text unquoted. Reasons read
`[x] in a terminal tab: ...`; a template approval deny reads `[d] template approvals come only
from Lorenzo's own terminal (runbooks/template_approvals.md): in a terminal tab: ...`.
`mcp__terminal__open_terminal_tab` types nothing and gets no decision.

## Shells that read their program from stdin (every rule)

`bash`, `sh`, `zsh` (and `dash`, `ksh`, ...) run their standard input as the program when there
is no script, with `-s` (every other word is then one of its `$1 $2 ...`, so `bash -s x` counts),
and when the script operand is the standard input: `/dev/stdin` or `/dev/fd/N` however spelled
(`/dev/fd/0`, `//dev/stdin`, `/dev/./stdin`, `/DEV/stdin`, `/dev/fd/00`, `/dev/fd/3 3<&0`, a
heredoc on fd 3, a path relative to the working directory, a symlink that already exists),
`<(cat)`, or a computed word that could be one of these. In every one of these the heredoc,
here-string or piped `echo`/`printf` text is analyzed as shell for every rule, exactly as for
`bash -s`, and a `< file` is judged as a change-set run with the program's arguments. When a
plain shell, `-s` or a stdin script operand is fed text the guard cannot see (a file, another
program's output such as `cat script.sh` or `curl`, a heredoc whose unquoted delimiter lets
`$...` expand, or no feed at all, which is the keyboard in a terminal tab), the line is denied
if it names the template approvals (`approved_templates`, `approve_templates`,
`template_approvals`, `APPROVALS_PATH`, also in a variable set earlier on the line), a protected
file (`.claude` settings or hooks, `.env*`, `~/.advero`) or a live gate flag
(`ALLOW_LIVE_WRITES`, `MODE=live`). Without such a word it passes (`cat script.sh | bash`,
`curl -s https://example.com/x.sh | bash /dev/stdin`).

## Residual risks (read before relying on it)

- **A hook that times out lets the call through.** The guard stops itself after 5 seconds and
  denies, well inside the 15 s timeout, but a machine that is frozen solid could still miss it.
- **"Ask" is best-effort.** In bypass-permissions mode, Claude Code may not prompt for an
  `ask`. Only `deny` is guaranteed. Gmail/Calendar/GHL/Skool writes and HTTP writes to other
  hosts are `ask`.
- **It reads command text, not intent.** A script file Claude writes and then runs can set the
  flags or call the APIs from inside. That is what `shared.settings.guard_write`, `load_env`
  ignoring the gate flags in `.env`, and the test netguard are for. Code-level protection is
  still the real one.
- **`"disableAllHooks": true` in any project `.claude/settings*.json` turns the guard off.**
  Claude cannot write one (rule d). If one appears some other way, the session check prints
  the warning line, but it cannot block.
- **Opaque code gets through.** Text decoded at run time (`base64 -d`, `xxd -r`, `openssl enc -d`,
  `tr`/`rev`/`sed`/`awk` output, anything computed) and piped or `eval`'d into a shell or Python
  is not seen. The guard decodes only `echo`/`echo -e`/`printf` escapes and `$'...'`.
- **Brace words.** Comma lists and sequences (`{a,b}`, `{1..20}`, `{a..z}`, nested groups, cross
  products) are read the way bash and zsh read them. Every segment of every group is scanned for a
  live flag name, a secret path and a protected path, however long the word is. A word that stands
  for at most 256 words is expanded in full and every word is checked. A bigger one is denied as
  "brace expansion too large to check" when any of its words could hold a flag name, a secret or
  protected path or a glob, or when the working directory is `~/.advero` or a `.claude` folder.
  A big word with none of those (`touch file{1..300}.txt`) passes. A word the two shells expand
  differently (unmatched braces, a `..step`, a non-letter range such as zsh's `{-../}`) is also
  denied when that text could appear. A word that also holds `$NAME`, `${...}`, `$(...)` or
  backticks is read the same way, with those spans kept whole, because the shells expand braces
  before parameters (`export {ALLOW_LIVE_WRITES=$X,B=1}` and `cat {$D,.env}` are denied, while
  `${VAR:-default}` and `"${files[@]}"` are not brace expansion). An unquoted brace group in the
  command word or in any argument is split into words the way the shell does before the command
  is judged, so `{git,push} origin` and `env {git,push} origin` are judged as `git push origin`.
  A command word too big to split is denied ("brace expansion in the command name is too large to
  check"), and so is a too-big argument on a git, gh, modal, curl, python, shell or wrapper command
  line. URL braces are expanded for curl, wget, httpie, xh and nc (curl expands them itself, even
  quoted), and any variant with an Instantly, GHL or Modal host gets the rule h deny. What is left:
  a big harmless-looking word whose words only reach a secret through a symlink is not followed,
  and quoted braces are still treated like unquoted ones by the file and flag checks, so
  `'{ALLOW_LIVE_WRITES=1,X=1}'` is over-blocked.
- **`gh` is modelled, not complete.** Remote writes (`gh api` POST/PATCH/..., `gh secret set`,
  `gh repo sync`, `gh pr create`, `gh release create`, ...) are denied under rule c. Extensions
  and previously defined aliases are not judged. The repo has no remote today.
- **Whole-tree git reads.** `git show :.env` and `git show HEAD:.env` are denied, but
  `git archive`/`git bundle` or `git log -p` with no path could still print a secret that was
  ever committed.
- **Recursive grep over a folder** (`grep -r KEY .`) can print `.env` lines. The guard blocks
  naming a secret file, not reading a directory that contains one. The Grep tool is in the
  matcher and denies a secret path or a `.env*` glob; on a plain folder it relies on ripgrep
  skipping hidden and git-ignored files. Glob is not in the matcher (no Glob check exists, and
  Glob only lists file names).
- **Template approvals are only as safe as command text allows.** Arbitrary or obfuscated code
  cannot be caught: a script file Claude writes and then runs, code decoded at run time, a module
  alias the heuristics do not know, a copy of the CLI under another name, `find -exec python3 {}`,
  or a symlink created in the same command as the write. Git commands with no path (`git stash`,
  `git reset --hard`, `git checkout <branch>`) can also change the registry. The real protection
  is that approvals live in a committed file that Lorenzo reviews: check
  `git diff -- config/approved_templates.json` before every commit, and treat any approval record
  he did not make himself as an incident. Any path ending in
  `config/approved_templates.json` is protected, so a test fixture at that path is over-blocked,
  and so is `dd if=` reading it.
- **Git pathspecs the folder rule does not follow.** The git folder rule judges each operand from
  the folder the command runs in. It does not follow `git -C <dir>`, so
  `git -C 'Agentic Worklfows' checkout -- config` from the repo root passes. It does not read
  pathspec magic or quoted globs, which git expands itself: `git checkout -- ':/'`,
  `git checkout -- ':(glob)**/approved_templates.json'`,
  `git checkout -- '*approved_templates.json'` and `git restore -- 'config/*'` pass. An operand
  that itself ends in `config/approved_templates.json` is still caught by that suffix
  (`git -C 'Agentic Worklfows' checkout -- config/approved_templates.json`,
  `git restore ':/Agentic Worklfows/config/approved_templates.json'`), but a bare
  `approved_templates.json` under `git -C config` is not. The commit review of the registry is
  what covers these.
- **`--pathspec-from-file` is not read.** Git takes those paths from the file, so neither the file
  rule nor the folder rule sees them: `git checkout --pathspec-from-file=list.txt` passes whatever
  the list names.
- **Git over-blocks, left failing closed.** The file rule denies index-only forms that name the
  registry itself (`git restore --staged config/approved_templates.json`,
  `git reset -- config/approved_templates.json`). `git rm -n` on a folder that holds it is denied
  (only `--cached` is read as index-only). An abbreviated switch (`--stag`, `git rm --c`,
  `git clean --dry`) and a `~` inside a word (`git restore -s HEAD~1 -S config`: zsh's
  extendedglob reads it as a glob operator) count as writes.
- **Shell stdin the guard cannot see.** The keyword check above covers a plain shell, `-s` and a
  stdin script operand; `<(cat)` and a computed operand, which only might be stdin, get their
  visible text analyzed but no keyword check. Text fed by a process substitution
  (`bash < <(...)`, `bash /dev/stdin < <(...)`) is not analyzed (the keyword check still
  applies). A group `(a; b) | bash /dev/stdin` is read as its last command only. `python3` and
  `source` read `/dev/stdin` and `/dev/fd/0` as spelled, not `//dev/stdin`, `/dev/fd/3` or a
  symlink. Stdin handed on through an outer `bash -c '...'` is not followed into the inner
  command, for any interpreter (`bash -c 'bash /dev/stdin' <<< 'git push'`,
  `bash -c 'python3 -' <<< '...'`).
  `xargs` hands piped text to `bash /dev/stdin` as an argument, not as the program, but it is
  still analyzed as the program (an over-block).
- **`sed` in place over-blocks a script that reads as a protected path.** BSD sed (this Mac) reads
  `sed -i '' SCRIPT FILE` with `''` as the backup suffix; GNU sed reads `''` as the script and
  every later word as a file. The guard cannot tell which sed runs, so it judges every positional
  word of an in-place sed as a file, and a script such as `s/API_KEY/.env/` counts as a `.env`
  path: `sed -i '' 's/API_KEY/.env/' README.md` is denied ("sed on a .env file"). This is left
  failing closed on purpose. Pass the script with `-e`, which both seds read as the script:
  `sed -i '' -e 's/API_KEY/.env/' README.md` passes.
- **Claude may still edit the code around the approvals, by design.** `template_approvals.py`,
  `jobs/approve_templates.py` and the send paths that read the registry are normal repo files a
  Claude session is allowed to change. A change there could weaken what an approval means (the
  hash, the kill switch, which ids count) without touching the registry. Lorenzo's commit review
  must cover those files as well as `config/approved_templates.json`.
- **Known gaps shared by every rule, left as residuals:** `find config -delete`,
  `pathlib.Path.replace` and Node `appendFileSync`/`renameSync` (even when they name the
  registry), `python3 -m cProfile`/`trace`/`pdb` running a script, `tmux`/`screen`/`expect`/`at`
  and `launchctl submit` running a command later or elsewhere, glob sources copied into `config/`
  (`cp /tmp/*.json config/`), `ditto` of a folder onto `config`, and `tar -C config` extracting
  over the registry.
- **The terminal tab runs Lorenzo's login zsh, with his rc files and aliases.** The guard reads
  the command line as plain Bash text. An alias or shell function defined in `~/.zshrc` (or any
  file it sources) could hide a command name behind a harmless-looking word, and the guard cannot
  see rc files. Only `mcp__terminal__run_in_terminal` is judged; another MCP server that types
  into a terminal under a different tool name is not.
- **Other sessions.** `mcp__ccd_session_mgmt__send_message` and other cross-session messages can
  ask a different session to run something. The guard only protects sessions launched where the
  hook is registered (user level once this change-set is applied), and it judges each session's
  own tool calls, not the messages that asked for them.
- **Scheduled tasks start new sessions.** A scheduled or cloud task runs in a fresh session, with
  whatever settings its environment has. On this Mac with the user-level hook it is guarded like
  any other session; in a remote environment it is not.
- **Managed settings** (`/Library/Application Support/ClaudeCode/managed-settings.json`) would be
  stronger: a project could not turn them off. They need admin rights, so that is your call.
