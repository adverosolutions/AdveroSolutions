# Private assessment - Slack Automation Specialist, Trello and Google Drive Setup

Post: fixed $200, intermediate, client in UAE on Europe/Berlin time. Bids recorded 100 to 250.

## Time

Realistic 4 to 8 hours, call it 6.

- Private Slack channels by team, naming, membership, defaults: 1 to 2 h
- Trello to Slack (card created and card moved, board and list to channel routing): 1 to 2 h
- Google Drive folder watch to Slack (file name, folder, uploader, link): 1 to 2 h
- End to end testing plus the handoff Loom and a short written runbook: 1 to 2 h

Calendar: one week, mostly waiting on their admin access rather than build time.

## Likelihood

High that it works. This is connector plumbing, not engineering, and Lorenzo
builds in Make and n8n daily.

What actually breaks:

- Google Drive folder watch. Drive does not fire a clean "new file in this exact
  folder" event everywhere. Make's Drive watch is per folder and polls, and
  subfolders are not always included. Expect a polling interval, not instant, and
  say so on the call rather than promising real time.
- Slack app install. Posting into private channels needs the app invited to each
  private channel and a Slack workspace owner to approve the install. If the
  client is not the owner, the timeline is theirs, not his.
- Trello. Trello is not in the Make module catalog the way Slack and Sheets are,
  so the demo canvas draws it as a webhook. Production is Trello's own Slack
  power-up plus a webhook for the routing the power-up cannot do. That is an
  honest framing, not a workaround.
- Operations budget. Free Make caps at 1,000 operations a month and polling a
  Drive folder burns them. With several boards and folders this needs a paid
  Make tier or Zapier plan on the client's account.
- Scope creep. "Set up private channels by team" is undefined. Three teams is
  two hours. Twelve teams with member provisioning is a different job.

Unverified for Lorenzo: nothing here is a stretch. He has not asserted a past
Trello build specifically, so the Loom should show a real Make or n8n build of
his with private details blurred and frame this canvas as the one built for them.

## Standard pricing

Market for this scope is $400 to $900 fixed, or $60 to $100/hr for 4 to 8 hours.
The post's $200 is roughly half market. Recurring software the client pays, not
him: Make Core about $9 to $10/mo (or Zapier Starter about $20/mo), Slack and
Google Workspace they already have.

**Say out loud in the Loom, since the post demands it:** $200 to $350 fixed,
"about 6 hours". Quote $200 flat only if he wants the fast yes at the post's own
number and treats it as a door opener into the 27 active contracts; $350 if he
wants the job to pay for itself. Either way the sentence must carry "for the
scope we lock on the call" so the hours number does not become a ceiling on an
open scope.

## Flags

- Proposal must START with the word SLACK, before the greeting.
- Loom max 3 minutes, screen share, must show (1) an automation he built before
  with private details blurred and (2) the fixed price and hour count spoken.
- NDA required. Fine, but it means no public write up of the build afterwards.
- Client record is mixed: 55 contracts, $17.5k spent, 4.5 over 15 reviews, but
  two contracts ended at 1 star in both directions (a scriptwriter and a video
  editing team). Lock scope in writing before any work starts, and use Upwork
  milestones. Do not start on a verbal.
- 27 active contracts means a busy, fast moving client. Good for repeat work,
  bad for slow replies about access.
- They want a call this week. Say a day and a time window in the proposal.

## Ask before quoting

1. How many teams and how many private channels, and do you want members
   provisioned too or just the channels created?
2. How many Trello boards, and which card events matter - created, moved to a
   specific list, due date, comments?
3. Which Drive folders exactly, and do subfolders need to be watched?
4. Who has Google Workspace admin and who is the Slack workspace owner?
5. Do you already own a Zapier or Make plan, or are we starting on free? Free
   Make caps operations and a polled Drive folder eats them.
6. Is near real time acceptable, or do you expect instant on Drive uploads?
