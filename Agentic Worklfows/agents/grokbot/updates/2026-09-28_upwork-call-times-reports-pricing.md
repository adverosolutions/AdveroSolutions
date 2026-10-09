# Grok update, 2026-09-28: Upwork call times, follow-ups, reports, pricing

This is an update to what you already have, not a new onboarding. Apply the edits in part 2 to your copies in `~/advero/`, then confirm to Lorenzo with the list of files you changed.

## 1. What changed

- **Upwork call times.** When a client in an Upwork room is ready for a call, the draft now offers three times instead of two. They are stated in the client's time zone with a label ("Thursday at 1pm ET"), all inside noon to 6pm CT, Monday to Friday, at least 4 hours out and no more than 5 business days out. The first can be today. The draft adds one line offering to work around their schedule, such as "If none of those work, send me a couple of times that work for you." Lorenzo checks the times against his calendar and sends it himself. Upwork drafts arrive with the times already written: pass them on exactly as written.
- **Email call times are unchanged:** two times, 12:00 to 18:00 CT, from free_times. The email rule no longer applies to Upwork cases.
- **New Upwork follow-up option, the build update.** Any of T2 to T5 can be "added X to your build since you run Z". It is always flagged NEEDS_YOU, because Lorenzo has to add X to the build before it goes out. List the change he has to make on the `NEEDS_YOU` line of that touch's `UPWORK DRAFT` card.
- **New Upwork numbers in reports:** calls booked, close rate (hires / calls booked), return on connects (Upwork earnings / dollars spent on connects) and median job age at apply. The KPI dashboard is now 15 rows. Upwork view rate and median job age at apply read `no data` until the daily metrics job computes them. Report `no data` as it is, never 0.
- **Upwork pricing for pre-call briefs.** A new section in `sales-call` tells Opus how to size an Upwork job for Lorenzo's call prep. Prices still never go in a proposal or an Upwork chat.
- **Upwork proposal opener.** Lorenzo's proposals now open "Hey [greeting] 👋 I went ahead and built your [tools from the post] [system], [N]-min Loom:". You don't write proposals; this is context only.

## 2. Edits to your copies

### `~/advero/ask_opus.py`

In `DECISION_RULES`, replace the whole line that starts `6. Emails go out 07:00 to 19:00 CT only.` with:

```
6. Emails go out 07:00 to 19:00 CT only. Follow-up touches go at 10:00 CT on business days. Email call times: 12:00 to 18:00 CT, Monday to Friday, at least 4 hours from now, within 5 business days, only from context.free_times, never a time in context.offered_times (offered to this lead or any other lead). With fewer than two usable times, follow the skill's no-free-times rule. Upwork call times follow upwork-followups: three times stated in the client's time zone, all inside 12:00 to 18:00 CT, Monday to Friday, at least 4 hours from now, no more than 5 business days out, plus one line offering to work around their schedule. Use context.free_times when it is there; an Upwork case does not need it. Lorenzo checks the times against his calendar before he sends.
```

### `~/advero/skills/upwork-followups.md`

a) Right after the T7 row of the touch table (`| T7 | 30 | a graceful close ...`) and its blank line, add the block below, then one blank line, so the block sits between two blank lines and `- **Check-in**` follows after the second one:

```
- **Build update** (an option for any of T2 to T5): "added X to your build
  since you run Z", with a screenshot or a short Loom. X and Z come only from
  their post or the room. The draft may propose X, but it is flagged
  NEEDS_YOU, because Lorenzo has to add X to the build before it can be
  sent. Never claim a change that wasn't made.
```

b) Replace the `- Calls:` bullet (it ends "Lorenzo checks them against his calendar before sending.") with:

```
- Calls: offer a short Upwork call only when the client is engaged, has asked
  about scope, fit or timeline, or the thread has momentum. Offer three times,
  in words. The first can be today when it is at least 4 hours out. All
  three sit inside Lorenzo's window: noon to 6pm CT, Monday to Friday, no
  more than 5 business days out. State them in the client's time zone with
  its label ("Thursday at 1pm ET"; label with ET, CT, MT or PT, or the
  client's local zone name for non-US clients). Take the time zone from the client's
  location in the room or the proposal data; when it's unknown, use CT. Add
  one line offering to work around their schedule if none of the three fit
  ("If none of those work, send me a couple of times that work for you.").
  Lorenzo checks the times against his calendar before sending.
```

c) Replace `- **NEEDS_YOU** (replies only): each fact he has to fill in or decide.` with:

```
- **NEEDS_YOU** (replies and build-update touches): each fact he has to
  fill in or decide, or the change he has to make to the build first.
```

### `~/advero/skills/grok-operator.md`

In "Sending rules", replace the line that starts `- Offer call slots 12:00` with these two lines:

```
- Email call slots: offer 12:00–18:00 CT, Monday to Friday, at least 4 hours out and no more than 5 business days out. Never offer the same slot twice.
- Upwork call times follow `upwork-followups` (three times, in the client's time zone). Lorenzo sends every Upwork message himself.
```

### `~/advero/skills/lorenzo-voice.md`

a) Under "How he asks for a call", right after the bullet that ends "The lead picks one and Lorenzo sends the invite.", add:

```
- Upwork chats: three specific times, stated in the client's time zone with
  its label ("Thursday at 1pm ET"; label with ET, CT, MT or PT, or the
  client's local zone name for non-US clients), plus one line offering to
  work around their schedule. Full rule in `upwork-followups`.
```

b) Replace item 9 (the "Hey there 👋 I build [their kind of system] like this all the time" hook) with:

```
9. "Hey [greeting] 👋 I went ahead and built your [2-3 tool names from the
   post] [their kind of system], [N]-min Loom:" (Upwork Template A preview
   hook, locked 2026-09-28.) Built-for-you beat in their own tools, nothing
   about other companies. The previous hook, locked 2026-09-03, was "Hey
   there 👋 I build [their kind of system] like this all the time, so I went
   ahead and built this one custom for you, [N]-min Loom:".
```

### `~/advero/skills/daily-reports-and-metrics.md`

a) In the description line and the heading `## KPI dashboard (13 rows)`, change `13` to `15`.

b) In rule 10 ("Lower is better"), insert `, job age at apply` right after `time` on the second line of the rule and keep the line break where it is. These two lines:

```
10. **Lower is better** for bounce rate, time to first reply, Upwork response
    time and cost per verified lead. Write thresholds with the direction
```

become:

```
10. **Lower is better** for bounce rate, time to first reply, Upwork response
    time, job age at apply and cost per verified lead. Write thresholds with the direction
```

c) Right after the Daily Log row that starts `| Upwork Proposals, Connects Spent,`, add:

```
| Upwork Calls Booked, Upwork Close Rate, Upwork Return on Connects, Median Job Age at Apply | flow / rate | `Coding/upwork-pipeline/proposals.csv` (columns `viewed, replied, interviewed, hired, connects, boosted, age_hours_at_apply`). Calls booked = proposals whose `interviewed` is set. Close rate = hired / calls booked. Return on connects = Upwork earnings from Upwork financials / connects $. Median job age at apply = median of `age_hours_at_apply`. No Daily Log column yet |
```

d) In the KPI table, add this row right before `| Upwork reply rate |`:

```
| Upwork view rate | >= 25% | not set | 7 days | Upwork handoff (`proposals.csv` `viewed` gives the per-proposal breakdown); not yet computed by the daily metrics job: reads `no data` |
```

and this row right after the `| Upwork reply rate |` row, so the three rows read view rate, reply rate, median job age:

```
| Median job age at apply | <= 2 h | > 12 h | 7 days | `proposals.csv` (`age_hours_at_apply`); not yet computed by the daily metrics job: reads `no data` |
```

### `~/advero/skills/sales-call.md`

Right before the heading `## Proof to cite`, add the block below, then one blank line, so a blank line separates the block's last bullet from `## Proof to cite`:

```
## Upwork jobs (separate from the six offers)
offers.md does not cover Upwork. For a call that came from an Upwork proposal, Opus's pre-call brief uses these rules instead of the offer table:
- Price from value. Turn the hours the build saves into dollars first (hours saved a year times the client's hourly cost), then suggest 10 to 20% of that yearly dollar value or of the yearly revenue the build adds.
- Land a small first milestone, then upsell the larger build.
- Split larger work into 3 to 4 milestones, each paid "once [deliverables] are delivered and you've signed off".
- Lorenzo sets the final price himself on the call. Prices never go in a proposal or an Upwork chat.
- While his Upwork profile has no reviews, a smaller first project that earns a review is worth taking.
```

## 3. Nothing else changes

Your role, access, sending rules for email, the approved copy doc and the "never send an Upwork message" rule stay exactly as they are.
