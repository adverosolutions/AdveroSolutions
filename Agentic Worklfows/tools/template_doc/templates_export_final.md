# Cold-email templates for approval

Generated 2026-09-23T17:34:58+00:00.

Approving a template means every email of that type sends automatically, without a per-email Approve, for as long as its text stays exactly as shown here. The safety checks stay on for every send: the send window, the slot rules, the offers.md copy gate, the recipient check and the kill switch. If the wording changes in code or in a prompt file, the template drops back to "changed_since_approval" and goes back to a card until it is approved again.

Each block shows the main template and then every variant the same email can go out as: missing lead data, no free slot, another timezone, the fallback subject. Approving an id approves all of the text in its block. Placeholders like `{first_name}` are filled per lead. Only templates with an approve marker can be approved; reference pieces and unextractable entries are listed for context.

Every template with a time or slot in it ends with a value_formats block: how the engine writes those times, rendered by its own code at fixed example times. It is the same block each time, and it is part of what you approve, so a change to how times are written sends every one of those templates back for approval.

To approve everything in this file exactly as shown, from your own terminal (refused if any text was edited in this file or changed in the code since export):

    python3 jobs/approve_templates.py --approve-all-shown <this file>

Kill switch: off.

## Counts

- first_reply: 36
- cadence: 10
- cadence_fragment: 14
- booking: 13
- show_rate: 21
- no_show: 15
- first_reply_piece: 48
- total: 157
- approvable: 108

## First reply to an interested lead (full body per offer and question type)

### `first_reply.cleaning_reactivation.pricing.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `86fd91b8e6d34a67b7292fe0a2c2755094650e8422027c662608ba605e2370b0`

<!-- approve-template id=first_reply.cleaning_reactivation.pricing.full sha256=86fd91b8e6d34a67b7292fe0a2c2755094650e8422027c662608ba605e2370b0 -->

```text
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_reactivation.send_info.full`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `03b13af373e9eba9bda7d0d293f967fdb79d93300fd52f9282f4e62b7d679b4e`

<!-- approve-template id=first_reply.cleaning_reactivation.send_info.full sha256=03b13af373e9eba9bda7d0d293f967fdb79d93300fd52f9282f4e62b7d679b4e -->

```text
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for your business.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_reactivation.mechanism.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `8b6482e1dae0b88fc5304cf6b6a734d2357aa3a1970f158fcc37ab862180657f`

<!-- approve-template id=first_reply.cleaning_reactivation.mechanism.full sha256=8b6482e1dae0b88fc5304cf6b6a734d2357aa3a1970f158fcc37ab862180657f -->

```text
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_reactivation.other.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval. Also used for every neutral_question that is not pricing, send_info or mechanism.
- sha256: `7bdddcc774cfb23cb72955ccd4f6b95cae94ed9c1b4827b5d8aca88e1e68efe0`

<!-- approve-template id=first_reply.cleaning_reactivation.other.full sha256=7bdddcc774cfb23cb72955ccd4f6b95cae94ed9c1b4827b5d8aca88e1e68efe0 -->

```text
Hey {first_name},

Good question. The short version is that I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Good question. The short version is that I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Good question. The short version is that I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. The rest is easier to cover on a quick call.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Good question. The short version is that I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. The rest is easier to cover on a quick call.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Good question. The short version is that I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. The rest is easier to cover on a quick call.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_reactivation.referral.full`

- status: unapproved
- variables: `{first_name}`, `{referral_name}`, `{referral_first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8`

<!-- approve-template id=first_reply.cleaning_reactivation.referral.full sha256=5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8 -->

```text
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {slots} work for {referral_first_name}? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Appreciate you pointing me to the right person. Would you mind looping them in on this thread so I can send the details over?

Would {slots} work for them? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {referral_first_name} have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

{slot} CT works on my end. Once {referral_first_name} is on the thread, I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_reactivation.default.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `ef7bad495660c7e7aa8fa91526c86ceffd258e082fd246e54cf20af5aff5a661`

<!-- approve-template id=first_reply.cleaning_reactivation.default.full sha256=ef7bad495660c7e7aa8fa91526c86ceffd258e082fd246e54cf20af5aff5a661 -->

```text
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Glad to hear it. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.pricing.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `3384db0a14cecc47917681fddf7e7249fea8ca1c05bf1220cb59a0e1d8f11e20`

<!-- approve-template id=first_reply.bookkeeping_reactivation.pricing.full sha256=3384db0a14cecc47917681fddf7e7249fea8ca1c05bf1220cb59a0e1d8f11e20 -->

```text
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.send_info.full`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `9725e0c571f556cd9df009e6b6fd6d71b7e760d6d5288a5d9975183aebf15ab2`

<!-- approve-template id=first_reply.bookkeeping_reactivation.send_info.full sha256=9725e0c571f556cd9df009e6b6fd6d71b7e760d6d5288a5d9975183aebf15ab2 -->

```text
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for your business.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.mechanism.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `beef59f962de3484644183441b3c75ae068bf0fbf8adfca24d2f354bbeadcd48`

<!-- approve-template id=first_reply.bookkeeping_reactivation.mechanism.full sha256=beef59f962de3484644183441b3c75ae068bf0fbf8adfca24d2f354bbeadcd48 -->

```text
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. All I need to start is a list of 60 or more former clients or lost inquiries.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. All I need to start is a list of 60 or more former clients or lost inquiries.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. All I need to start is a list of 60 or more former clients or lost inquiries.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. All I need to start is a list of 60 or more former clients or lost inquiries.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. All I need to start is a list of 60 or more former clients or lost inquiries.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.other.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval. Also used for every neutral_question that is not pricing, send_info or mechanism.
- sha256: `42529618cbd8003d048561f66034f2a05ffb296670a83845cb2ff38adf8e8d1b`

<!-- approve-template id=first_reply.bookkeeping_reactivation.other.full sha256=42529618cbd8003d048561f66034f2a05ffb296670a83845cb2ff38adf8e8d1b -->

```text
Hey {first_name},

Good question. The short version is that I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Good question. The short version is that I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Good question. The short version is that I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. The rest is easier to cover on a quick call.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Good question. The short version is that I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. The rest is easier to cover on a quick call.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Good question. The short version is that I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. The rest is easier to cover on a quick call.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.referral.full`

- status: unapproved
- variables: `{first_name}`, `{referral_name}`, `{referral_first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8`

<!-- approve-template id=first_reply.bookkeeping_reactivation.referral.full sha256=5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8 -->

```text
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {slots} work for {referral_first_name}? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Appreciate you pointing me to the right person. Would you mind looping them in on this thread so I can send the details over?

Would {slots} work for them? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {referral_first_name} have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

{slot} CT works on my end. Once {referral_first_name} is on the thread, I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.default.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `686a06381d7696642bb2188a25ed721c71ebd65a09e694204b5226a8bc80f2d5`

<!-- approve-template id=first_reply.bookkeeping_reactivation.default.full sha256=686a06381d7696642bb2188a25ed721c71ebd65a09e694204b5226a8bc80f2d5 -->

```text
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more former clients or lost inquiries.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Glad to hear it. All I need to start is a list of 60 or more former clients or lost inquiries.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more former clients or lost inquiries.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more former clients or lost inquiries.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more former clients or lost inquiries.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.pricing.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `2040d4b9ca979eee42c92f43f1f07defb22a76538197221a82b542e2f5697ee0`

<!-- approve-template id=first_reply.recruiting_reactivation.pricing.full sha256=2040d4b9ca979eee42c92f43f1f07defb22a76538197221a82b542e2f5697ee0 -->

```text
Hey {first_name},

Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.send_info.full`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `8ea38bba59d5d4c473cf566952a2468319b906c2bedad76ab5da9957cbf05a27`

<!-- approve-template id=first_reply.recruiting_reactivation.send_info.full sha256=8ea38bba59d5d4c473cf566952a2468319b906c2bedad76ab5da9957cbf05a27 -->

```text
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for your business.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.mechanism.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `f9b503a72c7200a39634fa740a99d8ed9478ce0b0a3a891de56620788c73f5e9`

<!-- approve-template id=first_reply.recruiting_reactivation.mechanism.full sha256=f9b503a72c7200a39634fa740a99d8ed9478ce0b0a3a891de56620788c73f5e9 -->

```text
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. All I need to start is a list of 60 or more dormant client accounts.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. All I need to start is a list of 60 or more dormant client accounts.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. All I need to start is a list of 60 or more dormant client accounts.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. All I need to start is a list of 60 or more dormant client accounts.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. All I need to start is a list of 60 or more dormant client accounts.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.other.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval. Also used for every neutral_question that is not pricing, send_info or mechanism.
- sha256: `e9074d8e2ba72742af3c3025235a1b7c7e148770c3b49e9656bb846871a4b019`

<!-- approve-template id=first_reply.recruiting_reactivation.other.full sha256=e9074d8e2ba72742af3c3025235a1b7c7e148770c3b49e9656bb846871a4b019 -->

```text
Hey {first_name},

Good question. The short version is that I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Good question. The short version is that I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Good question. The short version is that I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. The rest is easier to cover on a quick call.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Good question. The short version is that I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. The rest is easier to cover on a quick call.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Good question. The short version is that I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. The rest is easier to cover on a quick call.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.referral.full`

- status: unapproved
- variables: `{first_name}`, `{referral_name}`, `{referral_first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8`

<!-- approve-template id=first_reply.recruiting_reactivation.referral.full sha256=5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8 -->

```text
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {slots} work for {referral_first_name}? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Appreciate you pointing me to the right person. Would you mind looping them in on this thread so I can send the details over?

Would {slots} work for them? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {referral_first_name} have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

{slot} CT works on my end. Once {referral_first_name} is on the thread, I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.default.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `3e88702a94a9f3b09e4423ffe5e2f8d9116291b5fc1bcf2e9f707e45733563ed`

<!-- approve-template id=first_reply.recruiting_reactivation.default.full sha256=3e88702a94a9f3b09e4423ffe5e2f8d9116291b5fc1bcf2e9f707e45733563ed -->

```text
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more dormant client accounts.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Glad to hear it. All I need to start is a list of 60 or more dormant client accounts.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more dormant client accounts.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more dormant client accounts.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Glad to hear it. All I need to start is a list of 60 or more dormant client accounts.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.pricing.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `f0b729c432e273e0a2f272596154b18e23b95ce8497435b34ce62e4a62a0f4e7`

<!-- approve-template id=first_reply.cleaning_trigger.pricing.full sha256=f0b729c432e273e0a2f272596154b18e23b95ce8497435b34ce62e4a62a0f4e7 -->

```text
Hey {first_name},

Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.send_info.full`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `b5c90233881e6fdcd9e3fa0962ca8e8cc41c0a4021a1f67da3a631e7565db1bb`

<!-- approve-template id=first_reply.cleaning_trigger.send_info.full sha256=b5c90233881e6fdcd9e3fa0962ca8e8cc41c0a4021a1f67da3a631e7565db1bb -->

```text
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for your business.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.mechanism.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `133615ad65a537d5e2a9bad6d759c2fab44aa1a5c882734249c7bb0e902152f1`

<!-- approve-template id=first_reply.cleaning_trigger.mechanism.full sha256=133615ad65a537d5e2a9bad6d759c2fab44aa1a5c882734249c7bb0e902152f1 -->

```text
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. All I need to start is your service area and the building types you want.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. All I need to start is your service area and the building types you want.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. All I need to start is your service area and the building types you want.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. All I need to start is your service area and the building types you want.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. All I need to start is your service area and the building types you want.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.other.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval. Also used for every neutral_question that is not pricing, send_info or mechanism.
- sha256: `0ccfdd86472ddee24e0970a2e86393cf9b81d237f8d73da6f3b64fb86ebde21e`

<!-- approve-template id=first_reply.cleaning_trigger.other.full sha256=0ccfdd86472ddee24e0970a2e86393cf9b81d237f8d73da6f3b64fb86ebde21e -->

```text
Hey {first_name},

Good question. The short version is that I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Good question. The short version is that I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Good question. The short version is that I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. The rest is easier to cover on a quick call.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Good question. The short version is that I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. The rest is easier to cover on a quick call.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Good question. The short version is that I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. The rest is easier to cover on a quick call.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.referral.full`

- status: unapproved
- variables: `{first_name}`, `{referral_name}`, `{referral_first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8`

<!-- approve-template id=first_reply.cleaning_trigger.referral.full sha256=5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8 -->

```text
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {slots} work for {referral_first_name}? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Appreciate you pointing me to the right person. Would you mind looping them in on this thread so I can send the details over?

Would {slots} work for them? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {referral_first_name} have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

{slot} CT works on my end. Once {referral_first_name} is on the thread, I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.default.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `0c1f98c5486ba982da717d66e3ccc035ead7ef435d9bbf308d473fad4ee167aa`

<!-- approve-template id=first_reply.cleaning_trigger.default.full sha256=0c1f98c5486ba982da717d66e3ccc035ead7ef435d9bbf308d473fad4ee167aa -->

```text
Hey {first_name},

Glad to hear it. All I need to start is your service area and the building types you want.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Glad to hear it. All I need to start is your service area and the building types you want.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Glad to hear it. All I need to start is your service area and the building types you want.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Glad to hear it. All I need to start is your service area and the building types you want.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Glad to hear it. All I need to start is your service area and the building types you want.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.pricing.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `fda12094c293cd263813fc732889f9af8139f96dcf7768e6e25ddc9fd7f46d4e`

<!-- approve-template id=first_reply.bookkeeping_trigger.pricing.full sha256=fda12094c293cd263813fc732889f9af8139f96dcf7768e6e25ddc9fd7f46d4e -->

```text
Hey {first_name},

Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.send_info.full`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `d1be23f2566a52f5c4e674097b4ca8a09a82678ce875d7b97fddb0a0925817d6`

<!-- approve-template id=first_reply.bookkeeping_trigger.send_info.full sha256=d1be23f2566a52f5c4e674097b4ca8a09a82678ce875d7b97fddb0a0925817d6 -->

```text
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for your business.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.mechanism.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `0734fb753c68f891793a1397a22ef110434ae8c1d4933e1c73214d21fba12a20`

<!-- approve-template id=first_reply.bookkeeping_trigger.mechanism.full sha256=0734fb753c68f891793a1397a22ef110434ae8c1d4933e1c73214d21fba12a20 -->

```text
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. All I need to start is the client profile you want more of.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. All I need to start is the client profile you want more of.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. All I need to start is the client profile you want more of.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. All I need to start is the client profile you want more of.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. All I need to start is the client profile you want more of.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.other.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval. Also used for every neutral_question that is not pricing, send_info or mechanism.
- sha256: `f6a6b264228af36da7b41f033fb3c47b916840243cc4159878a74da1ace059d3`

<!-- approve-template id=first_reply.bookkeeping_trigger.other.full sha256=f6a6b264228af36da7b41f033fb3c47b916840243cc4159878a74da1ace059d3 -->

```text
Hey {first_name},

Good question. The short version is that I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Good question. The short version is that I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Good question. The short version is that I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. The rest is easier to cover on a quick call.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Good question. The short version is that I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. The rest is easier to cover on a quick call.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Good question. The short version is that I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. The rest is easier to cover on a quick call.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.referral.full`

- status: unapproved
- variables: `{first_name}`, `{referral_name}`, `{referral_first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8`

<!-- approve-template id=first_reply.bookkeeping_trigger.referral.full sha256=5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8 -->

```text
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {slots} work for {referral_first_name}? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Appreciate you pointing me to the right person. Would you mind looping them in on this thread so I can send the details over?

Would {slots} work for them? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {referral_first_name} have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

{slot} CT works on my end. Once {referral_first_name} is on the thread, I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.default.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `e6fdfaa95d1881aa53612f79b7692cc1d87cdae2550551506c0345a0be208138`

<!-- approve-template id=first_reply.bookkeeping_trigger.default.full sha256=e6fdfaa95d1881aa53612f79b7692cc1d87cdae2550551506c0345a0be208138 -->

```text
Hey {first_name},

Glad to hear it. All I need to start is the client profile you want more of.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Glad to hear it. All I need to start is the client profile you want more of.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Glad to hear it. All I need to start is the client profile you want more of.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Glad to hear it. All I need to start is the client profile you want more of.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Glad to hear it. All I need to start is the client profile you want more of.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.pricing.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `f8cfe61d243072dcf105a6e3af7faf0850870d12905cb226b2636dd48f964195`

<!-- approve-template id=first_reply.recruiting_outbound.pricing.full sha256=f8cfe61d243072dcf105a6e3af7faf0850870d12905cb226b2636dd48f964195 -->

```text
Hey {first_name},

Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.send_info.full`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `7d7e8363cb5de1599c037f980db90769f3aea2865c3d640952d18c70954b5aef`

<!-- approve-template id=first_reply.recruiting_outbound.send_info.full sha256=7d7e8363cb5de1599c037f980db90769f3aea2865c3d640952d18c70954b5aef -->

```text
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for your business.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.mechanism.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `1eaafc5ab75e524d29c277c2415cb26d408611b26c81467def778f098525d0fb`

<!-- approve-template id=first_reply.recruiting_outbound.mechanism.full sha256=1eaafc5ab75e524d29c277c2415cb26d408611b26c81467def778f098525d0fb -->

```text
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. All I need to start is your specialty and geography.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. All I need to start is your specialty and geography.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. All I need to start is your specialty and geography.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. All I need to start is your specialty and geography.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. All I need to start is your specialty and geography.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.other.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval. Also used for every neutral_question that is not pricing, send_info or mechanism.
- sha256: `b13c6188feacfb84c2d6d523dac8fb327ec7809a927f1b6507f6aaaca5895148`

<!-- approve-template id=first_reply.recruiting_outbound.other.full sha256=b13c6188feacfb84c2d6d523dac8fb327ec7809a927f1b6507f6aaaca5895148 -->

```text
Hey {first_name},

Good question. The short version is that I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Good question. The short version is that I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. The rest is easier to cover on a quick call.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Good question. The short version is that I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. The rest is easier to cover on a quick call.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Good question. The short version is that I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. The rest is easier to cover on a quick call.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Good question. The short version is that I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. The rest is easier to cover on a quick call.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.referral.full`

- status: unapproved
- variables: `{first_name}`, `{referral_name}`, `{referral_first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8`

<!-- approve-template id=first_reply.recruiting_outbound.referral.full sha256=5d4e90e7c46dfd3ba88e35ef4a57ac15aad8feb73d03dcc682c0e6777d8138d8 -->

```text
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {slots} work for {referral_first_name}? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Appreciate you pointing me to the right person. Would you mind looping them in on this thread so I can send the details over?

Would {slots} work for them? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

Would {referral_first_name} have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?

{slot} CT works on my end. Once {referral_first_name} is on the thread, I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.default.full`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{slot}`, `{asked_time}`, `{original_subject}`
- variants: missing_lead_data, no_slots, confirmed_time, proposed_time_refused, subject, value_formats
- source: `services/reply_engine/draft.py:build_draft (skeleton)`
- sent from: `services/reply_engine/draft.py:build_draft (body) -> app.py pipeline -> approval.py:create_approval / send_approved`
- notes: The template body before any LLM polish (draft.build_draft with use_llm=False). A polished body is different text and is not covered by this approval.
- sha256: `b3c5b2c44a271c21c69ef60d6b118f39db846dd06607ee46d3ec6029fafc329f`

<!-- approve-template id=first_reply.recruiting_outbound.default.full sha256=b3c5b2c44a271c21c69ef60d6b118f39db846dd06607ee46d3ec6029fafc329f -->

```text
Hey {first_name},

Glad to hear it. All I need to start is your specialty and geography.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Glad to hear it. All I need to start is your specialty and geography.

Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Glad to hear it. All I need to start is your specialty and geography.

Do you have 15 minutes this week or next? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: confirmed_time (the lead proposed a time that passes every slot rule) ===
Hey {first_name},

Glad to hear it. All I need to start is your specialty and geography.

{slot} CT works on my end. I will send the invite over, and if anything shifts, you can grab a different time here: {booking_url}

Lorenzo

=== variant: proposed_time_refused (the lead proposed a time the slot rules refuse) ===
Hey {first_name},

Glad to hear it. All I need to start is your specialty and geography.

{asked_time} is tough on my end. Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

## Daily follow-up cadence (prompts/cadence_*.md)

### `cadence.d1`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d1.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- sha256: `738aa25b58b86beed6575f11922306f40ad90a2b84f6b22082be3823e1e4dca0`

<!-- approve-template id=cadence.d1 sha256=738aa25b58b86beed6575f11922306f40ad90a2b84f6b22082be3823e1e4dca0 -->

```text
Hey {first_name},

Here are two new times in case the first ones did not suit: {slots}.

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Here are two new times in case the first ones did not suit: {slots}.

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

In case the first times did not suit, grab any open time that works for you here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d2`

- status: unapproved
- variables: `{first_name}`, `{research_line}`, `{company}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d2.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- notes: {research_line} is cadence.d2.research_fallback.<offer>, the fixed fallback line, which is what the engine uses by default (CT3). A line written per lead by the LLM (cadence.d2.research_line) is not covered by any approval, so a day 2 touch carrying one is always held, never sent.
- sha256: `d7ff0c8bb79897079ef5617d1102b817fd36c568852b7df44cc5e424cef22063`

<!-- approve-template id=cadence.d2 sha256=d7ff0c8bb79897079ef5617d1102b817fd36c568852b7df44cc5e424cef22063 -->

```text
Hey {first_name},

{research_line}

Fifteen minutes is enough for me to show you how this would run for {company}. I have {slots} open, or grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{research_line}

Fifteen minutes is enough for me to show you how this would run for your team. I have {slots} open, or grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

{research_line}

Fifteen minutes is enough for me to show you how this would run for {company}. Grab any open time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d3`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d3.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- sha256: `e9bfcc019e24396c6c74678389774cb6d42af2d67ed66906aaf5ef5665a35810`

<!-- approve-template id=cadence.d3 sha256=e9bfcc019e24396c6c74678389774cb6d42af2d67ed66906aaf5ef5665a35810 -->

```text
Hey {first_name},

A couple more options if those did not work: {slots}.

Or pick whatever suits you here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

A couple more options if those did not work: {slots}.

Or pick whatever suits you here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

If none of those times worked, pick whatever suits you here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d4`

- status: unapproved
- variables: `{first_name}`, `{case_study}`, `{company}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d4.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- notes: {case_study} is cadence.d4.case_study.<offer>; the variants show the reactivation line in place.
- sha256: `525217c4db339aa62a2cc58a5415de0902af958d43d9fccaf0233533bb093396`

<!-- approve-template id=cadence.d4 sha256=525217c4db339aa62a2cc58a5415de0902af958d43d9fccaf0233533bb093396 -->

```text
Hey {first_name},

Quick bit of context on why I keep nudging. {case_study}

Happy to walk through what that would look like for {company}. I have {slots}, or grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Quick bit of context on why I keep nudging. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

Happy to walk through what that would look like for your team. I have {slots}, or grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Quick bit of context on why I keep nudging. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

Happy to walk through what that would look like for {company}. Grab any open time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d5`

- status: unapproved
- variables: `{first_name}`, `{free_work}`, `{slots}`, `{booking_url}`, `{company}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d5.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- notes: {free_work} is cadence.d5.free_work.<niche>_<offer>; the variants show the cleaning line in place.
- sha256: `4d479127db28ef4e0de427a834af5b6500854b91cf2bc1d90d1eb5052802d77a`

<!-- approve-template id=cadence.d5 sha256=4d479127db28ef4e0de427a834af5b6500854b91cf2bc1d90d1eb5052802d77a -->

```text
Hey {first_name},

{free_work}

Happy to walk through it together. I have {slots}, or grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I can draft the first two emails for the accounts your team lost or bid on and never closed. Want to see them?

Happy to walk through it together. I have {slots}, or grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

I can draft the first two emails for the accounts {company} lost or bid on and never closed. Want to see them?

Happy to walk through it together. Grab any open time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d6`

- status: unapproved
- variables: `{first_name}`, `{slot1}`, `{slot2}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, one_slot, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d6.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- notes: Needs Lorenzo's one-tap OK on the calendar hold today (Touch.requires_approval).
- sha256: `c68d4366e4db185472a6bd4f78a53b9385903752cb6163d51260ca1afe78672c`

<!-- approve-template id=cadence.d6 sha256=c68d4366e4db185472a6bd4f78a53b9385903752cb6163d51260ca1afe78672c -->

```text
Hey {first_name},

I put a 15-minute hold on my calendar for {slot1}. If {slot2} is better, say the word and I will move it.

Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

I put a 15-minute hold on my calendar for {slot1}. If {slot2} is better, say the word and I will move it.

Or grab any time here: {booking_url}

Lorenzo

=== variant: one_slot (only one free slot) ===
Hey {first_name},

I put a 15-minute hold on my calendar for {slot1}. If another time is better, say the word and I will move it.

Or grab any time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d6_noinvite`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d6_noinvite.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- sha256: `f43912114866c5bca078ed38784f1e564ce2743e0aed54f40601c37c43bf6158`

<!-- approve-template id=cadence.d6_noinvite sha256=f43912114866c5bca078ed38784f1e564ce2743e0aed54f40601c37c43bf6158 -->

```text
Hey {first_name},

Here are two more times on my side: {slots}. Either one works for a 15-minute walkthrough.

Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Here are two more times on my side: {slots}. Either one works for a 15-minute walkthrough.

Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

If a 15-minute walkthrough would help, grab any open time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d7`

- status: unapproved
- variables: `{first_name}`, `{original_subject}`
- variants: missing_lead_data, subject
- source: `services/reply_engine/prompts/cadence_d7.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- notes: No slots.
- sha256: `7adfc20bd241c19f411391febaa14b608faa92c3a08a1241ecad81bf7cf08091`

<!-- approve-template id=cadence.d7 sha256=7adfc20bd241c19f411391febaa14b608faa92c3a08a1241ecad81bf7cf08091 -->

```text
Hey {first_name},

Should I close your file, or is a different week better?

Either answer is fine. I just want to keep my notes straight.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Should I close your file, or is a different week better?

Either answer is fine. I just want to keep my notes straight.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply
```

### `cadence.d14`

- status: unapproved
- variables: `{first_name}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d14.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- sha256: `a0eb4f3c8c2db1d55c1fba6508dae5847a4afa6f7549a0844c02cddc365cbd13`

<!-- approve-template id=cadence.d14 sha256=a0eb4f3c8c2db1d55c1fba6508dae5847a4afa6f7549a0844c02cddc365cbd13 -->

```text
Hey {first_name},

Circling back in case the timing is better now. I have {slots} open, or grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Circling back in case the timing is better now. I have {slots} open, or grab a time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Circling back in case the timing is better now. Grab any open time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `cadence.d30`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_slots, subject, value_formats
- source: `services/reply_engine/prompts/cadence_d30.md`
- sent from: `services/reply_engine/cadence.py:build_touch -> tick_lead -> _send`
- sha256: `5c3217cd9af5b5dece520ce8ec1c0e2378e663c1984a0e1117bc0238ec8dc661`

<!-- approve-template id=cadence.d30 sha256=5c3217cd9af5b5dece520ce8ec1c0e2378e663c1984a0e1117bc0238ec8dc661 -->

```text
Hey {first_name},

Last one from me for a while. If {company} still wants a look, I have {slots}, or grab a time here: {booking_url}

If not, I will leave it here and check back in a few months.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Last one from me for a while. If your team still wants a look, I have {slots}, or grab a time here: {booking_url}

If not, I will leave it here and check back in a few months.

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Hey {first_name},

Last one from me for a while. If {company} still wants a look, grab any open time here: {booking_url}

If not, I will leave it here and check back in a few months.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

## Cadence: lines spliced into day 2, day 4 and day 5

### `cadence.d4.case_study.reactivation`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:case_study_line (config/offers.md proof table)`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- sha256: `0d17141b74612f8369284e941b3185f81e28eaf707df03c781a29281f6edb37a`

<!-- approve-template id=cadence.d4.case_study.reactivation sha256=0d17141b74612f8369284e941b3185f81e28eaf707df03c781a29281f6edb37a -->

```text
I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.
```

### `cadence.d4.case_study.outbound`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:case_study_line (config/offers.md proof table)`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- sha256: `6b5911b1a091bb7d557ef931f598e520e8fce9c8e7ad173325b87af09b629767`

<!-- approve-template id=cadence.d4.case_study.outbound sha256=6b5911b1a091bb7d557ef931f598e520e8fce9c8e7ad173325b87af09b629767 -->

```text
I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.
```

### `cadence.d5.free_work.cleaning_reactivation`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `dffc5e226ec27ff2c78c50491159f017e74fd543a81f9861afd3b705fb5a4735`

<!-- approve-template id=cadence.d5.free_work.cleaning_reactivation sha256=dffc5e226ec27ff2c78c50491159f017e74fd543a81f9861afd3b705fb5a4735 -->

```text
I can draft the first two emails for the accounts {company} lost or bid on and never closed. Want to see them?
```

### `cadence.d5.free_work.cleaning_outbound`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `309c6e52e49cef6643b151819947beb54b1e00c9ad87f4da6805240b2e35136a`

<!-- approve-template id=cadence.d5.free_work.cleaning_outbound sha256=309c6e52e49cef6643b151819947beb54b1e00c9ad87f4da6805240b2e35136a -->

```text
I can pull the buildings in your area that just signed a new lease, expanded, or changed property managers this month. Want the list?
```

### `cadence.d5.free_work.bookkeeping_reactivation`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `f21d4c3ac095004efadfaa1f611df0c04d4d4449771ef914ec0de4a1627923ef`

<!-- approve-template id=cadence.d5.free_work.bookkeeping_reactivation sha256=f21d4c3ac095004efadfaa1f611df0c04d4d4449771ef914ec0de4a1627923ef -->

```text
I can draft the first two emails for the clients {company} lost or quoted and never closed. Want to see them?
```

### `cadence.d5.free_work.bookkeeping_outbound`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `9be1ba7d8fbb7811cab3b0a09be5dd995227472862bf8c8feeefafe6f071e0f7`

<!-- approve-template id=cadence.d5.free_work.bookkeeping_outbound sha256=9be1ba7d8fbb7811cab3b0a09be5dd995227472862bf8c8feeefafe6f071e0f7 -->

```text
I can pull the businesses in your area that just formed or posted a part-time bookkeeper role this month. Want the list?
```

### `cadence.d5.free_work.recruiting_reactivation`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `f9a35e0e60c301e25a5c94aeda22b63643faf1b3982a91594f97e6342e8db8e3`

<!-- approve-template id=cadence.d5.free_work.recruiting_reactivation sha256=f9a35e0e60c301e25a5c94aeda22b63643faf1b3982a91594f97e6342e8db8e3 -->

```text
I can draft the first two emails for the clients {company} made one placement for and never heard from again. Want to see them?
```

### `cadence.d5.free_work.recruiting_outbound`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `6a8ce242bac65a605fef4792aea359a6564075e8f3f047100b13ae3b0a671a2f`

<!-- approve-template id=cadence.d5.free_work.recruiting_outbound sha256=6a8ce242bac65a605fef4792aea359a6564075e8f3f047100b13ae3b0a671a2f -->

```text
I can pull the roles in your specialty that opened this week in your market, with the hiring manager for each. Want the list?
```

### `cadence.d5.free_work.recruiting_outbound_specialty`

- status: unapproved
- variables: `{specialty}`
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `466cf54bffcb59c1a92f78aba91d3b40ec6dc3ced21d3475adf0ca74ab239f9b`

<!-- approve-template id=cadence.d5.free_work.recruiting_outbound_specialty sha256=466cf54bffcb59c1a92f78aba91d3b40ec6dc3ced21d3475adf0ca74ab239f9b -->

```text
I can pull the {specialty} roles that opened this week in your market, with the hiring manager for each. Want the list?
```

### `cadence.d5.free_work.generic_reactivation`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `dffc5e226ec27ff2c78c50491159f017e74fd543a81f9861afd3b705fb5a4735`

<!-- approve-template id=cadence.d5.free_work.generic_reactivation sha256=dffc5e226ec27ff2c78c50491159f017e74fd543a81f9861afd3b705fb5a4735 -->

```text
I can draft the first two emails for the accounts {company} lost or bid on and never closed. Want to see them?
```

### `cadence.d5.free_work.generic_outbound`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/cadence.py:free_work_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: 'generic' is any niche the function does not name. Without a company the cadence passes its own fallback (see the cadence variants).
- sha256: `034ad531e92fec00e8e92748c14d500cf78a6346f35463593b64361eb5f3dd4b`

<!-- approve-template id=cadence.d5.free_work.generic_outbound sha256=034ad531e92fec00e8e92748c14d500cf78a6346f35463593b64361eb5f3dd4b -->

```text
I can put together a short sample of the first two emails I would send for {company}. Want to see it?
```

### `cadence.d2.research_fallback.reactivation`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:fallback_research_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: Used when the research model returns nothing usable.
- sha256: `872527079d5663a61bc683dfeddaad059124c645926852afcc1d1ac3f218ff59`

<!-- approve-template id=cadence.d2.research_fallback.reactivation sha256=872527079d5663a61bc683dfeddaad059124c645926852afcc1d1ac3f218ff59 -->

```text
The quickest place to start is usually the accounts that already know you and went quiet.
```

### `cadence.d2.research_fallback.outbound`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:fallback_research_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- notes: Used when the research model returns nothing usable.
- sha256: `379bc5ef9ba12b82b3fddf6d059a56d0f00554ac9769d88a7ee99fe8c27cdc99`

<!-- approve-template id=cadence.d2.research_fallback.outbound sha256=379bc5ef9ba12b82b3fddf6d059a56d0f00554ac9769d88a7ee99fe8c27cdc99 -->

```text
The quickest place to start is usually the prospects who are in market right now.
```

### `cadence.d2.research_line`

- status: unapproved
- variables: none
- source: `services/reply_engine/cadence.py:generate_research_line`
- sent from: `services/reply_engine/cadence.py:build_touch (spliced into the day body) -> tick_lead -> _send`
- not extractable: Written per lead by the LLM (shared.llm role 'research') from the prompt in prompts/cadence_research.md, so there is no fixed text to hash. CT3: day 2 uses the fallback line by default; a touch carrying an LLM line is always held, never sent.

## Booking: confirmation, counter-proposals, already booked

### `booking.confirmation.zoom_link`

- status: unapproved
- variables: `{first_name}`, `{slot}`, `{zoom_link}`, `{lead_local_time}`, `{original_subject}`
- variants: lead_in_other_timezone, missing_lead_data, subject, value_formats
- source: `services/reply_engine/booking.py:_confirmation_draft`
- sent from: `services/reply_engine/booking.py:_confirmation_draft <- book() / _already_booked_result; sent as an approval card via app.py -> approval.py:send_approved`
- notes: Claims an invite: approval.py:claims_invite rules still apply.
- sha256: `640bd28996621bf1ef28792bbab112741da73fe28bfe6f518c752718f9b63a3c`

<!-- approve-template id=booking.confirmation.zoom_link sha256=640bd28996621bf1ef28792bbab112741da73fe28bfe6f518c752718f9b63a3c -->

```text
Hey {first_name},

Locked in {slot} CT, invite on the way. Here is the Zoom link:
{zoom_link}

I will keep it to 15 minutes.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Hey {first_name},

Locked in {slot} CT ({lead_local_time} your time), invite on the way. Here is the Zoom link:
{zoom_link}

I will keep it to 15 minutes.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Locked in {slot} CT, invite on the way. Here is the Zoom link:
{zoom_link}

I will keep it to 15 minutes.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.confirmation.no_zoom_link`

- status: unapproved
- variables: `{first_name}`, `{slot}`, `{lead_local_time}`, `{original_subject}`
- variants: lead_in_other_timezone, missing_lead_data, subject, value_formats
- source: `services/reply_engine/booking.py:_confirmation_draft`
- sent from: `services/reply_engine/booking.py:_confirmation_draft <- book() / _already_booked_result; sent as an approval card via app.py -> approval.py:send_approved`
- notes: Claims an invite: approval.py:claims_invite rules still apply.
- sha256: `916534ad8fb2e33a0653b27477e4c8d3410389114182d34798e654b3cc5c8bd5`

<!-- approve-template id=booking.confirmation.no_zoom_link sha256=916534ad8fb2e33a0653b27477e4c8d3410389114182d34798e654b3cc5c8bd5 -->

```text
Hey {first_name},

Locked in {slot} CT. The calendar invite with the video link follows in a separate email. I will keep it to 15 minutes.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Hey {first_name},

Locked in {slot} CT ({lead_local_time} your time). The calendar invite with the video link follows in a separate email. I will keep it to 15 minutes.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Locked in {slot} CT. The calendar invite with the video link follows in a separate email. I will keep it to 15 minutes.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.window_no_fit`

- status: unapproved
- variables: `{first_name}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `05b67816838bab4c42867411226ddf0c0ecf67f2a70cb74a181d6e8c6d9230cb`

<!-- approve-template id=booking.counter.window_no_fit sha256=05b67816838bab4c42867411226ddf0c0ecf67f2a70cb74a181d6e8c6d9230cb -->

```text
Hey {first_name},

Nothing inside that window is open on my side in the next week. Could you do {alt_slots}?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

Nothing inside that window is open on my side in the next week. Could you do {alt_slots}?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

Nothing inside that window is open on my side in the next week. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Nothing inside that window is open on my side in the next week. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.outside_window_early`

- status: unapproved
- variables: `{first_name}`, `{asked_time}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, no_proposed_time, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `93b1b929b90636520210d7d97e7962ad3add969b200bba2497dec7c662f18add`

<!-- approve-template id=booking.counter.outside_window_early sha256=93b1b929b90636520210d7d97e7962ad3add969b200bba2497dec7c662f18add -->

```text
Hey {first_name},

{asked_time} is a touch early on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{asked_time} is a touch early on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{asked_time} is a touch early on my side. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: no_proposed_time (the lead's time could not be read) ===
Hey {first_name},

That time does not work on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Tue Jan 8 9:47am CT is a touch early on my side. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.outside_window_late`

- status: unapproved
- variables: `{first_name}`, `{asked_time}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, no_proposed_time, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `255d01c911eee3af5b832e1c69546587c7bad7ae50c735915f7578cfd4ca8844`

<!-- approve-template id=booking.counter.outside_window_late sha256=255d01c911eee3af5b832e1c69546587c7bad7ae50c735915f7578cfd4ca8844 -->

```text
Hey {first_name},

{asked_time} is past my last slot. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{asked_time} is past my last slot. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{asked_time} is past my last slot. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: no_proposed_time (the lead's time could not be read) ===
Hey {first_name},

That time does not work on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Tue Jan 8 7:47pm CT is past my last slot. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.weekend`

- status: unapproved
- variables: `{first_name}`, `{asked_time}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, no_proposed_time, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `bcc7c9cb0eb30cf20c1ef50c5e8e17b796fc109d59239a38307a0c84d825a959`

<!-- approve-template id=booking.counter.weekend sha256=bcc7c9cb0eb30cf20c1ef50c5e8e17b796fc109d59239a38307a0c84d825a959 -->

```text
Hey {first_name},

{asked_time} lands on a weekend for me. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{asked_time} lands on a weekend for me. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{asked_time} lands on a weekend for me. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: no_proposed_time (the lead's time could not be read) ===
Hey {first_name},

That time does not work on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Sat Jan 12 1:47pm CT lands on a weekend for me. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.too_soon`

- status: unapproved
- variables: `{first_name}`, `{asked_time}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, no_proposed_time, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `5cb89c71b36785d9fe81e8afd90391c1aa595d36fd96efb5d6b7e021efda60da`

<!-- approve-template id=booking.counter.too_soon sha256=5cb89c71b36785d9fe81e8afd90391c1aa595d36fd96efb5d6b7e021efda60da -->

```text
Hey {first_name},

{asked_time} is a little tight on my end. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{asked_time} is a little tight on my end. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{asked_time} is a little tight on my end. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: no_proposed_time (the lead's time could not be read) ===
Hey {first_name},

That time does not work on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Tue Jan 8 1:47pm CT is a little tight on my end. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.beyond_horizon`

- status: unapproved
- variables: `{first_name}`, `{asked_time}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, no_proposed_time, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `a831686722389be12f2cba09f491ac5ab188d292371f1eb0b9d8752b508f95c8`

<!-- approve-template id=booking.counter.beyond_horizon sha256=a831686722389be12f2cba09f491ac5ab188d292371f1eb0b9d8752b508f95c8 -->

```text
Hey {first_name},

{asked_time} is further out than I can lock in right now. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{asked_time} is further out than I can lock in right now. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{asked_time} is further out than I can lock in right now. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: no_proposed_time (the lead's time could not be read) ===
Hey {first_name},

That time does not work on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Fri Jan 11 1:47pm CT is further out than I can lock in right now. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.counter.slot_taken`

- status: unapproved
- variables: `{first_name}`, `{asked_time}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, no_proposed_time, dated, subject, value_formats
- source: `services/reply_engine/booking.py:counter_proposal_text`
- sent from: `services/reply_engine/booking.py:counter_proposal_text <- app.py; sent via approval.py:send_approved`
- sha256: `d24be2d01c393370f528a21d3e2506fdb9936f702bb93202fd42abbdf0126f2f`

<!-- approve-template id=booking.counter.slot_taken sha256=d24be2d01c393370f528a21d3e2506fdb9936f702bb93202fd42abbdf0126f2f -->

```text
Hey {first_name},

{asked_time} just got taken on my calendar. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{asked_time} just got taken on my calendar. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{asked_time} just got taken on my calendar. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: no_proposed_time (the lead's time could not be read) ===
Hey {first_name},

That time does not work on my side. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: dated (the refused time and the alternatives fall in different weeks (example dates)) ===
Hey {first_name},

Tue Jan 8 1:47pm CT just got taken on my calendar. Could you do Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.slot_already_taken`

- status: unapproved
- variables: `{first_name}`, `{slot}`, `{alt_slots}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_alternatives, subject, value_formats
- source: `services/reply_engine/booking.py:_unbookable_result`
- sent from: `services/reply_engine/booking.py:_unbookable_result <- book(); the draft carries the slot_already_taken problem, so it is always a card, never auto-sent`
- notes: Sent when the calendar filled between the offer and the booking.
- sha256: `c57ddd2725f2d2d91fa638e0d438696139f50fa3cf2b0850872a1e54d4deb3cd`

<!-- approve-template id=booking.slot_already_taken sha256=c57ddd2725f2d2d91fa638e0d438696139f50fa3cf2b0850872a1e54d4deb3cd -->

```text
Hey {first_name},

{slot} CT just got taken on my calendar. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

{slot} CT just got taken on my calendar. Could you do {alt_slots} instead?

Or if it's easier, grab a time here: {booking_url}

Lorenzo

=== variant: no_alternatives (no free alternative time) ===
Hey {first_name},

{slot} CT just got taken on my calendar. Could you grab a time that suits you here instead? {booking_url}

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: {first_name}, question
Subject when there is no first name either: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.already_booked.awaiting_approval`

- status: unapproved
- variables: `{first_name}`, `{slot}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_booking_link, subject, value_formats
- source: `services/reply_engine/app.py:_already_booked_body`
- sent from: `services/reply_engine/app.py:_already_booked_body -> approval card`
- notes: When the lead also asked a question, the answer paragraph is inserted after the greeting; that answer is the first reply's answer text.
- sha256: `6ce2bffdd547c73854b7cd0062430fafeb40f46d6f652fee4ff70849eff33ec2`

<!-- approve-template id=booking.already_booked.awaiting_approval sha256=6ce2bffdd547c73854b7cd0062430fafeb40f46d6f652fee4ff70849eff33ec2 -->

```text
Hey {first_name},

You are locked in for {slot} CT, invite on the way. If that no longer works, grab another time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

You are locked in for {slot} CT, invite on the way. If that no longer works, grab another time here: {booking_url}

Lorenzo

=== variant: no_booking_link (no booking link configured) ===
Hey {first_name},

You are locked in for {slot} CT, invite on the way.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.already_booked.invite_withheld`

- status: unapproved
- variables: `{first_name}`, `{slot}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_booking_link, subject, value_formats
- source: `services/reply_engine/app.py:_already_booked_body`
- sent from: `services/reply_engine/app.py:_already_booked_body -> approval card`
- notes: When the lead also asked a question, the answer paragraph is inserted after the greeting; that answer is the first reply's answer text.
- sha256: `d6844a4c0747f8188a96a6f0f457c6b04cc235a7ac97b094606b05a1eedbc767`

<!-- approve-template id=booking.already_booked.invite_withheld sha256=d6844a4c0747f8188a96a6f0f457c6b04cc235a7ac97b094606b05a1eedbc767 -->

```text
Hey {first_name},

We are already set for {slot} CT. If that no longer works, grab another time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

We are already set for {slot} CT. If that no longer works, grab another time here: {booking_url}

Lorenzo

=== variant: no_booking_link (no booking link configured) ===
Hey {first_name},

We are already set for {slot} CT.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `booking.already_booked.invite_on_calendar`

- status: unapproved
- variables: `{first_name}`, `{slot}`, `{booking_url}`, `{original_subject}`
- variants: missing_lead_data, no_booking_link, subject, value_formats
- source: `services/reply_engine/app.py:_already_booked_body`
- sent from: `services/reply_engine/app.py:_already_booked_body -> approval card`
- notes: When the lead also asked a question, the answer paragraph is inserted after the greeting; that answer is the first reply's answer text.
- sha256: `81334e1dbf58e7b90237bf9971ca3b920ff4b07375a73bef278004e058d7eed8`

<!-- approve-template id=booking.already_booked.invite_on_calendar sha256=81334e1dbf58e7b90237bf9971ca3b920ff4b07375a73bef278004e058d7eed8 -->

```text
Hey {first_name},

We are already set for {slot} CT and the invite is on your calendar. If that no longer works, grab another time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there,

We are already set for {slot} CT and the invite is on your calendar. If that no longer works, grab another time here: {booking_url}

Lorenzo

=== variant: no_booking_link (no booking link configured) ===
Hey {first_name},

We are already set for {slot} CT and the invite is on your calendar.

Lorenzo

=== variant: subject (subject line (thread subject, and the fallback when the thread has none)) ===
Subject: Re: {original_subject}
Subject when the thread has none: Re: your reply

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

## Show-rate: confirmation, pre-read and reminders

### `show_rate.confirm_email.cleaning_reactivation`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation.
- sha256: `961392d634f6ed3c8b2ef673c75b046f74776117c52505839414541bf66da1d6`

<!-- approve-template id=show_rate.confirm_email.cleaning_reactivation sha256=961392d634f6ed3c8b2ef673c75b046f74776117c52505839414541bf66da1d6 -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your lost or dormant accounts are worth going after first
- what the email and text sequences say, so it sounds like you and not a vendor
- the commission-only numbers, so you know exactly what a returned account pays me

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your lost or dormant accounts are worth going after first
- what the email and text sequences say, so it sounds like you and not a vendor
- the commission-only numbers, so you know exactly what a returned account pays me

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which of your lost or dormant accounts are worth going after first
- what the email and text sequences say, so it sounds like you and not a vendor
- the commission-only numbers, so you know exactly what a returned account pays me

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your lost or dormant accounts are worth going after first
- what the email and text sequences say, so it sounds like you and not a vendor
- the commission-only numbers, so you know exactly what a returned account pays me

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your lost or dormant accounts are worth going after first
- what the email and text sequences say, so it sounds like you and not a vendor
- the commission-only numbers, so you know exactly what a returned account pays me

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which of your lost or dormant accounts are worth going after first
- what the email and text sequences say, so it sounds like you and not a vendor
- the commission-only numbers, so you know exactly what a returned account pays me

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.cleaning_outbound`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/outbound.
- sha256: `06cc4cd6faa3016509fb06720f0f5f6bd562aa9dc1142be611b4a1699aec5b92`

<!-- approve-template id=show_rate.confirm_email.cleaning_outbound sha256=06cc4cd6faa3016509fb06720f0f5f6bd562aa9dc1142be611b4a1699aec5b92 -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which building types and trigger events (new leases, expansions, PM changes) fit your crews
- how the outreach runs under your name and books walkthroughs on your calendar
- the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which building types and trigger events (new leases, expansions, PM changes) fit your crews
- how the outreach runs under your name and books walkthroughs on your calendar
- the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which building types and trigger events (new leases, expansions, PM changes) fit your crews
- how the outreach runs under your name and books walkthroughs on your calendar
- the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which building types and trigger events (new leases, expansions, PM changes) fit your crews
- how the outreach runs under your name and books walkthroughs on your calendar
- the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which building types and trigger events (new leases, expansions, PM changes) fit your crews
- how the outreach runs under your name and books walkthroughs on your calendar
- the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which building types and trigger events (new leases, expansions, PM changes) fit your crews
- how the outreach runs under your name and books walkthroughs on your calendar
- the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.bookkeeping_reactivation`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: bookkeeping/reactivation.
- sha256: `8a2d6201946f66444f17d6a02dea61d5b3c0e0d5f2939928205baf6e209a728b`

<!-- approve-template id=show_rate.confirm_email.bookkeeping_reactivation sha256=8a2d6201946f66444f17d6a02dea61d5b3c0e0d5f2939928205baf6e209a728b -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which former clients and lost inquiries to go after first, timed to tax season and year-end
- what the email and text sequences say, so it reads like your practice
- the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which former clients and lost inquiries to go after first, timed to tax season and year-end
- what the email and text sequences say, so it reads like your practice
- the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which former clients and lost inquiries to go after first, timed to tax season and year-end
- what the email and text sequences say, so it reads like your practice
- the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which former clients and lost inquiries to go after first, timed to tax season and year-end
- what the email and text sequences say, so it reads like your practice
- the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which former clients and lost inquiries to go after first, timed to tax season and year-end
- what the email and text sequences say, so it reads like your practice
- the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which former clients and lost inquiries to go after first, timed to tax season and year-end
- what the email and text sequences say, so it reads like your practice
- the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.bookkeeping_outbound`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: bookkeeping/outbound.
- sha256: `270be85c9b8a021da01c3cf552a51d19013abc6fceae8b2aa1fee7a90ee31762`

<!-- approve-template id=show_rate.confirm_email.bookkeeping_outbound sha256=270be85c9b8a021da01c3cf552a51d19013abc6fceae8b2aa1fee7a90ee31762 -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client
- how the outreach runs under your name and books discovery calls on your calendar
- the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client
- how the outreach runs under your name and books discovery calls on your calendar
- the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client
- how the outreach runs under your name and books discovery calls on your calendar
- the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client
- how the outreach runs under your name and books discovery calls on your calendar
- the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client
- how the outreach runs under your name and books discovery calls on your calendar
- the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client
- how the outreach runs under your name and books discovery calls on your calendar
- the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.recruiting_reactivation`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: recruiting/reactivation.
- sha256: `de286619b454d9ea57d5af747e532a74ded1b645839340cdb33bff327c6a193f`

<!-- approve-template id=show_rate.confirm_email.recruiting_reactivation sha256=de286619b454d9ea57d5af747e532a74ded1b645839340cdb33bff327c6a193f -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which dormant and near-miss client accounts are worth going after first
- what the sequences say to a hiring manager who used you once
- the numbers: $0 up front, a cut of the first placement fee on accounts that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which dormant and near-miss client accounts are worth going after first
- what the sequences say to a hiring manager who used you once
- the numbers: $0 up front, a cut of the first placement fee on accounts that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which dormant and near-miss client accounts are worth going after first
- what the sequences say to a hiring manager who used you once
- the numbers: $0 up front, a cut of the first placement fee on accounts that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which dormant and near-miss client accounts are worth going after first
- what the sequences say to a hiring manager who used you once
- the numbers: $0 up front, a cut of the first placement fee on accounts that come back

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which dormant and near-miss client accounts are worth going after first
- what the sequences say to a hiring manager who used you once
- the numbers: $0 up front, a cut of the first placement fee on accounts that come back

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which dormant and near-miss client accounts are worth going after first
- what the sequences say to a hiring manager who used you once
- the numbers: $0 up front, a cut of the first placement fee on accounts that come back

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.recruiting_outbound`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: recruiting/outbound.
- sha256: `3415030ceac7b5a7cd3b01c4412afe313b369da089caa76b9d2e748f6f011bb1`

<!-- approve-template id=show_rate.confirm_email.recruiting_outbound sha256=3415030ceac7b5a7cd3b01c4412afe313b369da089caa76b9d2e748f6f011bb1 -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which specialties and geographies to watch for open roles
- how the outreach reaches hiring managers under your agency's name
- the guarantee ($40,000 in new placement fees within 180 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which specialties and geographies to watch for open roles
- how the outreach reaches hiring managers under your agency's name
- the guarantee ($40,000 in new placement fees within 180 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which specialties and geographies to watch for open roles
- how the outreach reaches hiring managers under your agency's name
- the guarantee ($40,000 in new placement fees within 180 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which specialties and geographies to watch for open roles
- how the outreach reaches hiring managers under your agency's name
- the guarantee ($40,000 in new placement fees within 180 days) and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which specialties and geographies to watch for open roles
- how the outreach reaches hiring managers under your agency's name
- the guarantee ($40,000 in new placement fees within 180 days) and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which specialties and geographies to watch for open roles
- how the outreach reaches hiring managers under your agency's name
- the guarantee ($40,000 in new placement fees within 180 days) and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.generic_reactivation`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: generic/reactivation.
- sha256: `440edf5ecfdda043f5107182b875750eecb156a997b6f5ed4ea4822ff9efc26b`

<!-- approve-template id=show_rate.confirm_email.generic_reactivation sha256=440edf5ecfdda043f5107182b875750eecb156a997b6f5ed4ea4822ff9efc26b -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your dormant accounts are worth going after first
- what the sequences say, so it sounds like you
- the numbers, so you know exactly what it pays me and what it costs you

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your dormant accounts are worth going after first
- what the sequences say, so it sounds like you
- the numbers, so you know exactly what it pays me and what it costs you

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which of your dormant accounts are worth going after first
- what the sequences say, so it sounds like you
- the numbers, so you know exactly what it pays me and what it costs you

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your dormant accounts are worth going after first
- what the sequences say, so it sounds like you
- the numbers, so you know exactly what it pays me and what it costs you

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- which of your dormant accounts are worth going after first
- what the sequences say, so it sounds like you
- the numbers, so you know exactly what it pays me and what it costs you

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- which of your dormant accounts are worth going after first
- what the sequences say, so it sounds like you
- the numbers, so you know exactly what it pays me and what it costs you

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_email.generic_outbound`

- status: unapproved
- variables: `{when_ct}`, `{first_name}`, `{zoom_link}`, `{loom_url}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, no_loom_url, no_call_link_or_loom, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: generic/outbound.
- sha256: `19180affbb3bb6ff31da7c224a495ea93959d4811100480f594fd98c53e02e49`

<!-- approve-template id=show_rate.confirm_email.generic_outbound sha256=19180affbb3bb6ff31da7c224a495ea93959d4811100480f594fd98c53e02e49 -->

```text
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- who is in market for what you sell right now
- how the outreach runs under your name and books calls on your calendar
- the guarantee and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey there,

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- who is in market for what you sell right now
- how the outreach runs under your name and books calls on your calendar
- the guarantee and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- who is in market for what you sell right now
- how the outreach runs under your name and books calls on your calendar
- the guarantee and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Confirmed: Tue, Jan 8 at 1:47pm CT (2:47pm ET), 15 minutes with Lorenzo

Hey {first_name},

Locked in for Tue, Jan 8 at 1:47pm CT (2:47pm ET). The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- who is in market for what you sell right now
- how the outreach runs under your name and books calls on your calendar
- the guarantee and what it would cost

Here is a 60-second walkthrough of what I will show you, if you want a head start: {loom_url}

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_loom_url (no Loom URL configured (the sentence is dropped)) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link, and here it is too so you do not have to dig: {zoom_link}

Here is what I want to cover in the 15 minutes:
- who is in market for what you sell right now
- how the outreach runs under your name and books calls on your calendar
- the guarantee and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: no_call_link_or_loom (no call link on file and no Loom URL configured) ===
Subject: Confirmed: {when_ct}, 15 minutes with Lorenzo

Hey {first_name},

Locked in for {when_ct}. The calendar invite is on its way with the call link.

Here is what I want to cover in the 15 minutes:
- who is in market for what you sell right now
- how the outreach runs under your name and books calls on your calendar
- the guarantee and what it would cost

If anything comes up before then, reply here and we will move it.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.confirm_sms`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{zoom_link}`
- variants: missing_lead_data, no_call_link, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound. SMS bodies are cut at 320 characters.
- sha256: `f302848463911b92a2f7547398fa27fd9503bfc5a2351de88d613a156131ec20`

<!-- approve-template id=show_rate.confirm_sms sha256=f302848463911b92a2f7547398fa27fd9503bfc5a2351de88d613a156131ec20 -->

```text
Hey {first_name}, Lorenzo here. We are locked in for a 15-min call on {when_ct}. Call link: {zoom_link}. Reply here if anything changes.

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there, Lorenzo here. We are locked in for a 15-min call on {when_ct}. Call link: {zoom_link}. Reply here if anything changes.

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Hey {first_name}, Lorenzo here. We are locked in for a 15-min call on {when_ct}. The link is on your calendar invite. Reply here if anything changes.

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Hey {first_name}, Lorenzo here. We are locked in for a 15-min call on Tue, Jan 8 at 1:47pm CT (2:47pm ET). Call link: {zoom_link}. Reply here if anything changes.

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.cleaning_reactivation`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation.
- sha256: `04933c3e85b26ab7be043937e7fc03a57aa76e0c160ab180ab2fd067aabc5ef7`

<!-- approve-template id=show_rate.preread_email.cleaning_reactivation sha256=04933c3e85b26ab7be043937e7fc03a57aa76e0c160ab180ab2fd067aabc5ef7 -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the reactivation system does
- We take every account that cancelled, stopped renewing, or never closed, and run a short email plus text sequence to each one under your name.
- The messages are timed to when a facility manager actually re-bids janitorial (budget season, a bad month with the current vendor, a lease change), not "checking in."
- Anyone who bites lands straight on your calendar as a walkthrough or a call. You never chase.

What it costs
- $0 up front. I take 20 to 30% of the first-year contract value on accounts that come back, a smaller cut on bigger lists, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more lost or dormant accounts, or lost proposals, with a contact name and email. A CSV export from your CRM or accounting system is fine.
- Ten minutes on the call to tell me which accounts you would actually want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many accounts have you lost or let go quiet in the last three years?
2. What does a typical account bill per year?
3. Who on your side signs off if we move forward today?

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the reactivation system does
- We take every account that cancelled, stopped renewing, or never closed, and run a short email plus text sequence to each one under your name.
- The messages are timed to when a facility manager actually re-bids janitorial (budget season, a bad month with the current vendor, a lease change), not "checking in."
- Anyone who bites lands straight on your calendar as a walkthrough or a call. You never chase.

What it costs
- $0 up front. I take 20 to 30% of the first-year contract value on accounts that come back, a smaller cut on bigger lists, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more lost or dormant accounts, or lost proposals, with a contact name and email. A CSV export from your CRM or accounting system is fine.
- Ten minutes on the call to tell me which accounts you would actually want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many accounts have you lost or let go quiet in the last three years?
2. What does a typical account bill per year?
3. Who on your side signs off if we move forward today?

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the reactivation system does
- We take every account that cancelled, stopped renewing, or never closed, and run a short email plus text sequence to each one under your name.
- The messages are timed to when a facility manager actually re-bids janitorial (budget season, a bad month with the current vendor, a lease change), not "checking in."
- Anyone who bites lands straight on your calendar as a walkthrough or a call. You never chase.

What it costs
- $0 up front. I take 20 to 30% of the first-year contract value on accounts that come back, a smaller cut on bigger lists, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more lost or dormant accounts, or lost proposals, with a contact name and email. A CSV export from your CRM or accounting system is fine.
- Ten minutes on the call to tell me which accounts you would actually want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many accounts have you lost or let go quiet in the last three years?
2. What does a typical account bill per year?
3. Who on your side signs off if we move forward today?

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.cleaning_outbound`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/outbound.
- sha256: `c7281457e1619768aa0beb83162739f685519e0746eecf953ad5e521b6df8bb6`

<!-- approve-template id=show_rate.preread_email.cleaning_outbound sha256=c7281457e1619768aa0beb83162739f685519e0746eecf953ad5e521b6df8bb6 -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the system does
- We watch the events that put a building in the market for a new janitorial vendor: a new lease signed, an office expansion, a property manager change, a new build coming online in your service area.
- The moment one of those fires, the building gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who bites lands straight on your calendar as a walkthrough. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your service area, and the guarantee covers it.
- The guarantee: $24,000 a year in new cleaning contracts signed within 90 days, or you get your money back plus a $200 steakhouse gift card.

What I need from you to start
- Your service area and the building types your crews are actually set up for.
- Ten minutes on the call to tell me which buildings you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical account bill per year for you?
2. How many buildings can your crews take on in the next 90 days?
3. Who on your side signs off if we move forward today?

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the system does
- We watch the events that put a building in the market for a new janitorial vendor: a new lease signed, an office expansion, a property manager change, a new build coming online in your service area.
- The moment one of those fires, the building gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who bites lands straight on your calendar as a walkthrough. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your service area, and the guarantee covers it.
- The guarantee: $24,000 a year in new cleaning contracts signed within 90 days, or you get your money back plus a $200 steakhouse gift card.

What I need from you to start
- Your service area and the building types your crews are actually set up for.
- Ten minutes on the call to tell me which buildings you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical account bill per year for you?
2. How many buildings can your crews take on in the next 90 days?
3. Who on your side signs off if we move forward today?

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the system does
- We watch the events that put a building in the market for a new janitorial vendor: a new lease signed, an office expansion, a property manager change, a new build coming online in your service area.
- The moment one of those fires, the building gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who bites lands straight on your calendar as a walkthrough. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your service area, and the guarantee covers it.
- The guarantee: $24,000 a year in new cleaning contracts signed within 90 days, or you get your money back plus a $200 steakhouse gift card.

What I need from you to start
- Your service area and the building types your crews are actually set up for.
- Ten minutes on the call to tell me which buildings you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical account bill per year for you?
2. How many buildings can your crews take on in the next 90 days?
3. Who on your side signs off if we move forward today?

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.bookkeeping_reactivation`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: bookkeeping/reactivation.
- sha256: `f057a4ebe02ef9ccb49d5a11e5c741ba461d46d338c6c795dfd873290539070b`

<!-- approve-template id=show_rate.preread_email.bookkeeping_reactivation sha256=f057a4ebe02ef9ccb49d5a11e5c741ba461d46d338c6c795dfd873290539070b -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the reactivation system does
- We take your lost inquiries and former clients and run a short email plus text sequence to each one under your name.
- The messages are timed to the moments they actually hire a bookkeeper again: tax season, quarterly estimates, year-end cleanup, a new entity.
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- $0 up front. I take 20 to 30% of first-year fees from clients brought back, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more former clients or lost inquiries with a name and email. An export from your practice management tool or QuickBooks customer list works.
- Ten minutes on the call to flag the ones you would want back and the ones you would not.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many clients or inquiries have gone quiet in the last three years?
2. What does a typical client pay you per year?
3. Who signs off if we move forward today?

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the reactivation system does
- We take your lost inquiries and former clients and run a short email plus text sequence to each one under your name.
- The messages are timed to the moments they actually hire a bookkeeper again: tax season, quarterly estimates, year-end cleanup, a new entity.
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- $0 up front. I take 20 to 30% of first-year fees from clients brought back, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more former clients or lost inquiries with a name and email. An export from your practice management tool or QuickBooks customer list works.
- Ten minutes on the call to flag the ones you would want back and the ones you would not.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many clients or inquiries have gone quiet in the last three years?
2. What does a typical client pay you per year?
3. Who signs off if we move forward today?

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the reactivation system does
- We take your lost inquiries and former clients and run a short email plus text sequence to each one under your name.
- The messages are timed to the moments they actually hire a bookkeeper again: tax season, quarterly estimates, year-end cleanup, a new entity.
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- $0 up front. I take 20 to 30% of first-year fees from clients brought back, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more former clients or lost inquiries with a name and email. An export from your practice management tool or QuickBooks customer list works.
- Ten minutes on the call to flag the ones you would want back and the ones you would not.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many clients or inquiries have gone quiet in the last three years?
2. What does a typical client pay you per year?
3. Who signs off if we move forward today?

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.bookkeeping_outbound`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: bookkeeping/outbound.
- sha256: `a885d306b9cc52944da08fbacb4b08ff885ea21fa3c564162f6986a323e90a10`

<!-- approve-template id=show_rate.preread_email.bookkeeping_outbound sha256=a885d306b9cc52944da08fbacb4b08ff885ea21fa3c564162f6986a323e90a10 -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the system does
- We watch the events that put a business in the market for a bookkeeper: a new entity formed, a part-time bookkeeper or admin role posted, a second location opening.
- The moment one of those fires, that owner gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who responds lands straight on your calendar as a discovery call. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it.
- The guarantee: $15,000 in new annual client fees within 90 days, or you get your money back plus a $200 gift card.

What I need from you to start
- Your target client profile: entity size, industries you are good at, and the geography you want.
- Ten minutes on the call to tell me which clients you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical client pay you per year?
2. How many new clients can you onboard in the next 90 days?
3. Who signs off if we move forward today?

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the system does
- We watch the events that put a business in the market for a bookkeeper: a new entity formed, a part-time bookkeeper or admin role posted, a second location opening.
- The moment one of those fires, that owner gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who responds lands straight on your calendar as a discovery call. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it.
- The guarantee: $15,000 in new annual client fees within 90 days, or you get your money back plus a $200 gift card.

What I need from you to start
- Your target client profile: entity size, industries you are good at, and the geography you want.
- Ten minutes on the call to tell me which clients you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical client pay you per year?
2. How many new clients can you onboard in the next 90 days?
3. Who signs off if we move forward today?

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the system does
- We watch the events that put a business in the market for a bookkeeper: a new entity formed, a part-time bookkeeper or admin role posted, a second location opening.
- The moment one of those fires, that owner gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who responds lands straight on your calendar as a discovery call. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it.
- The guarantee: $15,000 in new annual client fees within 90 days, or you get your money back plus a $200 gift card.

What I need from you to start
- Your target client profile: entity size, industries you are good at, and the geography you want.
- Ten minutes on the call to tell me which clients you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical client pay you per year?
2. How many new clients can you onboard in the next 90 days?
3. Who signs off if we move forward today?

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.recruiting_reactivation`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: recruiting/reactivation.
- sha256: `de28181298e8198cf4137eee2cbcc5048ca0fab8878d26d9b7b8319367282b53`

<!-- approve-template id=show_rate.preread_email.recruiting_reactivation sha256=de28181298e8198cf4137eee2cbcc5048ca0fab8878d26d9b7b8319367282b53 -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the reactivation system does
- We take your dormant and near-miss client accounts, the hiring managers who used you once or almost did, and run a short email plus text sequence to each one under your name.
- The messages are timed to when they are actually hiring again: a new role posted, a team expanding, a competitor's placement falling through.
- Anyone who responds lands straight on your calendar as an intro call. You never chase.

What it costs
- $0 up front. I take a percentage of the placement fees from accounts brought back (20 to 30% of the first placement fee), and $0 if nothing closes.

What I need from you to start
- A list of 60 or more dormant client accounts with a hiring manager name and email. An ATS or CRM export is fine.
- Ten minutes on the call to tell me which accounts and specialties you want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many client accounts have gone quiet in the last two years?
2. What does a typical placement fee look like for you?
3. Who signs off if we move forward today?

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the reactivation system does
- We take your dormant and near-miss client accounts, the hiring managers who used you once or almost did, and run a short email plus text sequence to each one under your name.
- The messages are timed to when they are actually hiring again: a new role posted, a team expanding, a competitor's placement falling through.
- Anyone who responds lands straight on your calendar as an intro call. You never chase.

What it costs
- $0 up front. I take a percentage of the placement fees from accounts brought back (20 to 30% of the first placement fee), and $0 if nothing closes.

What I need from you to start
- A list of 60 or more dormant client accounts with a hiring manager name and email. An ATS or CRM export is fine.
- Ten minutes on the call to tell me which accounts and specialties you want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many client accounts have gone quiet in the last two years?
2. What does a typical placement fee look like for you?
3. Who signs off if we move forward today?

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the reactivation system does
- We take your dormant and near-miss client accounts, the hiring managers who used you once or almost did, and run a short email plus text sequence to each one under your name.
- The messages are timed to when they are actually hiring again: a new role posted, a team expanding, a competitor's placement falling through.
- Anyone who responds lands straight on your calendar as an intro call. You never chase.

What it costs
- $0 up front. I take a percentage of the placement fees from accounts brought back (20 to 30% of the first placement fee), and $0 if nothing closes.

What I need from you to start
- A list of 60 or more dormant client accounts with a hiring manager name and email. An ATS or CRM export is fine.
- Ten minutes on the call to tell me which accounts and specialties you want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

The three questions I will ask
1. How many client accounts have gone quiet in the last two years?
2. What does a typical placement fee look like for you?
3. Who signs off if we move forward today?

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.recruiting_outbound`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: recruiting/outbound.
- sha256: `9b1ed89e7f9f0a96474edc14f11940e3d61c8a0e653620d8570379bbcfb06fbd`

<!-- approve-template id=show_rate.preread_email.recruiting_outbound sha256=9b1ed89e7f9f0a96474edc14f11940e3d61c8a0e653620d8570379bbcfb06fbd -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the system does
- We watch the job boards for roles opening in your specialty, so we reach a hiring manager in the days after the role goes live and before they have committed to anyone.
- Each one gets a short email plus text sequence under your agency's name, written the way you would write it.
- Anyone who responds lands straight on your calendar as an intro call. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it.
- The guarantee: $40,000 in new placement fees within 180 days, or you get your money back plus a $200 gift card.

What I need from you to start
- The specialty and the geography you want roles watched in.
- Ten minutes on the call to tell me which roles you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical placement fee look like for you?
2. How many roles can your recruiters work in the next 90 days?
3. Who signs off if we move forward today?

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the system does
- We watch the job boards for roles opening in your specialty, so we reach a hiring manager in the days after the role goes live and before they have committed to anyone.
- Each one gets a short email plus text sequence under your agency's name, written the way you would write it.
- Anyone who responds lands straight on your calendar as an intro call. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it.
- The guarantee: $40,000 in new placement fees within 180 days, or you get your money back plus a $200 gift card.

What I need from you to start
- The specialty and the geography you want roles watched in.
- Ten minutes on the call to tell me which roles you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical placement fee look like for you?
2. How many roles can your recruiters work in the next 90 days?
3. Who signs off if we move forward today?

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the system does
- We watch the job boards for roles opening in your specialty, so we reach a hiring manager in the days after the role goes live and before they have committed to anyone.
- Each one gets a short email plus text sequence under your agency's name, written the way you would write it.
- Anyone who responds lands straight on your calendar as an intro call. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it.
- The guarantee: $40,000 in new placement fees within 180 days, or you get your money back plus a $200 gift card.

What I need from you to start
- The specialty and the geography you want roles watched in.
- Ten minutes on the call to tell me which roles you would take tomorrow and which ones you would pass on.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

The three questions I will ask
1. What does a typical placement fee look like for you?
2. How many roles can your recruiters work in the next 90 days?
3. Who signs off if we move forward today?

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.generic_reactivation`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: generic/reactivation.
- sha256: `48a59b2c6487aaea5caf9dc33b0d9038e74d50616f78bb2d0159ea591b836ae9`

<!-- approve-template id=show_rate.preread_email.generic_reactivation sha256=48a59b2c6487aaea5caf9dc33b0d9038e74d50616f78bb2d0159ea591b836ae9 -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the reactivation system does
- We take every account that went quiet, cancelled, or never closed and run a short email plus text sequence to each one under your name.
- The messages are timed to the moments those accounts actually buy again, not "checking in."
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- $0 up front. I take 20 to 30% of the first-year value on accounts that come back, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more lost or dormant accounts with a name and email.
- Ten minutes on the call to tell me which ones you would actually want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the reactivation system does
- We take every account that went quiet, cancelled, or never closed and run a short email plus text sequence to each one under your name.
- The messages are timed to the moments those accounts actually buy again, not "checking in."
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- $0 up front. I take 20 to 30% of the first-year value on accounts that come back, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more lost or dormant accounts with a name and email.
- Ten minutes on the call to tell me which ones you would actually want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the reactivation system does
- We take every account that went quiet, cancelled, or never closed and run a short email plus text sequence to each one under your name.
- The messages are timed to the moments those accounts actually buy again, not "checking in."
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- $0 up front. I take 20 to 30% of the first-year value on accounts that come back, and $0 if nothing closes.

What I need from you to start
- A list of 60 or more lost or dormant accounts with a name and email.
- Ten minutes on the call to tell me which ones you would actually want back.

Proof
- I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.preread_email.generic_outbound`

- status: unapproved
- variables: `{first_name}`, `{when_ct}`, `{company}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: generic/outbound.
- sha256: `8199557d5f067d49df4f546ec6ffb0e4d45836d6bc2c791a4fafcd32823ab398`

<!-- approve-template id=show_rate.preread_email.generic_outbound sha256=8199557d5f067d49df4f546ec6ffb0e4d45836d6bc2c791a4fafcd32823ab398 -->

```text
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on {when_ct}, so the call itself can be about {company} and not about me.

What the system does
- We watch for the events that put a buyer in the market for what you sell, so we reach them in the window where they are actually deciding.
- Each one gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your market. The guarantee is a set amount of new signed business within a fixed window, which I will size for you on the call. If we miss it, you get your money back plus a $200 gift card.

What I need from you to start
- The market you want watched: who the buyer is, where they are, and what you will not take.
- Ten minutes on the call to tell me which accounts you would take tomorrow.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Before our call: the one-page version

Hey there, here is the short version of what I will walk through on {when_ct}, so the call itself can be about your business and not about me.

What the system does
- We watch for the events that put a buyer in the market for what you sell, so we reach them in the window where they are actually deciding.
- Each one gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your market. The guarantee is a set amount of new signed business within a fixed window, which I will size for you on the call. If we miss it, you get your money back plus a $200 gift card.

What I need from you to start
- The market you want watched: who the buyer is, where they are, and what you will not take.
- Ten minutes on the call to tell me which accounts you would take tomorrow.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Before our call: the one-page version

Hey {first_name}, here is the short version of what I will walk through on Tue, Jan 8 at 1:47pm CT (2:47pm ET), so the call itself can be about {company} and not about me.

What the system does
- We watch for the events that put a buyer in the market for what you sell, so we reach them in the window where they are actually deciding.
- Each one gets a short email plus text sequence under your name, written the way you would write it.
- Anyone who responds lands straight on your calendar. You never chase.

What it costs
- Setup plus a monthly retainer, sized to your market. The guarantee is a set amount of new signed business within a fixed window, which I will size for you on the call. If we miss it, you get your money back plus a $200 gift card.

What I need from you to start
- The market you want watched: who the buyer is, where they are, and what you will not take.
- Ten minutes on the call to tell me which accounts you would take tomorrow.

Proof
- I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.reminder_24h_sms`

- status: unapproved
- variables: `{first_name}`, `{time_ct}`, `{company}`, `{booking_url}`
- variants: missing_lead_data, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound. SMS bodies are cut at 320 characters.
- sha256: `45f738e41afc197c423462b0a6b43301d6a6a301ffefb0f12e0833cfa1c76dec`

<!-- approve-template id=show_rate.reminder_24h_sms sha256=45f738e41afc197c423462b0a6b43301d6a6a301ffefb0f12e0833cfa1c76dec -->

```text
Hey {first_name}, Lorenzo here. We are on tomorrow at {time_ct} for the 15-min call about {company}. Reply C to confirm, or grab a new time: {booking_url}

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there, Lorenzo here. We are on tomorrow at {time_ct} for the 15-min call about your business. Reply C to confirm, or grab a new time: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.reminder_24h_email`

- status: unapproved
- variables: `{time_ct}`, `{first_name}`, `{when_ct}`, `{company}`, `{booking_url}`
- variants: missing_lead_data, lead_in_other_timezone, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `f580e768b66756a5b4f3e080868b7e26dd02b182b6a49e38c0ee60f7b822da97`

<!-- approve-template id=show_rate.reminder_24h_email sha256=f580e768b66756a5b4f3e080868b7e26dd02b182b6a49e38c0ee60f7b822da97 -->

```text
Subject: Tomorrow at {time_ct}, still good?

Hey {first_name},

We are on for tomorrow, {when_ct}. Reply C to confirm and I will have everything ready for {company}.

If the time no longer works, grab a new one here instead: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Tomorrow at {time_ct}, still good?

Hey there,

We are on for tomorrow, {when_ct}. Reply C to confirm and I will have everything ready for your business.

If the time no longer works, grab a new one here instead: {booking_url}

Lorenzo

=== variant: lead_in_other_timezone (the lead wrote in another timezone (example times)) ===
Subject: Tomorrow at 1:47pm CT, still good?

Hey {first_name},

We are on for tomorrow, Tue, Jan 8 at 1:47pm CT (2:47pm ET). Reply C to confirm and I will have everything ready for {company}.

If the time no longer works, grab a new one here instead: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.reminder_1h_sms`

- status: unapproved
- variables: `{first_name}`, `{time_ct}`, `{zoom_link}`
- variants: missing_lead_data, no_call_link, value_formats
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound. SMS bodies are cut at 320 characters.
- sha256: `69669370a2316df08d8b04c7654b275a0c9e695bd163d7a741a3b2c3467b5284`

<!-- approve-template id=show_rate.reminder_1h_sms sha256=69669370a2316df08d8b04c7654b275a0c9e695bd163d7a741a3b2c3467b5284 -->

```text
Hey {first_name}, Lorenzo here. Talk in an hour at {time_ct}. Call link: {zoom_link}

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there, Lorenzo here. Talk in an hour at {time_ct}. Call link: {zoom_link}

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Hey {first_name}, Lorenzo here. Talk in an hour at {time_ct}. The link is on your calendar invite.

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `show_rate.reminder_15m_sms`

- status: unapproved
- variables: `{first_name}`, `{zoom_link}`
- variants: missing_lead_data, no_call_link
- source: `services/reply_engine/show_rate.py:render`
- sent from: `services/reply_engine/show_rate.py:render <- schedule_for; sent by show_rate.dispatch_touch (run)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound. SMS bodies are cut at 320 characters.
- sha256: `b1d63cd6078f525ada148c56e358fc15257f5446daa043ce0ef172372d61a204`

<!-- approve-template id=show_rate.reminder_15m_sms sha256=b1d63cd6078f525ada148c56e358fc15257f5446daa043ce0ef172372d61a204 -->

```text
Hey {first_name}, Lorenzo here. Hopping on now: {zoom_link}. See you in a few.

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there, Lorenzo here. Hopping on now: {zoom_link}. See you in a few.

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Hey {first_name}, Lorenzo here. Hopping on now. The link is on your calendar invite. See you in a few.
```

## No-show recovery

### `no_show.ns_still_on_sms`

- status: unapproved
- variables: `{first_name}`, `{zoom_link}`, `{booking_url}`
- variants: missing_lead_data, no_call_link
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `2af91dd279e9a71772e13d3ea0fd3c89cdf975efb62d0e55a695a9bed009d216`

<!-- approve-template id=no_show.ns_still_on_sms sha256=2af91dd279e9a71772e13d3ea0fd3c89cdf975efb62d0e55a695a9bed009d216 -->

```text
Hey {first_name}, Lorenzo here. I am on the call now: {zoom_link}. I will stay on for 10 more minutes. If today fell apart, grab another time: {booking_url}

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there, Lorenzo here. I am on the call now: {zoom_link}. I will stay on for 10 more minutes. If today fell apart, grab another time: {booking_url}

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Hey {first_name}, Lorenzo here. I am on the call now. The link is on your calendar invite. I will stay on for 10 more minutes. If today fell apart, grab another time: {booking_url}
```

### `no_show.ns_still_on_email`

- status: unapproved
- variables: `{first_name}`, `{zoom_link}`, `{booking_url}`
- variants: missing_lead_data, no_call_link
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `bb0aa9e116680a10653b3be1bd2d78ade946027abeea7c221790a24b76757c11`

<!-- approve-template id=no_show.ns_still_on_email sha256=bb0aa9e116680a10653b3be1bd2d78ade946027abeea7c221790a24b76757c11 -->

```text
Subject: Still on?

Hey {first_name},

Still on? I am on the call now: {zoom_link}

I will stay on for 10 more minutes in case you are running behind. If today fell apart, no worries, grab another time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Still on?

Hey there,

Still on? I am on the call now: {zoom_link}

I will stay on for 10 more minutes in case you are running behind. If today fell apart, no worries, grab another time here: {booking_url}

Lorenzo

=== variant: no_call_link (no call link on file (the sentence says the link is on the calendar invite)) ===
Subject: Still on?

Hey {first_name},

Still on? I am on the call now. The link is on your calendar invite.

I will stay on for 10 more minutes in case you are running behind. If today fell apart, no worries, grab another time here: {booking_url}

Lorenzo
```

### `no_show.ns_reschedule_email`

- status: unapproved
- variables: `{first_name}`, `{time_ct}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `3aaf509bd3c105e76ffff8d482855d430be1643e4b40750548033c52f1ea6dba`

<!-- approve-template id=no_show.ns_reschedule_email sha256=3aaf509bd3c105e76ffff8d482855d430be1643e4b40750548033c52f1ea6dba -->

```text
Subject: Missed you on our call

Hey {first_name},

I was on the line at {time_ct} but did not see you join. No worries, things come up.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

If something changed and this is no longer a fit, just say so and I will close it out.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Missed you on our call

Hey there,

I was on the line at {time_ct} but did not see you join. No worries, things come up.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

If something changed and this is no longer a fit, just say so and I will close it out.

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: Missed you on our call

Hey {first_name},

I was on the line at {time_ct} but did not see you join. No worries, things come up.

Grab any time that suits you here: {booking_url}

If something changed and this is no longer a fit, just say so and I will close it out.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d1_other_channel`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `4530be398f97b988a208a930a0c31a7397841aaa28c5787e41cfdddf8a924706`

<!-- approve-template id=no_show.ns_d1_other_channel sha256=4530be398f97b988a208a930a0c31a7397841aaa28c5787e41cfdddf8a924706 -->

```text
Hey {first_name}, Lorenzo again. Still happy to walk through the plan for {company}. Two times that work on my side: {slots}. Or grab any time here: {booking_url}

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Hey there, Lorenzo again. Still happy to walk through the plan for your business. Two times that work on my side: {slots}. Or grab any time here: {booking_url}

=== variant: no_slots (no free slot to offer) ===
Hey {first_name}, Lorenzo again. Still happy to walk through the plan for {company}. Grab any time that suits you here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.cleaning_reactivation`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation.
- sha256: `bb070897cd5555f58f9afa14806f29deaebfbdb0ba29e1e869f33ca82898fc49`

<!-- approve-template id=no_show.ns_d3_value_email.cleaning_reactivation sha256=bb070897cd5555f58f9afa14806f29deaebfbdb0ba29e1e869f33ca82898fc49 -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: email and text sequences to every account that cancelled or went quiet, timed to when they re-bid, with the ready ones landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For your business the first step is the same: email and text sequences to every account that cancelled or went quiet, timed to when they re-bid, with the ready ones landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: email and text sequences to every account that cancelled or went quiet, timed to when they re-bid, with the ready ones landing on your calendar.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.cleaning_outbound`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/outbound.
- sha256: `170fcc4e5c2333ca1e4572cea9ce6a683b2aa38968754157d7dec2266f663466`

<!-- approve-template id=no_show.ns_d3_value_email.cleaning_outbound sha256=170fcc4e5c2333ca1e4572cea9ce6a683b2aa38968754157d7dec2266f663466 -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching new leases, expansions and PM changes in your area and putting walkthroughs on your calendar under your name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For your business the first step is the same: watching new leases, expansions and PM changes in your area and putting walkthroughs on your calendar under your name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching new leases, expansions and PM changes in your area and putting walkthroughs on your calendar under your name.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.bookkeeping_reactivation`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: bookkeeping/reactivation.
- sha256: `ed57112b012fadaefa8db590dfb4bb64add69ab1c1952a1292ff9b1ead216f1b`

<!-- approve-template id=no_show.ns_d3_value_email.bookkeeping_reactivation sha256=ed57112b012fadaefa8db590dfb4bb64add69ab1c1952a1292ff9b1ead216f1b -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: sequences to your lost inquiries and former clients timed to tax season and year-end, with the ready ones landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For your business the first step is the same: sequences to your lost inquiries and former clients timed to tax season and year-end, with the ready ones landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: sequences to your lost inquiries and former clients timed to tax season and year-end, with the ready ones landing on your calendar.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.bookkeeping_outbound`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: bookkeeping/outbound.
- sha256: `2249f2194e753164054b47a9a0850e00e3f728043dab5a8ee097b79295e99425`

<!-- approve-template id=no_show.ns_d3_value_email.bookkeeping_outbound sha256=2249f2194e753164054b47a9a0850e00e3f728043dab5a8ee097b79295e99425 -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching new formations and bookkeeper job posts and putting discovery calls on your calendar under your name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For your business the first step is the same: watching new formations and bookkeeper job posts and putting discovery calls on your calendar under your name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching new formations and bookkeeper job posts and putting discovery calls on your calendar under your name.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.recruiting_reactivation`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: recruiting/reactivation.
- sha256: `3bd9695631250f521d3e2c7ab58b51a49705f59e9707dc24040462eff8238364`

<!-- approve-template id=no_show.ns_d3_value_email.recruiting_reactivation sha256=3bd9695631250f521d3e2c7ab58b51a49705f59e9707dc24040462eff8238364 -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: sequences to your dormant and near-miss client accounts, with the hiring managers who bite landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For your business the first step is the same: sequences to your dormant and near-miss client accounts, with the hiring managers who bite landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: sequences to your dormant and near-miss client accounts, with the hiring managers who bite landing on your calendar.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.recruiting_outbound`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: recruiting/outbound.
- sha256: `bf471ca4ab471887e50515ac707a293b3970e2ec84b9ab48133e4a1eb7be6b18`

<!-- approve-template id=no_show.ns_d3_value_email.recruiting_outbound sha256=bf471ca4ab471887e50515ac707a293b3970e2ec84b9ab48133e4a1eb7be6b18 -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching open roles in your specialty and putting intro calls with hiring managers on your calendar under your agency's name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For your business the first step is the same: watching open roles in your specialty and putting intro calls with hiring managers on your calendar under your agency's name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching open roles in your specialty and putting intro calls with hiring managers on your calendar under your agency's name.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.generic_reactivation`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: generic/reactivation.
- sha256: `9125cebbabe3431efe496bdfbd301325966ab5a387aa65660e6ce6ede32f0774`

<!-- approve-template id=no_show.ns_d3_value_email.generic_reactivation sha256=9125cebbabe3431efe496bdfbd301325966ab5a387aa65660e6ce6ede32f0774 -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: sequences to every account that went quiet, with the ready ones landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For your business the first step is the same: sequences to every account that went quiet, with the ready ones landing on your calendar.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

For {company} the first step is the same: sequences to every account that went quiet, with the ready ones landing on your calendar.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d3_value_email.generic_outbound`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: generic/outbound.
- sha256: `ef20bfabbd1579cda2dcd19292133dc95eaff51497c54f7a614a919c9a87b96e`

<!-- approve-template id=no_show.ns_d3_value_email.generic_outbound sha256=ef20bfabbd1579cda2dcd19292133dc95eaff51497c54f7a614a919c9a87b96e -->

```text
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching for the events that put a buyer in the market and putting those calls on your calendar under your name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: One thing worth knowing before you decide

Hey there,

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For your business the first step is the same: watching for the events that put a buyer in the market and putting those calls on your calendar under your name.

Two times that work on my side: {slots}. Or grab any time here: {booking_url}

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: One thing worth knowing before you decide

Hey {first_name},

Quick thought while this is still on your desk. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

For {company} the first step is the same: watching for the events that put a buyer in the market and putting those calls on your calendar under your name.

Grab any time that suits you here: {booking_url}

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `no_show.ns_d7_yes_no_email`

- status: unapproved
- variables: `{first_name}`, `{company}`, `{booking_url}`
- variants: missing_lead_data
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `3e30605b64e73dad21fc789f0d3dcede5c3444325d101986c504a4d220794ac6`

<!-- approve-template id=no_show.ns_d7_yes_no_email sha256=3e30605b64e73dad21fc789f0d3dcede5c3444325d101986c504a4d220794ac6 -->

```text
Subject: Should I close your file?

Hey {first_name},

I know you were interested enough to book, so I wanted to check in directly before I close things out.

Still want to talk through the plan for {company}, or has the timing changed? Either answer is fine. It just helps me update my notes.

If yes: {booking_url}

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Should I close your file?

Hey there,

I know you were interested enough to book, so I wanted to check in directly before I close things out.

Still want to talk through the plan for your business, or has the timing changed? Either answer is fine. It just helps me update my notes.

If yes: {booking_url}

Lorenzo
```

### `no_show.ns_d14_breakup_email`

- status: unapproved
- variables: `{first_name}`, `{booking_url}`
- variants: missing_lead_data
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound.
- sha256: `6ae8cbf4ba65624a4c374cd46b818c2cd785733f816428befe11dd4e75cf5a17`

<!-- approve-template id=no_show.ns_d14_breakup_email sha256=6ae8cbf4ba65624a4c374cd46b818c2cd785733f816428befe11dd4e75cf5a17 -->

```text
Subject: Closing your file

Hey {first_name},

Have not heard back, so I am going to assume the timing is not right and close out your file for now.

If things change down the road, this link will still work: {booking_url}

Best of luck with everything.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Closing your file

Hey there,

Have not heard back, so I am going to assume the timing is not right and close out your file for now.

If things change down the road, this link will still work: {booking_url}

Best of luck with everything.

Lorenzo
```

### `no_show.ns_reschedule_email.repeat`

- status: unapproved
- variables: `{first_name}`, `{time_ct}`, `{slots}`, `{booking_url}`
- variants: missing_lead_data, no_slots, value_formats
- source: `services/reply_engine/no_show.py:render`
- sent from: `services/reply_engine/no_show.py:render <- recovery_touches; sent by show_rate.dispatch_touch (run_recovery)`
- notes: Applies to: cleaning/reactivation, cleaning/outbound, bookkeeping/reactivation, bookkeeping/outbound, recruiting/reactivation, recruiting/outbound, generic/reactivation, generic/outbound. Second no-show for the same lead.
- sha256: `b24db8d3fb3bc782ff056df1918a5acc873bc258887ed2398edcb82811ec951c`

<!-- approve-template id=no_show.ns_reschedule_email.repeat sha256=b24db8d3fb3bc782ff056df1918a5acc873bc258887ed2398edcb82811ec951c -->

```text
Subject: Missed you on our call

Hey {first_name},

I was on the line at {time_ct} but did not see you join. No worries, things come up.

I know this is the second time the timing did not work out, so if a shorter call or a different day works better, just tell me. Two times that work on my side: {slots}. Or grab any time here: {booking_url}

If something changed and this is no longer a fit, just say so and I will close it out.

Lorenzo

=== variant: missing_lead_data (no first name, company or referral name on file) ===
Subject: Missed you on our call

Hey there,

I was on the line at {time_ct} but did not see you join. No worries, things come up.

I know this is the second time the timing did not work out, so if a shorter call or a different day works better, just tell me. Two times that work on my side: {slots}. Or grab any time here: {booking_url}

If something changed and this is no longer a fit, just say so and I will close it out.

Lorenzo

=== variant: no_slots (no free slot to offer) ===
Subject: Missed you on our call

Hey {first_name},

I was on the line at {time_ct} but did not see you join. No worries, things come up.

I know this is the second time the timing did not work out, so if a shorter call or a different day works better, just tell me. Grab any time that suits you here: {booking_url}

If something changed and this is no longer a fit, just say so and I will close it out.

Lorenzo

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

## First reply: reference pieces (not approved on their own)

### `first_reply.cleaning_reactivation.greeting`

- status: unapproved
- variables: `{first_name}`
- source: `services/reply_engine/draft.py:greeting`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Hey {first_name},
```

### `first_reply.cleaning_reactivation.answer.pricing`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.
```

### `first_reply.cleaning_reactivation.answer.send_info`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.
```

### `first_reply.cleaning_reactivation.answer.mechanism`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.
```

### `first_reply.cleaning_reactivation.answer.other`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Good question. The short version is that I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar. The rest is easier to cover on a quick call.
```

### `first_reply.cleaning_reactivation.answer.referral`

- status: unapproved
- variables: `{referral_name}`, `{referral_first_name}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?
```

### `first_reply.cleaning_reactivation.answer.default`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Glad to hear it. All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.
```

### `first_reply.cleaning_reactivation.slots`

- status: unapproved
- variables: `{slots}`, `{booking_url}`
- variants: value_formats
- source: `services/reply_engine/draft.py:slot_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_reactivation.greeting`

- status: unapproved
- variables: `{first_name}`
- source: `services/reply_engine/draft.py:greeting`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Hey {first_name},
```

### `first_reply.bookkeeping_reactivation.answer.pricing`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.
```

### `first_reply.bookkeeping_reactivation.answer.send_info`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.
```

### `first_reply.bookkeeping_reactivation.answer.mechanism`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. All I need to start is a list of 60 or more former clients or lost inquiries.
```

### `first_reply.bookkeeping_reactivation.answer.other`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Good question. The short version is that I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar. The rest is easier to cover on a quick call.
```

### `first_reply.bookkeeping_reactivation.answer.referral`

- status: unapproved
- variables: `{referral_name}`, `{referral_first_name}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?
```

### `first_reply.bookkeeping_reactivation.answer.default`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Glad to hear it. All I need to start is a list of 60 or more former clients or lost inquiries.
```

### `first_reply.bookkeeping_reactivation.slots`

- status: unapproved
- variables: `{slots}`, `{booking_url}`
- variants: value_formats
- source: `services/reply_engine/draft.py:slot_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_reactivation.greeting`

- status: unapproved
- variables: `{first_name}`
- source: `services/reply_engine/draft.py:greeting`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Hey {first_name},
```

### `first_reply.recruiting_reactivation.answer.pricing`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.
```

### `first_reply.recruiting_reactivation.answer.send_info`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.
```

### `first_reply.recruiting_reactivation.answer.mechanism`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. All I need to start is a list of 60 or more dormant client accounts.
```

### `first_reply.recruiting_reactivation.answer.other`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Good question. The short version is that I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar. The rest is easier to cover on a quick call.
```

### `first_reply.recruiting_reactivation.answer.referral`

- status: unapproved
- variables: `{referral_name}`, `{referral_first_name}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?
```

### `first_reply.recruiting_reactivation.answer.default`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Glad to hear it. All I need to start is a list of 60 or more dormant client accounts.
```

### `first_reply.recruiting_reactivation.slots`

- status: unapproved
- variables: `{slots}`, `{booking_url}`
- variants: value_formats
- source: `services/reply_engine/draft.py:slot_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.cleaning_trigger.greeting`

- status: unapproved
- variables: `{first_name}`
- source: `services/reply_engine/draft.py:greeting`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Hey {first_name},
```

### `first_reply.cleaning_trigger.answer.pricing`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.
```

### `first_reply.cleaning_trigger.answer.send_info`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.
```

### `first_reply.cleaning_trigger.answer.mechanism`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. All I need to start is your service area and the building types you want.
```

### `first_reply.cleaning_trigger.answer.other`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Good question. The short version is that I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar. The rest is easier to cover on a quick call.
```

### `first_reply.cleaning_trigger.answer.referral`

- status: unapproved
- variables: `{referral_name}`, `{referral_first_name}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?
```

### `first_reply.cleaning_trigger.answer.default`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Glad to hear it. All I need to start is your service area and the building types you want.
```

### `first_reply.cleaning_trigger.slots`

- status: unapproved
- variables: `{slots}`, `{booking_url}`
- variants: value_formats
- source: `services/reply_engine/draft.py:slot_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.bookkeeping_trigger.greeting`

- status: unapproved
- variables: `{first_name}`
- source: `services/reply_engine/draft.py:greeting`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Hey {first_name},
```

### `first_reply.bookkeeping_trigger.answer.pricing`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.
```

### `first_reply.bookkeeping_trigger.answer.send_info`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.
```

### `first_reply.bookkeeping_trigger.answer.mechanism`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. All I need to start is the client profile you want more of.
```

### `first_reply.bookkeeping_trigger.answer.other`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Good question. The short version is that I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar. The rest is easier to cover on a quick call.
```

### `first_reply.bookkeeping_trigger.answer.referral`

- status: unapproved
- variables: `{referral_name}`, `{referral_first_name}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?
```

### `first_reply.bookkeeping_trigger.answer.default`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Glad to hear it. All I need to start is the client profile you want more of.
```

### `first_reply.bookkeeping_trigger.slots`

- status: unapproved
- variables: `{slots}`, `{booking_url}`
- variants: value_formats
- source: `services/reply_engine/draft.py:slot_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

### `first_reply.recruiting_outbound.greeting`

- status: unapproved
- variables: `{first_name}`
- source: `services/reply_engine/draft.py:greeting`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Hey {first_name},
```

### `first_reply.recruiting_outbound.answer.pricing`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.
```

### `first_reply.recruiting_outbound.answer.send_info`

- status: unapproved
- variables: `{company}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for {company}.
```

### `first_reply.recruiting_outbound.answer.mechanism`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. All I need to start is your specialty and geography.
```

### `first_reply.recruiting_outbound.answer.other`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Good question. The short version is that I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar. The rest is easier to cover on a quick call.
```

### `first_reply.recruiting_outbound.answer.referral`

- status: unapproved
- variables: `{referral_name}`, `{referral_first_name}`
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Appreciate you pointing me to {referral_name}. Would you mind looping {referral_first_name} in on this thread so I can send the details over?
```

### `first_reply.recruiting_outbound.answer.default`

- status: unapproved
- variables: none
- source: `services/reply_engine/draft.py:answer_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Glad to hear it. All I need to start is your specialty and geography.
```

### `first_reply.recruiting_outbound.slots`

- status: unapproved
- variables: `{slots}`, `{booking_url}`
- variants: value_formats
- source: `services/reply_engine/draft.py:slot_paragraph`
- sent from: `services/reply_engine/draft.py:skeleton (not sent on its own)`
- reference only, not approved on its own

```text
Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}

=== variant: value_formats (how times and slots are written) ===
Example times: Mon Jan 7 9:45, Tue Jan 8 12:05 and Thu Jan 10 16:30, 2030, Central (America/Chicago). This block is the same on every template that has a time or slot in it.
Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT
One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT
A time without its zone, {slot}: Tue 12:05pm | Thu 4:30pm | Mon 9:45am
A counter-proposal that crosses a week, {alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT
The time the lead proposed, in the zone they wrote it in, {asked_time}: America/Chicago = Mon 9:45am CT | America/New_York = Mon 10:45am ET | America/Denver = Mon 8:45am MT | America/Los_Angeles = Mon 7:45am PT
The time the lead proposed, when the counter-proposal crosses a week, {asked_time}: America/Chicago = Mon Jan 7 9:45am CT | America/New_York = Mon Jan 7 10:45am ET | America/Denver = Mon Jan 7 8:45am MT | America/Los_Angeles = Mon Jan 7 7:45am PT
The lead's own time after the call time, {lead_local_time}: America/Chicago = (nothing added) | America/New_York = (1:05pm ET your time) | America/Denver = (11:05am MT your time) | America/Los_Angeles = (10:05am PT your time) | America/Phoenix = (11:05am MST your time)
The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT
The call time when the lead's timezone is known, {when_ct}: America/Chicago = Tue, Jan 8 at 12:05pm CT | America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET) | America/Denver = Tue, Jan 8 at 12:05pm CT (11:05am MT) | America/Los_Angeles = Tue, Jan 8 at 12:05pm CT (10:05am PT) | America/Phoenix = Tue, Jan 8 at 12:05pm CT (11:05am MST)
The clock time only, {time_ct}: 12:05pm CT | 4:30pm CT
Zone labels: America/Chicago = CT | America/New_York = ET | America/Denver = MT | America/Los_Angeles = PT | America/Phoenix = MST
```

## Not in the catalogue

These are not prospect-facing or are never auto-sent by the engine:

- show_rate unconfirmed_task (`services/reply_engine/show_rate.py:render`): a GHL task for Lorenzo; the suggested text inside it is sent by hand from his phone
- no_show ns_call_task and ns_d1_other_channel_task (`services/reply_engine/no_show.py:render`): tasks for Lorenzo with a voicemail script and a suggested text he sends by hand
- cadence day 6 channel_note (`services/reply_engine/cadence.py:build_touch`): a manual second-channel suggestion shown to Lorenzo, not sent by the engine
- booking 'NOT SENT - for Lorenzo' card (`services/reply_engine/booking.py:_unbookable_result`): a card for Lorenzo, never prospect-facing
- GHL appointment title ('Lorenzo <> {company}: 15-min ... plan') (`services/reply_engine/booking.py:book`): the calendar event title GHL shows on the invite; it is not an email body, and the invite itself is released only after the confirmation email is approved and sent
- bodies Lorenzo edits on a card (`services/reply_engine/approval.py:edit`): hand-written text with no template to hash; an edited body is never auto-sent and always goes through a card
- proposals and verbal-commit drafts (`services/reply_engine/proposal.py`): LLM-assembled documents Lorenzo pastes and sends himself; nothing in proposal.py sends
- LLM-polished first replies (`services/reply_engine/draft.py:build_draft`): free text per lead; only the unpolished template (first_reply.*.full) can be approved

## Placeholders

The examples here are a guide only. The exact time and slot formats are in each template's value_formats block, which is approved with it.

- `{alt_slots}`: counter-proposed times, e.g. 'Wed 2:00pm or Thu 3:00pm CT'
- `{asked_time}`: the time the lead proposed, in the zone they wrote it in, e.g. 'Sat 2:00pm CT' or 'Thu 11:00am ET'
- `{booking_url}`: Discovery Call booking link
- `{case_study}`: the offer type's proof line (cadence.d4.case_study.*)
- `{company}`: lead company name (fallback wording is shown in the missing_lead_data variant)
- `{first_name}`: lead first name (each template's missing_lead_data variant shows the fallback wording)
- `{free_work}`: the niche and offer sample-of-work line (cadence.d5.free_work.*)
- `{lead_local_time}`: the call time in the lead's zone, e.g. '3:00pm ET'
- `{loom_url}`: Loom walkthrough URL
- `{original_subject}`: the thread's own subject, reply prefixes stripped
- `{referral_first_name}`: first word of referral_name
- `{referral_name}`: the person the lead referred us to, as written
- `{research_line}`: one LLM-written line about the business (not covered by this approval)
- `{slot}`: one call time, weekday and clock time, e.g. 'Tue 2:00pm'
- `{slot1}`: the held slot with its zone, e.g. 'Tue 2:00pm CT'
- `{slot2}`: the alternative slot with its zone
- `{slots}`: two offered times, e.g. 'Tue 2:00pm or Thu 3:30pm CT'
- `{specialty}`: recruiting specialty from the lead record
- `{time_ct}`: '2:00pm CT'
- `{when_ct}`: 'Tue, Sep 23 at 2:00pm CT' (the lead's local time is added when known; see the timezone variant)
- `{zoom_link}`: the call's join link: Zoom, or the appointment's own Google Meet link on widget bookings (show-rate and no-show: the no_call_link variant shows the wording when none is on file)
