# Deliverable: the sequences

Three emails per contact, written in the **client's** voice, to the client's own former customers.

**The single most important thing on this page.** These emails are not Advero selling. They are the client writing to someone who already bought from them. So the proof lines and the guarantee in `config/offers.md` do **not** belong here: those are for Advero's outbound, where Lorenzo is the sender. Putting "I recovered about $6M for a commercial roofer" into a cleaning company's note to a former customer is the fastest way to make a warm list feel cold.

Placeholders come from the import: `{first_name}`, `{company}`, `{last_job}`, `{last_job_date}`, `{owner_name}`, `{client_business}`, `{owner_phone}`.

## Timing

Not a generic drip. Timed to the moment the client's buyer actually has the problem.

| Vertical | Email 1 | Email 2 | Email 3 | Hook |
| --- | --- | --- | --- | --- |
| Commercial cleaning | day 0 | day 10 | day 20 | Contract renewal and budget season, a second location, a property manager change |
| Bookkeeping and tax | day 0 | day 7 | day 16 | January, the quarterly estimate deadlines, year-end cleanup |
| Recruiting | day 0 | day 7 | day 16 | Their hiring wave, the role they filled badly last time |

The live campaign gaps are recorded in `config/ids.json` under `instantly.campaigns` (`email_gap` 7 or 10). Match the client's, do not invent one.

## Email 1: the one that does the work

```
Subject: {last_job} back in {last_job_year}

Hi {first_name},

We did the {last_job} for you back in {last_job_date}. I was going back
through the books and realised we never picked things up again.

Nothing to sell here. I wanted to ask whether {company} still handles that
the same way, or whether it moved to someone else.

If it moved, no hard feelings, I would just rather know. If it did not, I can
tell you in two minutes what it would cost now.

{owner_name}
{client_business}
{owner_phone}
```

## Email 2: the specific reason to talk now

```
Subject: {hook}

Hi {first_name},

Following up on my note. The reason I am asking now is {hook_sentence}.

Two ways to do this. Either I send you a number for what you had before, or
we spend fifteen minutes on what has changed at {company} since and I price
that instead.

Which is more useful.

{owner_name}
```

## Email 3: the close-the-file note

```
Subject: Closing this out

Hi {first_name},

Last one from me. I will assume {company} is covered and stop taking up your
inbox.

If it changes, or if you want a number to hold against what you are paying
now, reply any time and I will pull your old file.

Thanks for the work back then either way.

{owner_name}
```

## Rules the copy obeys

1. The client's signature, the client's phone, the client's trade words.
2. No em dashes, no exclamation marks.
3. Nothing from the do-not-say list, which is pasted into the prompt for every draft.
4. Email 3 actually stops. A fourth email to a former customer costs the relationship, not just the reply.
5. Any reply containing stop, remove or unsubscribe ends the sequence and sets DND the same day.
6. One offer per contact. A former customer who gets two different pitches from the same business reads it as a mailing list.
