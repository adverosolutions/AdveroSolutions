# Kickoff email (workflow step 4)

Sent by the `Client Onboarding: kickoff kit` workflow the moment a deal moves to Won, from `lorenzovillarreal@adverosolutions.com`, plain text, inside the 07:00 to 19:00 America/Chicago window.

Two links and nothing else: the kickoff form and the kickoff booking link. No attachment, no deck, no pricing. The price was agreed on the call and the invoice is a separate step.

Merge fields are GHL's. `{{custom_values.kickoff_form_url}}` and `{{custom_values.kickoff_booking_url}}` are set once at the location level, so a changed link never has to be chased through the workflow.

---

Subject: Welcome aboard, {{contact.company_name}}

{{contact.first_name}},

Good to have you. Here is everything I need from you, and it is short.

First, the form: {{custom_values.kickoff_form_url}}

It asks which accounts I need access to, where the lists live, and what you
never want said in your name. Access to anything with a login comes through a
password manager invite, not typed into a form, and the form says how.

Second, the call: {{custom_values.kickoff_booking_url}}

Forty five minutes, this week if you can. We walk through the form together,
I show you what the first version looks like, and you tell me what is wrong
with it. The clock on your term starts at that call, not today, so there is
no cost to taking a few days.

If the form is back before the call, the call is mostly me showing you
things. If it is not, we fill it in together.

Anything you want to ask before then, reply to this and it comes straight to
me.

Lorenzo
