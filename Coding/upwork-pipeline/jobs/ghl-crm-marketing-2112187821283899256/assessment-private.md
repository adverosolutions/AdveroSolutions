# Private content assessment

Job ID: `2112187821283899256`
Spec ID: `ghl-crm-marketing-2112187821283899256`
Source: original `jd.txt` and `intake-private.json` in this folder.

## Fit and scope

The title explicitly names GoHighLevel. The post asks for ongoing CRM and marketing management: lead capture, workflow optimization, email sequences, campaign performance, troubleshooting, and clear independent communication. This spec uses the supported GHL adapter and shows one trace that can be checked when a lead capture or email workflow has a reported issue.

No business name, industry, contact first name, actual form, campaign, workflow defect, send volume, or baseline appears in the post. No personalization is asserted. Client account metadata, contract terms, country, Connects, and activity are private and excluded from visible content.

## Sample path

Jordan Reed submits a website enquiry. Upstream form setup saves the request/source/campaign and applies `website-enquiry`. The displayed workflow starts with **Contact Tag**, configured for **Tag Added = website-enquiry**. This is a trigger that detects the change; it is not an Add Contact Tag action and does not represent a native Form Submitted trigger.

Workflow: Contact Tag → Assign To User (Sam Lee) → Create/Update Opportunity (New enquiry) → Send Email → Wait one day → Send Email follow-up → Wait for reply (up to two days).

The sample has no reply during the first day. Jordan replies to the second email while the final Wait is active. **Stop on Response** is an individual workflow setting, not a workflow action. Enabled, it removes this contact when the contact replies to a message sent from this workflow. The spec does not invent a Customer Replied trigger, Remove From Workflow action, tag action, or automated stage update outside the supported catalog.

After reading the reply, Sam manually moves the opportunity from New enquiry to Conversation active. The displayed result retains the campaign and source and explicitly leaves the opportunity open. There is no fabricated sale or confirmed appointment.

## Evidence and proof treatment

Jordan Reed, Sam Lee, all messages, the campaign, tag, timestamps, and the opportunity are invented sample data. The account is the neutral `CRM workspace`, not a fabricated customer business.

The required result scene includes a visible **Illustrative reply-exit trace**. It is sample proof of the proposed behavior, explicitly not a live execution log, historical delivery, or measured client result. No past-project financial claim was copied from the seed.

Official behavior references checked 2026-10-19:

- Contact Tag trigger: https://help.gohighlevel.com/support/solutions/articles/155000002482-workflow-trigger-contact-tag
- Workflow settings and Stop on Response: https://help.gohighlevel.com/support/solutions/articles/48001239875

The actual form-to-tag mapping, owner rules, sender setup, replies arriving in HighLevel, send timing, DND/unsubscribe handling, and existing overlapping workflows need account review before a live change. These are implementation uncertainties, not claims of a verified defect in this client's system.

## Content checks

- Locked opening caption and 15-minute CTA preserved.
- Colors/font/shared runtime untouched.
- Three directional metrics, definitions, and agreed-baseline note retained; no improvement percentage promised.
- Workflow is the first required scene. Messages and result/proof are required on Quick. Contact detail is optional for Detailed.
- No SMS, price, availability, credentials, client identity, actual performance numbers, or live integration claim.
- No stale Avery, Maya, Ron, Meta, lender, loan, or financial-services content in public spec.
- Self-review completed against original assignment; independent page review remains main's responsibility.

## Validation

Direct `schema.validate` with the current `schema.py` and `platforms.json` passes. Public serialization strips `source`.

The normal `build.py validate` command reported expected shared template drift while the maintenance agent is updating the template lock: `schema.py`, `runtime/components.css`, `runtime/platforms.css`, `runtime/platforms.js`, `runtime/app.js`, and `platforms.json`. No lock or shared file was edited. Main must run the normal build/validation after the approved maintenance lock is ready.

No adapter requirement identified for the scoped sample. No queue commands, generated pages, proposals, commits, approvals, browser, or external writes were performed.
