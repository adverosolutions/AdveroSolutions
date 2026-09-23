# Kickoff nudge email (workflow step 8a)

Sent two days after the kickoff email when the contact does not carry the `kickoff-form-done` tag. **One nudge only.** Step 8b raises a task for Lorenzo instead of a third email, because a client who has not answered twice is a phone call, not another message.

Same sender, same window, same merge fields as `kickoff_email.md`.

---

Subject: Two things still open, {{contact.company_name}}

{{contact.first_name}},

Two days in and the form is still open, so this is a nudge rather than
anything new.

The form: {{custom_values.kickoff_form_url}}

The call: {{custom_values.kickoff_booking_url}}

The only part I genuinely cannot start without is access and the lists.
Everything else on the form can wait until we talk, so if it is easier, fill
in those two sections and leave the rest.

If the hold up is on my side, or something in there does not make sense, tell
me and I will sort it out.

Lorenzo
