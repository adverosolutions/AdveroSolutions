# Kickoff form: "Advero Kickoff"

GHL form, built by hand (no create API). One page, grouped, every field's help text written so a client can answer it without a call. Submit sets the contact tag `kickoff-form-done`, which the onboarding workflow's step 8 reads.

Form settings: Sticky contact ON, one submission per contact, redirect to a thank-you page that repeats the kickoff booking link.

## Section 1: who to talk to

| Field | Type | Required | Help text |
| --- | --- | --- | --- |
| Your name | text | yes | prefilled |
| Best email for day to day | email | yes | prefilled |
| Best phone | phone | yes | Texts are fine, say so if they are not |
| Who else should be copied | textarea | no | Name, role, email. Anyone who has to approve what goes out |
| Who has the final yes | text | yes | One name. If it is two people, say both and say who wins |

## Section 2: accounts and access

| Field | Type | Required | Help text |
| --- | --- | --- | --- |
| Website | url | yes | |
| Where your email lives | select | yes | Google Workspace, Microsoft 365, other |
| Domain registrar | select | yes | GoDaddy, Namecheap, Cloudflare, other, not sure. Only needed if we are setting up new sending domains |
| CRM or where the client list lives | select + other | yes | GoHighLevel, HubSpot, Jobber, ServiceTitan, QuickBooks, a spreadsheet, other |
| Calendar to book onto | email | yes | The address of the calendar, not a screenshot |
| Scheduling tool | select | no | Calendly, Acuity, GHL, none |

**Calendar access:** the form asks for the address and the workflow's thank-you page tells them how to share it. For Google, Settings, Share with specific people, add `lorenzovillarreal@adverosolutions.com` with "Make changes to events". Nothing on the form asks them to give a password.

## Section 3: logins

One field, and it is not a password field.

| Field | Type | Required | Help text |
| --- | --- | --- | --- |
| Password manager invite sent to lorenzovillarreal@adverosolutions.com | checkbox | yes | We keep every client credential in a password manager vault, never in email or a form. Use 1Password, Bitwarden or LastPass, whichever you already have, and invite that address to a vault that holds only what this project needs. If you do not use one, tick the box below and we will set the vault up on our side and send you the invite instead |
| I need a vault set up | checkbox | no | |
| What is in the vault | textarea | no | Just the list, for example: Google Workspace admin, the CRM, the domain registrar |

**This is a hard rule, not a preference.** A password typed into a form lands in the CRM database and in the log of every workflow that touches the submission, and there is no way to rotate it afterwards. If a client pushes back, the answer is the vault or a screen share where they type it themselves.

## Section 4: the lists

| Field | Type | Required | Help text |
| --- | --- | --- | --- |
| Export of past and lost customers | file or text | for reactivation | CSV with name, email, phone, the last job or invoice date, and the amount if you have it. Straight out of the CRM is fine, we will clean it |
| How many rows roughly | number | for reactivation | Sixty is the floor for this to be worth running |
| Lost proposals or quotes that never closed | file | no | Same shape. These are usually the best ones |
| Who is off limits | textarea | yes | Current customers, anyone in a dispute, anyone a competitor poached who you do not want reminded of you |
| Service area | text | yes | |
| Who you want more of | textarea | yes | The last three customers you would clone, and why |

## Section 5: voice

| Field | Type | Required | Help text |
| --- | --- | --- | --- |
| Voice file | file upload | yes | Upload three to five things you have actually sent: a quote email, a follow-up, a thank-you note. Screenshots are fine. This is how we end up sounding like you instead of like a vendor |
| Or record two minutes | url | no | Paste a Loom or a voice memo link if writing samples are easier to talk through than to find |
| How you sign off | text | yes | For example "Thanks, Mike" or "Mike Rossi, Man Transformed" |
| First names or full names | radio | yes | |

## Section 6: the do-not-say list

| Field | Type | Required | Help text |
| --- | --- | --- | --- |
| Words and phrases to never use | textarea | yes | Anything that sounds wrong in your trade, any claim you cannot back, any competitor you do not name |
| Promises we must not make | textarea | yes | Timelines, warranties, price guarantees. If you never promise same-day, say so here |
| Compliance or licensing lines that must appear | textarea | no | License numbers, insurance language, anything a regulator expects |
| Anything else that would make you wince | textarea | no | |

The answers become `do-not-say.md` in the client's Drive folder, and they are pasted into the prompt of every draft written for that client. The F3 scorecard carries a line for the week when a draft was rejected for a do-not-say hit, because a rising count means the list is still incomplete.

## Kickoff email (workflow step 4)

Subject: `Getting started, {{contact.company_name}}`

```
{{contact.first_name}},

Good to have you on board. Two things and then I get out of your way.

The first is a short form. It asks for the lists, your calendar, how you sound
in writing, and anything we should never say. It takes about ten minutes and
it is the difference between this sounding like you and sounding like a vendor.

{{form_link}}

The second is the kickoff call. Forty-five minutes, and we go through what you
sent and I show you what the first week looks like.

{{kickoff_booking_link}}

If anything in the form is easier to just tell me, leave it blank and we will
cover it on the call.

Lorenzo
```

## Nudge email (workflow step 8a, two days later, once only)

Subject: `The form, whenever you get a minute`

```
{{contact.first_name}},

Just the form still outstanding. Here it is again.

{{form_link}}

The lists and the do-not-say list are the two that hold things up. The rest I
can fill in from the call.

Lorenzo
```
