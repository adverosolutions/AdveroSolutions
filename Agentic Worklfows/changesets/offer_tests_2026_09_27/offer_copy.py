"""The six bodies of the 2026-09-27 offer tests, exactly as Lorenzo wrote them.

Plain text, one entry per line, one blank line between paragraphs. Nothing
here is rewritten at run time: apply_offer_tests.py renders each body with
phase0_lib.text_to_html and refuses when the HTML does not round-trip back to
this text byte for byte. Straight apostrophes only; the tags are
{{personalization}}, {{firstName}} and {{companyName}} with no spaces inside.

Step 1 carries the subject "{{firstName}}, question"; step 2 carries "" so it
stays in step 1's thread (the parents do the same).
"""
from collections import OrderedDict

STEP1_SUBJECT = "{{firstName}}, question"
STEP2_SUBJECT = ""

CLEANING_CRM_1 = """{{personalization}}

I build CRM and pipeline systems. I built the same kind of system for a commercial roofing contractor that runs $750M+ a year in bids, and none of them get lost to manual chasing.

I do this by setting up one pipeline for {{companyName}} that tracks every inquiry, walkthrough and proposal until it signs. More of the bids you already send would turn into signed contracts.

I'm so confident that I guarantee it pays for itself within 90 days, or I give your money back and throw in a $200 gift card to your favorite steakhouse.

If this interests you, let's hop on a short 15 minute call. Just reply Yes and I can shoot you over a calendar invite.

Thanks,
Lorenzo"""

CLEANING_CRM_2 = """Hey {{firstName}},

Checking in, in case the first one got buried. Quick version:
- I want to build a CRM and pipeline for {{companyName}}. Goal is to track every inquiry, walkthrough and proposal until it signs.
- I built the same kind of system for a commercial roofing contractor that runs $750M+ a year in bids, and none of them get lost to manual chasing.
- If it doesn't pay for itself within 90 days, I give your money back and throw in a $200 gift card to your favorite steakhouse.

Worth a quick 15 minute call? Just reply yes and I'll send a calendar invite.

Thanks for the time,
Lorenzo"""

BOOKKEEPING_BUILD_1 = """{{personalization}}

I build custom systems that take manual work off small teams. I built a similar system for a commercial roofing contractor that runs $750M+ a year in bids, and none of them get lost to manual chasing.

I do this by building {{companyName}} a system that chases clients for missing documents and sorts everything that comes in. Nobody on your team would have to chase paperwork this tax season.

I'm so confident that I guarantee at least 10 hours a week back for your team this tax season, or I give your money back and throw in a $200 gift card to your favorite steakhouse.

If this interests you, let's hop on a short 15 minute call. Just reply Yes and I can shoot you over a calendar invite.

Thanks,
Lorenzo"""

BOOKKEEPING_BUILD_2 = """Hey {{firstName}},

Checking in, in case the first one got buried. Quick version:
- I want to build a system for {{companyName}} that chases clients for missing documents and sorts everything that comes in. Goal is nobody on your team chasing paperwork this tax season.
- I built a similar system for a commercial roofing contractor that runs $750M+ a year in bids, and none of them get lost to manual chasing.
- If it doesn't save your team at least 10 hours a week this tax season, I give your money back and throw in a $200 gift card to your favorite steakhouse.

Worth a quick 15 minute call? Just reply yes and I'll send a calendar invite.

Thanks for the time,
Lorenzo"""

RECRUITING_BUILD_1 = """{{personalization}}

Know this is out of left field, if I could build {{companyName}} custom systems that take the admin off your recruiters so they can spend the day on calls, in exchange for a fee that only starts once they're saving you time, would you be open? I work mostly on performance and am building my network.

About me: I build custom systems for small teams. I built one for a commercial roofing contractor that runs $750M+ a year in bids, and none of them get lost to manual chasing. Would cost you nothing upfront, and if they don't save you at least 10 hours a week within 30 days of going live, I'll send you a $200 gift card to your favorite steakhouse for your time.

Let me know.

Thanks,
Lorenzo"""

RECRUITING_BUILD_2 = """Hey {{firstName}},

Checking in, in case the first one got buried. Quick version:
- I want to build custom systems for {{companyName}} that take the admin off your recruiters. Goal is more of their day on calls.
- I built one for a commercial roofing contractor that runs $750M+ a year in bids, and none of them get lost to manual chasing.
- Nothing up front. The fee only starts once it's saving you time, and if it doesn't save you at least 10 hours a week within 30 days of going live, I'll send you a $200 gift card to your favorite steakhouse.

Worth a quick 15 minute call? Just reply yes and I'll send a calendar invite.

Thanks for the time,
Lorenzo"""

# key -> [(subject, plain-text body) for step 1, step 2]
COPY = OrderedDict([
    ("cleaning_crm", [(STEP1_SUBJECT, CLEANING_CRM_1), (STEP2_SUBJECT, CLEANING_CRM_2)]),
    ("bookkeeping_build", [(STEP1_SUBJECT, BOOKKEEPING_BUILD_1), (STEP2_SUBJECT, BOOKKEEPING_BUILD_2)]),
    ("recruiting_build", [(STEP1_SUBJECT, RECRUITING_BUILD_1), (STEP2_SUBJECT, RECRUITING_BUILD_2)]),
])
