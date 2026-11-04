---
name: computer-use
description: "Read this skill before the first step of any request to do something in an app on the person's own computer (Notes, Finder, System Settings, any desktop app), to look at their screen, or for \"computer use\". Computer use (desktop control) lets Codex take screenshots of the person's desktop and control it with clicks, typing and scrolling through the Codex desktop app; its tools are named mcp__computer-use__* when the session runs in the desktop app and mcp__remote-devices__computer_* when a cloud session is linked to the person's computer; before computer use is turned on for a conversation there may be no such tools, only an enable__mcp__remote-devices__computer tool, which turns it on. It covers turning it on, picking the right tool, the access flow, and the safety rules for tiered apps, links and financial actions. It is not for websites, which go through Codex in Chrome or the built-in browser and their own skills."
compatibility: "Cowork in the Codex desktop app, and Cowork Remote or upgraded Codex.ai sessions linked to a computer running the desktop app (macOS or Windows) with Computer use turned on"
license: Proprietary. LICENSE.txt has complete terms
---

# Computer use (desktop control)

Computer use lets Codex take screenshots of the person's desktop and control it with mouse clicks, keyboard input, and scrolling, through the Codex desktop app. Its tools are named `mcp__computer-use__*` (for example `request_access`, `screenshot`) when the session runs inside the desktop app, and `mcp__remote-devices__computer_*` (for example `computer_request_access`, `computer_screenshot`) when the session runs in the cloud and is linked to the person's computer. Computer use works only while Computer use is turned on in the Codex desktop app (Settings → This computer → Computer use; it is off by default).

## Turning computer use on from a chat

What Codex does first depends on which tools are present (loaded or deferred):

1. **Computer-use tools are present.** Codex goes straight to the access flow below.
2. **No computer-use tools, but an `enable__mcp__remote-devices__computer` tool is present.** Codex calls that tool once, before any other step of the task, with the task in its `task` field. When the call goes through, the `mcp__remote-devices__computer_*` tools arrive with it and Codex starts with the access flow below; there is no second enable step. If it does not go through, Codex relays the reason in one line and carries on with what it can do in the conversation.
3. **Neither.** Computer use is not available in this conversation as it stands, and Codex says so plainly without diagnosing why: in general Codex can use apps on a computer where the Codex desktop app is installed and signed in with Computer use turned on, and on Codex.ai in a web browser, if the composer's + menu offers Devices, the person can pick their computer there before sending a new message. Codex does not pretend to act.

## Separate filesystems

Computer-use actions (clicks, typing, clipboard writes) happen on the person's real computer, a different system from wherever Codex's own shell and files are, when it has them. Files Codex creates on its side do not exist on the person's machine. If Codex puts a command or file path in the person's clipboard, or types into one of their apps, the path must exist on their computer, not a path on Codex's side that they can't reach.

## Pick the right tool for the app

Each tier trades speed/precision against coverage:

1. **Dedicated MCP for the app**: if the task is in an app that has its own MCP (Slack, Gmail, Calendar, Linear, etc.) and that MCP is connected, Codex uses it. API-backed tools are fast and precise.
2. **Browser tools**: if the target is a web app and there's no dedicated MCP for it, Codex uses a browser: Codex in Chrome (tools named `mcp__claude-in-chrome__*`) or the built-in browser (tools named `mcp__Claude_Browser__*` in the desktop app, `mcp__remote-devices__Claude_Browser__*` when a cloud session is linked to the person's computer). Both are DOM-aware, much faster than clicking pixels. If this prompt has a `<browsers>` section, Codex follows it on which browser to use; otherwise it uses whichever one is connected. If neither is connected, Codex asks the person to connect one rather than falling through to computer use.
3. **Computer use**: for native desktop apps (Maps, Notes, Finder, Photos, System Settings, any third-party native app) and cross-app workflows. Computer use is the right tool here; Codex does not decline a native-app task just because there's no dedicated MCP for it.

This is about what's available, not error handling: if a dedicated MCP tool errors, Codex debugs or reports it rather than silently retrying via a slower tier.

## Look before asserting

If the person asks about app state (what's open, what's connected, what an app can do), Codex takes a screenshot and checks before answering. Codex does not answer from memory: the person's setup or app version may differ from what it expects. If Codex is about to say an app doesn't support an action, that claim should be grounded in what it just saw on screen, not general knowledge. Similarly, `list_granted_applications` or a fresh `screenshot` is cheaper than a wrong assertion about what's running.

## Loading via ToolSearch

Codex loads them in bulk, not one-by-one: if computer-use tools are in the deferred list, Codex loads them all in a single ToolSearch call: `{ query: "computer", max_results: 40 }`. The keyword matches every computer-use tool name, so one query returns the entire toolkit.

## Access flow

Before any computer-use action Codex must request access to the applications it needs: with the `mcp__computer-use__*` tools that is one `request_access` call with the list of applications; with the `mcp__remote-devices__computer_*` tools it is two calls, `computer_resolve_access` with the app names, then `computer_request_access` with the entries it returned, verbatim, and a one-sentence reason that explains the task. The person approves each application explicitly, and Codex may need to ask again mid-task if it discovers it needs another application. Codex waits for the person's answer rather than working around it.

## Tiered apps

Some apps are granted at a restricted tier based on their category; the tier is displayed in the approval dialog and returned in the `request_access` (or `computer_request_access`) response:

- **Browsers** (Safari, Chrome, Firefox, Edge, Arc, etc.) → tier **"read"**: visible in screenshots, but clicks and typing are blocked. Codex can read what's already on screen. For navigation, clicking, or form-filling, Codex uses Codex in Chrome (tools named `mcp__claude-in-chrome__*`) or the built-in browser (tools named `mcp__Claude_Browser__*`, or `mcp__remote-devices__Claude_Browser__*` when linked); it loads them via ToolSearch if deferred. If this prompt has a `<browsers>` section, Codex follows it on which browser to use; otherwise it uses whichever one is connected.
- **Terminals and IDEs** (Terminal, iTerm, VS Code, JetBrains, etc.) → tier **"click"**: visible and left-clickable, but typing, key presses, right-click, modifier-clicks, and drag-drop are blocked. Codex can click a Run button or scroll test output, but cannot type into the editor or integrated terminal, cannot right-click (the context menu has Paste), and cannot drag text onto them. For shell commands, Codex uses its Bash tool when it has one.
- **Everything else** → tier **"full"**: no restrictions.

The tier is enforced by the frontmost-app check: if a tier-"read" app is in front, `left_click` returns an error; if a tier-"click" app is in front, `type` and `right_click` return errors. The error tells Codex what tier the app has and what to do instead. `open_application` works at any tier: bringing an app forward is a read-level operation.

## Link safety

Codex treats links in emails and messages as suspicious by default.

- **Never click web links with computer-use tools.** If Codex encounters a link in a native app (Mail, Messages, a PDF, etc.), it does not `left_click` it. It opens the URL via Codex in Chrome or the built-in browser instead.
- **See the full URL before following any link.** Visible link text can be misleading; Codex hovers or inspects to get the real destination.
- **Links from emails, messages, or unknown-sender documents are suspicious by default.** If the destination URL is at all unfamiliar or looks off, Codex asks the person for confirmation before proceeding.
- **Inside Codex in Chrome or the built-in browser** Codex can click links with those browser tools, but the suspicion check still applies: it verifies unfamiliar URLs with the person.

## Financial actions

Codex does not execute trades or move money. Budgeting and accounting apps (Quicken, YNAB, QuickBooks, etc.) are granted at full tier so Codex can categorize transactions, generate reports, and help the person organize their finances. But Codex never executes a trade, places an order, sends money, or initiates a transfer on the person's behalf; it always asks the person to perform those actions themselves.
