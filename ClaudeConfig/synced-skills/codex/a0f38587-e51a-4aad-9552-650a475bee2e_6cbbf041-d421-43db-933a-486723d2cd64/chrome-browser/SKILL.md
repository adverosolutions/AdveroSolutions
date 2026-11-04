---
name: chrome-browser
description: "Read this skill before the first step that uses Codex in Chrome, the browser extension whose tools are named mcp__claude-in-chrome__* (also called Chrome, the browser extension, or the external browser) and which acts in the person's real Chrome with their own sign-ins; before those tools are turned on there may be a single enable__mcp__claude-in-chrome tool instead. It covers loading the tools in one ToolSearch call, checking the person's open tabs and working in a new tab, site permissions, GIF recordings, console logs, dialogs to avoid, and when to stop and ask. It is not for the built-in browser (mcp__Claude_Browser__* or mcp__remote-devices__Claude_Browser__* tools), which has its own skill, and it does not decide which browser to use."
compatibility: "Codex, Cowork (desktop and remote), and Codex.ai sessions upgraded to Cowork Remote, when the Codex in Chrome extension is connected"
license: Proprietary. LICENSE.txt has complete terms
---

# Codex in Chrome

Codex in Chrome is a browser extension. Its tools, named `mcp__claude-in-chrome__*`, act in the person's real Chrome, in new tabs alongside the person's own, with their existing sign-ins. Codex in Chrome is available only while the person's Chrome is running with the extension connected; if its tool calls report that the extension is not connected or get no response, Codex says so rather than retrying, and follows the session's browser guidance on whether to continue with the other browser or ask first.

If the only Codex in Chrome tool present is `enable__mcp__claude-in-chrome`, Codex calls it first: it turns Codex in Chrome on for this conversation, and the `mcp__claude-in-chrome__*` tools appear once it has run.

## Loading the tools

If the `mcp__claude-in-chrome__*` tools are deferred (meaning they have to be loaded through ToolSearch before use), Codex loads every tool it expects to need in ONE ToolSearch call, because the select query accepts a comma-separated list and each extra ToolSearch call costs a full round trip. The core set to start with:

```
ToolSearch with query "select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__tabs_close_mcp"
```

Codex adds task-specific tools to that same call when the task obviously needs them: `read_console_messages` and `read_network_requests` for debugging, `form_input` for forms, `gif_creator` for recordings, `javascript_tool` for page scripting. A second ToolSearch is only for a tool the task turned out to need later.

## Starting a session: tab context first, then a new tab

At the start of each browser session Codex calls `mcp__claude-in-chrome__tabs_context_mcp` first, to see the person's current tabs and understand what they may want to work with. Then:

1. Codex reuses an existing tab only when the person explicitly asks to work with it.
2. Otherwise Codex opens a new tab with `mcp__claude-in-chrome__tabs_create_mcp` and works there, and, unless the person wants them kept, closes the tabs it created before finishing.
3. Codex never reuses tab IDs remembered from an earlier or different session. If a tool reports that a tab does not exist or is invalid, or the person closes a tab, or a navigation error occurs, Codex calls `tabs_context_mcp` again for fresh tab IDs.

## Site permissions

Codex in Chrome acts on a site only once the person has allowed it; depending on their settings the person may be prompted per site, in the extension or in the app. When a tool call is waiting on or refused that permission, Codex tells the person and waits for them to allow it rather than working around it. A site the person declines is their decision; Codex moves on.

## Recording a GIF

For multi-step interactions the person may want to review or share, Codex can record them with `mcp__claude-in-chrome__gif_creator`. Codex captures a few extra frames before and after each action so playback is smooth, and gives the file a meaningful name (for example "login_process.gif").

## Reading console output

`mcp__claude-in-chrome__read_console_messages` reads the page's console. Console output can be verbose, so when Codex is looking for specific entries it passes the `pattern` parameter (a regular expression), for example pattern "[MyApp]" to keep only the application's own logs.

## Alerts and dialogs

Codex does not trigger JavaScript alerts, confirms, prompts, or other browser modal dialogs through its actions. Those dialogs block all further browser events, so the extension stops receiving commands. Instead:

1. Codex avoids clicking elements likely to raise a confirmation dialog (for example a "Delete" button) unless necessary.
2. If it must interact with such an element, Codex warns the person first that this may interrupt the session.
3. Codex can use `mcp__claude-in-chrome__javascript_tool` to check for and dismiss an existing dialog before proceeding, and prefers `console.log` plus `read_console_messages` over `alert` for debugging.

If a dialog does get triggered and the browser stops responding, Codex tells the person they need to dismiss it manually in Chrome.

## Staying on task, and when to stop

Codex stays focused on the specific task and does not wander into unrelated pages. Codex stops and asks the person how to proceed, explaining what it tried and what went wrong, when any of these happen:

- browser tool calls fail or return errors after 2 or 3 attempts
- the extension gives no response
- page elements do not respond to clicks or input, or pages do not load or time out
- the task turns out to involve unexpected complexity or tangents
- several approaches have not completed the task

Codex does not keep retrying the same failing action.
