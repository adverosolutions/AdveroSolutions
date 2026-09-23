"""Source of truth for the Phase 0 copy. Writes sequences/<campaign_key>.json
and subsequence_interested_quiet.json in the exact Instantly shape.

    python3 changesets/instantly_phase0/build_sequences.py          # write files
    python3 changesets/instantly_phase0/build_sequences.py --check  # exit 1 if files are stale

Rules baked in (blueprint M3, offers.md): {{personalization}} first line on
step 1; variant A = live copy with defects fixed, variant B = new angle; step 2
as today; step 3 on day 7 as a new thread with a different proof point; word
level spintax {{RANDOM | a | b | c}} on greeting/opener/CTA/sign-off, 3-5 per
email, never on merge variables; no em dashes; signed Lorenzo.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from changesets.instantly_phase0.phase0_lib import (  # noqa: E402
    SEQUENCES_DIR,
    SETTINGS_PATH,
    SUBSEQUENCE_PATH,
    load_json,
    text_to_html,
)

PROOF_REACT = (
    "I built a similar system for a commercial roofer doing $150M/year. "
    "I recovered about $6M worth of contracts within 6 months."
)
PROOF_OUT = (
    "I recently implemented the same system for a commercial roofer doing $150M/yr "
    "and generated about $180,000 in new contracts in 90 days."
)
PS_LENDER = (
    "P.S. A lender ran the same follow-up mechanics on a $1.5k build and turned it "
    "into a $5M pipeline. Different industry, same math."
)
PS_CONSULTANCY = (
    "P.S. A consultancy running this same outbound setup lifted its reply rate 35%. "
    "Same mechanics, different trade."
)
PS_AGENCY = "P.S. An agency I set this up for went from nothing to $10k/mo on it. Same mechanics."

GREETING = "{{RANDOM | Hey | Hi | Hello}} {{firstName}},"
GREETING2 = "{{RANDOM | Hey | Hi}} {{firstName}},"
BUMP = (
    "{{RANDOM | Checking in, in case the first one got buried. | Bumping this in case it got buried. "
    "| Following up in case my last note slipped through.}} Quick version:"
)
CALL_CTA = (
    "{{RANDOM | Worth a quick 15 minute call? | Open to a quick 15 minute call? "
    "| Want to give it 15 minutes?}} Just reply yes and I'll send a calendar invite."
)
SIGN_BUMP = "{{RANDOM | Thanks for the time, | Appreciate the time, | Thanks,}}\nLorenzo"
SIGN_A = "{{RANDOM | Thanks, | Appreciate it, | Cheers,}}\nLorenzo"
SIGN_B = "{{RANDOM | Thanks, | Appreciate it, | Talk soon,}}\nLorenzo"
SIGN_3 = "{{RANDOM | Thanks, | Appreciate it,}}\nLorenzo"
LAST_ONE = "{{RANDOM | Last one from me on this. | Closing the loop on this. | One more, then I'll leave it alone.}}"
QUICK_ONE = "{{RANDOM | Quick one: | Straight to it: | Here is the short version:}}"
LOW_EFFORT = (
    "{{RANDOM | Easiest way to see if this is worth your time: | Lowest-effort next step: "
    "| If you want a quick read on it:}}"
)
WORTH_CHASING = "{{RANDOM | show you which ones are worth chasing | flag the ones worth chasing | mark which are worth a second run}}"
INVITE = "{{RANDOM | shoot a calendar invite over | send a calendar invite | get an invite over to you}}"

SUBJECT_1 = "{{firstName}}, question"

# M3.3 asks for two variants on every step, not just step 1. These are the
# pieces the step 2 and step 3 B variants are built from (added 2026-09-22).
# Step 2 B drops A's three-bullet recap for a single yes/no question about the
# prospect's own situation and an easy "not now" out. Step 3 B is the takeaway:
# it closes the file instead of pitching a fourth time, and leaves the thread
# as the way back. Neither touches the campaign's one proof point, which stays
# identical across every step and both variants.
ONE_QUESTION = ("{{RANDOM | One question instead of another pitch. | Rather than pitch you again, one question. "
                "| One question, then I will leave it there.}}")
NOT_NOW = ("{{RANDOM | If the timing is wrong, reply 'not now' and I'll come back later in the year. "
           "| If it is not a priority, reply 'not now' and I'll leave it there. "
           "| Wrong quarter for this? Reply 'not now' and I'll check back.}}")
CLOSING_FILE = ("{{RANDOM | I'll close the file on this one. | Closing the file on this one. "
                "| I'll put this down to bad timing and close the file.}}")
DOOR_OPEN = ("{{RANDOM | If that changes, reply here and I'll pick it straight back up. "
             "| If it changes, this thread is the fastest way back to me. "
             "| If that changes later, reply here and I'll pick it up.}}")
PROOF_BUMP_REACT = ("For context: I did this for a commercial roofer doing $150M/yr and recovered about $6M in "
                    "contracts in 6 months.")
PROOF_BUMP_OUT = ("For context: I did this for a commercial roofer doing $150M/yr and generated about $180K in "
                  "new contracts in 90 days.")


def P(*paragraphs):
    return "\n\n".join(paragraphs)


# ----------------------------------------------------------------- cleaning
CLEANING_REACTIVATION = {
    "step1_A": P(
        "{{personalization}}",
        "{{RANDOM | Know this is out of left field, but | Out of left field, I know, but | Odd question, but}} "
        "if I could recover the money from accounts that cancelled or stopped renewing their contracts, in exchange "
        "for a commission on the ones I bring back, would you be open to it? I work mostly on performance and am "
        "building my network.",
        "About me: I build client reactivation systems. " + PROOF_REACT + " "
        "{{RANDOM | Would cost you nothing upfront. | Nothing up front on your end. | Costs you nothing until an account comes back.}}",
        "{{RANDOM | Let me know. | Worth a look? | Open to it?}}",
        SIGN_A,
    ),
    "step1_B": P(
        "{{personalization}}",
        QUICK_ONE + " I build reactivation systems for commercial cleaning companies. " + PROOF_REACT,
        "For {{companyName}} that means email and text sequences to every account that cancelled, stopped renewing, "
        "or never signed after the walkthrough. The ready ones book straight onto your calendar. "
        "{{RANDOM | Nothing up front, I only earn a cut of what comes back. | You pay nothing until an account comes back. "
        "| Commission only, on the accounts I actually bring back.}}",
        LOW_EFFORT + " send me your list of lost bids or former clients and I'll " + WORTH_CHASING + ". "
        "Takes me a day, costs you nothing.",
        SIGN_B,
    ),
    "step2": P(
        GREETING,
        BUMP + "\n"
        "- I want to build a reactivation system for {{companyName}}. Goal is to bring back the accounts that "
        "cancelled or stopped renewing, without you chasing anyone.\n"
        "- I did this for a commercial roofer doing $150M/yr and recovered about $6M in contracts in 6 months.\n"
        "- Nothing up front. I only take a commission on the accounts I bring back.",
        CALL_CTA,
        SIGN_BUMP,
    ),
    "step2_B": P(
        GREETING2,
        ONE_QUESTION + " Does {{companyName}} still have a list of accounts that cancelled or walkthroughs "
        "that never closed, or has someone already worked through it?",
        PROOF_BUMP_REACT + " Same mechanics, applied to your own lost accounts.",
        "Either way the terms do not change. Nothing up front, and I only take a commission on the accounts "
        "that come back.",
        NOT_NOW,
        SIGN_BUMP,
    ),
    "step3": P(
        GREETING2,
        LAST_ONE + " Most cleaning companies I talk to have 20 to 60 proposals from the last two years that never "
        "got a yes or a no. {{RANDOM | That list is usually the fastest money in the building. | Those are the "
        "easiest contracts to win back. | That is where the cheapest revenue sits.}}",
        "I run a follow-up sequence to every one of them under {{companyName}}'s name, and the ones that are ready "
        "book a walkthrough on your calendar. Nothing up front, commission on what comes back.",
        "{{RANDOM | Reply with a rough count of lost bids and I'll tell you what I'd expect to come back. "
        "| Send me roughly how many lost bids you have and I'll give you a realistic recovery number. "
        "| Reply with a rough count and I'll tell you which are worth chasing.}}",
        SIGN_3,
        PS_LENDER,
    ),
    "step3_B": P(
        GREETING2,
        CLOSING_FILE + " No hard feelings if the timing is off.",
        "One thing before I do. The pile of cancelled accounts and lost walkthroughs is the only pipeline you "
        "already paid for, and it gets colder every quarter.",
        "Whenever you want it worked, it is nothing up front and commission only on what comes back.",
        DOOR_OPEN,
        SIGN_3,
        PS_LENDER,
    ),
}

CLEANING_TRIGGER = {
    "step1_A": P(
        "{{personalization}}",
        "I build outbound acquisition systems. " + PROOF_OUT,
        "I do this by watching for triggers (new leases, office expansions, property management changes, new "
        "construction) and running outreach under {{companyName}}'s name. {{RANDOM | All the walkthroughs land "
        "straight on your calendar. | Every walkthrough lands on your calendar. | The walkthroughs go straight onto your calendar.}}",
        "I'm so confident that I guarantee at least $24,000 a year in new cleaning contracts signed within 90 days, "
        "or I give your money back and throw in a $200 gift card to your favorite steakhouse.",
        "{{RANDOM | If this interests you, let's hop on a short 15 minute call. | If that sounds useful, let's do a "
        "short 15 minute call. | Worth a short 15 minute call?}} Just reply Yes and I'll " + INVITE + ".",
        SIGN_A,
    ),
    "step1_B": P(
        "{{personalization}}",
        QUICK_ONE + " I build outbound acquisition systems for commercial cleaning companies. " + PROOF_OUT,
        "For {{companyName}} it looks like this: I watch {{metro}} for new leases, expansions, and property manager "
        "changes at {{buildingType}}, reach those decision makers under your name, and the walkthroughs land on "
        "your calendar. {{RANDOM | You only ever talk to people who already want a quote. | Your team just shows up "
        "to the walkthroughs. | No cold calling on your side.}}",
        "If {{companyName}} doesn't sign at least $24,000 a year in new cleaning contracts within 90 days, I give "
        "your money back and throw in a $200 gift card to your favorite steakhouse.",
        "{{RANDOM | Want me to send over the trigger list I'd start with? | Want to see the first 10 buildings I'd "
        "go after? | Should I send the first batch of triggers I'd work from?}} Reply yes and I'll get it over.",
        SIGN_B,
    ),
    "step2": P(
        GREETING,
        BUMP + "\n"
        "- I want to build an outbound system for {{companyName}}. Goal is to catch businesses signing new leases or "
        "expanding, reach them under your name, and land the walkthroughs on your calendar.\n"
        "- I did this for a commercial roofer doing $150M/yr and generated about $180K in new contracts in 90 days.\n"
        "- If you don't have at least $24K a year in new cleaning contracts signed within 90 days, I give your money "
        "back and throw in a $200 gift card to your favorite steakhouse.",
        CALL_CTA,
        SIGN_BUMP,
    ),
    "step2_B": P(
        GREETING2,
        ONE_QUESTION + " When a building in your service area signs a new lease, does anyone at {{companyName}} "
        "hear about it before the cleaning contract is decided?",
        PROOF_BUMP_OUT,
        "The guarantee does not change either: $24,000 a year in new cleaning contracts within 90 days, or your "
        "money back plus the $200 steakhouse gift card.",
        NOT_NOW,
        SIGN_BUMP,
    ),
    "step3": P(
        GREETING2,
        LAST_ONE + " Every month a set of companies in your area sign a new lease, add a floor, or switch property "
        "managers, and the cleaning contract gets decided in the first few weeks. {{RANDOM | Whoever shows up first "
        "usually wins it. | Most cleaning companies hear about it after the contract is signed. | The first bid in "
        "the door wins more often than the best bid.}}",
        "I catch those signals early, reach the decision maker under {{companyName}}'s name, and the walkthroughs "
        "land on your calendar. Guarantee stands: $24,000 a year in new contracts within 90 days or your money back "
        "plus the steakhouse gift card.",
        "{{RANDOM | Want me to send this week's trigger list for your service area? | Reply with your service area "
        "and I'll send the buildings I'd go after first. | Want the first ten triggers I'd start with?}}",
        SIGN_3,
        PS_CONSULTANCY,
    ),
    "step3_B": P(
        GREETING2,
        CLOSING_FILE + " No hard feelings if the timing is off.",
        "One thing before I do. The buildings signing leases in your area this month will pick a cleaner within "
        "a few weeks, and then that contract is gone for a year or two.",
        "Whenever you want those caught early, the offer and the guarantee are unchanged.",
        DOOR_OPEN,
        SIGN_3,
        PS_CONSULTANCY,
    ),
}

# -------------------------------------------------------------- bookkeeping
BOOKKEEPING_REACTIVATION = {
    "step1_A": P(
        "{{personalization}}",
        "I build client reactivation systems. " + PROOF_REACT,
        "{{RANDOM | TLDR: | Short version: | In plain terms:}} I'd recover lost revenue by building email sequences "
        "that go out to any lost inquiries and former clients, timed to tax season, quarterly estimates, and year-end "
        "cleanup. Booked straight onto your calendar.",
        "I'm so certain this would work for you that I won't charge you a single cent up front, only a percentage of "
        "first-year fees from clients I bring back, $0 if nothing closes. {{RANDOM | I truly believe | I genuinely "
        "think | I'm confident}} I can benefit {{companyName}}.",
        "{{RANDOM | Would you be open to a quick 15 minute call about this? | Open to a quick 15 minute call on it? "
        "| Worth 15 minutes to walk through it?}} If so just say yes and I'll " + INVITE + ".",
        SIGN_A,
    ),
    "step1_B": P(
        "{{personalization}}",
        QUICK_ONE + " I build reactivation systems for bookkeeping and tax firms. " + PROOF_REACT,
        "For {{companyName}} that means sequences to every lost inquiry and former client, timed to tax season, "
        "quarterly estimates, and year-end cleanup, with the ready ones booking straight onto your calendar. "
        "{{RANDOM | Nothing up front, only a percentage of first-year fees on clients who come back. | You pay "
        "nothing until a client comes back. | $0 up front, a cut of first-year fees on what returns.}}",
        LOW_EFFORT + " send me your list of former clients or inquiries that never signed and I'll "
        "{{RANDOM | show you which ones are worth chasing before year-end | flag the ones worth chasing | mark which "
        "are worth a second run}}. Takes me a day, costs you nothing.",
        SIGN_B,
    ),
    "step2": P(
        GREETING,
        BUMP + "\n"
        "- I want to build a reactivation system for {{companyName}}. Goal is to bring back lost inquiries and former "
        "clients with sequences timed to tax season, quarterly estimates, and year-end cleanup.\n"
        "- I did this for a commercial roofer doing $150M/yr and recovered about $6M in contracts in 6 months.\n"
        "- Nothing up front. I only take a percentage of first-year fees on clients I bring back, $0 if nothing closes.",
        CALL_CTA,
        SIGN_BUMP,
    ),
    "step2_B": P(
        GREETING2,
        ONE_QUESTION + " Does {{companyName}} still have last season's lost inquiries and former clients on "
        "file, or has that list gone cold for good?",
        PROOF_BUMP_REACT + " Same mechanics, applied to your old client list.",
        "Either way the terms do not change. Nothing up front, and I only take a percentage of first-year fees "
        "from clients who come back.",
        NOT_NOW,
        SIGN_BUMP,
    ),
    "step3": P(
        GREETING2,
        LAST_ONE + " Every firm I talk to has a stack of people from last tax season who asked for a quote, sent one "
        "document, or filed once and never came back. {{RANDOM | Those are the cheapest clients you'll ever win. "
        "| That list is worth more than any ad budget. | Nobody follows up with them, which is the whole opportunity.}}",
        "Between now and year-end cleanup is the best window to bring them back. I run the sequences under "
        "{{companyName}}'s name and the ones who are ready land on your calendar. $0 up front, a percentage of "
        "first-year fees on whoever returns.",
        "{{RANDOM | Reply with a rough count of former clients and lost inquiries and I'll tell you what I'd expect "
        "back. | Send me roughly how many people went quiet last season and I'll give you a realistic number. "
        "| Reply with a rough count and I'll tell you which are worth chasing.}}",
        SIGN_3,
        PS_LENDER,
    ),
    "step3_B": P(
        GREETING2,
        CLOSING_FILE + " No hard feelings if the timing is off.",
        "One thing before I do. The people who asked for a quote last season and never came back are still the "
        "cheapest clients you could win this year.",
        "Whenever you want that list worked, it is nothing up front and a percentage of first-year fees on "
        "whoever returns.",
        DOOR_OPEN,
        SIGN_3,
        PS_LENDER,
    ),
}

BOOKKEEPING_TRIGGER = {
    "step1_A": P(
        "{{personalization}}",
        "I build outbound acquisition systems. " + PROOF_OUT,
        "I do this by watching for triggers (new business formations, companies posting part time bookkeeper or "
        "admin roles, second location openings) and running outreach under {{companyName}}'s name. {{RANDOM | All "
        "the discovery calls land straight on your calendar. | Every discovery call lands on your calendar. | The "
        "discovery calls go straight onto your calendar.}}",
        "I'm so confident that I guarantee at least $15,000 in new annual client fees signed within 90 days, or I "
        "give your money back and throw in a $200 gift card.",
        "{{RANDOM | If this interests you, let's hop on a short 15 minute call. | If that sounds useful, let's do a "
        "short 15 minute call. | Worth a short 15 minute call?}} Just reply Yes and I'll " + INVITE + ".",
        SIGN_A,
    ),
    "step1_B": P(
        "{{personalization}}",
        QUICK_ONE + " I build outbound acquisition systems for bookkeeping and tax firms. " + PROOF_OUT,
        "For {{companyName}} it looks like this: I watch for new business formations, second locations, and "
        "companies posting part time bookkeeper or admin roles, reach the owner under your name, and the discovery "
        "calls land on your calendar. {{RANDOM | You only talk to people who already need the help. | Your team "
        "just takes the calls. | No prospecting on your side.}}",
        "If {{companyName}} doesn't sign at least $15,000 in new annual client fees within 90 days, I give your "
        "money back and throw in a $200 gift card.",
        "{{RANDOM | Want me to send over the first batch of new filings I'd start with? | Want to see the first 10 "
        "businesses I'd go after? | Should I send the trigger list I'd work from?}} Reply yes and I'll get it over.",
        SIGN_B,
    ),
    "step2": P(
        GREETING,
        BUMP + "\n"
        "- I want to build an outbound system for {{companyName}}. Goal is to catch new business formations and "
        "second locations opening, reach them under your name, and land the discovery calls on your calendar.\n"
        "- I did this for a commercial roofer doing $150M/yr and generated about $180K in new contracts in 90 days.\n"
        "- If you don't have at least $15K in new annual client fees signed within 90 days, I give your money back "
        "and throw in a $200 gift card.",
        CALL_CTA,
        SIGN_BUMP,
    ),
    "step2_B": P(
        GREETING2,
        ONE_QUESTION + " When a new business files in your area, does anyone at {{companyName}} reach the owner "
        "before they pick a bookkeeper?",
        PROOF_BUMP_OUT,
        "The guarantee does not change either: $15,000 in new annual client fees within 90 days, or your money "
        "back plus the $200 gift card.",
        NOT_NOW,
        SIGN_BUMP,
    ),
    "step3": P(
        GREETING2,
        LAST_ONE + " Every week new LLCs get filed in your area and most of them pick a bookkeeper in the first 90 "
        "days, usually whoever reaches them first. {{RANDOM | Almost nobody in your space does that outreach. "
        "| The firms that win them are simply the ones that showed up. | That window closes fast and then they are "
        "someone else's client for years.}}",
        "I watch the filings, reach the owner under {{companyName}}'s name, and the discovery calls land on your "
        "calendar. Guarantee stands: $15,000 in new annual client fees within 90 days or your money back plus the "
        "gift card.",
        "{{RANDOM | Want this week's list of new filings in your area? | Reply with your service area and I'll send "
        "the first businesses I'd go after. | Want the first ten triggers I'd start with?}}",
        SIGN_3,
        PS_CONSULTANCY,
    ),
    "step3_B": P(
        GREETING2,
        CLOSING_FILE + " No hard feelings if the timing is off.",
        "One thing before I do. The businesses filed in your area this month will pick a bookkeeper in the next "
        "90 days, and most of them pick whoever reached them first.",
        "Whenever you want those caught early, the offer and the guarantee are unchanged.",
        DOOR_OPEN,
        SIGN_3,
        PS_CONSULTANCY,
    ),
}

# --------------------------------------------------------------- recruiting
RECRUITING_REACTIVATION = {
    "step1_A": P(
        "{{personalization}}",
        "I build client reactivation systems. " + PROOF_REACT,
        # offers.md's recruiting_reactivation row is "Sequences to dormant and near-miss client
        # accounts" with no text channel, so this line must not promise one (see the channel test
        # in changesets/tests/test_phase0.py).
        "{{RANDOM | TLDR: | Short version: | In plain terms:}} I'd recover lost revenue by building "
        "sequences that go out to any dormant or near-miss client accounts, the companies that used you once or "
        "almost did.",
        "I'm so certain this would work for you that I won't charge you a single cent up front, only a percentage of "
        "placement fees from accounts I bring back, $0 if nothing closes. {{RANDOM | I truly believe | I genuinely "
        "think | I'm confident}} I can benefit {{companyName}}.",
        "{{RANDOM | Would you be open to a quick 15 minute call about this? | Open to a quick 15 minute call on it? "
        "| Worth 15 minutes to walk through it?}} If so just say yes and I'll " + INVITE + ".",
        SIGN_A,
    ),
    "step1_B": P(
        "{{personalization}}",
        QUICK_ONE + " I build reactivation systems for recruiting agencies. " + PROOF_REACT,
        "For {{companyName}} that means sequences to every client account that went quiet, the hiring managers who "
        "used you once and the ones who almost signed, with the ready ones booking straight onto your calendar. "
        "{{RANDOM | Nothing up front, only a percentage of placement fees on accounts that come back. | You pay "
        "nothing until an account places again. | $0 up front, a cut of the placement fee on what returns.}}",
        LOW_EFFORT + " send me your list of dormant client accounts and I'll " + WORTH_CHASING + ". "
        "Takes me a day, costs you nothing.",
        SIGN_B,
    ),
    "step2": P(
        GREETING,
        BUMP + "\n"
        "- I want to build a reactivation system for {{companyName}}. Goal is to bring back the accounts that went "
        "quiet on you, with sequences that run on their own.\n"
        "- I did this for a commercial roofer doing $150M/yr and recovered about $6M in contracts in 6 months.\n"
        "- Nothing up front. I only take a percentage of placement fees on accounts I bring back, $0 if nothing closes.",
        CALL_CTA,
        SIGN_BUMP,
    ),
    "step2_B": P(
        GREETING2,
        ONE_QUESTION + " Does {{companyName}} still have the client accounts that placed once and then went "
        "quiet, or have they been written off?",
        PROOF_BUMP_REACT + " Same mechanics, applied to your dormant accounts.",
        "Either way the terms do not change. Nothing up front, and I only take a percentage of the placement "
        "fees from accounts that come back.",
        NOT_NOW,
        SIGN_BUMP,
    ),
    "step3": P(
        GREETING2,
        LAST_ONE + " Most agencies I talk to have 30 to 100 client accounts that placed once or asked for a search "
        "and then went quiet, and nobody has emailed them in a year. {{RANDOM | Those hiring managers still have "
        "open reqs. | That list is the cheapest pipeline you own. | They already know your name, which is the hard part.}}",
        "I run the sequences under {{companyName}}'s name and the accounts that are hiring again land on your "
        "calendar. $0 up front, a percentage of the placement fee on whoever comes back.",
        "{{RANDOM | Reply with a rough count of quiet accounts and I'll tell you what I'd expect back. | Send me "
        "roughly how many client accounts went quiet and I'll give you a realistic number. | Reply with a rough "
        "count and I'll tell you which are worth chasing.}}",
        SIGN_3,
        PS_LENDER,
    ),
    "step3_B": P(
        GREETING2,
        CLOSING_FILE + " No hard feelings if the timing is off.",
        "One thing before I do. The hiring managers who used {{companyName}} once already trust you, which is "
        "the part that usually takes a year to earn.",
        "Whenever you want those accounts worked, it is nothing up front and a percentage of the placement fee "
        "on whoever comes back.",
        DOOR_OPEN,
        SIGN_3,
        PS_LENDER,
    ),
}

RECRUITING_OUTBOUND = {
    "step1_A": P(
        "{{personalization}}",
        "I build outbound systems for recruiting agencies. " + PROOF_OUT,
        "Here's what this would look like for {{companyName}}: I watch for {{specialty}} roles sitting open on job "
        "boards, run outreach to the hiring managers under your name, and put the intro calls straight on your "
        "calendar.",
        "I'm so confident this works that I guarantee at least $40,000 in new placement fees from those calls within "
        "180 days, or I return your money and throw in a $200 gift card.",
        "{{RANDOM | Open to a quick 15 minute call? | Worth a quick 15 minute call? | Want to give it 15 minutes?}} "
        "Just say yes and I'll " + INVITE + ".",
        SIGN_A,
    ),
    "step1_B": P(
        "{{personalization}}",
        QUICK_ONE + " I build outbound systems for recruiting agencies. " + PROOF_OUT,
        "For {{companyName}} it looks like this: every {{specialty}} role that has sat open on a job board for more "
        "than three weeks is a hiring manager who is stuck. I reach them under your name and the intro calls land on "
        "your calendar. {{RANDOM | You only talk to managers who already have a req. | Your recruiters just take the "
        "calls. | No cold calling on your side.}}",
        "If those calls don't produce at least $40,000 in new placement fees within 180 days, I return your money "
        "and throw in a $200 gift card.",
        "{{RANDOM | Want me to send the open reqs I'd start with? | Want to see the first 10 hiring managers I'd go "
        "after? | Should I send this week's stuck roles in your specialty?}} Reply yes and I'll get it over.",
        SIGN_B,
    ),
    "step2": P(
        GREETING,
        BUMP + "\n"
        "- I want to build an outbound system for {{companyName}}. Goal is to find {{specialty}} roles sitting open "
        "on job boards, reach the hiring managers under your name, and put the intro calls on your calendar.\n"
        "- I did this for a commercial roofer doing $150M/yr and generated about $180K in new contracts in 90 days.\n"
        "- If you don't see $40K in new placement fees within 180 days, I return your money and throw in a $200 gift "
        "card.",
        CALL_CTA,
        SIGN_BUMP,
    ),
    "step2_B": P(
        GREETING2,
        ONE_QUESTION + " When a {{specialty}} role sits open for a month in your market, does anyone at "
        "{{companyName}} call that hiring manager?",
        PROOF_BUMP_OUT,
        "The guarantee does not change either: $40,000 in new placement fees within 180 days, or your money "
        "back plus the $200 gift card.",
        NOT_NOW,
        SIGN_BUMP,
    ),
    "step3": P(
        GREETING2,
        LAST_ONE + " Right now there are {{specialty}} roles in your market that have been open for a month or more. "
        "{{RANDOM | Every one of those is a hiring manager who would take a call from a recruiter this week. | Those "
        "managers are the easiest intro calls you will ever book. | Nobody is calling them, which is the whole opportunity.}}",
        "I pull those reqs weekly, reach the hiring manager under {{companyName}}'s name, and the intro calls land "
        "on your calendar. Guarantee stands: $40,000 in new placement fees within 180 days or your money back plus "
        "the gift card.",
        "{{RANDOM | Want this week's list of stuck reqs in your specialty? | Reply with your specialty and I'll send "
        "the hiring managers I'd go after first. | Want the first ten reqs I'd start with?}}",
        SIGN_3,
        PS_AGENCY,
    ),
    "step3_B": P(
        GREETING2,
        CLOSING_FILE + " No hard feelings if the timing is off.",
        "One thing before I do. Every {{specialty}} req that has been open a month in your market is a hiring "
        "manager who is behind, and nobody is calling them.",
        "Whenever you want those calls booked, the offer and the guarantee are unchanged.",
        DOOR_OPEN,
        SIGN_3,
        PS_AGENCY,
    ),
}

COPY = {
    "cleaning_reactivation": CLEANING_REACTIVATION,
    "cleaning_trigger": CLEANING_TRIGGER,
    "bookkeeping_reactivation": BOOKKEEPING_REACTIVATION,
    "bookkeeping_trigger": BOOKKEEPING_TRIGGER,
    "recruiting_reactivation": RECRUITING_REACTIVATION,
    "recruiting_outbound": RECRUITING_OUTBOUND,
}

# Instantly `delay` on a step = days to wait before the NEXT step (matches the
# live snapshot: both steps carry delay 3 today). Step 1 -> step 2 after 3
# days, step 2 -> step 3 after 4 days (day 7). Verify in the UI preview after
# the first apply (runbooks/phase0.md).
DELAYS = (3, 4, 3)


def _step(delay, variants):
    # delay_unit / pre_delay_unit are on every live step (config/snapshots).
    # PATCH /campaigns replaces `sequences` wholesale, so a step that omits them
    # deletes them from the live object and leaves the unit to a server default.
    return {
        "type": "email",
        "delay": delay,
        "delay_unit": "days",
        "pre_delay_unit": "days",
        "variants": variants,
    }


def build_sequence(copy):
    return {
        "sequences": [
            {
                "steps": [
                    _step(DELAYS[0], [
                        {"subject": SUBJECT_1, "body": text_to_html(copy["step1_A"])},
                        {"subject": SUBJECT_1, "body": text_to_html(copy["step1_B"])},
                    ]),
                    # M3.3: two variants on EVERY step, not only step 1. Step 2
                    # keeps the empty subject on both so it stays in thread, and
                    # step 3 runs both bodies under the same fresh subject, so
                    # the verdict at 500 sends compares bodies and nothing else.
                    _step(DELAYS[1], [
                        {"subject": "", "body": text_to_html(copy["step2"])},
                        {"subject": "", "body": text_to_html(copy["step2_B"])},
                    ]),
                    _step(DELAYS[2], [
                        {"subject": copy["step3_subject"], "body": text_to_html(copy["step3"])},
                        {"subject": copy["step3_subject"], "body": text_to_html(copy["step3_B"])},
                    ]),
                ]
            }
        ]
    }


# ------------------------------------------------------- interested-quiet
# Timing (config/instantly_api_contract.md): on a subsequence `pre_delay` is the
# wait before the FIRST email and `delay` is the wait before the NEXT one. So a
# real D1/D3/D7 is pre_delay 1 on step 1, then delays 2 and 4. Without pre_delay
# the first email fires the moment the lead is moved (day 0 / 1 / 3), which would
# chase a warm positive three times in three days.
QUIET_PRE_DELAY = 1
QUIET_DELAYS = (2, 4, 0)  # step 3 has no next email

# Enrolment is meant to be an explicit move, one lead per call, never an
# auto-condition: Instantly has no "already booked" status on these leads today
# (no lead carries crm_status 2), so a crm_status [1] condition would enrol the
# positives who already hold a discovery call and tell them their slot is gone.
#
# UNVERIFIED, and treated as unverified everywhere a human reads it: neither
# config/instantly_api_contract.md nor the Instantly tool schema says how an
# empty condition set is evaluated. `conditions` is a plain object with no
# required inner keys (tool schema for subsequences_create, read 2026-09-22), so
# `reply_contains` is omitted rather than sent as "": an empty substring is
# contained in every reply, which is the one reading that would enrol the whole
# parent campaign. The two remaining keys are sent as explicit empty lists.
# runbooks/phase0.md go-live step 10 carries the mandatory post-create check
# (GET the new subsequence's lead count, delete it if it is not 0) that settles
# this, and nothing may be created on a second campaign before it passes.
QUIET_CONDITIONS = {"crm_status": [], "lead_activity": []}

# What has to be true of a lead before anyone moves them in. The D1 email opens
# by saying the times that were offered are gone, so a lead who was never
# offered times is told something false.
QUIET_ENROLMENT_PRECONDITION = "slots were offered and went unanswered"

QUIET_SCHEDULE = {
    "start_date": None,
    "end_date": None,
    "schedules": [
        {
            "name": "Weekday mornings CT",
            "timing": {"from": "10:00", "to": "12:00"},
            "days": {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": False},
            "timezone": "America/Chicago",
        }
    ],
}

MOVE_HOW = (
    "POST /leads/subsequence/move {id, subsequence_id}, one call per lead "
    "(shared.instantly.Instantly.move_leads_to_subsequence). There is no `ids` array on this endpoint."
)

# D3 says why the call is worth 15 minutes, in the lead's own business. Keyed on
# niche AND offer: a bookkeeping or recruiting positive must never be told to
# send "the accounts that cancelled or stopped renewing their cleaning contract".
QUIET_WHY = {
    ("cleaning", "reactivation"):
        "Quick reason it's worth 15 minutes: you send me the list of accounts that cancelled, stopped renewing, "
        "or never closed, and I show you which ones are worth chasing and what I'd expect to come back. "
        "Nothing up front, I only earn on what returns.",
    ("bookkeeping", "reactivation"):
        "Quick reason it's worth 15 minutes: you send me the former clients and the inquiries that never closed, "
        "and I show you which ones are worth a run before tax season and what I'd expect to come back. "
        "Nothing up front, I only earn on the fees that come back.",
    ("recruiting", "reactivation"):
        "Quick reason it's worth 15 minutes: you send me the client accounts that have gone dormant and the "
        "searches that never closed, and I show you which ones are worth a run and what I'd expect to come back. "
        "Nothing up front, I only earn on the placements that come from them.",
    ("cleaning", "outbound"):
        "Quick reason it's worth 15 minutes: I'll show you the exact triggers I'd watch for {{companyName}}, the "
        "new leases and office expansions in your service area, what the first month looks like, and how the "
        "guarantee is structured. If it doesn't fit, you'll know in ten minutes.",
    ("bookkeeping", "outbound"):
        "Quick reason it's worth 15 minutes: I'll show you the exact triggers I'd watch for {{companyName}}, the "
        "new business filings and the bookkeeper job posts in your area, what the first month looks like, and how "
        "the guarantee is structured. If it doesn't fit, you'll know in ten minutes.",
    ("recruiting", "outbound"):
        "Quick reason it's worth 15 minutes: I'll show you the exact triggers I'd watch for {{companyName}}, the "
        "roles sitting open on job boards in your specialty, what the first month looks like, and how the "
        "guarantee is structured. If it doesn't fit, you'll know in ten minutes.",
}


def quiet_copy(campaign_key, cfg, ids_campaign, booking_url):
    """Fixed-copy D1/D3/D7 fallback for positives who went quiet. The cadence
    agent (A2, blueprint S2) generates the live version with fresh slots; this
    static subsequence is only what runs if that service is down. This object is
    the single source of truth for the copy AND for the POST /subsequences body;
    changesets/instantly_subsequences/apply_subsequences.py sends exactly this."""
    offer = cfg["offer"]
    niche = ids_campaign.get("niche")
    why = QUIET_WHY[(niche, offer)]
    d1 = P(
        GREETING,
        "{{RANDOM | The times I floated have filled up on my end, so rather than leave you hanging, grab whatever "
        "works here: | Both slots I mentioned went to other calls, so pick any time that suits you here: | I lost "
        "the times I offered, easiest is to grab one that works for you here:}} " + booking_url,
        "{{RANDOM | If none of those fit, reply with a day and I'll make it work. | Or reply with a day and time "
        "and I'll send the invite. | If it's easier, tell me a day and I'll build around it.}}",
        SIGN_3,
    )
    d3 = P(
        GREETING2,
        why,
        "{{RANDOM | Grab a time here and I'll come prepared: | Any slot here works: | Pick whatever is easiest here:}} "
        + booking_url,
        SIGN_3,
    )
    d7 = P(
        GREETING2,
        "{{RANDOM | Should I close your file, or is a different week better? | Want me to close this out, or is "
        "there a better week to pick it up? | Is this a no for now, or just a bad week?}} "
        "{{RANDOM | Either answer is fine, I just don't want to keep landing in your inbox if the timing is off. "
        "| Either way is fine, I'd rather know than keep nudging. | No hard feelings either way.}}",
        "If it's the week, the calendar is here: " + booking_url,
        SIGN_3,
    )
    bodies = [d1, d3, d7]
    steps = []
    for i, body in enumerate(bodies):
        step = {
            "type": "email",
            "delay": QUIET_DELAYS[i],
            "delay_unit": "days",
            "variants": [{"subject": "", "body": text_to_html(body)}],
        }
        if i == 0:
            step["pre_delay"] = QUIET_PRE_DELAY
            step["pre_delay_unit"] = "days"
        steps.append(step)
    return {
        "parent_campaign": cfg["id"],
        "name": "Interested-quiet: %s" % ids_campaign["name"],
        "conditions": dict(QUIET_CONDITIONS),
        "subsequence_schedule": json.loads(json.dumps(QUIET_SCHEDULE)),
        "sequences": [{"steps": steps}],
        "_meta": {
            "campaign_key": campaign_key,
            "niche": niche,
            "offer": offer,
            "enrolment": "manual move only",
            "enrolment_precondition": QUIET_ENROLMENT_PRECONDITION,
            "conditions_semantics": "UNVERIFIED against a live create. No API document states how an empty "
                                    "condition set is evaluated, so the create is not assumed to enrol nobody: "
                                    "runbooks/phase0.md go-live step 10 requires the new subsequence's lead count "
                                    "to be read immediately and the subsequence deleted if it is not 0.",
            "how": MOVE_HOW,
            "send_days": [1, 3, 7],
            "note": "fallback only; services/reply_engine/cadence.py is the real follow-up. "
                    "Keys starting with _ are stripped before the POST.",
        },
    }


def build_all():
    settings = load_json(SETTINGS_PATH)
    ids = load_json(os.path.join(ROOT, "config", "ids.json"))
    booking_url = ids["ghl"]["calendars"]["discovery_call"]["booking_url"]
    seqs = {}
    quiet = {
        "_about": "THE Interested-quiet subsequence: both the copy Lorenzo reviews and the exact POST /subsequences "
                  "body that changesets/instantly_subsequences/apply_subsequences.py sends (keys starting with _ are "
                  "stripped first). Fixed-copy D1/D3/D7 fallback for when services/reply_engine/cadence.py, which owns "
                  "the real fresh-slot follow-up, is down. Field names follow config/instantly_api_contract.md "
                  "(verified 2026-09-21): conditions is required, the schedule key is subsequence_schedule, and "
                  "pre_delay on step 1 is what makes the first email land on day 1 instead of on the move. Leads are "
                  "meant to be enrolled only by an explicit move, one lead per call, and only when slots were "
                  "offered and went unanswered. The conditions object is sent with two empty lists and no "
                  "reply_contains, but HOW INSTANTLY EVALUATES AN EMPTY CONDITION SET IS UNVERIFIED: "
                  "runbooks/phase0.md go-live step 10 requires the new subsequence's enrolled-lead count to be read "
                  "immediately after the first create and the subsequence deleted if it is not 0. "
                  "Nothing is applied until Lorenzo approves.",
        "booking_url_note": ids["ghl"]["calendars"]["discovery_call"].get("booking_url_note", ""),
        "move_endpoint": MOVE_HOW,
        "campaigns": {},
    }
    for key, cfg in settings["campaigns"].items():
        copy = dict(COPY[key])
        copy["step3_subject"] = cfg["step3_subject"]
        seqs[key] = build_sequence(copy)
        quiet["campaigns"][key] = quiet_copy(key, cfg, ids["instantly"]["campaigns"][key], booking_url)
    return seqs, quiet


def _dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main(argv):
    check = "--check" in argv
    seqs, quiet = build_all()
    stale = []
    os.makedirs(SEQUENCES_DIR, exist_ok=True)
    targets = [(os.path.join(SEQUENCES_DIR, "%s.json" % k), v) for k, v in seqs.items()]
    targets.append((SUBSEQUENCE_PATH, quiet))
    for path, obj in targets:
        text = _dump(obj)
        if check:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    if fh.read() != text:
                        stale.append(path)
            except FileNotFoundError:
                stale.append(path)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print("wrote %s" % os.path.relpath(path, ROOT))
    if check:
        if stale:
            print("STALE: %s" % ", ".join(os.path.relpath(p, ROOT) for p in stale))
            return 1
        print("sequences up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
