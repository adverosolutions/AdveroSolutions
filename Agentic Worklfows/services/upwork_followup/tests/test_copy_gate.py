"""Copy gate (services/upwork_followup/copy_gate.py): one test per code plus the
edge cases DESIGN "Copy gate" names. Invented clients only."""
import time

import pytest

from services.upwork_followup import copy_gate
from services.upwork_followup.copy_gate import CODES, check
from services.upwork_followup.draft import UPWORK_OFFERS_PATH

OFFERS = UPWORK_OFFERS_PATH.read_text(encoding="utf-8")

POST = ("Brightline Tile needs showroom quote requests from our website form to land in HubSpot. "
        "Right now they sit in a spreadsheet and nobody follows up for days. Example form: "
        "https://brightline-tile.example.org/quote-request")


def room(first_name=None, post=POST, messages=None, job=True):
    r = {
        "room_id": "room_abc123",
        "client": "Brightline Tile",
        "client_first_name": first_name,
        "job_title": "HubSpot intake for tile showroom quotes",
        "messages": messages if messages is not None else [
            {"id": "m1", "side": "client", "at": "2026-09-18T15:00:00Z",
             "text": "Most requests come in with photos of the bathroom."},
            {"id": "m2", "side": "freelancer", "at": "2026-09-18T16:00:00Z", "text": "Thanks, that helps."},
        ],
        "job": {"post": post, "proposal": "", "beats": [], "ask_before_quoting": [], "private_notes": "",
                "loom_url": None, "applied_at": None} if job else None,
    }
    return r


BESPOKE = ("hey, one idea on the showroom quote requests you mentioned: I'd tag each one by tile line the "
           "moment it lands in HubSpot, so whoever picks it up can see the bathroom photos first. "
           "do most requests come from the website form, or do some still arrive by phone?")


def codes(text, kind="touch", r=None, private=()):
    return check(text, kind, r if r is not None else room(), OFFERS, private_texts=private)


def test_bespoke_draft_passes_clean():
    assert codes(BESPOKE) == []


def test_codes_are_stable_unique_and_ordered():
    text = "Hey Dana, just checking in!! We can do $999 \u2014 email me at dana@brightline.example.com [name]"
    out = codes(text)
    assert len(out) == len(set(out))
    assert out == [c for c in CODES if c in out]
    for expected in ("em_dash", "exclamation", "off_platform_contact", "figure_not_in_offers", "placeholder",
                     "first_name_unknown", "not_first_person", "filler_phrase"):
        assert expected in out


def test_empty():
    assert codes("   ") == ["empty"]
    assert codes(None) == ["empty"]


# ---------------------------------------------------------------- characters
@pytest.mark.parametrize("dash", ["\u2014", "\u2013", "\u2015", "\u2012"])
def test_em_and_en_dashes(dash):
    out = codes(BESPOKE.replace(": I'd", " %s I'd" % dash))
    assert "em_dash" in out
    assert "non_ascii" not in out  # a dash is reported once, as a dash


def test_exclamation():
    assert "exclamation" in codes(BESPOKE + " Excited to help!")


def test_smart_quotes_are_normalised_not_refused():
    smart = BESPOKE.replace("I'd", "I\u2019d") + " you said \u201cwe lose leads over the weekend\u201d, noted."
    assert codes(smart) == []


@pytest.mark.parametrize("ch", ["\U0001F44B", "\u00e9", "\u2026", "\u00a0"])
def test_non_ascii(ch):
    assert "non_ascii" in codes(BESPOKE + " ok" + ch)


def test_too_long_touch_vs_reply():
    long_touch = BESPOKE + " " + ("the HubSpot showroom routing " * 40)
    assert len(long_touch) > 900
    assert "too_long" in codes(long_touch, "touch")
    assert "too_long" in codes(long_touch, "checkin")
    assert "too_long" not in codes(long_touch[:1400], "reply")
    assert "too_long" in codes(long_touch + ("x " * 400), "reply")


# ---------------------------------------------------------------- contact
@pytest.mark.parametrize("contact", [
    "dana@brightline-tile.com",
    "dana.w+tile@mail.example.co.uk",
    "dana at gmail dot com",
    "(512) 555-0142",
    "512-555-0142",
    "512.555.0142",
    "+1 512 555 0142",
    "5125550142",
    "+44 20 7946 0958",
    "555-0142",
])
def test_email_and_phone_formats(contact):
    assert "off_platform_contact" in codes(BESPOKE + " reach me: " + contact)


@pytest.mark.parametrize("word", ["WhatsApp", "whatsapp", "WHATSAPP", "Whats App", "Telegram", "telegram",
                                  "Skype", "Calendly", "text me", "Email me", "call me at", "outside of Upwork",
                                  "pay via PayPal"])
def test_banned_off_platform_words_any_case(word):
    assert "off_platform_contact" in codes(BESPOKE + " also, %s works." % word)


@pytest.mark.parametrize("safe", ["$10,000 a month", "on 2026-09-22", "about 3,300x", "at 12:00 CT"])
def test_numbers_that_are_not_phone_numbers(safe):
    assert "off_platform_contact" not in codes(BESPOKE + " " + safe)


# ---------------------------------------------------------------- links
@pytest.mark.parametrize("link", ["https://www.loom.com/share/abc123def", "loom.com/share/abc123def",
                                  "https://loom.com/share/abc123def?sid=9"])
def test_loom_links_allowed(link):
    assert "external_link" not in codes(BESPOKE + " the walkthrough: " + link)


def test_job_post_url_allowed_other_urls_refused():
    assert "external_link" not in codes(BESPOKE + " on https://brightline-tile.example.org/quote-request.")
    assert "external_link" in codes(BESPOKE + " see https://tilecrm.example.net/demo")
    assert "external_link" in codes(BESPOKE + " built on make.com")
    r = room(post=POST + " We use make.com today.")
    assert "external_link" not in codes(BESPOKE + " built on make.com", r=r)


def test_upwork_links_always_refused_even_in_the_post():
    r = room(post=POST + " https://www.upwork.com/jobs/~02abc")
    assert "external_link" in codes(BESPOKE + " https://www.upwork.com/jobs/~02abc", r=r)
    assert "external_link" in codes(BESPOKE + " upwork.com/messages")


def test_email_is_not_also_read_as_a_link():
    out = codes(BESPOKE + " dana@brightline-tile.com")
    assert "off_platform_contact" in out and "external_link" not in out


# ---------------------------------------------------------------- figures
PROOF_LINES = [ln.strip() for ln in OFFERS.splitlines() if "$" in ln or "%" in ln]


def test_offers_file_has_the_four_proof_lines():
    assert len(PROOF_LINES) == 4


@pytest.mark.parametrize("line", PROOF_LINES)
def test_verbatim_proof_lines_pass(line):
    assert "figure_not_in_offers" not in codes(BESPOKE + " " + line)


@pytest.mark.parametrize("sentence", [
    "I built a routing system for a commercial roofing contractor that now carries $750M+ in annual bid volume.",
    "For a lender I generated $5M in loan applications on $1,500 of ad spend.",
    "I grew a software consultancy's qualified lead volume 35 percent with outbound.",
    "I grew a software consultancy's qualified lead volume thirty-five percent with outbound.",
    "I scaled my own AI agency to $10k a month on the same kind of system.",
    "For a lender I generated $5M in loan applications on $1500 of ad spend.",
])
def test_paraphrased_proof_statements_pass(sentence):
    assert "figure_not_in_offers" not in codes(BESPOKE + " " + sentence)


@pytest.mark.parametrize("figure", ["$750M+", "$5M", "$1,500", "$10,000", "35%", "35 percent", "3,300x"])
def test_proof_figures_outside_their_statement_are_refused(figure):
    assert "figure_not_in_offers" in codes(BESPOKE + " That's %s." % figure)


@pytest.mark.parametrize("figure", ["$1,50", "$15", "$150", "$5", "5%", "3%", "20-30%", "$1,500-2,000",
                                    "$2,500", "twenty percent", "$750"])
def test_figures_not_in_offers_refused_as_whole_tokens(figure):
    assert "figure_not_in_offers" in codes(BESPOKE + " (%s)" % figure)


def test_figure_extraction_is_whole_token():
    assert copy_gate.dollar_figures("$1,500 and $1500") == ["1500", "1500"]
    assert copy_gate.dollar_figures("$750M+") == ["750000000"]
    assert copy_gate.percent_figures("35%") == ["35"]
    assert copy_gate.percent_figures("a 3,300x return") == []


def test_no_pricing_in_offers_means_no_price():
    assert "figure_not_in_offers" in codes(BESPOKE + " I'd do it for $800.")


# ---------------------------------------------------------------- private
PRIVATE = ("Time: 25-30 hours, about 2 calendar weeks.\n"
           "Likelihood: high, HubSpot API access is the one risk.\n"
           "Standard pricing: $3,500-5,000 plus $50/mo software.\n"
           "Client intel: 4.9 stars over 12 reviews, hire rate 80%.")


@pytest.mark.parametrize("leak", ["it's about 30 hours of work", "roughly $3,500", "the likelihood is high",
                                  "your 4.9 stars", "a hire rate of 80%", "about 25 hrs"])
def test_private_facts_refused(leak):
    assert "private_fact" in codes(BESPOKE + " " + leak + ".", private=[PRIVATE])


def test_private_fact_needs_a_private_source():
    assert "private_fact" not in codes(BESPOKE + " about 30 hours of work.")
    assert "private_fact" not in codes(BESPOKE, private=[PRIVATE])


# ---------------------------------------------------------------- placeholders
@pytest.mark.parametrize("slot", ["[name]", "{{loom}}", "TODO", "TBD", "XX", "<client name>"])
def test_placeholders(slot):
    assert "placeholder" in codes(BESPOKE + " " + slot)


# ---------------------------------------------------------------- greeting
def test_first_name_greeting_without_a_known_name():
    assert "first_name_unknown" in codes("hey dana, " + BESPOKE[5:])
    assert "first_name_unknown" in codes("Hi Dana,\n" + BESPOKE[5:])
    assert "first_name_unknown" not in codes("hey dana, " + BESPOKE[5:], r=room(first_name="Dana"))
    assert "first_name_unknown" not in codes("hey there, " + BESPOKE[5:])
    assert "first_name_unknown" not in codes("hey quick idea on the showroom quote requests in HubSpot")


# ---------------------------------------------------------------- voice
@pytest.mark.parametrize("plural", ["we can wire the HubSpot side", "our team handles it", "let us know",
                                    "We'll map the tile lines"])
def test_not_first_person(plural):
    assert "not_first_person" in codes(BESPOKE + " " + plural + ".")


def test_we_allowed_inside_a_client_quote_and_us_the_country():
    assert "not_first_person" not in codes(BESPOKE + ' you wrote "we lose leads on weekends".')
    assert "not_first_person" not in codes(BESPOKE + " I'm US-based, so Central time works.")


def test_third_person_self_reference():
    assert "not_first_person" in codes(BESPOKE + " Lorenzo will set it up.")


@pytest.mark.parametrize("filler", ["Just checking in on the HubSpot build.", "circling back on this",
                                    "bumping this", "Following up on my proposal"])
def test_filler_phrases(filler):
    assert "filler_phrase" in codes(BESPOKE + " " + filler)


def test_ai_and_automation_words_are_allowed():
    assert codes(BESPOKE + " the AI step and the automation around it stay in HubSpot.") == []


# ---------------------------------------------------------------- generic phrasing
STOCK = ("hey there, hope you're doing well. wanted to follow up and see if you had any questions about the "
         "project. happy to hop on a quick call whenever works.")


def test_generic_stock_draft_fails():
    assert "generic_phrasing" in codes(STOCK)


def test_generic_no_shared_term_fails_even_without_stock_lines():
    plain = "hey, I had another thought about the build and how it could work for you. want to talk it through?"
    assert "generic_phrasing" in codes(plain)


def test_stock_line_fails_even_with_client_terms():
    assert "generic_phrasing" in codes("Hope this finds you well. " + BESPOKE)
    assert "generic_phrasing" in codes(BESPOKE + " Let me know if you have any questions.")


def test_bespoke_draft_passes_generic_check_via_messages_only():
    r = room(job=False)
    draft = "hey, about the bathroom photos you said come with most requests: I'd attach them to each record."
    assert "generic_phrasing" not in codes(draft, r=r)


def test_client_name_alone_is_not_distinctive():
    r = room(first_name="Dana", messages=[{"side": "client", "text": "Dana here. Any thoughts?"}], job=False)
    assert "generic_phrasing" in codes("hey Dana, had another thought about the build for you.", r=r)


def test_generic_check_skipped_with_no_client_text():
    r = room(messages=[], job=False)
    r["job_title"] = None
    assert "generic_phrasing" not in codes("hey, I had another thought about the build.", r=r)


def test_shared_terms_match_plurals():
    assert "showroom" in copy_gate.shared_terms("the showrooms", room())


# ---------------------------------------------------------------- platform names in the post
BOT_POST = ("Need a WhatsApp bot for Brightline Tile showroom quote requests: customers send bathroom photos on "
            "WhatsApp and the bot books a measure visit in HubSpot.")


def test_platform_word_allowed_when_the_post_names_it():
    r = room(post=BOT_POST)
    draft = ("hey, one idea for the WhatsApp flow: I'd have the bot ask for the room size right after the bathroom "
             "photos, so the measure visit in HubSpot already has it.")
    assert codes(draft, r=r) == []


@pytest.mark.parametrize("ask", ["message me on WhatsApp", "text me on whatsapp", "reach me on Telegram",
                                 "my WhatsApp is open", "let's continue this on WhatsApp",
                                 "happy to chat about it over WhatsApp", "I'm @brightline_dev there"])
def test_off_platform_invitations_refused_even_when_the_post_names_the_platform(ask):
    r = room(post=BOT_POST)
    draft = "hey, one idea for the WhatsApp flow and the bathroom photos in HubSpot. " + ask + "."
    assert "off_platform_contact" in codes(draft, r=r)


def test_platform_word_allowed_when_the_client_names_it():
    r = room(messages=[{"side": "client", "text": "We run intake calls on Zoom, could it log those too?"}])
    draft = BESPOKE + " each Zoom recording could land on the same HubSpot record."
    assert "off_platform_contact" not in codes(draft, r=r)
    assert "off_platform_contact" in codes(BESPOKE + " each Zoom recording could land there.")


def test_other_platforms_stay_refused_on_a_whatsapp_job():
    r = room(post=BOT_POST)
    assert "off_platform_contact" in codes("hey, the WhatsApp flow could mirror to Telegram for the bathroom photos.",
                                           r=r)


def test_message_me_on_upwork_is_fine():
    assert "off_platform_contact" not in codes(BESPOKE + " message me on Upwork any time.")


# ---------------------------------------------------------------- escaped client text
ESCAPED_POST = ("Brightline Tile: website form \\-&gt; HubSpot &amp; Slack. &quot;Showroom&quot; follow\\-ups "
                "lag&nbsp;days. See https://brightline-tile.example.org/q?a=1&amp;b=2")


def test_escapes_do_not_create_junk_distinctive_terms():
    terms = copy_gate.distinctive_terms(copy_gate.client_source_text(room(post=ESCAPED_POST, messages=[])))
    assert not {"quot", "nbsp", "amp"} & terms
    assert {"showroom", "hubspot", "slack"} <= terms


def test_escaped_source_still_matches_a_bespoke_draft_and_stays_generic_otherwise():
    r = room(post=ESCAPED_POST, messages=[])
    r["job_title"] = None
    assert codes("hey, one idea: I'd post each HubSpot showroom request to Slack the minute it lands.", r=r) == []
    assert "generic_phrasing" in codes("hey, quot nbsp amp, had another thought about the build.", r=r)


def test_escapes_do_not_trigger_non_ascii():
    r = room(post=ESCAPED_POST)
    assert "non_ascii" not in codes(BESPOKE + " the form -> HubSpot -> Slack path.", r=r)
    assert "non_ascii" not in codes(BESPOKE + " (form &gt; HubSpot)", r=r)


def test_job_post_url_with_escaped_ampersand_is_allowed():
    r = room(post=ESCAPED_POST)
    assert "external_link" not in codes(BESPOKE + " per https://brightline-tile.example.org/q?a=1&b=2", r=r)


# ================================================================ round 2 (reviewer probes p2, p3, p6, p7)
# ---------------------------------------------------------------- 1. off-platform phrasing
PLATFORM_POST = (POST + " Customers message us on WhatsApp and we book on Calendly. We meet on Google Meet and "
                 "Zoom, and the office uses Microsoft Teams.")


@pytest.mark.parametrize("phrase", [
    "WhatsApp me when ready", "whatsapp me", "message me directly on WhatsApp", "ping me on WhatsApp",
    "hop on a WhatsApp call", "happy to hop on a WhatsApp call Thursday at noon",
    "I can do a quick WhatsApp call Thursday at noon", "grab a slot on your Calendly",
    "grab any slot on your Calendly", "I booked a slot on your Calendly for Thursday", "send me your Calendly link",
    "free for a Google Meet", "I'm free for a Google Meet Thursday at noon", "let's hop on Google Meet",
    "happy to jump on a Zoom call Thursday at noon", "I'll send a Zoom link", "I'll send a Zoom link for Thursday",
    "I'll send a Google Meet link", "I'll send you a Teams invite", "happy to jump on Microsoft Teams Thursday",
    "lets continue on google meet", "Telegram works too",
])
def test_platform_contact_refused_even_when_the_post_names_the_platform(phrase):
    r = room(post=PLATFORM_POST)
    assert "off_platform_contact" in codes(BESPOKE + " " + phrase + ".", r=r)


@pytest.mark.parametrize("phrase", [
    "reach out to me at dana dot tile at gmail", "drop me a line at lorenzo at advero dot com",
    "shoot me an email and I'll send the file", "send me an email and I'll send the map", "drop me a text",
    "you can find me on LinkedIn", "add me on Discord", "DM me on Instagram", "ping me on Slack",
    "let's move this to email", "I'd rather continue by email", "happy to continue over email",
    "reach me by phone", "I can get back to you via email", "my gmail is lorenzo.v", "my cell is below",
    "hit me up on whatsapp", "hmu on telegram", "I'm lorenzo_v on telegram", "search lorenzov on skype",
    "my handle is lorenzov", "my number is five one two, five five five, zero one four two",
    "call me on 512 555 0142", "lorenzo AT advero DOT com", "lorenzo(at)advero(dot)com", "lorenzo@advero",
    "happy to pay you back via Payoneer", "send the payment through Wise", "you can pay me by bank transfer",
    "we can skip the Upwork fee if you pay directly", "I can invoice you directly",
    "let's do this outside the platform", "let's take this off-site",
])
def test_off_platform_phrasings_refused(phrase):
    assert "off_platform_contact" in codes(BESPOKE + " " + phrase + ".")


@pytest.mark.parametrize("host", [
    "https://calendly.com/brightline-owner/intro", "cal.com/lorenzo", "zcal.co/lorenzo", "tidycal.com/lv",
    "savvycal.com/lv/intro", "https://meetings.hubspot.com/brightline", "https://calendar.google.com/x",
    "wa.me/15125550142", "t.me/lorenzov",
])
def test_booking_and_chat_hosts_refused_even_from_the_post(host):
    r = room(post=POST + " Book a call with me first: " + host)
    out = codes(BESPOKE + " I grabbed a slot at " + host + ".", r=r)
    assert "external_link" in out and "off_platform_contact" in out


@pytest.mark.parametrize("ok", [
    "happy to do a short call here on Upwork Thursday at noon",
    "a quick Upwork call would settle it",
    "want to hop on a quick call?",
])
def test_calls_on_upwork_are_fine(ok):
    assert "off_platform_contact" not in codes(BESPOKE + " " + ok + ".")


@pytest.mark.parametrize("subject", [
    "the WhatsApp flow could ask for the room size first",
    "each Calendly booking would land in HubSpot as a showroom visit",
    "the Google Meet recordings could attach to the HubSpot record",
])
def test_platform_as_the_project_subject_passes_when_the_post_names_it(subject):
    assert "off_platform_contact" not in codes(BESPOKE + " " + subject + ".", r=room(post=PLATFORM_POST))


@pytest.mark.parametrize("near_miss", [
    "my email sequences use the same idea", "a bank transfer marks it paid",
    "when a client pays via PayPal the invoice closes itself", "the Slack message tags @frontdesk",
    "at 300-1200 leads a month the queue matters", "I'd like to continue the sequence over email on day two",
    "the text goes out first, then the email follows",
])
def test_topic_words_are_not_contact(near_miss):
    # Round 3: Slack is a named platform like WhatsApp, so the post names it here.
    r = room(post=POST + " Clients pay via PayPal or bank transfer. We get 300-1200 leads a month. "
                         "The front desk works in Slack.")
    assert "off_platform_contact" not in codes(BESPOKE + " " + near_miss + ".", r=r)


def test_phone_shapes():
    assert copy_gate._phone_numbers("reach me at 555-0142") == ["555-0142"]
    assert copy_gate._phone_numbers("300-1200 leads a month") == []
    assert copy_gate._phone_numbers("+1 512 555 0142")
    assert copy_gate._phone_numbers("5125550142")


# ---------------------------------------------------------------- 2. money without "$"
@pytest.mark.parametrize("amount", [
    "3,500 dollars", "3500 USD", "USD 3,500", "EUR 3,500", "3.5k", "3,500 bucks", "five thousand dollars",
    "five grand", "$3.5k", "$ 3,500", "US$3,500", "3,500 dollars a month",
])
def test_money_amounts_without_a_dollar_sign(amount):
    assert "figure_not_in_offers" in codes(BESPOKE + " I'd put it at %s." % amount)


def test_money_values_are_canonical():
    assert copy_gate.dollar_figures("five thousand dollars") == ["5000"]
    assert copy_gate.dollar_figures("five grand") == ["5000"]
    assert copy_gate.dollar_figures("USD 3,500 or 3.5k") == ["3500", "3500"]


PRIVATE_PRICING = ("Standard pricing:\n$3,500-5,000 plus $50/mo\nTime:\n25-30 hours\nLikelihood:\nhigh")


@pytest.mark.parametrize("leak", ["the build is 3,500 to 5,000", "priced at 3,500-5,000", "my odds here are high"])
def test_private_pricing_without_a_dollar_sign_is_refused(leak):
    assert "private_fact" in codes(BESPOKE + " " + leak + ".", private=[PRIVATE_PRICING])


def test_bare_numbers_outside_private_pricing_pass():
    assert "private_fact" not in codes(BESPOKE + " about 140 SKUs.", private=[PRIVATE_PRICING])
    assert copy_gate.private_pricing_lines(PRIVATE_PRICING) == ["Standard pricing:", "$3,500-5,000 plus $50/mo"]


# ---------------------------------------------------------------- 3. proof figures used as prices
@pytest.mark.parametrize("price", [
    "I can build the whole thing for $1,500 fixed.", "my rate for this would be $1,500.", "a 35% deposit works.",
    "the full build is $10,000.", "call it $5M.", "a 3500 budget works.", "I can do the intake for 3500.",
])
def test_proof_figures_as_prices_are_refused(price):
    assert "figure_not_in_offers" in codes(BESPOKE + " " + price, kind="reply")


def test_volume_numbers_are_not_prices():
    assert "figure_not_in_offers" not in codes(BESPOKE + " for 300 leads a month the queue matters.")


def test_pricing_section_figures_are_allowed_as_prices():
    offers = OFFERS.replace("No Upwork pricing yet: Lorenzo adds it.", "Intake builds start at $1,200 fixed.")
    assert "figure_not_in_offers" not in check(BESPOKE + " the intake alone is $1,200 fixed.", "reply", room(),
                                               offers)
    assert "figure_not_in_offers" in check(BESPOKE + " the intake alone is $1,300 fixed.", "reply", room(), offers)


# ---------------------------------------------------------------- 4. first-name shapes
TAIL = "one idea on the showroom quote requests in HubSpot."


@pytest.mark.parametrize("opening", [
    "Hi Dana. ", "Dana, ", "Hey Dana Whitfield, ", "Hey Dana - ", "Hey Dana; ", "Hey, Dana, ", "Good morning, Dana. ",
    "Thanks Dana, ", "Hello Mr. Whitfield, ", "hey dana, ", "Hi Dana\n\n", "Hey @Dana, ", "Hey Dana ",
])
def test_first_name_shapes_refused(opening):
    assert "first_name_unknown" in codes(opening + TAIL)


def test_lowercase_name_without_punctuation_refused_when_the_client_signed_it():
    r = room(messages=[{"side": "client", "text": "Most requests come with bathroom photos. Thanks, Dana"}])
    assert "first_name_unknown" in codes("hey dana " + TAIL, r=r)
    r = room(messages=[{"side": "client", "text": "Dana here. Most requests come with bathroom photos."}])
    assert "first_name_unknown" in codes("hey dana " + TAIL, r=r)


def test_client_room_name_in_the_opening_is_refused():
    r = room()
    r["client"] = "Dana Whitfield"
    assert "first_name_unknown" in codes("hey whitfield " + TAIL, r=r)
    assert "first_name_unknown" in codes("dana, " + TAIL, r=r)


@pytest.mark.parametrize("opening", [
    "hey there, ", "hey, quick idea: ", "Hey Brightline team, ", "hey, ", "Thanks for the Loom question. ",
    "Quick question, ", "Honestly, ", "Hi all, ", "hey quick ",
])
def test_non_name_openings_pass(opening):
    assert "first_name_unknown" not in codes(opening + TAIL)


def test_known_first_name_may_be_used():
    assert "first_name_unknown" not in codes("Hi Dana. " + TAIL, r=room(first_name="Dana"))


# ---------------------------------------------------------------- 8. escapes decoded before the checks
@pytest.mark.parametrize("dash", ["&mdash;", "&amp;mdash;", "&#8212;", "&#x2013;", "&ndash;", "&horbar;",
                                  "\\u2014", "--"])
def test_escaped_dashes_are_caught_by_check_directly(dash):
    assert "em_dash" in codes(BESPOKE.replace(": I'd", " %s I'd" % dash))


def test_decode_escapes_stops_after_three_passes():
    assert copy_gate.decode_escapes("&amp;amp;mdash;") == "\u2014"
    assert copy_gate.decode_escapes("&amp;amp;amp;amp;mdash;") == "&amp;mdash;"


# ---------------------------------------------------------------- false positives the reviewer listed
@pytest.mark.parametrize("phrase,code", [
    ("the bot can circle back with the lead after 24 hours", "filler_phrase"),
    ("you mentioned your front desk wanted to follow up faster", "generic_phrasing"),
    ("touch base with the lead within 5 minutes", "generic_phrasing"),
    ("any update to a lead's stage fires the Slack alert", "generic_phrasing"),
    ("a todo list for the front desk", "placeholder"),
    ("you said 'our front desk misses the late ones'", "not_first_person"),
    ("if they don't answer, the sequence bumps this lead up", "filler_phrase"),
])
def test_client_subject_phrases_pass(phrase, code):
    assert code not in codes(BESPOKE + " " + phrase + ".")


@pytest.mark.parametrize("phrase,code", [
    ("I wanted to follow up on this", "generic_phrasing"),
    ("just circling back on the HubSpot piece", "filler_phrase"),
    ("I'm just checking in", "filler_phrase"),
    ("any updates?", "generic_phrasing"),
    ("I'd like to touch base", "generic_phrasing"),
    ("TODO", "placeholder"),
    ("[todo]", "placeholder"),
    ("our front desk would love it", "not_first_person"),
])
def test_lorenzo_voice_phrases_refused(phrase, code):
    assert code in codes(BESPOKE + " " + phrase + ".")


# ================================================================ round 3 (concept check; reviewer probes p8, p9)
# The off-platform check reads a CHANNEL plus a DIRECTION per clause (module
# docstring, "Off-platform concepts"). Most rooms below name the platforms the
# way real posts do, so these tests exercise the direction logic rather than
# the "platform the post never names" fallback.
WA_POST = ("Brightline Tile needs showroom quote requests from our website form to land in HubSpot. "
           "Customers send bathroom photos on WhatsApp and we meet vendors on Zoom and Google Meet.")
MED_POST = ("Med spa using GoHighLevel. New leads from Facebook ads should get an SMS and email follow-up sequence, "
            "and the front desk gets pinged in Slack. We get 300-1200 leads a month. Clients pay via PayPal or bank "
            "transfer.")
BOOK_POST = ("Med spa needs a GoHighLevel bot that answers new Facebook leads by SMS, qualifies them and books a "
             "consult. Right now leads get our Calendly link by hand and half never book. Consults should land in "
             "Google Calendar and the front desk gets a calendar invite.")
WABOT_POST = "Need a WhatsApp bot for a tile showroom quote intake in HubSpot."
STRIPE_POST = ("We run a yoga studio. Need Stripe webhooks to mark members paid in Airtable, send a receipt email, "
               "and text the member a class reminder by SMS. PayPal payments should land there too.")
LINKEDIN_POST = ("B2B software company. We run LinkedIn ads and get demo requests through a LinkedIn lead form. Need "
                 "them in HubSpot with a follow-up email and a Slack alert for the sales reps. Demos happen on Zoom.")
ZOOM_POST = ("Business coach. Clients book a free 20 min Zoom call through Kajabi. Need reminders by email and SMS and "
             "a follow-up after the call with a replay link.")
TILE_B = "one idea on the showroom quote requests: I'd tag each one by tile line when it lands in HubSpot."
MED_B = "hey, on the after-hours leads from your Facebook ads: I'd send the first SMS right away from GoHighLevel."


def r3_room(post, client_text, client="Brightline Tile", title="HubSpot intake for tile showroom quotes"):
    return dict(room(post=post, messages=[{"side": "client", "text": client_text}]), client=client, job_title=title)


def wa_room():
    return r3_room(WA_POST, "Most requests come in with photos of the bathroom.")


def med_room():
    return r3_room(MED_POST, "Can the bot also send an auto-reply after hours?", client="Invented Co",
                   title="GoHighLevel follow-up for a med spa")


def book_room():
    return r3_room(BOOK_POST, "Can the bot send the booking link itself, or does it book directly?",
                   client="Glow Aesthetics", title="GoHighLevel SMS booking bot for med spa")


def off(text, r):
    return "off_platform_contact" in codes(text, r=r)


# ---------------------------------------------------------------- defect 1: calls and contact on a named platform
@pytest.mark.parametrize("phrase", [
    "happy to do a quick call on WhatsApp Thursday at noon", "I can call you on WhatsApp",
    "I can call you on WhatsApp Thursday at noon", "give me a call on WhatsApp", "a call via Google Meet works",
    "happy to hop on a call via WhatsApp", "I'll WhatsApp you the details",
    "happy to walk you through it on Zoom Thursday at noon", "let's do Zoom Thursday at noon",
    "Zoom Thursday at noon works for me", "I'm around on WhatsApp all week", "happy to screen share over Zoom Thursday",
    "we could jump on a quick Meet", "share your WhatsApp and I'll send the flow",
])
def test_r3_calls_and_contact_on_a_platform_the_post_names_are_refused(phrase):
    assert off(TILE_B + " " + phrase + ".", wa_room())


@pytest.mark.parametrize("phrase", [
    "I'll email you the scope tonight", "I can text you the link", "I'll give you a ring Thursday",
    "send it to my email", "I'll send it to your email", "forward the doc to my email", "what's your email",
    "send me your email and I'll share the doc", "put your email here", "drop your number and I'll call",
    "what's the best number to reach you", "share your WhatsApp", "I can send the walkthrough to your inbox",
])
def test_r3_email_text_and_contact_requests_are_refused_with_no_platform_in_the_post(phrase):
    assert off(BESPOKE + " " + phrase + ".", room())


@pytest.mark.parametrize("post,phrase", [
    (POST, "PayPal works for me for the deposit"), (POST, "I accept PayPal and Wise"),
    (POST, "payment via PayPal works"), (POST, "send the deposit to my PayPal"),
    (POST, "happy to take payment by wire"), (POST, "I invoice through PayPal"),
    (POST, "I can send you a Stripe invoice"), (POST, "I'd rather be paid outside the contract"),
    (POST, "you can settle it on Wise"), (POST, "pay me by bank transfer"), (POST, "you can pay by bank transfer"),
    (MED_POST, "PayPal works for me for the deposit"), (MED_POST, "I accept PayPal and bank transfer"),
    (MED_POST, "payment via PayPal works"), (MED_POST, "send the deposit to my PayPal"),
    (MED_POST, "happy to take payment by bank transfer"), (MED_POST, "I invoice through PayPal"),
    (MED_POST, "you can settle it by bank transfer"), (MED_POST, "the deposit can go through PayPal"),
    (STRIPE_POST, "I can send you a Stripe invoice"), (STRIPE_POST, "pay the deposit through my Stripe link"),
    (STRIPE_POST, "happy to take the deposit via Stripe"), (STRIPE_POST, "I'll bill you on Stripe"),
    (STRIPE_POST, "PayPal works for me"),
])
def test_r3_payment_outside_upwork_is_refused_even_when_the_post_names_the_rail(post, phrase):
    assert off(BESPOKE + " " + phrase + ".", room(post=post))


@pytest.mark.parametrize("phrase", ["lorenzov on LinkedIn has the case study", "follow @advero_ai",
                                    "follow @advero_ai for the case study", "I'm @lorenzov on X"])
def test_r3_identity_on_a_network_is_refused(phrase):
    assert off(TILE_B + " " + phrase + ".", wa_room())


@pytest.mark.parametrize("post", [POST, MED_POST])
@pytest.mark.parametrize("phrase", [
    "I can also take payment directly by bank transfer so you skip the fee.",
    "Search my name on LinkedIn and message me there.",
    "I can move this conversation to a direct chat.",
])
def test_r3_coordinator_cases_are_refused(post, phrase):
    assert off(BESPOKE + " " + phrase, room(post=post))


@pytest.mark.parametrize("ok", [
    "a short call here on Upwork", "a quick Upwork call", "happy to do a short call here on Upwork Thursday at noon",
    "I'm free for a short call on Upwork Thursday at noon or Friday at 3pm CT",
    "happy to walk you through it on a quick Upwork call Thursday at noon", "message me here on Upwork any time",
])
def test_r3_calls_here_on_upwork_pass(ok):
    assert not off(TILE_B + " " + ok + ".", wa_room())


def test_r3_slack_is_a_named_platform():
    # the project may use Slack once the post or client names it; otherwise it reads as a new channel
    assert off(BESPOKE + " the Slack alert could tag the showroom rep.", room())
    assert not off(MED_B + " the Slack alert could tag the front desk.", med_room())
    assert off(MED_B + " ping me on Slack.", med_room())


# ---------------------------------------------------------------- defect 1: the project's own subject passes
@pytest.mark.parametrize("post,phrase", [
    (MED_POST, "the bot sends the lead a text"), (MED_POST, "the workflow emails the front desk"),
    (STRIPE_POST, "we'd connect your Stripe webhooks"), (STRIPE_POST, "I'd connect your Stripe webhooks to Airtable"),
    (MED_POST, "when a client pays via PayPal the invoice closes itself"), (MED_POST, "a bank transfer marks it paid"),
    (MED_POST, "bank transfer payments get tagged by hand today"),
    (STRIPE_POST, "PayPal payments could land in the same Airtable table"),
    (WA_POST, "customers who message the showroom on WhatsApp get a reply from the bot"),
    (WA_POST, "I'd pull the Zoom meeting notes into the deal"),
    (LINKEDIN_POST, "demo requests from LinkedIn could book the Zoom demo straight away"),
])
def test_r3_a_platform_the_post_names_passes_as_the_project_subject(post, phrase):
    assert not off(BESPOKE + " " + phrase + ".", room(post=post))


def test_r3_the_project_reaching_the_client_is_not_lorenzo_reaching_the_client():
    r = r3_room(WABOT_POST, "Most requests come in with photos of the bathroom.")
    assert not off("hey, the bot can text you when a big quote request lands, so you see it before HubSpot does.", r)
    assert not off("hey, customers who message you on WhatsApp get a reply from the bot within a minute.", r)
    assert off("hey, I can text you when the HubSpot quote bot is live.", r)
    assert off("hey, my assistant will WhatsApp you the HubSpot quote bot demo.", r)
    assert off("hey, I'll send you the bot summary by email.", r)


# ---------------------------------------------------------------- defect 2: filler in Lorenzo's own voice
@pytest.mark.parametrize("opening", [
    "hey, circling back on the showroom form.", "so, circling back on the showroom form.",
    "quick one, circling back on the tile photos.", "hey, wanted to follow up on the showroom form.",
    "Wanted to follow up on the showroom quote requests.", "hey, wanted to circle back on the HubSpot intake.",
    "hey, touching base on the showroom form.", "hey there, circling back on the HubSpot intake.",
    "hi, just circling back on the showroom form.", "hey, checking in on the HubSpot showroom intake.",
    "hey, following up on my last message about the showroom form.", "hey, following up on the showroom form.",
    "hey, bumping this in case it got buried.", "Circling back on the showroom form.",
])
def test_r3_filler_after_a_greeting_is_refused(opening):
    assert "filler_phrase" in codes(opening + " " + TILE_B, r=wa_room())


@pytest.mark.parametrize("opening", ["hope all's well with the showroom launch.",
                                     "hope the week's going well at the showroom.", "any news on the showroom form?",
                                     "any thoughts on the HubSpot idea?"])
def test_r3_stock_lines_after_a_greeting_are_refused(opening):
    assert "generic_phrasing" in codes(opening + " " + TILE_B, r=wa_room())


@pytest.mark.parametrize("phrase", [
    "the bot can circle back with the lead", "your front desk wanted to follow up faster",
    "the system checks in with each lead after a day", "the sequence follows up on day three",
    "the workflow circles back after 24 hours", "leads who go quiet get a follow up on day two",
    "reps can touch base with a lead from the Slack alert", "they wanted to follow up faster",
    "it can circle back after 24 hours", "your team wanted to follow up the same day",
])
def test_r3_filler_said_by_another_subject_passes(phrase):
    out = codes(MED_B + " " + phrase + ".", r=med_room())
    assert "filler_phrase" not in out and "generic_phrasing" not in out


# ---------------------------------------------------------------- defect 3: booking terms
BOOK_B = "hey, on the consults that never get booked from your Facebook leads:"


@pytest.mark.parametrize("phrase", [
    "booking link", "calendar invite", "the Calendly link", "sending the booking link",
    "I'd have the bot send the Calendly link", "I'll set up the booking link so the bot sends it by SMS",
    "the front desk still gets the calendar invite", "I can send the booking link from GoHighLevel instead of by hand",
    "the booking link goes out in the first SMS", "the Calendly link stays the same",
    "I'll send you the booking link the bot uses so you can test it",
])
def test_r3_booking_terms_pass_in_a_booking_job_whoever_they_are_for(phrase):
    assert not off(BOOK_B + " " + phrase + ".", book_room())


@pytest.mark.parametrize("phrase", [
    "send me your Calendly link", "book a time with me Thursday", "here's my booking link",
    "I'll send you a calendar invite for a call", "grab a slot on my Calendly", "our booking link has open slots",
    "I'll send a calendar invite for Thursday at noon", "use my Calendly to pick a time for a call",
    "grab a time that works on the Calendly link below", "here's the booking link if you want to chat",
    "pick any time on my calendar", "grab a time on my calendar for a call",
])
def test_r3_booking_for_a_call_with_lorenzo_is_refused(phrase):
    assert off(BOOK_B + " " + phrase + ".", book_room())


def test_r3_booking_link_on_a_job_that_is_not_about_booking_is_refused():
    assert off(MED_B + " the auto-reply could carry a booking link.", med_room())


@pytest.mark.parametrize("draft_text", [
    "hey, on the half of leads who never book: I'd have the bot send the Calendly link right after it qualifies "
    "them, then text a reminder if no slot is taken within an hour. do most consults come from the Facebook ads or "
    "from the website?",
    "hey, to your question on the booking link: the bot can book directly. it checks Google Calendar, offers two "
    "open consult times by SMS, and books the one the lead picks, so the front desk still gets the calendar invite. "
    "is the consult length always the same?",
    "one idea on the consult booking: once a lead picks a time on your Calendly, GoHighLevel can tag the lead as "
    "booked so the SMS follow-up stops. does the front desk want a text when a consult is booked?",
    "hey, the part I'd build first is the qualifying SMS, because half your Facebook leads never book. the bot can "
    "schedule a consult in Google Calendar without anyone sending the booking link by hand.",
    "quick thought on the no-shows: the calendar invite could carry the consult prep notes, and the bot can send a "
    "Calendly reschedule link by SMS the day before.",
])
def test_r3_probe_p9_booking_drafts_pass_clean(draft_text):
    assert codes(draft_text, r=book_room()) == []


@pytest.mark.parametrize("phrase", [
    "send it to my email", "forward the doc to my email", "I'll send it to your email",
    "put your email here and I'll send the doc", "happy to show you the bot live on WhatsApp Thursday at noon",
    "give me a call on WhatsApp Thursday at noon",
])
def test_r3_probe_p9_off_platform_on_a_whatsapp_bot_job_is_refused(phrase):
    r = r3_room(WABOT_POST, "Can the bot send the booking link itself, or does it book directly?")
    assert off("hey, one idea for the WhatsApp showroom quote bot. " + phrase + ".", r)


# ---------------------------------------------------------------- adversarial phrasings the reviewer did not list
@pytest.mark.parametrize("phrase", [
    "I'm easier to reach on WhatsApp", "if Upwork is slow, WhatsApp works too", "my WhatsApp is the fastest way to get me",
    "WhatsApp is the fastest way to get me", "the best way to reach me is WhatsApp", "feel free to text me whenever",
    "you can reach me directly at my email", "I'll drop my number in the attachment", "happy to jump on Zoom tomorrow",
    "happy to hop on a Google Meet tomorrow", "let me know your WhatsApp and I'll add you", "shoot me a text when you're ready",
    "send the files over WhatsApp", "send it to me on WhatsApp", "call me Thursday at noon on WhatsApp",
    "Thursday at noon on WhatsApp works for me", "happy to keep talking here or on WhatsApp",
    "happy to keep going here, or WhatsApp if that's easier", "Loom is easiest, or a Zoom if you prefer",
    "if you'd rather talk live, my Zoom is open Thursday", "we can keep chatting on WhatsApp", "talk soon on Zoom",
    "DM me the details", "let's continue this in a private chat", "the easiest is to email me the spreadsheet",
    "happy to give you my number if a call is easier", "our WhatsApp group is the easiest place to share photos",
    "I'll set up a shared WhatsApp group with you", "catch me on WhatsApp after 5pm", "is WhatsApp ok for you",
    "can I get your WhatsApp", "are you on WhatsApp", "I can show you a demo on Zoom", "my email is on my profile",
    "happy to send the scope by email", "I'll send the recap over WhatsApp tonight", "leave your number and I'll ring you",
    "you can Venmo me the deposit", "Zelle works for the deposit", "I take crypto too",
    "pay the second milestone straight to me", "we could skip Upwork's fee on the next phase",
    "happy to do the next phase as a direct hire", "my rate outside Upwork would be lower", "let's talk off Upwork",
    "happy to move this off the platform", "let's chat privately", "Google my name for the case study",
    "email works better for me", "I'm reachable by phone all week", "happy to take this to email",
    "I'll follow up by email tonight", "I'll message you on WhatsApp once it's live", "we could go over it by phone",
    "you'll get a text from me when it's live", "I'll email the proposal over tonight", "I'd rather use email for the scope",
    "text is easier than Upwork chat for me", "Signal or WhatsApp both work for me", "just reply here or on WhatsApp",
    "reach out anytime on WhatsApp", "I'll be on Zoom at noon if you want to join", "a 15 min Zoom works for me",
    "I'd love to connect on LinkedIn", "you'll find me as lorenzo.v on Skype", "shoot me a WhatsApp",
    "I can loop you in by email", "we can chat on the phone if that's easier", "I'm usually quicker on email",
    "text works best", "I'll update you by email once it's live", "reach me at five one two five five five zero one four two",
])
def test_r3_adversarial_off_platform_moves_are_refused(phrase):
    assert off(TILE_B + " " + phrase + ".", wa_room())


@pytest.mark.parametrize("post,phrase", [
    (MED_POST, "invite me to your Slack"), (MED_POST, "add me to your Slack and I'll post updates there"),
    (MED_POST, "I'll ping you on Slack when it's ready"), (MED_POST, "happy to jump on a Slack huddle Thursday"),
    (LINKEDIN_POST, "connect with me on LinkedIn"), (LINKEDIN_POST, "I sent you a connection request on LinkedIn"),
    (LINKEDIN_POST, "follow me on LinkedIn for the case study"), (LINKEDIN_POST, "happy to share a Slack channel with you"),
    (LINKEDIN_POST, "send me the lead form export by email"), (ZOOM_POST, "I'll send a Zoom link"),
    (ZOOM_POST, "Zoom tomorrow?"), (ZOOM_POST, "if a Zoom is easier for you"),
    (ZOOM_POST, "let me know a time and I'll send the Zoom"), (ZOOM_POST, "I'll send you a Zoom invite for Thursday"),
])
def test_r3_adversarial_moves_on_named_platforms_are_refused(post, phrase):
    assert off(BESPOKE + " " + phrase + ".", room(post=post))


REALISTIC = [
    (WABOT_POST, "hey, one idea for the WhatsApp quote bot: when a customer sends bathroom photos, the bot can ask for "
                 "the room size before anything lands in HubSpot. do most customers send photos first, or a question "
                 "first?"),
    (WABOT_POST, "hey, on the WhatsApp side: if a customer messages you after 6pm, the bot can answer with a quote "
                 "range and book a showroom visit. is the showroom open weekends?"),
    (WABOT_POST, "one thought on the HubSpot intake: I'd have the bot create the contact the moment the first WhatsApp "
                 "message comes in, so nobody retypes it. do you use one WhatsApp number for the whole showroom?"),
    (WA_POST, "one idea on the showroom quote requests: the bathroom photos from WhatsApp can land on the HubSpot "
              "record, and the vendor meetings on Zoom could log a note on the same deal. do vendors quote from the "
              "photos?"),
    (MED_POST, "hey, on the leads that come in after 9pm from your Facebook ads: the first SMS can go out right away, "
               "and the email follow-up waits until morning so it doesn't feel automated. does the front desk want the "
               "Slack ping at night too, or only in the morning?"),
    (MED_POST, "quick one on the 300-1200 leads a month: at the top of that range, I'd batch the Slack pings into one "
               "message per hour so the front desk isn't buried. is one channel enough, or does each provider get "
               "their own?"),
    (MED_POST, "hey, one idea on the auto-reply: it can text the lead back with two questions, and the answers show up "
               "in the Slack ping so the front desk calls with context. do most leads text back, or do they wait for "
               "a call?"),
    (STRIPE_POST, "hey, on the Stripe webhooks: the webhook can catch each refund and flip the member's row in "
                  "Airtable back to unpaid, so nobody has to. do refunds ever cover part of a class pack?"),
    (STRIPE_POST, "one idea on the PayPal side: PayPal payments can land in the same Airtable table as Stripe ones, "
                  "keyed on the member's email, so you see one list. do members ever pay with a different email?"),
    (STRIPE_POST, "quick one on the class reminders: when Stripe marks a member paid, the SMS reminder can go out the "
                  "night before class. do you refund class packs in Stripe or in PayPal?"),
    (LINKEDIN_POST, "hey, on the Slack alerts for the sales reps: I'd pull the company size from the LinkedIn lead "
                    "form into HubSpot first, then build the Slack alert from the HubSpot record. is company size a "
                    "required field on the form?"),
    (LINKEDIN_POST, "one idea on the demo requests: the follow-up email can include a Zoom link picked from the rep's "
                    "calendar, so the lead books without a back and forth. do all reps run demos?"),
    (ZOOM_POST, "hey, on the no-shows for the free Zoom calls: a text 15 minutes before with the Zoom link usually "
                "beats another email. do most no-shows book the same day?"),
    (ZOOM_POST, "quick one on the Kajabi side: I'd put the Zoom link in the reminder text, so nobody digs through "
                "email for it. is it the same Zoom link for every call?"),
    (ZOOM_POST, "one idea on the replay link: the follow-up email after the call can carry it, plus a one-click rebook "
                "for the next session. do clients get the replay today?"),
    ("HVAC company. Missed calls after hours should get an SMS back from our Twilio number and create a job in "
     "ServiceTitan. Customers often call twice.",
     "hey, on the missed calls after hours: the text back can go out from your Twilio number within a minute, and the "
     "job lands in ServiceTitan either way. do most after-hours callers want a same-day visit?"),
    ("HVAC company. Missed calls after hours should get an SMS back from our Twilio number and create a job in "
     "ServiceTitan. Customers often call twice.",
     "one idea on the customers who call twice: the second call could skip the SMS and ring the on-call tech "
     "instead. is there always one tech on call at night?"),
    ("Real estate team. Zillow leads come into Follow Up Boss. Need an AI text and email follow-up and a call task "
     "for the agent if the lead replies.",
     "one thought on the email follow-up: I'd keep it to two emails, because most Zillow leads answer the text first "
     "or not at all. do your agents call from their own cell phones?"),
    ("Personal injury law firm. Web form and phone intake into Clio. Need automated emails and SMS reminders for "
     "consultation appointments, and a call from an intake specialist within 5 minutes.",
     "hey, on the 5-minute call from the intake specialist: the form can trigger a Clio task and an SMS to the "
     "specialist at the same time, so nobody watches the inbox. do phone intakes go into Clio by hand today?"),
    ("Recruiting agency. Candidates apply through Indeed and LinkedIn. Need screening questions by SMS, then book a "
     "phone screen on the recruiter's Calendly, and log everything in Bullhorn.",
     "hey, on the phone screens: the bot can ask the screening questions by SMS first, and only candidates who pass "
     "get the recruiter's Calendly link. do recruiters want a text when a screen gets booked?"),
    ("Restaurant group, 3 locations. Reservations via OpenTable, catering inquiries by email and Instagram DM. Need "
     "catering inquiries in one Airtable board with an auto-reply.",
     "hey, on the catering inquiries from Instagram DMs and email: I'd route both into one Airtable board and send "
     "the same auto-reply, so nobody checks two inboxes. do most catering inquiries come by email or DM?"),
    ("Shopify store. Need abandoned cart SMS via Klaviyo and a WhatsApp message for international customers.",
     "one idea on the abandoned carts: I'd send the Klaviyo SMS first and the WhatsApp message only to numbers "
     "outside the US, so nobody gets both. how many carts a week are international?"),
    ("Invoice automation. When a job is marked done in Jobber, send the customer a Stripe invoice by text and email, "
     "and chase unpaid invoices after 7 days.",
     "hey, on the unpaid invoices: the reminder after 7 days can include the same Stripe payment link, so the "
     "customer pays in one tap. do most customers pay by card, or do some still send checks?"),
    ("Invoice automation. When a job is marked done in Jobber, send the customer a Stripe invoice by text and email, "
     "and chase unpaid invoices after 7 days.",
     "one idea on the Jobber side: the Stripe invoice can go out the moment a job is marked done, by text first and "
     "email second. how many jobs close a day?"),
    ("We send cold email with Instantly and need someone to fix our deliverability and warm up new inboxes.",
     "hey, on the new inboxes: I'd warm them for two weeks before any campaign traffic, and move the sending to a "
     "separate domain so the main one stays clean. how many inboxes are you planning?"),
    ("Need Calendly bookings to create deals in Pipedrive and send a Slack alert to the sales team.",
     "one idea: I'd skip the Zapier step and use the Calendly webhook directly, so deals show up in Pipedrive in "
     "seconds. are you on a paid Calendly plan?"),
    ("Need a Telegram bot for our crypto newsletter that answers FAQs and collects emails into Mailchimp.",
     "hey, on the weekly call time questions: the Telegram bot can answer those from one pinned schedule, so you "
     "only update it in one place. do the call times change every week?"),
    ("We want a Slack app that posts new HubSpot deals into a channel and lets reps claim them with a button.",
     "hey, on the double claims: the Slack button can lock the deal in HubSpot the moment one rep clicks, and the "
     "message updates to show who has it. do reps ever need to hand a deal back?"),
    ("Therapy practice: new client consults happen on Zoom. Need GoHighLevel to send the Zoom link and intake form "
     "when a consult is booked on the calendar, and remind by SMS.",
     "hey, on the intake forms that get forgotten: GoHighLevel can put the Zoom link and the intake form in the same "
     "SMS, then send one reminder the day before. do consults always run on Zoom, or sometimes in person?"),
    ("Therapy practice: new client consults happen on Zoom. Need GoHighLevel to send the Zoom link and intake form "
     "when a consult is booked on the calendar, and remind by SMS.",
     "one idea on the Zoom consults: the reminder SMS can carry the Zoom link, so new clients never dig through "
     "email for it. how far ahead do most consults get booked?"),
]


@pytest.mark.parametrize("post,draft_text", REALISTIC)
def test_r3_realistic_automation_drafts_pass_clean(post, draft_text):
    r = dict(room(post=post, messages=[]), client="Invented Co", job_title="Automation build")
    assert codes(draft_text, r=r) == []


def test_r3_probe_p3_near_misses_pass_clean_in_the_med_spa_room():
    for phrase in ["the bot can circle back with the lead after 24 hours",
                   "any update to a lead's stage fires the Slack alert", "at 300-1200 leads a month the queue matters",
                   "the Slack message tags @frontdesk", "I can move this to email for the second step of the sequence",
                   "my email sequences use the same idea", "when a client pays via PayPal the invoice closes itself",
                   "a bank transfer marks it paid", "the text goes out first, then the email follows",
                   "if they don't answer, the sequence bumps this lead up",
                   "I'd rather keep the SMS on your GoHighLevel number than move this to a separate SMS tool",
                   "I'd like to continue the sequence over email on day two",
                   "you mentioned your front desk wanted to follow up faster",
                   "touch base with the lead within 5 minutes", "a todo list for the front desk",
                   "I'm US based, so the hours line up", "you said 'our front desk misses the late ones'",
                   "the reply comes from your own number, not mine"]:
        assert codes(MED_B + " " + phrase + ".", r=med_room()) == [], phrase


# ---------------------------------------------------------------- names
@pytest.mark.parametrize("opening", [
    "Hey there Dana, ", "Hi again Dana, ", "Hey Dana :) ", "Hey Dana and team, ", "Dear Dana ", "Hey D, ", "hey Dana ",
    "Dana - ", "Dana: ", "Hey Dana\n", "Morning Dana ", "Hey Ms Whitfield ", "Yo Dana, ", "Hey Dana-", "Greetings Dana, ",
    "Hello there, Dana. ",
])
def test_r3_probe_p8_first_name_shapes_are_refused(opening):
    assert "first_name_unknown" in codes(opening + TILE_B, r=wa_room())


@pytest.mark.parametrize("opening", [
    "Yesterday, ", "Meanwhile, ", "Earlier, ", "Airtable, not Sheets, is the right home. ", "Otherwise, ", "Instead, ",
    "Hey Brightline team, ", "Thanks for the photos, ", "Hey, Friday works. ", "Hi, quick one. ", "Makes sense, ",
    "HubSpot first, then the rest. ", "Monday, ", "Tonight, ", "Separately, ", "Zapier, ", "Hey again, ", "Hey all, ",
    "Gotcha, ", "Sounds good, ", "Right, ",
])
def test_r3_openers_and_tool_names_are_not_first_names(opening):
    assert "first_name_unknown" not in codes(opening + TILE_B, r=wa_room())


@pytest.mark.parametrize("signed_post", [WA_POST + "\n\nThanks,\nDana", WA_POST + " - Dana", "Dana here. " + WA_POST])
@pytest.mark.parametrize("opening", ["Hey there Dana, ", "Hi again Dana, ", "Hello there, Dana. ", "hey dana ", "Dana: "])
def test_r3_a_name_signed_in_the_job_post_is_refused(signed_post, opening):
    r = r3_room(signed_post, "Most requests come in with photos of the bathroom.")
    assert "dana" in copy_gate.client_names(r)
    assert "first_name_unknown" in codes(opening + TILE_B, r=r)


# ---------------------------------------------------------------- prices without a currency
@pytest.mark.parametrize("phrase", [
    "I'd put the whole build at around 3,000", "call it 2,400 for everything", "for 1,200 and have it live Friday",
    "the first milestone would run 900", "I can do it for 1,200 if we keep it to the form",
    "it would come to about 2,800 all in", "I'd charge 2,500", "the showroom form alone for 1200-1500",
])
def test_r3_bare_prices_near_price_words_are_refused(phrase):
    assert "figure_not_in_offers" in codes(TILE_B + " " + phrase + ".", r=wa_room())


@pytest.mark.parametrize("phrase", [
    "for 300 leads a month the queue is fine", "3,000 contacts is still small for GoHighLevel",
    "at 300-1200 leads a month the queue matters", "I'd test it on 300 leads first", "it runs 900 times a day at peak",
    "the SMS goes out at 9am and the email at 2pm", "in 2026 the Slack plan changed",
    "for 1,200 leads a month I'd batch the SMS",
])
def test_r3_volumes_times_and_years_are_not_prices(phrase):
    assert "figure_not_in_offers" not in codes(MED_B + " " + phrase + ".", r=med_room())


def test_r3_a_phone_number_is_contact_not_a_price():
    out = codes(TILE_B + " call me at 512-555-0142.", r=wa_room())
    assert "off_platform_contact" in out and "figure_not_in_offers" not in out


@pytest.mark.parametrize("phrase", ["that's 35 percent", "a 12% lift", "12 pct", "fifteen percent", "a 2x lift",
                                    "half the price", "a budget of five thousand dollars", "five grand"])
def test_r3_probe_p2_figures_are_refused(phrase):
    assert "figure_not_in_offers" in codes(BESPOKE + " " + phrase + ".")


@pytest.mark.parametrize("leak", ["the build is 3,500 to 5,000", "priced at 3,500-5,000", "about 25-30 hours",
                                  "25 to 30 hrs", "fifty a month for software", "my odds here are high"])
def test_r3_probe_p2_private_leaks_are_refused(leak):
    assert "private_fact" in codes(BESPOKE + " " + leak + ".", private=[PRIVATE_PRICING])


@pytest.mark.parametrize("link", ["https://www.upwork.com/ab/messages/rooms/room_1", "upwork.com/jobs/~02",
                                  "Upwork.com/freelancers/~01", "www.upwork.com", "https://upwork.com",
                                  "community.upwork.com/t/x", "upwork dot com/jobs"])
def test_r3_probe_p2_upwork_links_are_refused(link):
    assert "external_link" in codes(BESPOKE + " see " + link)


# ---------------------------------------------------------------- escapes and invisible characters in the draft
@pytest.mark.parametrize("raw", [
    "email me at lorenzo&#64;advero.com", "wh&#97;tsapp me", "W​hatsApp me", "What\\u0073App me",
    "call me at 512&#45;555&#45;0142", "e\\-mail me", "email&nbsp;me", "ＷhatsApp me", "text me­",
    "\\u0040lorenzov on telegram", "&#x2014; one idea", "one idea \\\\u2014 tag",
    "reach me at five one two five five five zero one four two",
])
def test_r3_probe_p8_escaped_or_hidden_contact_is_still_refused(raw):
    from services.upwork_followup.draft import parse_output
    text, _, _ = parse_output(TILE_B + " " + raw)
    assert codes(text, r=wa_room())


@pytest.mark.parametrize("post,phrase", [
    (STRIPE_POST, "Stripe can hold the deposit until the class starts"),
    (STRIPE_POST, "I'd rather use SMS for this, since members skip email"),
    (STRIPE_POST, "for members who never open email, SMS works best"),
    (STRIPE_POST, "the Stripe checkout can take the deposit up front"),
    (MED_POST, "can you get me the Slack export of the front desk channel"),
    (MED_POST, "for after-hours leads, SMS works best"),
    (MED_POST, "I'd rather use SMS for the first touch, since most leads never open email"),
    (MED_POST, "I can text the lead back within a minute from your number"),
])
def test_r3_project_opinions_about_a_channel_pass(post, phrase):
    assert not off(BESPOKE + " " + phrase + ".", room(post=post))


@pytest.mark.parametrize("phrase", ["the fastest way to get me is Slack", "Slack works best for me",
                                    "I'd rather use email for the scope", "SMS works for me too",
                                    "I'd rather text for updates"])
def test_r3_lorenzos_own_channel_preferences_are_refused(phrase):
    assert off(MED_B + " " + phrase + ".", med_room())


# ================================================================ round 4 (reviewer probes p10, p12, p13, p14)
# The main case: a client asks to move off Upwork and the draft goes along.
# Round 4 adds questions about the client's details whatever the question word,
# the channel used as a verb with no person after it, the client's inbox or
# phone as where Lorenzo's work arrives, invoices and payment to Lorenzo on any
# rail, and the project set up to reach the client for a test now.
SMS_POST = "Twilio SMS bot for showroom quote requests: text each new lead, log replies and bathroom photos in HubSpot."
SLACK_POST = "Slack bot that posts each new HubSpot showroom quote request to the sales channel so a rep can claim it."
MEET_POST = "Pull each Zoom sales meeting recording and transcript into HubSpot and post a summary to Slack."
PAY_POST = ("Sync Stripe and PayPal payments into QuickBooks. Customers pay deposits by card, bank transfer or PayPal, "
            "and refunds must sync back. We pay vendors through Wise too.")
DRIP_POST = "Set up a 3-email drip in Instantly, forward replies to the owner's inbox and remove bounces."
CAL_POST = "Calendly to HubSpot: when a prospect books a demo on Calendly, create the deal and send the Zoom link."
R4_B = "one idea on the showroom quote photos in HubSpot:"


def r4_room(post=POST, ask="Most requests come in with photos of the bathroom."):
    return r3_room(post, ask, client="Invented Co", title="Automation build")


def r4_off(phrase, post=POST):
    return off(R4_B + " " + phrase, r4_room(post))


# ---------------------------------------------------------------- defect 1: questions about the client's details
@pytest.mark.parametrize("phrase", [
    # the reviewer's cases
    "What number should I call, and does Thursday at noon work?", "Sure, which email should I send it to?",
    "Is there a good number for you?", "Drop me your contact info.", "Mind if I call your cell Thursday?",
    "Is email ok?",
    # the same concept, other question words and channel words
    "What number should I call?", "Which email should I send the doc to?", "Can I grab your number for a quick call?",
    "Send over your digits and I'll call.", "Drop me your contact info and I'll send the diagram.",
    "What's a good number to reach you Thursday?", "Which phone should I try?", "Which number works best?",
    "Is there an email I can send the diagram to?", "Is there a number I can reach you on?",
    "What are your contact details?", "Could you share your contact details?", "Can I get your digits?",
    "Is text ok?", "Would email be easier?", "Mind if I text your cell?", "Is your cell ok for a quick call?",
    "Who should I email the scope to?", "Should I call your office line or your cell?",
    "Which email should I send the bot demo to?", "Which email should I send the workflow diagram to?",
    "Is there an email I can send the bot demo to?", "Is email ok for the bot demo?",
    "Which is better for you, email or phone?", "Which works better for you: email or phone?",
    "Do you prefer email or a call?", "Would you rather do email or phone?", "Do you have a cell I can text?",
    "Got a number I can reach you at?", "Got a cell I can reach you on?", "My assistant will call your cell Thursday.",
    "My VA will ring your cell tomorrow.",
])
def test_r4_questions_about_the_clients_contact_details_are_refused(phrase):
    assert r4_off(phrase)


@pytest.mark.parametrize("post,phrase", [
    (SMS_POST, "Which number should the texts come from?"), (SMS_POST, "What number should I text the leads from?"),
    (SMS_POST, "Which number should I use for the bot?"), (SMS_POST, "Is there a number the leads already know?"),
    (SMS_POST, "Is SMS ok for the leads?"), (SMS_POST, "Which of your numbers should the bot text from?"),
    (SMS_POST, "Should I text your leads from the Twilio number?"),
    (DRIP_POST, "Which email should the replies go to?"), (DRIP_POST, "Which email should I send the drip from?"),
    (DRIP_POST, "What email should I use for the Instantly account?"),
    (DRIP_POST, "Which email should I forward the replies to?"), (DRIP_POST, "Which email should I use as the sender?"),
    (DRIP_POST, "Is there an inbox you'd like the replies forwarded to?"),
    (DRIP_POST, "Is email ok for the drip, or do you want SMS too?"), (DRIP_POST, "Is email ok for the reminders?"),
    (POST, "Which email does the website form send to?"), (SMS_POST, "Which number should I send the alerts to?"),
    (DRIP_POST, "Which email should I send the new leads to?"), (SMS_POST, "Would you prefer the alerts by email or SMS?"),
    (SMS_POST, "Would you rather the bot text or email the leads?"), (SMS_POST, "Do your leads prefer text or email?"),
    (SMS_POST, "Do you have a number the leads already text?"), (SMS_POST, "Do you have a Twilio number already?"),
    (SMS_POST, "Got a number the bot can text from?"), (POST, "Is a cell in the sheet enough for the rep name?"),
    (SLACK_POST, "Which is better for your reps, a Slack ping or a HubSpot task?"),
])
def test_r4_the_project_may_ask_about_a_contact_detail(post, phrase):
    assert not r4_off(phrase, post)


# ---------------------------------------------------------------- defect 2: sending with no person after the verb
@pytest.mark.parametrize("phrase", [
    # the reviewer's cases
    "I'll write up the scope for the showroom quote intake and email it tonight.",
    "You'll have it in your inbox tonight.", "Feel free to text if anything comes up.", "Text anytime.",
    "Happy to connect outside of here.", "Happy to take this elsewhere.",
    # the same concept
    "I'll write it up and email it tonight.", "I'll put the diagram together and text it over.",
    "Will email it tonight.", "Sure, will text it later today.", "You'll find it in your inbox tomorrow.",
    "Expect it in your inbox tonight.", "It'll be in your inbox by Friday.", "The scope will be in your inbox tonight.",
    "It'll hit your inbox tonight.", "I'll get it to your inbox tonight.", "Feel free to email anytime.",
    "Email anytime.", "Just text if the form breaks.", "You can always email if that's easier.",
    "Let's continue outside of here.", "Happy to chat somewhere else.", "Let me send you a message elsewhere.",
    "Look out for it in your inbox this afternoon.", "It's in your inbox now.",
    "Happy to continue somewhere more convenient.", "We can take this conversation offline.",
    "Reach out whenever, by text or email.", "Email works better for attachments.",
])
def test_r4_lorenzo_sending_or_leaving_with_no_person_named_is_refused(phrase):
    assert r4_off(phrase)


@pytest.mark.parametrize("post,phrase", [
    (DRIP_POST, "I'd forward replies to your inbox."),
    (DRIP_POST, "Each reply lands in your inbox with the lead's name in the subject."),
    (DRIP_POST, "You'll see every reply in your inbox, tagged by campaign."),
    (DRIP_POST, "so replies reach your inbox, not spam."), (DRIP_POST, "bounces never reach your inbox."),
    (DRIP_POST, "fewer bounces hit your inbox."), (DRIP_POST, "cold emails that reach your inbox get read."),
    (DRIP_POST, "nothing will reach your inbox until it's verified."),
    (SMS_POST, "You'll get a text on your phone when a lead books."),
    (SMS_POST, "I'd text the reminder to each lead the day before."),
    (SMS_POST, "Leads can text anytime and the bot answers."), (SMS_POST, "Customers can text STOP to opt out."),
    (SMS_POST, "Once it's live, you can text the bot yourself."),
    (SMS_POST, "Once it's live, you can text the test number to try it."),
    (SMS_POST, "I'd set up a test number so you can text the bot yourself."),
    (WABOT_POST, "Leads who message you elsewhere get the same reply."),
    (DRIP_POST, "The warmup emails won't reach your inbox, they go to the warmup pool."),
    (DRIP_POST, "My test sends never reach your inbox, they go to the seed list."),
    (DRIP_POST, "Look out for the first replies in your inbox tomorrow morning."),
    (DRIP_POST, "Keep an eye out for bounce spikes in the first week."),
    (POST, "Reps can reach out by phone within 5 minutes."),
    (SMS_POST, "Your front desk can reach out by text if a lead goes quiet."),
    (SMS_POST, "When a lead goes quiet, the bot can reach out by text after 24 hours."),
    (WABOT_POST, "Customers can reach out on WhatsApp any time and the bot answers."),
])
def test_r4_the_projects_own_messages_to_the_client_pass(post, phrase):
    assert not r4_off(phrase, post)


# ---------------------------------------------------------------- defect 3: invoices and payment to Lorenzo
@pytest.mark.parametrize("post", [POST, PAY_POST])
@pytest.mark.parametrize("phrase", [
    # the reviewer's cases
    "I'll send you an invoice for the deposit.", "I'll invoice you through my company.",
    "You can pay the deposit to my account.", "I can send a separate invoice for the deposit.",
    # the same concept
    "I'll bill you for the deposit separately.", "Just pay me when it's done.",
    "I'll send over an invoice once the scope is set.", "Happy to invoice you for the first half now.",
    "I can invoice the deposit through my LLC.", "The deposit can go to my bank account.",
    "You can transfer the deposit to my account.", "Once you approve, I'll invoice you.",
    "I'll email you an invoice for the deposit.", "My invoice will cover the deposit.",
    "Send the deposit to my account and I'll start Monday.", "I'll send payment details separately.",
    "Let me send you my payment details.", "Direct payment keeps it simpler for both of us.",
])
def test_r4_invoices_and_payment_to_lorenzo_are_refused_on_any_job(post, phrase):
    assert r4_off(phrase, post)


def test_r4_a_payment_link_for_the_deposit_is_lorenzos_unless_the_job_takes_deposits():
    assert r4_off("I can set up a payment link for the deposit.")
    assert not r4_off("I can set up a payment link for the deposit.", PAY_POST)  # "customers pay deposits"


@pytest.mark.parametrize("post,phrase", [
    (POST, "I'd set the deposit up as the first Upwork milestone."),
    (POST, "The deposit can be the first milestone here on Upwork."),
    (POST, "You can fund the first milestone for the deposit."),
    (POST, "Upwork holds the deposit in escrow until the milestone is approved."),
    (PAY_POST, "That way you get paid faster through Stripe."),
    (PAY_POST, "You can pay your vendors through Wise from the same sheet."),
    (PAY_POST, "The bot can invoice each customer through QuickBooks."),
    (PAY_POST, "QuickBooks sends each customer an invoice for the deposit."),
    (PAY_POST, "I'd send your invoices from QuickBooks."),
    (PAY_POST, "Customers pay the deposit to your account through Stripe."),
    (PAY_POST, "I'd have Stripe invoice your customers automatically."),
    (PAY_POST, "You can invoice customers from QuickBooks as usual."),
    (PAY_POST, "I'd test it with a sandbox payment to your Stripe account."),
    (PAY_POST, "Vendors get paid to their accounts through Wise."),
    (PAY_POST, "When a customer pays by card in Stripe, QuickBooks closes the matching invoice."),
    (PAY_POST, "Refunds you issue in PayPal sync back to the order."),
    (PAY_POST, "Each customer gets a Stripe payment link for the deposit when the quote is approved."),
    (PAY_POST, "The bot can send a payment link for the balance once the job is done."),
    (PAY_POST, "Direct deposits from Stripe show up in QuickBooks the next day."),
    (PAY_POST, "Customers can pay by direct transfer or card."),
    (PAY_POST, "I'd send each customer the payment details with the quote."),
    (PAY_POST, "The invoice email includes your bank details for wire transfers."),
])
def test_r4_upwork_milestones_and_the_projects_own_money_pass(post, phrase):
    assert not r4_off(phrase, post)


# ---------------------------------------------------------------- defect 4: the project set up to reach the client now
@pytest.mark.parametrize("post,phrase", [
    # the reviewer's cases
    (WABOT_POST, "I can have the bot message you on WhatsApp so you can try it."),
    (SMS_POST, "I can have the bot text you so you can reply with a photo."),
    (WABOT_POST, "I'll add you to the WhatsApp test group."), (SLACK_POST, "I can join your Slack to test it."),
    # the same concept
    (WABOT_POST, "Let me have the bot WhatsApp you a sample quote."),
    (WABOT_POST, "I can get the bot to message you so you can test it."),
    (WABOT_POST, "I'll put you in the WhatsApp group with the bot."),
    (WABOT_POST, "I'll loop you into the WhatsApp test chat."),
    (WABOT_POST, "I'll have the bot ping you on WhatsApp Thursday."),
    (SMS_POST, "I'll set the bot up to text you tonight so you can see it work."),
    (SMS_POST, "I'll point the test number at your cell so you can try it."),
    (SMS_POST, "I can have the bot text your cell tonight."), (SMS_POST, "I can have the bot text you right now."),
    (SMS_POST, "Want me to have the bot text you a test quote?"),
    (SLACK_POST, "I'll invite you to the test channel in Slack."), (SLACK_POST, "I can hop into your Slack to watch it run."),
    (SLACK_POST, "I'll join the sales channel to test the alerts."),
    (WABOT_POST, "I'll hook the bot up to your WhatsApp so you can test it."),
    (WABOT_POST, "Let me add you as a tester so the bot can message you."),
    (WABOT_POST, "I can have the bot message you on WhatsApp each time I update it."),
    (SMS_POST, "I can have the bot text you each time I push a change."),
    (SLACK_POST, "I'll create a Slack channel for us."),
])
def test_r4_the_project_set_up_to_reach_the_client_now_is_refused(post, phrase):
    assert r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    # the reviewer's keep case, and Lorenzo describing the finished system
    (SMS_POST, "the bot can text you when a quote lands."), (SMS_POST, "When a quote lands, the bot texts you the photos."),
    (SMS_POST, "You'll get a text on your cell for each big quote."),
    (SMS_POST, "I can have the bot text you when a quote lands."),
    (SMS_POST, "I can have the bot text you whenever a big quote lands, so you see it first."),
    (SMS_POST, "I can set it up so the bot texts you each time a quote lands."),
    (SMS_POST, "I can have the bot text you as soon as a big quote comes in."),
    (SMS_POST, "I can have the bot send you a daily summary."),
    (WABOT_POST, "Once it's live, the bot can message you on WhatsApp when a big quote request comes in."),
    (WABOT_POST, "I'll set it up so the bot messages you on WhatsApp whenever a big quote lands."),
    (WABOT_POST, "Customers can join the WhatsApp group for showroom updates."),
    (WABOT_POST, "The bot can add each customer to a WhatsApp broadcast list."),
    (WABOT_POST, "The bot can message your front desk on WhatsApp when a photo arrives."),
    (SLACK_POST, "The bot posts each quote request to your sales channel in Slack."),
    (SLACK_POST, "I'd add a Slack button so a rep can claim the quote request."),
    (SLACK_POST, "Your reps can join the Slack channel the bot posts to."),
    (SLACK_POST, "New reps get added to the channel automatically."),
    (SLACK_POST, "The alerts can go to a Slack channel you pick."),
    (SMS_POST, "I can have the bot text you every morning with the new quotes."),
    (SMS_POST, "I can have the bot text you each time a quote lands."),
    (SLACK_POST, "The bot can create a Slack channel for each big quote."),
    (WABOT_POST, "The bot can add new customers to a WhatsApp list."),
])
def test_r4_the_finished_system_reaching_the_client_passes(post, phrase):
    assert not r4_off(phrase, post)


# ---------------------------------------------------------------- probe p14: go-along replies to a client's ask
GO_ALONG = [
    (POST, "Can we just talk on the phone? Easier for me.",
     "Happy to talk it through. What number should I call, and does Thursday at noon work? I'd start with how the "
     "quote requests land in HubSpot."),
    (POST, "Can you email me the scope?",
     "Sure. I'll write up the scope for the showroom quote intake and email it tonight, with the HubSpot fields and "
     "where the photos go."),
    (POST, "Can you email me the scope?",
     "Will do. You'll have it in your inbox tonight: the HubSpot fields for the quote requests and where the photos "
     "land."),
    (POST, "Can you email me the scope?",
     "Sure, which email should I send it to? It covers the HubSpot fields and the bathroom photos."),
    (POST, "How do you want to handle the deposit?",
     "I'll send you an invoice for the deposit once the showroom intake scope in HubSpot is agreed."),
    (POST, "Can you text me when it's ready?", "Sure, I'll text you when the HubSpot intake is ready."),
    (POST, "Can you invoice me directly? Upwork fees are high.",
     "I get it on the fees. I'll invoice you directly for the HubSpot intake once the scope is set."),
    (WABOT_POST, "Can I see it working?",
     "Yes. I can have the bot message you on WhatsApp so you can try it: send a bathroom photo and watch the quote "
     "request land in HubSpot."),
    (WABOT_POST, "Can I see it working?",
     "Yes. I'll add you to the WhatsApp test group so you can send a bathroom photo and see it land in HubSpot."),
    (SMS_POST, "Can I see it working?",
     "Yes. I can have the bot text you so you can reply with a bathroom photo and watch the quote request land in "
     "HubSpot."),
]
STAY_HERE = [
    (POST, "Can we just talk on the phone? Easier for me.",
     "Happy to talk it through on a short Upwork call Thursday at noon. I'd start with how the quote requests land "
     "in HubSpot with the photos attached."),
    (POST, "Can you email me the scope?",
     "I'll put the scope for the showroom quote intake right here in this chat tonight, with the HubSpot fields and "
     "where the photos go."),
    (POST, "How do you want to handle the deposit?",
     "I'd set the deposit up as the first Upwork milestone once the HubSpot intake scope is agreed."),
    (POST, "Can you invoice me directly? Upwork fees are high.",
     "I get it on the fees, but I keep payment on Upwork. The HubSpot intake can be one milestone here."),
    (WABOT_POST, "Can I see it working?",
     "Yes. I can record a Loom of the bot taking a bathroom photo on WhatsApp and logging the quote request in "
     "HubSpot."),
]


@pytest.mark.parametrize("post,ask,draft_text", GO_ALONG)
def test_r4_a_reply_that_goes_along_with_the_clients_ask_is_refused(post, ask, draft_text):
    assert "off_platform_contact" in codes(draft_text, kind="reply", r=r4_room(post, ask))


@pytest.mark.parametrize("post,ask,draft_text", STAY_HERE)
def test_r4_a_reply_that_keeps_the_same_ask_on_upwork_passes(post, ask, draft_text):
    assert "off_platform_contact" not in codes(draft_text, kind="reply", r=r4_room(post, ask))


# ---------------------------------------------------------------- probe p10: the rest of the leaks and false positives
@pytest.mark.parametrize("post,phrase", [
    (POST, "Thursday at noon on the phone works for me."), (POST, "Anytime, reach out by email."),
    (POST, "Email or here, whichever you prefer."), (POST, "You can also reach me through my website."),
    (POST, "Check your email, I just sent the scope."), (POST, "Just replied by email."),
    (POST, "Got your email, I'll reply there."), (POST, "I'll send the details to the address you gave."),
    (POST, "Let's chat on the phone."), (POST, "My calendar is open Thursday at noon, grab a slot."),
    (POST, "Here's where you can book me: my booking page."), (POST, "A voice call might be quicker."),
    (POST, "I'd rather talk by phone."), (POST, "Let's continue this in email."), (POST, "Easier over email."),
    (POST, "Email is quicker for me."), (POST, "We can finish the deal off the books."),
    (POST, "I'll ping you on my other account."),
    (WABOT_POST, "Easier to share screenshots over WhatsApp."), (WABOT_POST, "WhatsApp works better for voice notes."),
    (WABOT_POST, "I'll answer on WhatsApp."), (WABOT_POST, "Ping the test bot on WhatsApp and I'll reply from there."),
    (WABOT_POST, "Message me through the bot on WhatsApp."), (WABOT_POST, "Save my number and message the bot."),
    (WABOT_POST, "I'll WhatsApp the demo over tonight."),
    (SLACK_POST, "Invite me to your Slack workspace."), (SLACK_POST, "I'll DM you on Slack."),
    (MEET_POST, "I'd test it on a Zoom call with you Thursday."), (MEET_POST, "Send me a Zoom link for Thursday."),
    (MEET_POST, "Let's jump on Zoom."),
    (CAL_POST, "Grab a slot on my Calendly."), (CAL_POST, "Book a demo with me on Calendly."),
    (CAL_POST, "Here's my Calendly if you want to chat."),
])
def test_r4_probe_p10_moves_off_upwork_are_refused(post, phrase):
    assert r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    (MEET_POST, "Once a Zoom meeting ends, the summary goes to Slack."),
    (MEET_POST, "I'd test it on a recorded Zoom meeting first."),
    (MEET_POST, "I'd pull each Zoom recording into HubSpot."),
    (MEET_POST, "Your Zoom calls get transcribed and attached to the deal."),
    (CAL_POST, "When a prospect books a demo on Calendly, the deal lands in HubSpot with the Zoom link."),
    (CAL_POST, "I'd have the Calendly webhook create the deal."),
    (SMS_POST, "The bot texts each lead within a minute and the reply lands in HubSpot."),
    (SMS_POST, "If a lead texts back STOP, the bot marks them unsubscribed."),
    (SMS_POST, "Your front desk can text leads from the same number."),
    (SMS_POST, "The missed-call text back goes out within 30 seconds."),
    (DRIP_POST, "I'd forward replies to the owner's inbox and tag them in Instantly."),
    (DRIP_POST, "Each reply gets emailed to you with the lead's name in the subject."),
    (WABOT_POST, "The bot replies on WhatsApp within a minute and logs the photos in HubSpot."),
    (WABOT_POST, "Customers who message you on WhatsApp get an instant reply."),
])
def test_r4_probe_p10_project_sentences_pass(post, phrase):
    assert not r4_off(phrase, post)


def test_r4_must_keep_cases_from_earlier_rounds():
    assert not r4_off("I can call you Thursday.")
    assert not r4_off("Happy to do a short call here on Upwork Thursday at noon.")
    assert r4_off("I have a booking link if you want to pick a time.")  # the post never mentions booking


# ---------------------------------------------------------------- leaks with no channel word
# Asking where or how to reach the client, "there" for a channel a client
# message named, and a group Lorenzo sets up for himself and the client.
@pytest.mark.parametrize("post,phrase", [
    (POST, "Where should I send the scope?"), (POST, "Where do you want me to send the diagram?"),
    (POST, "Where would you like the scope sent?"), (POST, "Let me know where I should send the proposal."),
    (POST, "Tell me where to send it."), (POST, "How should I send you the scope?"),
    (POST, "How should I get it to you?"), (POST, "How do you want me to share the file with you?"),
    (POST, "What's the best way to get the scope to you?"), (POST, "What's the best way to reach you?"),
    (POST, "How can I reach you?"), (POST, "Where can I reach you Thursday?"),
    (POST, "How do I get in touch with you?"), (POST, "Where's the best place to send the doc?"),
    (POST, "Where should I send the invoice?"), (POST, "Any preference on where I send the scope?"),
    (SLACK_POST, "Where would you like the scope sent?"), (SMS_POST, "Where do you want me to send the test texts?"),
])
def test_r4_asking_where_to_reach_the_client_is_refused(post, phrase):
    assert r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    (POST, "Where should the bot send the quote requests?"),
    (POST, "Where should I send the new leads, HubSpot or Pipedrive?"),
    (SLACK_POST, "Where would you like the alerts sent?"),
    (POST, "Where do new quote requests go today?"), (SMS_POST, "How should the bot reach you when a big quote lands?"),
    (SMS_POST, "How can leads reach you after hours?"), (SMS_POST, "Where should I send the new lead alerts?"),
    (DRIP_POST, "Where should the replies go?"), (DRIP_POST, "Where should I send the bounces, a sheet or HubSpot?"),
    (POST, "Where can I get the API key?"), (POST, "How should I get the HubSpot fields right?"),
    (POST, "How should I share the HubSpot view?"), (POST, "Where can I find you on Upwork?"),
    (POST, "How can I find you a better CRM?"),
])
def test_r4_the_projects_routing_questions_pass(post, phrase):
    assert not r4_off(phrase, post)


THERE_GO_ALONG = [
    (POST, "What's your email? I'd rather do this there.",
     "Sure, just message me there and I'll send the HubSpot scope."),
    (POST, "Can we move this to WhatsApp?", "Sure, message me there."),
    (POST, "Can we move this to WhatsApp?", "Happy to continue there."),
    (POST, "Can we move this to WhatsApp?", "I'll reply there tonight."),
    (POST, "Can we move this to WhatsApp?", "Happy to keep you posted there."),
    (POST, "Let's do a Zoom call tomorrow.", "Great, see you there."),
    (POST, "Can we hop on Zoom?", "Happy to walk you through it there."),
    (POST, "Can you email me the scope?", "Sure, I'll send it there tonight."),
    (POST, "Can you text me the details?", "Sure, hit me up there anytime."),
    (POST, "Can the daily report go to my email?", "Yes, I'll send it there every morning."),
    (SMS_POST, "Can the bot text me when a lead replies?", "Yes, I'll send you a copy of each reply there."),
    (POST, "Can we move this to WhatsApp?", "I'll go over it with you there."),
    (POST, "Can you add me to the Slack workspace?", "Sure, I'll get you set up there."),
]
THERE_PROJECT = [
    (WABOT_POST, "Customers message us on WhatsApp all day.",
     "The bot will reply there within a minute and log the photos in HubSpot."),
    (WABOT_POST, "Customers message us on WhatsApp all day.",
     "Customers who message there get a reply from the bot within a minute."),
    (SMS_POST, "Can the bot text me when a lead comes in?", "Yes, and you can reply there to claim it."),
    (SMS_POST, "Most leads text us after hours.", "Your front desk can reply there if a lead asks something odd."),
    (SMS_POST, "Can the bot text me when a big quote lands?",
     "Yes, and I can have it text you there when a quote lands."),
    (SLACK_POST, "Can the alerts go to our Slack?", "Yes, the bot posts each quote request there with the photos."),
    (DRIP_POST, "Replies should go to my inbox.", "The drip will forward every reply there within a minute."),
    (POST, "Leads should go to my email.", "I'll forward the new leads there."),
    (POST, "Can the daily report go to my email?", "Yes, the bot will send it there every morning."),
    (POST, "Can we do an Upwork call tomorrow?", "Sure, see you there."),
    (POST, "Can we do a Zoom call?", "Upwork has calls built in. See you there tomorrow at 2."),
    (POST, "Most requests come in with photos of the bathroom.", "Happy to continue there."),  # no channel named
    (POST, "Check the photos on our Facebook page.", "I saw the photos you posted there, the bathroom ones are clear."),
    (SLACK_POST, "Can we get the alerts in Slack?", "I'll set up the alerts for you there."),
]


@pytest.mark.parametrize("post,ask,draft_text", THERE_GO_ALONG)
def test_r4_there_for_a_channel_the_client_named_is_refused(post, ask, draft_text):
    assert "off_platform_contact" in codes(draft_text, kind="reply", r=r4_room(post, ask))


@pytest.mark.parametrize("post,ask,draft_text", THERE_PROJECT)
def test_r4_there_for_the_projects_channel_or_for_upwork_passes(post, ask, draft_text):
    assert "off_platform_contact" not in codes(draft_text, kind="reply", r=r4_room(post, ask))


def test_r4_there_is_is_not_the_channel_the_client_named():
    # the email ask was answered, so the round-5 move rule does not read it,
    # but the "there" rule still does: only a place "there" is refused
    r = dict(room(messages=[{"side": "client", "text": "Can you email me the scope?"},
                            {"side": "freelancer", "text": "I'll put the scope together tonight."},
                            {"side": "client", "text": "Most requests come in with photos of the bathroom."}]),
             client="Invented Co", job_title="Automation build")
    assert "off_platform_contact" not in codes("I'll let you know if there is anything else to check in HubSpot.",
                                               kind="reply", r=r)
    assert "off_platform_contact" in codes("Sure, I'll send it there tonight.", kind="reply", r=r)


@pytest.mark.parametrize("post,phrase", [
    (WABOT_POST, "I'll set up a shared WhatsApp group for updates."),
    (SLACK_POST, "I'll set up a Slack channel for updates."), (WABOT_POST, "Let's set up a shared WhatsApp group."),
    (SLACK_POST, "I can create a private Slack channel for the project."),
    (WABOT_POST, "I'll start a WhatsApp group for questions."), (POST, "I'll make a group chat for quick questions."),
    (SLACK_POST, "Can we set up a shared Slack channel for feedback?"),
    (SLACK_POST, "I'll create a private Slack channel for us."),
    (WABOT_POST, "I'll set up a WhatsApp group for your team and me."),
    (WABOT_POST, "I'll set up a WhatsApp group for updates with you and your team."),
])
def test_r4_a_group_lorenzo_sets_up_for_himself_and_the_client_is_refused(post, phrase):
    assert r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    (WABOT_POST, "I'd set up a shared WhatsApp group for your installers."),
    (SLACK_POST, "The bot can post updates to a shared Slack channel for your reps."),
    (SLACK_POST, "I'd set up a Slack channel for the quote updates."),
    (SLACK_POST, "The bot can create a Slack channel for each big quote."),
    (DRIP_POST, "I'd set up a shared inbox for the front desk."),
    (WABOT_POST, "The bot can start a WhatsApp group for each install crew."),
    (SLACK_POST, "I'd create a private Slack channel for your sales reps."),
    (SLACK_POST, "I'll set up a private Slack channel for the alerts."),
    (SLACK_POST, "I'd set up a shared channel so your installers see each job."),
    (POST, "I'll create a shared workspace in Airtable for the project."),
])
def test_r4_a_group_for_the_clients_team_or_the_projects_stream_passes(post, phrase):
    assert not r4_off(phrase, post)


# ---------------------------------------------------------------- the drip, campaign and sequence as the project
@pytest.mark.parametrize("post,phrase", [
    (DRIP_POST, "The drip can email you a copy of each reply."),
    (DRIP_POST, "The campaign can email you a summary when a lead replies."),
    (DRIP_POST, "I can have the drip email you a copy of each reply."),
    (DRIP_POST, "The sequence can email you a copy of each reply."),
    (DRIP_POST, "The workflow can email you a copy of each reply."),
    (SMS_POST, "the bot can text your cell when a quote lands."),
    (SMS_POST, "Can the bot text your cell when a big quote lands?"),
    (SMS_POST, "I can have the bot text your cell when a quote lands."),
    (SMS_POST, "The workflow will email your inbox a digest each morning."),
])
def test_r4_the_project_reaching_the_clients_own_line_passes(post, phrase):
    assert not r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    (DRIP_POST, "I can have the drip email you a test tonight so you can see it work."),
    (SMS_POST, "I can have the bot text your cell tonight."), (POST, "The bot works fine, what's your email?"),
    (POST, "What's your cell?"), (SMS_POST, "My assistant can text your cell the details."),
    (SMS_POST, "Do you prefer Slack or email for the alerts?"),  # the post never names Slack
])
def test_r4_the_project_nouns_do_not_open_the_clients_details(post, phrase):
    assert r4_off(phrase, post)


# ---------------------------------------------------------------- figures that are volumes, limits or changes
@pytest.mark.parametrize("phrase", [
    "HubSpot's rate limit of 100 per second is the one thing to watch", "you mentioned about 400 total showroom requests",
    "missed quote requests went from 300 down to 40", "I'd batch them 500 at a time", "I'd batch them 250 per run",
    "the API budget of 1000 calls a day covers it", "the API allows 100 requests per second",
    "it handled 1,200 quote requests last month",
])
def test_r4_rate_limits_totals_changes_and_batches_are_not_prices(phrase):
    assert "figure_not_in_offers" not in codes(R4_B + " " + phrase + ".", r=r4_room())


@pytest.mark.parametrize("phrase", ["the whole build comes to 3,000 total", "I'd do it for 2,000 total",
                                    "my rate is 100 an hour", "the quote for the build is 1,200"])
def test_r4_prices_next_to_those_words_are_still_refused(phrase):
    assert "figure_not_in_offers" in codes(R4_B + " " + phrase + ".", r=r4_room())


# ---------------------------------------------------------------- probes p12 and p13: time on adversarial input
ADVERSARIAL_UNITS = ["email ", "text ", "text me ", "1000 ", "one ", "the bot ", "1-", "$1 ", "call you on ", "x ", "@ab ",
                     "a, ", "Hey Dana, ", "in your inbox tonight ", "what number ", "I can have the bot text you ",
                     "pay the deposit to my account ", "your cell? "]


@pytest.mark.parametrize("unit", ADVERSARIAL_UNITS)
def test_r4_a_50kb_adversarial_draft_is_checked_in_under_a_second(unit):
    text = (unit * (50000 // len(unit) + 1))[:50000]
    start = time.perf_counter()
    out = codes(text, kind="reply")
    assert time.perf_counter() - start < 1.0
    assert "too_long" in out


@pytest.mark.parametrize("unit", ["email ", "text me ", "one ", "1-"])
def test_r4_check_time_stays_flat_as_the_draft_grows(unit):
    for n in (1500, 3000, 6000, 12000):
        text = (unit * (n // len(unit) + 1))[:n]
        start = time.perf_counter()
        codes(text, kind="reply")
        assert time.perf_counter() - start < 1.0, n


SOURCE_UNITS = {"channel words": "WhatsApp calendly email ", "sign-offs": "Thanks, Dana. ",
                "number words": "one two three ", "digits": "1000 ", "no spaces": "a", "the bot": "the bot ",
                "entities": "&amp;", "backslash-u": "\\u00", "brackets": "[lorenzo, x] "}


@pytest.mark.parametrize("unit", list(SOURCE_UNITS.values()), ids=list(SOURCE_UNITS))
def test_r4_a_66kb_adversarial_post_and_thread_are_checked_in_under_a_second(unit):
    post = (unit * (6000 // len(unit) + 1))[:6000]
    messages = [{"side": "client", "at": "2026-09-20T10:00:00Z", "text": post[:2000]} for _ in range(30)]
    r = room(post=post, messages=messages)
    start = time.perf_counter()
    codes(BESPOKE, kind="reply", r=r)
    assert time.perf_counter() - start < 1.0


# ================================================================ round 5: the client's own move request
# The client asks, after Lorenzo's last message, to move contact, a call,
# files, a group or payment off Upwork, or gives a number, address or handle
# for him to use. A draft that does not keep things on Upwork in so many words
# (Upwork, here, this chat, an Upwork call, milestones, escrow) is refused,
# and the reason names the category, never the client's words.
R5_POST = POST + " New requests should also ping the sales rep in Slack."
R5_TAIL = " It covers the HubSpot fields for the showroom quote requests and where the bathroom photos go."


def r5_room(*unanswered, **kw):
    """Client messages Lorenzo already answered (``earlier``), then the
    unanswered ones."""
    msgs = []
    for text in kw.get("earlier", ()):
        msgs += [{"side": "client", "text": text}, {"side": "freelancer", "text": "Thanks, noted."}]
    if not msgs:
        msgs.append({"side": "freelancer", "text": "Here is a short Loom of the HubSpot intake."})
    msgs += [{"side": "client", "text": t} for t in unanswered]
    return dict(room(post=kw.get("post", R5_POST), messages=msgs), client="Invented Co", job_title="Automation build")


def r5_off(draft_text, *unanswered, **kw):
    """The off_platform_contact reason for a draft in a room with those client
    messages, or None."""
    kind = kw.pop("kind", "reply")
    out = copy_gate.check_detailed(draft_text + R5_TAIL, kind, r5_room(*unanswered, **kw), OFFERS)
    return dict(out).get("off_platform_contact")


R5_BANK = "Would it be ok if I paid you directly by bank transfer? Saves us both the fees."
R5_PAYPAL = "Could I pay you through PayPal for this one?"
R5_CELL = "A call would be quicker. My cell is 512 555 0199."
R5_EMAIL = "Can you send the scope to my email? pat.l@invented-tile.example.com"
R5_WHATSAPP = "Are you on WhatsApp? It's much quicker for me."
R5_ZOOM = "Could we walk through it on Zoom instead?"
R5_MEET = "Let's hop on Google Meet tomorrow, I'll send you my link."
R5_CALENDLY = "Do you have a Calendly I can book from?"
R5_SLACK = "Could we move this conversation to our Slack?"
R5_GROUP = "Could you start a WhatsApp group with me and our office manager for updates?"
R5_FILES = "What's your email so I can send over our logo files?"
R5_HANDLE = "I'm @pat_invented on Telegram if that's easier."

R5_GO_ALONG = [
    # the reviewer's list
    (R5_BANK, "Sure, that works for me."), (R5_BANK, "No problem, whatever works for you."),
    (R5_PAYPAL, "Happy to do PayPal for this one."),
    (R5_CELL, "Works for me, I'll call that number Thursday at noon."),
    (R5_CELL, "Sure, I'll ring that number tomorrow at noon."), (R5_CELL, "Sure, I'll call you tomorrow at noon."),
    (R5_EMAIL, "Sure, I'll send the scope over to that address tonight."),
    (R5_EMAIL, "Will do, sending the scope over by email tonight."), (R5_EMAIL, "Sure, I'll send it over tonight."),
    (R5_WHATSAPP, "I'm on it too, happy to continue the conversation there."),
    (R5_ZOOM, "Happy to. I'll send an invite for Thursday at noon."), (R5_MEET, "Sure, I'll join at noon."),
    (R5_ZOOM, "Happy to demo it there Thursday at noon."), (R5_CALENDLY, "Sure, I'll send the link over."),
    (R5_SLACK, "Sure, send me an invite to your workspace."),
    (R5_GROUP, "Sure, I'll set up a WhatsApp group with your team for updates."),
    # more of the same
    (R5_BANK, "Sure, a bank transfer is fine."), (R5_PAYPAL, "No problem, I can take PayPal."),
    (R5_WHATSAPP, "Yep, WhatsApp works."), (R5_ZOOM, "Zoom works for me, Thursday at noon?"),
    (R5_EMAIL, "Perfect, it'll be in your inbox by tonight."),
    (R5_FILES, "Sure, send them over whenever you're ready."),
    (R5_HANDLE, "Got it, I'll message you tonight."), (R5_GROUP, "Sounds good, count me in."),
    ("Could I pay you outside Upwork to skip the fees?", "Sure, that's fine by me."),
]
R5_KEEP = [
    (R5_CELL, "Happy to talk it through on an Upwork call Thursday at noon."),
    (R5_EMAIL, "I'll post the scope right here in this chat tonight as a PDF."),
    (R5_BANK, "I keep payment on Upwork, so the deposit would be the first milestone."),
    (R5_PAYPAL, "I'd rather keep payment through Upwork, split into two milestones."),
    (R5_WHATSAPP, "I'd rather keep our messages on here so everything stays in one place."),
    (R5_ZOOM, "Upwork has video calls built in, so a call here Thursday at noon works."),
    (R5_CALENDLY, "Easiest is a call here on Upwork, Thursday at noon or Friday at 3pm CT."),
    (R5_SLACK, "I'll keep the updates in this thread so they are easy to find."),
    (R5_GROUP, "I'll post the updates in this chat so they are all in one place."),
    (R5_BANK, "The deposit can sit in escrow until the HubSpot intake is live."),
    (R5_FILES, "Feel free to attach the logo files right here."),
]


@pytest.mark.parametrize("ask,draft_text", R5_GO_ALONG)
def test_r5_a_draft_that_goes_along_with_the_clients_move_request_is_refused(ask, draft_text):
    assert r5_off(draft_text, ask)


@pytest.mark.parametrize("ask,draft_text", R5_KEEP)
def test_r5_a_draft_that_keeps_it_on_upwork_passes(ask, draft_text):
    assert not r5_off(draft_text, ask)


@pytest.mark.parametrize("ask,draft_text", [(ask, text) for ask, text in R5_GO_ALONG[:16]])
def test_r5_the_same_drafts_pass_when_nobody_asked(ask, draft_text):
    # the draft rules alone: only what names a channel or a group is refused
    expected = {"Happy to do PayPal for this one.", "Sure, I'll set up a WhatsApp group with your team for updates."}
    assert bool(r5_off(draft_text, "Most requests come in with photos of the bathroom.")) is (draft_text in expected)


@pytest.mark.parametrize("ask,draft_text,category", [
    (R5_BANK, "Sure, that works for me.", "payment"), (R5_BANK, "No problem, whatever works for you.", "payment"),
    (R5_CELL, "Sure, I'll call you tomorrow at noon.", "call"),  # round 7: a number and a call word
    (R5_EMAIL, "Sure, I'll send it over tonight.", "files"),
    (R5_ZOOM, "Happy to. I'll send an invite for Thursday at noon.", "call"),
    (R5_MEET, "Sure, I'll join at noon.", "call"),
    (R5_CALENDLY, "Sure, I'll send the link over.", "call"), (R5_GROUP, "Sounds good, count me in.", "group"),
    (R5_WHATSAPP, "Yep, happy to.", "contact"), (R5_HANDLE, "Got it, I'll message you tonight.", "details"),
])
def test_r5_the_reason_names_the_category(ask, draft_text, category):
    reason = r5_off(draft_text, ask)
    assert reason.startswith(copy_gate.MOVE_REASONS[category] + ", and the draft ")


@pytest.mark.parametrize("ask", [R5_CELL, R5_EMAIL, R5_HANDLE, R5_BANK, R5_FILES, "Call me on 512-555-0199 at noon."])
def test_r5_the_reason_never_quotes_the_client(ask):
    out = copy_gate.check_detailed("Sure, sounds good." + R5_TAIL, "reply", r5_room(ask), OFFERS)
    reasons = " ".join(reason for _, reason in out).lower()
    assert "off_platform_contact" in dict(out)
    for piece in ("512", "555", "0199", "pat", "invented-tile", "@", "telegram", "bank transfer", "logo"):
        assert piece not in reasons, piece


# ---------------------------------------------------------------- the detector, both directions
@pytest.mark.parametrize("ask,category", [
    (R5_BANK, "payment"), (R5_PAYPAL, "payment"), ("Could I pay you outside Upwork to skip the fees?", "payment"),
    ("Would Wise work for paying you? Upwork takes a big cut.", "payment"),
    ("Can you invoice me directly instead?", "payment"), ("Do you take bitcoin?", "payment"),
    ("Is Stripe ok?", "payment"), ("Please send me your bank details.", "payment"), ("Can I pay cash?", "payment"),
    (R5_ZOOM, "call"), (R5_MEET, "call"), (R5_CALENDLY, "call"), ("Can you call me at 512 555 0199 tomorrow?", "call"),
    ("Can we have a quick chat on WhatsApp?", "call"),
    (R5_GROUP, "group"), ("Can you add me to a Slack workspace for the project?", "group"),
    (R5_FILES, "files"), ("Can I send the brand files over Dropbox instead?", "files"), (R5_EMAIL, "files"),
    (R5_WHATSAPP, "contact"), ("Text me instead, it's easier.", "contact"), (R5_SLACK, "contact"),
    ("Let's keep payment on Upwork but chat on WhatsApp.", "contact"),
    (R5_CELL, "call"), ("My email is pat.l@invented-tile.example.com if that helps.", "details"),
    (R5_HANDLE, "details"), ("Let's meet on Zoom every Monday.", "call"),
    ("Email me every Monday with an update on the build.", "contact"),
])
def test_r5_the_detector_reads_a_move_request_and_its_category(ask, category):
    assert copy_gate.client_move_request(r5_room(ask)) == category


R5_PROJECT_ASKS = [
    "Can the confirmation text go to the homeowner too?",
    "We record our sales calls on Zoom, can those go into HubSpot?",
    "Our customers pay deposits by bank transfer, can the workflow mark them paid?",
    "Could we do a quick Upwork call tomorrow?", "The photos I emailed to the rep last month never reached HubSpot.",
    "Can the rep get the quote by email as well as in Slack?",
    "Does it work with the WhatsApp number our customers already use?",
    "Can the bot text me when a big quote comes in?", "Will the sales rep get a Slack ping for every request?",
    "Our installers have a WhatsApp group already, can the bot post jobs there?",
    "Can you keep everything here on Upwork? I prefer that.", "Why don't we set up a call here on Upwork?",
    "Customers usually call us or text the showroom line.", "How would the Calendly bookings get into HubSpot?",
    "Thanks, the Loom helped. Most requests come in with bathroom photos.", "We record every sales call on Zoom.",
    "All our consults happen on Google Meet.", "Can we accept payments via PayPal too?",
    "Can the report go to my email every Monday?", "Text me when a big quote lands.",
]


@pytest.mark.parametrize("ask", R5_PROJECT_ASKS)
def test_r5_the_detector_leaves_project_questions_alone(ask):
    assert copy_gate.client_move_request(r5_room(ask)) is None


@pytest.mark.parametrize("ask", ["Is Stripe ok or should we switch to Square?",
                                 "Can we accept payments via PayPal too?", "Would PayPal work for the deposit?",
                                 "Could we switch to Stripe?", "Is Stripe ok?"])
def test_r5_in_a_payments_job_the_rails_are_the_project(ask):
    assert copy_gate.client_move_request(r5_room(ask, post=PAY_POST)) is None


@pytest.mark.parametrize("ask", ["Is PayPal ok for paying you?", "Can I pay you via Wise?", "What's your PayPal?",
                                 "Can I just pay directly?", "Can I pay via PayPal to avoid the fees?",
                                 "Do you accept PayPal?"])
def test_r5_in_a_payments_job_paying_lorenzo_still_counts(ask):
    assert copy_gate.client_move_request(r5_room(ask, post=PAY_POST)) == "payment"


R5_PROJECT_ROOMS = [
    ("HVAC company: ServiceTitan jobs should text the tech the address and notes, and email the customer a "
     "confirmation.", ("Can the tech get the job details by text?", "Will customers get an email too?"), (
        "Yes, the tech gets a text with the address and the customer's notes as soon as the job is booked in "
        "ServiceTitan.",
        "Customers get a confirmation email from your ServiceTitan account with the tech's name and arrival window.")),
    ("Law firm: new web inquiries go into Clio, the paralegal gets an email with the intake answers, and the caller "
     "gets an SMS confirmation.", ("Will the paralegal see the intake answers?", "Can callers reply to the SMS?"), (
        "The paralegal gets an email with the intake answers and the caller's number, and the matter is created in "
        "Clio.",
        "Callers can reply to the SMS, and the reply lands on the Clio matter so the paralegal sees it.")),
    ("Gym: members book classes in Mindbody, get a reminder text two hours before, and can reply X to cancel.",
     ("Do members get a reminder before class?",), (
        "Members get a text two hours before class from your Twilio number, and a reply of X cancels the booking in "
        "Mindbody.",)),
    ("Bookkeeping firm: match client bank transfers to open invoices in Xero and email the client a receipt.",
     ("Our clients pay invoices by bank transfer, can it match them?",), (
        "When a bank transfer lands, the workflow matches it to the open Xero invoice by amount and client name, then "
        "emails the receipt.",)),
    ("Real estate team: a WhatsApp bot sends agents new listings that match a buyer, and agents reply to book a "
     "showing.", ("Can agents get a WhatsApp message when a new listing matches?",), (
        "Yes, the agent gets a WhatsApp message with the listing link as soon as it matches a buyer's criteria, and "
        "can reply to book the showing.",)),
    ("Sales team: pull each Zoom sales call recording into HubSpot with a summary, and post the summary to Slack.",
     ("Can the Zoom recordings land on the HubSpot deal?", "We record every sales call on Zoom."), (
        "Each Zoom recording gets attached to the HubSpot deal with a short summary once the call ends, and the same "
        "summary goes to the sales channel in Slack.",
        "Recordings from every sales call would be pulled in within a few minutes of the call ending.")),
    ("Stripe and PayPal payments into QuickBooks, with refunds synced back.",
     ("Is Stripe ok or should we switch to Square?", "Do refunds sync both ways?"), (
        "Each Stripe payout lands in QuickBooks with the fees split out, and refunds sync back as credit memos.",)),
]


@pytest.mark.parametrize("post,asks,draft_text",
                         [(post, asks, text) for post, asks, texts in R5_PROJECT_ROOMS for text in texts])
def test_r5_ordinary_project_replies_pass(post, asks, draft_text):
    r = dict(r5_room(*asks, post=post), job_title="Automation build")
    assert copy_gate.client_move_request(r) is None
    assert "off_platform_contact" not in codes(draft_text, kind="reply", r=r)


# ---------------------------------------------------------------- pointing back at the client's ask beats a keep cue
R5_MIXED = [
    # the coordinator's three
    (R5_CELL, "Works for me, I'll call that number Thursday at noon and post the agenda here first."),
    (R5_EMAIL, "Sure, I'll send the scope over to that address tonight, and a copy here."),
    (R5_MEET, "Sure, I'll join at noon, and put the notes in this chat after."),
    # one per pointer
    (R5_EMAIL, "I'll use that email for the scope, and keep a copy here."),
    (R5_CALENDLY, "I'll book through that link, and confirm the time here."),
    (R5_SLACK, "Thanks for that invite, I'll keep the files here too."),
    (R5_GROUP, "I'll check that group daily and post the summary here."),
    (R5_SLACK, "I'll hop into that workspace and keep a copy here."),
    (R5_CELL, "I'll call you tomorrow at noon, and recap here after."),
    (R5_CELL, "I'll ring you tomorrow and recap on Upwork after."),
    (R5_WHATSAPP, "I'll text you the recap and post it here too."),
    (R5_EMAIL, "I'll send the scope over to you tonight and keep a copy in this chat."),
    (R5_ZOOM, "Sounds good, I'll join the call Thursday and share notes here."),
    (R5_GROUP, "I'll set up the group tonight and keep the files here too."),
    (R5_GROUP, "I'll add the group to my phone and keep the files here."),
    (R5_CELL, "I'll call that phone number Thursday, and confirm here."),
]


@pytest.mark.parametrize("ask,draft_text", R5_MIXED)
def test_r5_a_keep_cue_does_not_save_a_draft_that_goes_along(ask, draft_text):
    # since round 6 an extra copy ("a copy here", "here too"), a confirmation or a recap is no keep cue at
    # all; the rest still have one
    extra = any(word in draft_text for word in ("a copy", "here too", "confirm", "recap"))
    assert copy_gate.keeps_on_upwork(draft_text) is not extra
    assert "goes along with it" in copy_gate.move_request_reason(draft_text, r5_room(ask))
    assert r5_off(draft_text, ask)  # some are refused earlier by the draft rules, all are refused


@pytest.mark.parametrize("draft_text", ["Sure, I'll join the Upwork call at noon.",
                                        "I'll call you here on Upwork Thursday at noon.",
                                        "I'll text the lead from the bot and keep updates here."])
def test_r5_those_words_matter_only_after_a_move_request(draft_text):
    assert not r5_off(draft_text, "Most requests come in with photos of the bathroom.")


def test_r5_the_goes_along_reason_quotes_the_draft_not_the_client():
    reason = r5_off("Works for me, I'll call that number Thursday at noon and post the agenda here first.", R5_CELL)
    expected = copy_gate.MOVE_REASONS["call"] + ", and the draft goes along with it ('that number')"
    assert reason.startswith(expected)
    assert "512" not in reason and "0199" not in reason


# ---------------------------------------------------------------- which messages are read, and for which drafts
def test_r5_a_request_lorenzo_already_answered_is_not_read():
    r = r5_room("Thanks, the Loom helped.", earlier=[R5_CELL, R5_BANK])
    assert copy_gate.client_move_request(r) is None
    assert not r5_off("Sure, I'll call you tomorrow at noon.", "Thanks, the Loom helped.", earlier=[R5_CELL])
    assert not r5_off("Sure, that works for me.", "Thanks, the Loom helped.", earlier=[R5_BANK])


def test_r5_every_unanswered_message_is_read_and_the_newest_request_decides():
    assert copy_gate.client_move_request(r5_room(R5_WHATSAPP, "Also, how many reps get the Slack ping?")) == "contact"
    assert copy_gate.client_move_request(r5_room(R5_BANK, R5_ZOOM)) == "call"
    assert copy_gate.client_move_request(r5_room(R5_ZOOM, "Or I could pay you directly, whichever.")) == "payment"


def test_r5_room_events_and_empty_messages_do_not_end_the_run():
    r = r5_room(R5_CELL)
    r["messages"] += [{"side": None, "text": "Invented Co viewed the proposal"}, {"side": "client", "text": ""}]
    assert copy_gate.client_move_request(r) == "call"


def test_r5_only_the_newest_ten_unanswered_messages_are_read():
    asks = [R5_CELL] + ["Most requests come in with photos of the bathroom."] * copy_gate.MOVE_REQUEST_MESSAGES
    assert copy_gate.client_move_request(r5_room(*asks)) is None
    assert copy_gate.client_move_request(r5_room(*asks[:-1])) == "call"


def test_r5_at_most_8000_characters_of_unanswered_text_are_read_newest_first():
    long = ("Most requests come in with photos of the bathroom. " * 100)[:copy_gate.ANALYSIS_MAX_CHARS]
    assert copy_gate.MOVE_REQUEST_CHARS == 2 * copy_gate.ANALYSIS_MAX_CHARS
    assert copy_gate.client_move_request(r5_room(R5_CELL, long)) == "call"
    assert copy_gate.client_move_request(r5_room(R5_CELL, long, long)) is None
    assert copy_gate.client_move_request(r5_room(long + " " + R5_CELL)) is None  # past the per-message cap


@pytest.mark.parametrize("kind", ["touch", "checkin"])
def test_r5_touches_and_checkins_read_the_clients_last_message_too(kind):
    ask = "Not now. Message me on WhatsApp in October, it's easier."
    assert r5_off("Checking back in on the showroom quote intake.", ask, kind=kind)
    assert not r5_off("Checking back in here on the showroom quote intake.", ask, kind=kind)
    assert not r5_off("Checking back in on the showroom quote intake.", "Not now, check back in October.", kind=kind)


# ---------------------------------------------------------------- the keep cue
@pytest.mark.parametrize("text,keeps", [
    ("I'll keep the scope here on Upwork.", True), ("A quick Upwork call Thursday at noon works.", True),
    ("I'll post it in this chat tonight.", True), ("The first milestone covers the intake.", True),
    ("The deposit can sit in escrow.", True), ("Happy to keep talking on here.", True),
    ("Feel free to attach them right here.", True), ("I'll reply in this thread.", True),
    ("Here's the plan for the intake.", False), ("Here is the plan.", False), ("Here you go.", False),
    ("Happy to move this off Upwork.", False), ("We can skip Upwork's fees that way.", False),
    ("Upwork's fees are high, so PayPal is easier.", False), ("Instead of Upwork, email works.", False),
    ("Rather than the milestones, I'll invoice you.", False), ("Sure, that works for me.", False),
    ("Let's move away from Upwork.", False), ("Not on Upwork, by email.", False),
    ("We can work outside of Upwork.", False), ("No Upwork fees that way.", False), ("Where should I send it?", False),
])
def test_r5_keeps_on_upwork(text, keeps):
    assert copy_gate.keeps_on_upwork(text) is keeps


# ---------------------------------------------------------------- optional fix: a group's purpose beats the team word
@pytest.mark.parametrize("post,phrase", [
    (WABOT_POST, "I can set up a shared WhatsApp group for updates with your team."),
    (WABOT_POST, "I'll set up a WhatsApp group with your team for updates."),
    (POST, "I'll set up a WhatsApp group for questions with your office manager."),
    (SLACK_POST, "I'll create a Slack channel for feedback with your reps."),
    (WABOT_POST, "I'll start a WhatsApp group for quick questions, your team can join too."),
])
def test_r5_a_group_for_updates_or_questions_is_refused_even_with_the_clients_team(post, phrase):
    assert r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    (WABOT_POST, "I'll set up a WhatsApp group for updates to your installers."),
    (WABOT_POST, "I'll set up a WhatsApp group with your installers for each job."),
    (SLACK_POST, "I'll set up a Slack channel with your reps for the new quote alerts."),
    (SLACK_POST, "I'll set up a Slack channel for updates on each quote request for your reps."),
    (WABOT_POST, "I'll set up a WhatsApp group for questions so your customers get answers fast."),
    (POST, "I'll create a shared workspace for the project in Airtable."),
])
def test_r5_the_teams_or_the_projects_group_still_passes(post, phrase):
    assert not r4_off(phrase, post)


# ---------------------------------------------------------------- time
@pytest.mark.parametrize("unit", ["Can we move this to WhatsApp? ", "pay you directly ", "my cell is 512 555 0199 ",
                                  "call me ", "you ", "Zoom ", "a, ", "@ab "])
def test_r5_long_hostile_client_messages_are_read_in_under_a_second(unit):
    text = (unit * (2000 // len(unit) + 1))[:2000]
    r = r5_room(*[text] * 30)  # 60 KB unanswered; the detector reads the newest 8,000 characters
    start = time.perf_counter()
    codes("Sure, that works for me." + R5_TAIL, kind="reply", r=r)
    assert time.perf_counter() - start < 1.0


# ================================================================ round 6
# ---------------------------------------------------------------- the detector: paying another way, agreeing words
R6_PAY_ANOTHER_WAY = [
    # the reviewer's five
    "Upwork takes a big cut, can I pay you another way?", "Is there another way to pay you besides Upwork?",
    "The fees on here are brutal, any other way to pay you?", "Can I pay you some other way? Upwork charges me a lot.",
    "I'd rather not pay the Upwork fees, can I just send a bank transfer?",
    # the same concepts, other words
    "Upwork keeps a hefty cut, could I pay you a different way?",
    "Is there some other way to pay you apart from Upwork?",
    "Honestly the fees here are steep. How should I pay you?", "Other than Upwork, how can I pay you?",
    "Is there a different way I can pay you?", "Upwork takes 20%, is there another option?",
    "I'd prefer not to pay the Upwork fees.", "I'd rather not pay the fees on here.",
    "Can I just send you a wire for the deposit?", "I'll send you a bank transfer tomorrow.",
    "Can I send a payment now for the first part?", "I can send the money straight to your bank account.",
    "The fees here are killing me, what payment options do you have?",
]


@pytest.mark.parametrize("ask", R6_PAY_ANOTHER_WAY)
def test_r6_asks_to_pay_lorenzo_another_way_are_payment(ask):
    assert copy_gate.client_move_request(r5_room(ask)) == "payment"


@pytest.mark.parametrize("ask,category", [
    ("I don't mind paying via PayPal if that's easier for you.", "payment"),
    ("I wouldn't mind paying you through Wise.", "payment"), ("No problem paying you through Wise.", "payment"),
    ("Not a problem, I can pay you via Zelle.", "payment"), ("Why don't I just pay you by Zelle?", "payment"),
    ("Wouldn't it be easier to chat on WhatsApp?", "contact"),
    ("Would it not be easier to chat on WhatsApp?", "contact"),
    ("Is it easier to just text you?", "contact"),
])
def test_r6_agreeing_words_are_not_negations(ask, category):
    assert copy_gate.client_move_request(r5_room(ask)) == category


@pytest.mark.parametrize("ask", [
    "No need to pay me outside Upwork, milestones are fine.", "I don't want to move off Upwork for this.",
    "We don't need a Zoom call, the Loom covers it.", "Would it be easier if the bot texted the rep?",
])
def test_r6_real_negations_and_the_project_still_hold(ask):
    assert copy_gate.client_move_request(r5_room(ask)) is None


R6_PAY_PROJECT = [
    "Can customers pay another way, like Apple Pay?", "We need another way to pay our vendors.",
    "Is there another way to pay for the Zapier plan?", "Can the workflow send money to the installers every Friday?",
    "The workflow should send a payment reminder when the invoice is due.",
    "Can the bot send the payment confirmation to the homeowner?", "I'll send payment when the milestone is approved.",
    "I'll send the payment tonight through Upwork.", "Can I send you a payment for the next milestone?",
    # three more ("Upwork takes a cut, so can I pay you a bit more ...") now
    # count outside a payments job under round 9's wider rule: see R9_WAS_R6
    "The fees here are steep. Anyway, is there another way to structure the Zapier flow?",
    "I'd rather not pay the fees for the Zapier premium plan, can we use Make instead?",
    "I'd rather not pay the setup fee.", "Upwork's fees are high, so can I pay you the first milestone now?",
    "How do I pay you, through the milestone?",
]


@pytest.mark.parametrize("ask", R6_PAY_PROJECT)
def test_r6_the_new_payment_forms_leave_milestones_and_the_project_alone(ask):
    assert copy_gate.client_move_request(r5_room(ask)) is None


@pytest.mark.parametrize("ask,post,category", [
    ("For your fee, would a bank transfer work?", PAY_POST, "payment"),
    ("Upwork takes a big cut, can I pay you another way?", PAY_POST, "payment"),
    ("Would a bank transfer work for the refunds?", PAY_POST, None),
    ("Can customers pay another way, like Apple Pay?", PAY_POST, None),
    ("Would WhatsApp be easier?", R5_POST, "contact"), ("Would WhatsApp be easier?", WABOT_POST, None),
    ("I can't do calls on Upwork, the app never works for me. Zoom?", R5_POST, "call"),
    ("Upwork messages are so slow. WhatsApp?", R5_POST, "contact"),
    ("Where should the alerts go? Slack?", R5_POST, None), ("Slack?", R5_POST, None),
    ("Would Slack be easier for the alerts?", R5_POST, None),
])
def test_r6_lorenzos_fee_a_platform_offered_as_easier_and_a_bare_platform_question(ask, post, category):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == category


# ---------------------------------------------------------------- the keep cue, category by category
# Since round 7 every draft in a move-request room needs the category's keep
# cue, whatever it opens with; an opening yes only labels the reason.
R6_GO_ALONG_STRAY_KEEP = [
    # the reviewer's go-along replies, in this file's rooms (a Zoom ask is a call)
    (R5_BANK, "Sure, that works for me. One thing I'd flag here: the photos need a size cap."),
    (R5_BANK, "Sure, that works for me. I'll post the updated scope here tonight."),
    (R5_BANK, "No problem, whatever works for you. Happy to help here."),
    (R5_BANK, "That works. I'd split it into two milestones: intake first, then the Slack ping."),
    (R5_BANK, "Sounds good, that's fine by me. I've attached the scope here as a PDF."),
    (R5_ZOOM, "Sure, Thursday at noon works. I'll post a short agenda here first."),
    (R5_ZOOM, "Works for me, talk Thursday at noon. I'll put the questions in this chat beforehand."),
    (R5_EMAIL, "Sure, you'll have it tonight. I'll drop a short summary here too."),
    (R5_EMAIL, "Will do, I'll send it over tonight and post the key points here."),
    (R5_SLACK, "Sure, send the invite over. I'll keep the Loom link here for reference."),
    (R5_SLACK, "Sounds good, happy to switch. I'll leave a note here with the plan."),
    # a keep cue for another category does not count
    (R5_BANK, "Sure, that works. I'll keep the scope here so it's easy to find."),
    (R5_ZOOM, "Sure, Thursday works. I'll attach the agenda right here."),
    (R5_ZOOM, "Sounds good. I'd keep payment in milestones."),
    (R5_PAYPAL, "Happy to. I'll reply here once the invoice is ready."),
    (R5_BANK, "Sure, that works. The scope is here on Upwork."), (R5_BANK, "Of course. I'll attach the invoice here."),
]


@pytest.mark.parametrize("ask,draft_text", R6_GO_ALONG_STRAY_KEEP)
def test_r6_a_stray_keep_word_does_not_save_a_draft_that_goes_along(ask, draft_text):
    reason = r5_off(draft_text, ask)
    assert reason and "goes along with it" in reason  # each opens with a yes, which labels the reason


def test_r6_a_go_along_in_a_payments_job_is_refused():
    assert r5_off("Sure, that works for me.", "For your fee, would a bank transfer work?", post=PAY_POST)


R6_KEEPS_THE_ASKED_THING = [
    (R5_BANK, "Sure, that works, I'll split it into two milestones."),  # the reviewer's ruling
    (R5_BANK, "Sure thing. I keep payment on Upwork, so the deposit would be the first milestone."),
    (R5_PAYPAL, "No problem at all, the deposit can sit in escrow until the intake is live."),
    (R5_ZOOM, "Happy to talk. Upwork has calls built in, so Thursday at noon on here works for me."),
    (R5_ZOOM, "Sure, a quick call here on Upwork Thursday at noon works."),
    (R5_CELL, "Happy to talk it through on an Upwork call Thursday at noon."),
    (R5_EMAIL, "Sure, I'll post the scope right here in this chat tonight."),
    (R5_FILES, "Sure, feel free to attach the logo files right here."),
    (R5_SLACK, "Sounds good, I'll keep the updates in this thread."),
    (R5_WHATSAPP, "No problem, I'll keep our messages on here so everything stays in one place."),
    (R5_GROUP, "Happy to keep things here on Upwork, and I'll post the updates in this chat."),
    (R5_ZOOM, "Sounds good, let's do it on Upwork instead, Thursday at noon."),
    (R5_ZOOM, "Sure, happy to meet on Upwork Thursday at noon."), (R5_FILES, "Sure, send them through Upwork."),
]


@pytest.mark.parametrize("ask,draft_text", R6_KEEPS_THE_ASKED_THING)
def test_r6_a_draft_that_keeps_the_asked_thing_on_upwork_passes(ask, draft_text):
    assert not r5_off(draft_text, ask)


@pytest.mark.parametrize("draft_text,passes", [
    ("Happy to talk it through. A quick Upwork call Thursday at noon or Friday at 3pm CT works for me.", True),
    ("I'll keep the scope here on Upwork so it's all in one place. I can attach the PDF in this chat tonight.", True),
    ("I'd rather keep things on Upwork for now, but a quick call here Thursday at noon works.", True),
    # round 7: payment or files kept here do not keep the call on Upwork
    ("Easiest is to keep payment through Upwork milestones, and I'd split it into two so the first one is small.",
     False),
    ("Feel free to attach the brand files right here in the chat.", False),
    ("I can send the scope here as a PDF tonight.", False),
])
def test_r7_in_a_call_room_only_a_call_keep_counts(draft_text, passes):
    assert bool(r5_off(draft_text, "Can we talk by phone?")) is not passes


@pytest.mark.parametrize("text,category,keeps", [
    ("I'll keep payment in milestones.", "payment", True), ("I'll keep payment in milestones.", "call", False),
    ("The deposit can sit in escrow.", "payment", True), ("Happy to keep payment here.", "payment", True),
    ("I'd split it into two milestones: intake first, then the ping.", "payment", False),
    ("I'd split it into two milestones, one for intake and one for the ping.", "payment", False),
    ("A quick call here on Upwork works.", "call", True), ("Upwork has video calls built in.", "call", True),
    ("Thursday at noon on here works.", "call", True), ("I'll attach the agenda here.", "call", False),
    ("I'll put the questions in this chat.", "call", False),
    ("A quick call here on Upwork works.", "contact", True),
    ("Feel free to attach the files here.", "files", True), ("Feel free to attach the files here.", "payment", False),
    ("I'll reply in this thread.", "contact", True), ("I'll reply in this thread.", "details", True),
    ("I'll keep the updates in this chat.", "group", True),
    ("Let's keep things here on Upwork.", "payment", True), ("Let's keep things here on Upwork.", "call", True),
    ("Let's keep things here on Upwork.", "files", True),
    ("Paying through Upwork keeps us both covered.", "payment", True),
    ("Keeping it on Upwork protects both of us.", "payment", True),
    ("The scope is here on Upwork.", "payment", False), ("I'll attach the invoice here.", "payment", False),
    ("Let's do it on Upwork instead.", "call", True), ("I'll post the agenda on Upwork first.", "call", False),
])
def test_r6_keep_cues_by_category(text, category, keeps):
    assert copy_gate.keeps_on_upwork(text, category) is keeps


@pytest.mark.parametrize("text", [
    "One thing I'd flag here: the photos need a size cap.", "Happy to help here.", "The key here is speed.",
    "I'll drop a short summary here too.", "I'll keep a copy here.", "I'll also post the key points here.",
    "I can't keep payment here.", "The fees on here are high.", "Two milestones: intake first, then the ping.",
])
def test_r6_filler_here_extra_copies_and_phases_are_not_keep_cues(text):
    assert not copy_gate.keeps_on_upwork(text)


@pytest.mark.parametrize("draft_text", [
    "Sure, I'll send it over here tonight.", "Sure, I'll send an invite for a call here on Upwork.",
    "Happy to switch the order of the milestones.", "Sure, I'll send the updated milestones over tonight.",
])
def test_r6_sending_or_switching_here_is_not_going_along(draft_text):
    assert copy_gate._goes_along(draft_text) is None


@pytest.mark.parametrize("ask,draft_text,ways", [
    (R5_BANK, "Sure, that works for me.", "payment through Upwork milestones or escrow"),
    (R5_ZOOM, "Sure, Thursday works. I'll attach the agenda here.", "a call here on Upwork"),
    (R5_EMAIL, "Sure, you'll have it tonight.", "the files attached here in this chat"),
    (R5_WHATSAPP, "Yep, happy to.", "Upwork messages here"),
    (R5_HANDLE, "Thanks, noted.", "Upwork messages or a call here on Upwork"),
    (R5_CELL, "Thanks, noted.", "a call here on Upwork"),
])
def test_r6_the_reason_says_how_that_category_stays_on_upwork(ask, draft_text, ways):
    reason = r5_off(draft_text, ask)
    assert reason.endswith(ways + ")")
    for piece in ("bank", "fees", "zoom", "whatsapp", "512", "pat"):
        assert piece not in reason.lower()


# ---------------------------------------------------------------- a group the project needs
DISPATCH_POST = ("HVAC company needs a dispatch bot: new jobs from ServiceTitan should post to a WhatsApp group for "
                 "our techs, and the office wants a Slack channel with updates on every job.")


@pytest.mark.parametrize("phrase", [
    "I'd set up a WhatsApp group for updates to your techs, and the bot posts each new ServiceTitan job there.",
    "The bot would post every new job to a WhatsApp group for your techs, with the address and the unit type.",
    "I'd create a Slack channel for updates on every job, so the office sees each ServiceTitan status change.",
    "I'd set up a private Slack channel for job updates, and each ServiceTitan stage change posts there for the "
    "office.",
    "I'd create a WhatsApp group for each tech, and the bot posts that tech's jobs for the day.",
    "I'd start a Slack channel for the office with updates on every job as it moves through ServiceTitan.",
    "I'd set up a shared WhatsApp group for updates with your techs, and the bot drops each new job in it.",
])
def test_r6_a_group_the_sentence_or_the_post_ties_to_the_project_passes(phrase):
    assert not off(phrase, r3_room(DISPATCH_POST, "How would the tech updates work?", client="Invented Co",
                                   title="Dispatch bot"))


def test_r6_a_group_the_client_asks_for_as_the_deliverable_passes():
    ask = "Could the bot post each new quote to a WhatsApp group for my reps?"
    phrase = "I'd set up a WhatsApp group for updates with your reps, and each new quote lands there."
    assert copy_gate.client_move_request(r5_room(ask)) is None
    assert not r5_off(phrase, ask)
    # the same group, when nobody asked for one, is a group for Lorenzo and the client
    assert r4_off("I can set up a shared WhatsApp group for updates with your team.", WABOT_POST)


# ================================================================ round 7
# ---------------------------------------------------------------- every draft needs the category's keep cue
R7_ANY_OPENER_GO_ALONG = [
    (R5_BANK, "Great, that works for me. I'll post the updated scope here tonight."),
    (R5_BANK, "Perfect. I'll attach the revised scope here this evening."),
    (R5_PAYPAL, "Ok, PayPal's fine for this one. I'll drop the invoice details here."),
    (R5_BANK, "Fine with me. I'll post the milestone plan: intake first, then the ping."),
    (R5_BANK, "Noted, that works. I'll reply here with the account details."),
    (R5_BANK, "Deal. I'll put a summary of the scope in this chat."),
    (R5_ZOOM, "Cool, works for me. I'll post a short agenda here first."),
    (R5_ZOOM, "Thursday at noon works for me. I'll post a short agenda here first."),
    (R5_ZOOM, "Thursday at noon is good. I'll put the questions in this chat beforehand."),
    (R5_ZOOM, "Talk Thursday at noon then. I'll post the agenda here."),
    (R5_CELL, "Alright, Thursday at noon. I'll send the agenda here first."),
]


@pytest.mark.parametrize("ask,draft_text", R7_ANY_OPENER_GO_ALONG)
def test_r7_a_draft_without_the_categorys_keep_is_refused_whatever_it_opens_with(ask, draft_text):
    assert r5_off(draft_text, ask)


R7_ANY_OPENER_KEEP = [
    (R5_BANK, "Great question. I only take payment through Upwork, but the first milestone can be small."),
    (R5_PAYPAL, "Totally get it. Paying through Upwork keeps us both covered, and I'd split it into two milestones."),
    (R5_ZOOM, "Great, a call would help. I'd keep it on Upwork: Thursday at noon or Friday at 3pm CT?"),
    (R5_ZOOM, "Perfect, an Upwork call Thursday at noon works."),
    (R5_CELL, "Thursday at noon works for me as a call here on Upwork."),
    (R5_WHATSAPP, "Thanks, I keep client chats here on Upwork and reply quickly through the day."),
    (R5_FILES, "Great, feel free to upload them here on Upwork."),
    (R5_GROUP, "Totally, I'll post updates here on Upwork after each step."),
]


@pytest.mark.parametrize("ask,draft_text", R7_ANY_OPENER_KEEP)
def test_r7_a_draft_with_the_categorys_keep_passes_whatever_it_opens_with(ask, draft_text):
    assert not r5_off(draft_text, ask)


def test_r7_an_opening_yes_only_labels_the_reason():
    ask = R5_BANK
    labelled = r5_off("Sure, that works. I'll post the updated scope here tonight.", ask)
    plain = r5_off("Great, that works. I'll post the updated scope here tonight.", ask)
    assert "goes along with it ('Sure')" in labelled
    assert "does not keep it on Upwork" in plain
    for reason in (labelled, plain):
        assert reason.startswith(copy_gate.MOVE_REASONS["payment"])


# ---------------------------------------------------------------- the detector: other payees, schedules, others' fees
R7_NO_POST = "Coaching business wants session recordings transcribed and summarized into Notion for each client."
R7_FSM_POST = "HVAC company needs Jobber jobs synced to QuickBooks and a weekly payout report for the techs."


@pytest.mark.parametrize("post,ask", [
    (PAY_POST, "Square fees are steep, any other option?"),
    (PAY_POST, "Processing fees are killing us. What else could customers use for large orders?"),
    (PAY_POST, "The card fees are too high, is there a cheaper way?"),
    (PAY_POST, "Stripe fees are brutal, is there another option?"),
    (PAY_POST, "We send a wire to our main supplier every month, can the sync log it?"),
    (PAY_POST, "I send a bank transfer to the landlord on the 1st, can the sync skip it?"),
    (PAY_POST, "Upwork fees aside, when could you start?"),
    (R7_FSM_POST, "We send the payments to our techs by wire, can Jobber show that?"),
    (R7_FSM_POST, "We send a bank transfer to each installer on Fridays, can the payout report show it?"),
    (R7_FSM_POST, "The fees on our payroll tool are brutal, is there a cheaper way to pay the crews?"),
    (R7_NO_POST, "Which app are the recordings on? Zoom?"),
    (R7_NO_POST, "Where do the session videos come from? Zoom?"),
    (R5_POST, "How would the rep see new requests? Slack?"),
])
def test_r7_payments_to_others_third_party_fees_and_tool_questions_are_the_project(post, ask):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


@pytest.mark.parametrize("ask,category", [
    ("Upwork's service fees are brutal, is there another option?", "payment"),
    ("The platform fee is way too high, how should I pay you?", "payment"),
    ("Can I just send a wire for the deposit?", "payment"), ("I'll send you a transfer on Friday.", "payment"),
    ("I can send the money to your account tomorrow.", "payment"),
    ("Upwork's call never connects for me. Zoom?", "call"), ("Can we just talk? Zoom?", "call"),
    ("A quick call would be easier. Google Meet?", "call"),
])
def test_r7_upwork_fees_money_sent_to_lorenzo_and_a_platform_after_talk_still_fire(ask, category):
    assert copy_gate.client_move_request(r5_room(ask)) == category


@pytest.mark.parametrize("post,ask,draft_text", [
    (PAY_POST, "Stripe fees are brutal, is there another option?",
     "Yes, ACH through Stripe costs less on big orders, and the QuickBooks sync matches those deposits the same way."),
    (PAY_POST, "We send a bank transfer to each supplier on Fridays, can the workflow log it in QuickBooks?",
     "Yes, each Friday transfer would post to QuickBooks as a bill payment against the supplier's open bill."),
    (R7_FSM_POST, "We send a wire to each installer every Friday, can the report show it?",
     "Sure, the weekly payout report would list each installer's Friday wire next to the Jobber jobs it covers."),
])
def test_r7_project_replies_about_payments_pass(post, ask, draft_text):
    assert not r5_off(draft_text, ask, post=post)


# ---------------------------------------------------------------- a phone number and a call word is a call request
@pytest.mark.parametrize("ask,category", [
    ("A call would be quicker, my cell is 512 555 0142.", "call"), ("Easier to just talk. 512 555 0142", "call"),
    ("Give me a ring when you're free: 512 555 0142.", "call"), ("My cell is 512 555 0142, call anytime.", "call"),
    ("My cell is 512 555 0142 if texting is easier.", "details"),
    ("My email is pat.l@invented-tile.example.com if you'd rather talk there.", "details"),
])
def test_r7_a_phone_number_with_a_call_word_is_a_call_request(ask, category):
    assert copy_gate.client_move_request(r5_room(ask)) == category


@pytest.mark.parametrize("draft_text,refused", [
    ("Great, Thursday at noon works. I'll post a short agenda here first.", True),
    ("Thursday at noon works for me. I'll put the questions in this chat beforehand.", True),
    ("Makes sense. A quick Upwork call Thursday at noon works for me.", False),
])
def test_r7_after_a_number_and_a_call_word_only_a_call_keep_counts(draft_text, refused):
    assert bool(r5_off(draft_text, "Easier to just talk. 512 555 0142")) is refused


# ---------------------------------------------------------------- a group the project needs, team word or not
R7_AGENCY_POST = "Agency wants a shared Slack channel for project updates with each client, fed from ClickUp."


@pytest.mark.parametrize("post,phrase", [
    (R7_AGENCY_POST, "I'd set up a shared Slack channel for updates, fed from ClickUp."),
    (R7_AGENCY_POST, "I'd create a private Slack channel for updates."),
    (R5_POST, "I'd set up a shared Slack channel for updates, and the bot posts each new quote there."),
    (R5_POST, "I'd set up a private Slack channel for updates on each HubSpot stage change."),
    (WABOT_POST, "I'll set up a shared WhatsApp group for updates on each HubSpot deal."),
])
def test_r7_a_group_the_post_asks_for_or_the_sentence_ties_to_the_project_passes(post, phrase):
    assert not r4_off(phrase, post)


@pytest.mark.parametrize("post,phrase", [
    (WABOT_POST, "I can set up a shared WhatsApp group for updates."),
    (R5_POST, "I'll set up a shared Slack channel for updates every Monday."),
    (WABOT_POST, "I'll set up a shared WhatsApp group and post each update there."),
    (R5_POST, "I'll create a private Slack channel for each project."),
    (WABOT_POST, "I can set up a shared WhatsApp group for updates with your team."),
])
def test_r7_an_unprompted_group_for_lorenzo_and_the_client_is_still_refused(post, phrase):
    reason = dict(copy_gate.check_detailed(R4_B + " " + phrase, "touch", r4_room(post), OFFERS)).get(
        "off_platform_contact") or ""
    assert reason.startswith("off-platform contact (a group for Lorenzo and the client)")


# ================================================================ round 8
# ---------------------------------------------------------------- money sent to Lorenzo, any schedule or purpose
# Only a "to" that names someone else (a supplier, the installers, payroll,
# "each / every" and a person) makes a send the client's own business. "Send
# you", "to your account" and "to your bank" are always Lorenzo, "to" and a
# verb is a purpose, and a schedule on its own never clears a send.
R8_TILE_POST = ("Brightline Tile needs showroom quote requests to land in HubSpot with the bathroom photos, and a "
                "Slack ping for the sales rep.")
R8_RETAINER_POST = ("Agency needs ongoing n8n maintenance on a monthly retainer, about 10 hours a month fixing and "
                    "adding workflows.")
R8_SENDS_TO_LORENZO = [
    (R8_RETAINER_POST, "Could I just send you a bank transfer every month instead?"),
    (R8_RETAINER_POST, "For the retainer, can I send you a wire each month?"),
    (R8_RETAINER_POST, "I'd prefer to send you the payment monthly by bank transfer."),
    (R8_RETAINER_POST, "I'll send you a wire every Friday for the hours."),
    (R8_RETAINER_POST, "Can I pay you by bank transfer every month?"),
    (R8_TILE_POST, "Can I just send a bank transfer to get things started?"),
    (R8_TILE_POST, "Could I send a wire to cover the deposit?"),
    (R8_TILE_POST, "I can send a transfer to speed things up."),
    (R8_TILE_POST, "Can I send you a bank transfer to get started?"),
    (R8_TILE_POST, "Easier if I send a wire to your account."),
]
R8_ROOMS = [("own", None), ("payments job", PAY_POST), ("payroll job", R7_FSM_POST)]


@pytest.mark.parametrize("room_name,other_post", R8_ROOMS)
@pytest.mark.parametrize("post,ask", R8_SENDS_TO_LORENZO)
def test_r8_money_sent_to_lorenzo_is_a_payment_request_in_every_room(post, ask, room_name, other_post):
    assert copy_gate.client_move_request(r5_room(ask, post=other_post or post)) == "payment"


@pytest.mark.parametrize("room_name,other_post", R8_ROOMS)
@pytest.mark.parametrize("post,ask", R8_SENDS_TO_LORENZO)
def test_r8_going_along_with_money_sent_to_lorenzo_is_refused_in_every_room(post, ask, room_name, other_post):
    reason = r5_off("Sure, that works for me.", ask, post=other_post or post)
    assert reason.startswith(copy_gate.MOVE_REASONS["payment"])
    assert "goes along with it ('Sure')" in reason


# the same asks, with "to" naming someone else: the client's own payments
R8_SENDS_TO_OTHERS = [
    (R7_FSM_POST, "Could we just send a bank transfer to each installer every month instead?"),
    (R7_FSM_POST, "For payroll, can we send a wire to the techs each month?"),
    (PAY_POST, "We'll send a wire to our supplier every Friday, can the sync log it?"),
    (R7_FSM_POST, "I'll send a wire to each of our installers every Friday for the hours."),
    (PAY_POST, "Can we send an e-transfer to the landlord every month?"),
    (PAY_POST, "Can I just send a bank transfer to each supplier to get things started?"),
    (PAY_POST, "Could I send a wire to our vendor to cover the deposit?"),
    (R7_FSM_POST, "I can send a transfer to our techs to speed things up."),
    (R7_FSM_POST, "Can we send a bank transfer to payroll to get started?"),
    (PAY_POST, "Easier if we send a wire to our supplier's account."),
    (R7_FSM_POST, "Could we send a wire to every contractor on Fridays?"),
    (R7_FSM_POST, "We'll send a transfer to each of them every Friday."),
    (PAY_POST, "We can send a wire to pay our suppliers every month, can the workflow log it?"),
]


@pytest.mark.parametrize("post,ask", R8_SENDS_TO_OTHERS)
def test_r8_a_send_whose_to_names_someone_else_is_the_project(post, ask):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


@pytest.mark.parametrize("ask", [
    "I'll send a wire every Friday.", "Could we send a bank transfer monthly instead?",
    "Can I send a wire to your business account each month?", "Can I send a transfer to your team every month?",
    "Can I send a bank transfer to you each month?", "What if I send payment to your account each week?",
    "Could I send a wire straight to your bank every Friday?", "Can I send a transfer every month to cover your hours?",
])
def test_r8_a_schedule_your_account_or_a_purpose_never_clears_a_send(ask):
    for post in (R8_TILE_POST, PAY_POST, R7_FSM_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"


# ---------------------------------------------------------------- the client sending, whatever the opening
R8_CLIENT_SENDS = [
    "I'd rather send a wire.", "Let me send a bank transfer to get started.", "I'm happy to send a bank transfer.",
    "Easier if I send a wire to you directly.", "Happy to send a check if that's easier.",
    "We'd prefer to send a wire to you each month.", "Would it be easier for me to send a bank transfer?",
    "I'll send the payment to you directly.", "Let me send you a check.", "I was going to send a bank transfer today.",
]


@pytest.mark.parametrize("room_name,other_post", R8_ROOMS)
@pytest.mark.parametrize("ask", R8_CLIENT_SENDS)
def test_r8_the_client_sending_money_counts_whatever_the_opening(ask, room_name, other_post):
    post = other_post or R8_TILE_POST
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"
    assert r5_off("Sure, that works for me.", ask, post=post).startswith(copy_gate.MOVE_REASONS["payment"])


@pytest.mark.parametrize("ask", [
    # Upwork, the platform or the project as the sender
    "Upwork will send the payment to you.", "Upwork sends it once I approve.",
    "Upwork will send you the money when I approve the work.", "The platform will send you the payment.",
    "I think Upwork will send the payment to your account.",
    "I'd like the workflow to send a transfer when the job closes.", "The system will send a wire to your account.",
    "I want the bot to send a check when an invoice is paid.",
    # a negation, another payee, or a check that is not money
    "I'd rather not send a wire.", "I can't send a bank transfer from here.", "I don't want to send a check.",
    "I'd rather send a wire to each supplier.", "Let me send a bank transfer to our techs to get started.",
    "Happy to send a check to the landlord every month.", "I'll send a check-in message every Monday.",
    "I'll send a check to see if the webhook fires.",
])
def test_r8_upwork_the_project_a_negation_or_another_payee_is_not_the_client_paying_lorenzo(ask):
    for post in (R8_TILE_POST, PAY_POST, R7_FSM_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


# ---------------------------------------------------------------- Upwork named only to leave it
R8_REFUSED_KEEP = [
    "I'd rather not pay through Upwork, I'll just send a wire.", "I'd rather not pay through Upwork.",
    "I don't want to pay through Upwork, can I send you a bank transfer?", "Instead of milestones, can I send a wire?",
    "Instead of paying via Upwork, I'll send a check.", "Skip the milestones, I'll send a bank transfer.",
    "I can't pay through Upwork right now, can I send a wire?", "Not through Upwork though, I'd send a wire.",
    "Outside of Upwork, could I send a bank transfer?", "I'd rather not pay through Upwork and just send a wire.",
]


@pytest.mark.parametrize("room_name,other_post", R8_ROOMS)
@pytest.mark.parametrize("ask", R8_REFUSED_KEEP)
def test_r8_upwork_named_only_to_leave_it_does_not_clear_the_request(ask, room_name, other_post):
    post = other_post or R8_TILE_POST
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"
    assert r5_off("Sure, that works for me.", ask, post=post).startswith(copy_gate.MOVE_REASONS["payment"])


@pytest.mark.parametrize("ask", [
    "I'll pay through Upwork milestones.",
    "I'll pay through Upwork milestones, and I'll send a payment for the first one.",
    "No problem paying through Upwork, I'll send a payment for the next milestone.",
    "I don't mind paying through Upwork, I'll send a payment for the first milestone.",
    "Why not just pay through Upwork?", "It's not a problem to pay through Upwork.",
    "I can't wait to fund the first milestone and send a payment for the rest.",
])
def test_r8_upwork_kept_still_clears_the_sentence(ask):
    for post in (R8_TILE_POST, PAY_POST, R7_FSM_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


# ---------------------------------------------------------------- the client's own habits are project talk
@pytest.mark.parametrize("ask", [
    "We send a wire every Friday, can the report show it?", "I send a bank transfer every month, can the sync log it?",
    "We usually send a check on the 1st, can QuickBooks match it?",
    "We pay by wire every Friday, can the report show it?",
    "I pay by check every month, can the sync log it?", "If we send a wire, can the report show it?",
    "We're sending a wire every Friday, can the report show it?",
])
def test_r8_how_the_client_pays_people_today_is_project_talk(ask):
    for post in (R7_FSM_POST, PAY_POST, R8_TILE_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


@pytest.mark.parametrize("ask", [
    "I'll send a wire every Friday for the hours.", "We send a wire every Friday, is that ok?",
    "If I send a wire, can you start today?", "I'm sending a wire today.", "Why don't I just send a wire?",
    "Do I just send a bank transfer?", "What if I send a check instead?", "We send a wire to you every Friday.",
])
def test_r8_an_offer_an_ask_or_you_still_counts(ask):
    for post in (R7_FSM_POST, PAY_POST, R8_TILE_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"


def test_r8_a_habit_asked_about_still_counts():
    ask = "We pay by bank transfer, is that ok?"
    assert copy_gate.client_move_request(r5_room(ask, post=R8_TILE_POST)) == "payment"


# ================================================================ round 9
# ---------------------------------------------------------------- the reviewer's missed asks and go-along replies
R9_SHOP_POST = ("Wholesale shop needs Shopify orders synced to QuickBooks; customers pay by Stripe or bank "
                "transfer and deposits must match invoices.")
R9_ROOF_POST = ("Roofing company needs missed calls texted back and leads pushed into GoHighLevel with the roof "
                "type and address.")
R9_MISSED_ASKS = [
    (R9_SHOP_POST, "For your fee I'd rather send a wire than go through Upwork."),
    (R8_TILE_POST, "For your fee I'd rather send a wire than go through Upwork."),
    (R8_TILE_POST, "I'd rather send a wire than go through Upwork."),
    (R8_TILE_POST, "I'd rather send a wire than pay through Upwork."),
    (R8_TILE_POST, "I'd rather pay by wire than through Upwork."),
    (R9_ROOF_POST, "Can I mail you a check?"), (R9_ROOF_POST, "Can I just mail you a check instead?"),
    (R9_ROOF_POST, "I'll mail you a check for the first half."), (R9_ROOF_POST, "Can I pay you by check?"),
    (R9_ROOF_POST, "Can I send you a check?"), (R9_ROOF_POST, "I'd rather write you a check."),
    (R9_ROOF_POST, "Would a check work?"), (R9_ROOF_POST, "Do you take checks?"),
    (R9_ROOF_POST, "I'd rather pay with a check, is that ok?"),
]


@pytest.mark.parametrize("post,ask", R9_MISSED_ASKS)
def test_r9_the_missed_asks_are_payment_requests(post, ask):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"
    assert r5_off("Sure, that works for me.", ask, post=post).startswith(copy_gate.MOVE_REASONS["payment"])


@pytest.mark.parametrize("ask,reply", [
    (ask, reply) for ask, replies in (
        ("I'd rather send a wire than go through Upwork.", (
            "Sure, that works for me.", "Sure, a wire works for me.",
            "That works, I'll send over the details for the wire.", "No problem, happy to do it that way.",
            "Sure, whatever is easier for you on the payment side.",
            "Understood, that's fine by me. I'll get started once it lands.")),
        ("Can I just mail you a check instead?", (
            "Sure, that works for me.", "Sure, a check works.", "Of course, I'll send you the mailing address.",
            "No problem, a check is fine.", "Sure, happy to take a check.")),
        ("Do you take checks?", ("Yes, I do.", "Yes, checks are fine.", "Sure, a check works for me.")),
    ) for reply in replies])
def test_r9_going_along_with_a_wire_or_a_check_is_refused(ask, reply):
    assert r5_off(reply, ask, post=R9_ROOF_POST)


# ---------------------------------------------------------------- "rather X than through Upwork" refuses Upwork
R9_THAN_UPWORK = [
    "I'd rather send a wire than go through Upwork.", "I'd rather send a wire than pay through Upwork.",
    "I'd rather pay by wire than through Upwork.", "For your fee I'd rather send a wire than go through Upwork.",
    "Honestly it's easier to wire it than to go through Upwork.", "I'd sooner mail a check than pay on Upwork.",
    "I'd prefer a bank transfer than paying via Upwork.",
]


@pytest.mark.parametrize("room_name,other_post", R8_ROOMS)
@pytest.mark.parametrize("ask", R9_THAN_UPWORK)
def test_r9_rather_than_through_upwork_is_neither_a_keep_nor_a_venue(ask, room_name, other_post):
    post = other_post or R8_TILE_POST
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"
    assert r5_off("Sure, that works for me.", ask, post=post).startswith(copy_gate.MOVE_REASONS["payment"])


@pytest.mark.parametrize("ask", [
    "I'll pay through Upwork milestones.", "Paying through Upwork is easier than a wire, so let's keep it there.",
    "I'd rather pay through Upwork than wire it.",
])
def test_r9_upwork_kept_against_another_rail_still_clears(ask):
    for post in (R8_TILE_POST, PAY_POST, R7_FSM_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


# ---------------------------------------------------------------- cheques, client side
R9_CHECK_ASKS = [
    "Can I mail you a check?", "I'll write you a check for the deposit.", "Can I send you a check?",
    "Do you take checks?", "Do you accept checks?", "Would a check work?", "Is a check fine?",
    "A check works for me, if that's ok.", "Can I pay by check?", "Paying by check is easiest for us.",
    "Can I mail a check to you?", "Who do I make the check out to?", "What name should I make the check payable to?",
    "Can I just mail a check?", "I'll drop a check in the mail.", "Would a cheque be ok?", "Do you take cheques?",
]


@pytest.mark.parametrize("post", [R9_ROOF_POST, PAY_POST, R7_FSM_POST])
@pytest.mark.parametrize("ask", R9_CHECK_ASKS)
def test_r9_a_check_for_lorenzo_is_a_payment_request_in_every_room(ask, post):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"


@pytest.mark.parametrize("ask", [
    "I'll send a check-in text to each lead.", "Can you run a check to see if the webhook fires?",
    "We take checks at the counter, can the sync log them?",
    "We drop a check in the mail every Friday for our supplier, can the report show it?",
    "We mail checks to our suppliers every month, can QuickBooks match them?",
    "Can the workflow mail a check to each installer?", "The bot should make the check out to the vendor on file.",
])
def test_r9_a_check_that_is_not_money_for_lorenzo_is_not_a_request(ask):
    for post in (R9_ROOF_POST, PAY_POST, R7_FSM_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


def test_r9_check_your_inbox_is_not_payment():
    for post in (R9_ROOF_POST, PAY_POST):
        assert copy_gate.client_move_request(r5_room("Can you check your inbox for the Loom?", post=post)) != "payment"


# ---------------------------------------------------------------- cheques, draft side
@pytest.mark.parametrize("draft_text", [
    "Sure, happy to take a check.", "No problem, a check is fine.", "Yes, checks are fine.",
    "Sure, a check works for me.", "Of course, I'll send you the mailing address.",
    "That works, I'll send over the details for the wire.", "Happy to take a bank transfer.",
    "Sure, mail me a check.", "You can mail the check to my office.", "Make the check payable to Advero Solutions.",
    "You can make the check out to me.", "Checks can be made payable to Advero Solutions.",
    "Just make it payable to Advero.",
])
def test_r9_lorenzo_taking_a_check_or_giving_mailing_or_wire_details_is_refused(draft_text):
    for post in (R9_ROOF_POST, PAY_POST):
        assert r5_off(draft_text, "Thanks, looks good.", post=post)


@pytest.mark.parametrize("draft_text", [
    "I'll add a check-in text for each new lead.", "I'd run a check to see if the webhook fires first.",
    "I'll map the mailing address field into GoHighLevel.",
    "I'll send the mailing address to GoHighLevel with the roof type.",
    "The bot makes the checks out to each supplier on Fridays.",
    "I'd have the workflow mail a check to each installer.",
    "I can't make it out to the office Thursday, but an Upwork call works.",
    "Give me a check on whether the webhook fired.",
])
def test_r9_checks_and_addresses_in_the_build_pass(draft_text):
    for post in (R9_ROOF_POST, PAY_POST):
        assert r5_off(draft_text, "Thanks, looks good.", post=post) is None


# ---------------------------------------------------------------- the wider rule
# Outside a payments job, a message the narrow rules pass still counts when a
# sentence ties a money word to Lorenzo ("pay you", "your fee", "to you", "you
# take / accept", "mail / write / send you", "you ... get paid") or to Upwork
# ("than through Upwork", Upwork's fees or cut), unless it keeps payment on
# Upwork or Upwork, the platform or the project moves the money.
R9_WIDER = [
    "What's your fee for this?", "I'll send the deposit to you tomorrow.", "How would you like to get paid?",
    "Our accountant will send the check to you.", "Can I pay you half up front?",
    "Upwork takes a cut of every payment, which I'd rather avoid.",
    "Upwork takes 20% of every payment, can we avoid that?", "Is the Upwork fee included in your price?",
]


@pytest.mark.parametrize("post", [R8_TILE_POST, R9_ROOF_POST])
@pytest.mark.parametrize("ask", R9_WIDER)
def test_r9_money_tied_to_lorenzo_or_upwork_counts_outside_a_payments_job(ask, post):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"
    assert r5_off("Sure, that works for me.", ask, post=post).startswith(copy_gate.MOVE_REASONS["payment"])


@pytest.mark.parametrize("ask", ["What's your fee for this?", "Can I pay you half up front?"])
def test_r9_the_wider_rule_stays_out_of_payments_jobs(ask):
    assert copy_gate.client_move_request(r5_room(ask, post=PAY_POST)) is None


@pytest.mark.parametrize("ask", [
    "I'll pay you through Upwork milestones.", "Upwork will send the payment to you.",
    "The bot can send you the invoice when a job closes.", "Upwork fees aside, how soon could you start?",
    "How does Upwork handle the fee?", "What's your rate for ongoing work?", "Does your price include the Slack ping?",
])
def test_r9_kept_on_upwork_moved_by_upwork_or_the_project_or_no_money_word_is_not_tied(ask):
    for post in (R8_TILE_POST, R9_ROOF_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


R9_WAS_R6 = [
    "Upwork takes a cut, so can I pay you a bit more to cover it?",
    "Upwork's fees are steep, so I can only pay you $500 for this.",
    "Upwork takes a big cut of your pay, so I added a bonus. Can I send it now?",
]


@pytest.mark.parametrize("ask", R9_WAS_R6)
def test_r9_upworks_cut_and_paying_lorenzo_now_count_outside_a_payments_job(ask):
    assert copy_gate.client_move_request(r5_room(ask)) == "payment"
    for post in (PAY_POST, R7_FSM_POST):
        assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


# ---------------------------------------------------------------- no false fire on ordinary project messages
# The reviewer's project messages from probes 16, 19, 21 (its project set) and
# 33, in a job that is not about payments: none is a payment request.
R9_PROJECT_MESSAGES = [
    # p16
    "How would reps get notified?", "Do homeowners get a text right away?", "Can it handle reschedules?",
    "Will the front desk get the call transcripts?",
    "Can the hiring manager reply to the email to move a candidate forward?", "How do refunds work?",
    "We sometimes get paid by bank transfer for wholesale orders.", "Can buyers set their own criteria in the bot?",
    "What happens if a patient replies something else?",
    # p19
    "Can the bot send the Slack ping to the rep's phone too?",
    "We use Zoom for sales calls, can the recordings go into HubSpot?",
    "Our customers pay by bank transfer, can the workflow mark the deposits as paid?",
    "Can you do a quick Upwork call tomorrow?",
    "I emailed the photos to the rep last week and they never landed in HubSpot.",
    "Does it work with our Zoom recordings?", "Could the form also text the customer a confirmation?",
    "Can the rep get the quote by email as well as Slack?",
    # p21, the project set
    "Can we hop on a quick call this week to go over the scope?", "Can you send me the scope as a PDF?",
    "I'll send the brand files here tomorrow.", "Can I fund the first milestone now?",
    "Sounds good. When could you start?", "Does the Slack ping go to the rep's phone as a push notification?",
    "Our reps mostly work from their phones, so mobile matters.",
    "We tried Zapier before and it kept breaking on the photo uploads.",
    "Can the rep also get an email copy of each quote request?", "I'm out Friday, back Monday. Talk then.",
    "Let's do a quick call here on Upwork Thursday.", "Can you call out the risks in the scope?",
    "Please text-wrap the photo names, they get cut off in HubSpot.", "Could you walk me through it on a call?",
    "I'll drop the assets in a Google Drive folder and share the link here.",
    "Can the bot text patients back within a minute?", "Patients prefer WhatsApp, can the bot handle both?",
    "Can we book consults straight into Calendly from the chat?",
    "Our virtual consults happen on Zoom, can the bot send the link after booking?",
    "Can the bot text me when a VIP patient books?",
    "We'd like the bot to email the front desk a summary every morning.",
    "What number would the bot text from? We have a Twilio number already.", "Is Stripe ok for the checkout?",
    "Can we accept payments via PayPal too?",
    "Customers who pay by bank transfer often forget the invoice number.",
    "How do refunds through PayPal show up in QuickBooks?", "Can the digest go to my email every morning at 8?",
    "Hiring managers book interviews over Google Meet, can n8n add the link to the candidate email?",
    "Can you email the hiring manager when a candidate scores above 80?",
    "Can the workflow send me a text if it fails?", "We'll need to test with real resumes, I can share a few here.",
    # p33
    "Customers keep asking for another way to pay besides cash, can the checkout add Apple Pay?",
    "Stripe fees are brutal, is there another option?",
    "Card fees are crazy high for us. How should customers pay for big orders?",
    "We send a bank transfer to each supplier on Fridays, can the workflow log it in QuickBooks?",
    "We send a wire to each installer every Friday, can the report show it?",
    "I send the payment to our techs by bank transfer, can Jobber track that?",
    "The fees on our payroll app are brutal, is there a cheaper way to pay the techs?",
    "Would Telegram be easier for the reps than Slack?",
    "Would it be easier to text the reps instead of pinging Slack?", "Would email be easier for the rep?",
    "Most of my coaching calls happen on Zoom. Is that a problem?",
    "What tool do the recordings need to come from? Zoom?", "Can it pull from Google Meet too, or only Zoom?",
    "I'd rather not pay for another HubSpot seat, can the rep use a free one?",
    "Upwork fees aside, how soon could you start?",
]


@pytest.mark.parametrize("ask", R9_PROJECT_MESSAGES)
def test_r9_the_wider_rule_leaves_ordinary_project_messages_alone(ask):
    assert copy_gate.client_move_request(r5_room(ask, post=R8_TILE_POST)) != "payment"


# ================================================================ round 10
# ---------------------------------------------------------------- a rail in Lorenzo's draft, asked for or not
# Outside a payments job, a draft that offers or accepts payment by any rail
# but Upwork is refused whether the client asked or not: the reviewer's p43
# twins and p41 replies, and the forms in the brief.
R10_SPA_POST = ("Med spa wants a Vapi voice agent that books consults in Boulevard and takes a card deposit for "
                "no-shows.")
R10_NO_ASK = "Looks good. When could you start?"
R10_RAIL_DRAFTS = [
    # p43
    "Sure, just send a bank transfer.", "Paying by bank transfer works.", "Just send a wire whenever you are ready.",
    "Paying by check works.", "Cash works too.",
    # p41
    "Just send a wire whenever you're ready.", "Paying by check works too.",
    # "send a wire", "paying by X works", "X works (too / for me)", "X is fine", "you can pay by X"
    "Feel free to send the wire today.", "Send the check whenever you're ready.", "Wire it over whenever you're ready.",
    "A wire works for me.", "ACH works too.", "Venmo works for me.", "A cheque works too.", "Crypto works for me too.",
    "An e-transfer works too.", "A check is fine.", "Checks are fine too.", "Zelle is fine.",
    "Cash is fine for the deposit.",
    "A money order is fine.", "You can pay by check.", "You can pay by bank transfer, whichever is easier.",
    "You can pay by PayPal.", "Paying in cash is fine.", "Bank transfer is easiest for me.", "Happy to take a wire.",
    "I take cash or check.", "Sure. Wire or check, either works.", "You could just hand me cash on the first day.",
    "Once the wire clears I'll start.", "Happy to start as soon as the wire hits.", "No problem, a check works.",
    "No rush, cash works whenever.", "Why not just send a wire?", "My bank details are below.",
    "I'd take a bank transfer for the deposit and a milestone for the rest.",
]


@pytest.mark.parametrize("post", [R9_ROOF_POST, R8_TILE_POST, R10_SPA_POST])
@pytest.mark.parametrize("draft_text", R10_RAIL_DRAFTS)
def test_r10_a_rail_in_the_draft_is_refused_outside_a_payments_job_with_no_ask(draft_text, post):
    assert copy_gate.client_move_request(r5_room(R10_NO_ASK, post=post)) is None
    assert r5_off(draft_text, R10_NO_ASK, post=post)


def test_r10_the_new_rule_names_the_rail():
    reason = r5_off("Paying by check works.", R10_NO_ASK, post=R9_ROOF_POST)
    assert reason.startswith("off-platform contact (payment offered or accepted outside Upwork)") and "check" in reason


R10_P41_ASKS = ["Where should I send the money?", "Ready to go. How do you want the deposit?"]


@pytest.mark.parametrize("post", [R9_ROOF_POST, R8_TILE_POST])
@pytest.mark.parametrize("ask", R10_P41_ASKS)
def test_r10_the_p41_asks_are_payment_and_rail_replies_to_them_are_refused(ask, post):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"
    for reply in ("Just send a wire whenever you're ready.", "Paying by check works too.",
                  "A bank transfer works best for me.", "You can mail a check to my office."):
        assert r5_off(reply, ask, post=post), reply
    assert r5_off("I'll set up the first milestone here so you can fund it.", ask, post=post) is None


# refused, kept on Upwork, the project's money, or not money at all
R10_RAIL_PASSES = [
    "I'll set up the first milestone here so you can fund it.",
    "I keep payment on Upwork milestones, not wires or checks.",
    "No wires, checks or cash needed: the first milestone covers it.",
    "Rather than a bank transfer, I'd set up the first milestone here.",
    "Payment stays on Upwork, so no bank details needed.", "A check won't be needed, the milestone covers it.",
    "You can fund it on Upwork with a card or a bank transfer.",
    # the reviewer's p42 drafts outside a payments job
    "I'll check the GoHighLevel API tonight and confirm the missed-call trigger works with your number.",
    "I'd take a quick check of the call logs first, so the roof type and address map cleanly.",
    "The form would capture the homeowner's mailing address along with the roof type.",
    "I'd double-check the address field so the mailing address and the job address stay separate in GoHighLevel.",
    "Every lead gets a quick spot check before it lands in GoHighLevel with the roof type.",
    "The agent would take the card deposit in Boulevard, and a check-in text goes out the day before the consult.",
    # the project's money
    "Homeowners who pay by check would get a reminder text.", "The bot logs each check the front desk scans.",
    "Do you take checks at the office, or is it all card?", "Customers paying cash get a receipt text.",
    "Your front desk accepts cash, so the bot marks those as paid.",
    "Roofers who take cash on site could tap a button to mark the job paid.",
    "The bot texts the homeowner a thank-you once the check clears.",
    # cash and wire in other senses
    "Cash flow is tight in winter for most roofers, so the first milestone is small.",
    "I know cash is tight this quarter, so I'd split it into two milestones.",
    "I'd wire the webhook into GoHighLevel tonight.", "I'll wire or check the webhook tonight.",
    "Happy to do a quick spot check or check-in call next week.",
]


@pytest.mark.parametrize("draft_text", R10_RAIL_PASSES)
def test_r10_refused_kept_on_upwork_project_or_non_money_rails_pass(draft_text):
    for post in (R9_ROOF_POST, R8_TILE_POST, R10_SPA_POST):
        assert r5_off(draft_text, R10_NO_ASK, post=post) is None


@pytest.mark.parametrize("draft_text", [
    "I'll text the homeowners once the check clears.", "The build starts once the check clears.",
    "Once the check clears, I'll set up the homeowner texts.", "I'll start once the wire lands.",
])
def test_r10_waiting_on_the_clients_rail_is_still_lorenzos_payment(draft_text):
    assert r5_off(draft_text, R10_NO_ASK, post=R9_ROOF_POST)


@pytest.mark.parametrize("post,draft_text", [
    (R9_SHOP_POST, "The workflow would match wire details and check numbers to the QuickBooks invoice for each "
                   "Shopify order."),
    (R9_SHOP_POST, "Customers who pay by check would get the invoice marked paid in QuickBooks once the deposit "
                   "clears."),
    (PAY_POST, "Bank transfers are the tricky part: the deposit shows up in QuickBooks without the Shopify order "
               "number, so I'd match on amount and date."),
    (PAY_POST, "Stripe is fine for the checkout: each Shopify order would sync to QuickBooks with the Stripe fee "
               "split out."),
])
def test_r10_inside_a_payments_job_the_projects_rails_keep_passing(post, draft_text):
    assert r5_off(draft_text, R10_NO_ASK, post=post) is None


# ---------------------------------------------------------------- where or how the money goes
R10_WHERE_HOW = [
    "Where should I send the money?", "Where do I send the payment?", "Where can we wire the deposit?",
    "Ready to go. How do you want the deposit?", "How would you like the payment?", "How do you want the money sent?",
    "Where should the money go?", "Where should I mail the check?", "Perfect, where do we send the retainer?",
    "Where should I send the deposit, by the way?",
]
R10_WHERE_HOW_NOT = [
    "Where should I send the payment data?", "How do you want the payment page to look?",
    "Where do I send the payment for the Twilio number?", "How do you want the deposit reminder worded?",
    "Where should the deposit field go in GoHighLevel?", "Where should I send the check-in reminders?",
    "Where do I send the money for the first milestone?", "Where should the bot send the payment link?",
    "Where do customers send the deposit today?", "How would you like the deposit step to work for patients?",
]


@pytest.mark.parametrize("post", [R9_ROOF_POST, R8_TILE_POST, R10_SPA_POST])
@pytest.mark.parametrize("ask", R10_WHERE_HOW)
def test_r10_asking_where_or_how_to_send_the_money_is_payment(ask, post):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) == "payment"


@pytest.mark.parametrize("post", [R9_ROOF_POST, R8_TILE_POST, R10_SPA_POST])
@pytest.mark.parametrize("ask", R10_WHERE_HOW_NOT)
def test_r10_project_money_and_upwork_money_are_not_where_or_how_asks(ask, post):
    assert copy_gate.client_move_request(r5_room(ask, post=post)) is None


@pytest.mark.parametrize("ask", R10_WHERE_HOW[:4])
def test_r10_the_where_or_how_ask_stays_out_of_payments_jobs(ask):
    # part of round 9's wider rule, which a payments job does not use
    assert copy_gate.client_move_request(r5_room(ask, post=R9_SHOP_POST)) is None


# ---------------------------------------------------------------- private figures withheld from the model
R10_PRIVATE = ("Time:\n6-8 hours a week\nLikelihood:\n35% likely\nStandard pricing:\n"
               "$3,500-5,000 build, plus $50/mo hosting and 1,200 a year support")


@pytest.mark.parametrize("text,expected", [
    ("Budget is $3,500-5,000 for now.", "Budget is (figure withheld) for now."),
    ("Somewhere around 3500 to 5000 dollars.", "Somewhere around (figure withheld)."),
    ("Is $3.5k too low?", "Is (figure withheld) too low?"),
    ("Hosting is fifty a month today.", "Hosting is (figure withheld) a month today."),
    ("Support runs 1,200 a year.", "Support runs (figure withheld) a year."),
    ("Setup takes 6-8 hours.", "Setup takes (figure withheld)."),
    ("We see a 35% no-show rate.", "We see a (figure withheld) no-show rate."),
    ("We send from 20 domains and about 60 mailboxes.", "We send from 20 domains and about 60 mailboxes."),
    ("Budget is $2,000.", "Budget is $2,000."),
])
def test_r10_withhold_figures_hides_exactly_what_private_fact_refuses(text, expected):
    assert copy_gate.withhold_figures(text, [R10_PRIVATE]) == expected


def test_r10_withheld_figures_are_the_ones_the_gate_refuses():
    for figure in ("$3,500", "5,000 dollars", "fifty a month", "1,200 a year", "6 hours", "35%"):
        draft_text = "hey, on the showroom quote requests in HubSpot, it would be %s for the photos." % figure
        assert "private_fact" in check(draft_text, "touch", room(), OFFERS, private_texts=[R10_PRIVATE]), figure
    assert "private_fact" not in check("hey, on the showroom quote requests in HubSpot, 60 mailboxes is plenty.",
                                       "touch", room(), OFFERS, private_texts=[R10_PRIVATE])


def test_r10_every_figure_hides_all_money_percent_multiplier_and_hours():
    text = "Is a $900 pilot ok? Would 20% off or 3x volume matter? Is 40 hours enough? How many of the 60 mailboxes?"
    assert copy_gate.withhold_figures(text, (), every_figure=True) == (
        "Is a (figure withheld) pilot ok? Would (figure withheld) off or (figure withheld) volume matter? Is "
        "(figure withheld) enough? How many of the 60 mailboxes?")


def test_r10_no_private_text_withholds_nothing():
    text = "Budget is $3,500-5,000 and setup takes 6-8 hours."
    assert copy_gate.withhold_figures(text, ()) == text
    assert copy_gate.withhold_figures(text, ["", None]) == text


def test_r10_a_draft_that_echoes_the_withheld_marker_is_a_placeholder():
    out = dict(copy_gate.check_detailed("hey, the (figure withheld) budget covers the showroom quote requests in "
                                        "HubSpot.", "touch", room(), OFFERS))
    assert "placeholder" in out and "(figure withheld)" in out["placeholder"]


# ================================================================ round 11
# ---------------------------------------------------------------- the client's own figures are public
# The reviewer's p44, synthetic: the client states a list size and the same
# number sits in the private assessment's pricing section.
R11_POST = ("Lakeshore Supply wants cold email set up for our trade-show list, approx 25k emails. Need the list "
            "verified and warmed inboxes before we send anything.")
R11_NOTES = ["Time: 6 hours setup", "Likelihood: medium-high", "Standard pricing: $1,500 setup, $400/mo",
             "Run the 25k addresses through a verifier first", "A 25k list clears in under 3 weeks at 25/inbox",
             "Client reviews: 4.8 stars, 12 hires"]
R11_TAIL = " Some of those trade-show addresses are years old, so the verifier pass matters before any inbox warms up."


def r11_room(client_text="We have approx 25k emails from trade shows, some are years old. How long before we can send?",
             post=R11_POST, notes=None):
    return {"client": "Lakeshore Supply", "client_first_name": None, "job_title": "Cold email for trade-show list",
            "job": {"post": post, "private_notes": R11_NOTES if notes is None else notes, "proposal": "Loom attached."},
            "messages": [{"side": "freelancer", "text": "Here's the Loom.", "at": "2026-09-20T10:00:00Z"},
                         {"side": "client", "text": client_text, "at": "2026-09-21T10:00:00Z"}]}


def r11_check(draft_text, r=None, private=None):
    r = r or r11_room()
    private = ["\n".join(R11_NOTES)] if private is None else private
    return dict(copy_gate.check_detailed(draft_text + R11_TAIL, "reply", r, OFFERS, private))


@pytest.mark.parametrize("draft_text", [
    "I'd run the 25k emails through a verifier first.", "I'd run the 25,000 emails through a verifier first.",
    "I'd run the 25000 emails through a verifier first.", "I'd run the list of about 25k through a verifier first.",
])
def test_r11_the_clients_own_figure_is_not_a_private_fact(draft_text):
    out = r11_check(draft_text)
    assert "private_fact" not in out and "figure_not_in_offers" not in out, out


@pytest.mark.parametrize("draft_text,code", [
    ("Setup would be $1,500.", "private_fact"), ("It would take about 6 hours.", "private_fact"),
    ("At 400 a month it pays back fast.", "private_fact"), ("Setup would be $1,500.", "figure_not_in_offers"),
])
def test_r11_a_figure_only_the_private_notes_state_stays_refused(draft_text, code):
    assert code in r11_check(draft_text)


def test_r11_a_private_figure_the_room_never_states_stays_private():
    # "25k" on the private pricing lines, and nothing in the post or the room
    r = r11_room("Thanks for the Loom. How long before we can send?",
                 post="Lakeshore Supply wants cold email set up for our trade-show list.")
    assert "private_fact" in r11_check("I'd run the 25k emails through a verifier first.", r)


def test_r11_any_room_message_counts_whoever_wrote_it():
    r = r11_room("How long before we can send?", post="Lakeshore Supply wants cold email for the trade-show list.")
    r["messages"].insert(0, {"side": "freelancer", "text": "I'd start with the 25,000 addresses.",
                             "at": "2026-09-19T10:00:00Z"})
    assert "private_fact" not in r11_check("I'd run the 25k emails through a verifier first.", r)


@pytest.mark.parametrize("client_text,draft_text,public", [
    # a review figure the client states as one is the client's own
    ("Our reviews say 4.8 stars.", "Your 4.8 stars are a good hook for the first email.", True),
    # round 12: hours and a rate stay Lorenzo's estimate and price even when the client states them as the same kind
    ("We're open 6 hours on Saturdays.", "The 6 hours you're open on Saturdays are the busy ones.", False),
    ("We pay 400 a month for the old tool.", "At 400 a month the old tool is the one to beat.", False),
    # and another kind never frees them
    ("We have 6 techs on the road.", "It would take about 6 hours.", False),
    ("We get 400 leads a month.", "At 400 a month it pays back fast.", False),
])
def test_r11_reviews_are_public_as_the_same_kind_hours_and_rates_never(client_text, draft_text, public):
    out = r11_check(draft_text, r11_room(client_text, post="Lakeshore Supply wants cold email for the trade shows."))
    assert ("private_fact" not in out) == public, out


def test_r12_a_private_money_amount_stays_private_however_the_room_states_it():
    notes = ["Standard pricing:", "$25,000 build"]
    for public in (["We have approx 25k emails."], ["Our budget is $25k."]):
        figs = copy_gate.private_figures(["\n".join(notes)], public)
        assert figs["money"] == {"25000"} and figs["priced"] == {"25000"} and figs["stated"] == {"25000"}, public
    r = r11_room("Our budget is $25k. We have approx 25k emails.", notes=notes)
    assert "private_fact" in r11_check("Your $25k budget covers the build.", r, ["\n".join(notes)])
    assert "private_fact" not in r11_check("I'd run the 25k emails through a verifier first.", r, ["\n".join(notes)])


def test_r11_public_figures_match_on_the_canonical_value():
    for stated in ("approx 25k emails", "25,000 contacts", "25000 rows", "a list of 25K"):
        figs = copy_gate.private_figures(["Standard pricing:\nRun the 25k addresses"], [stated])
        assert figs["priced"] == {"25000"} and figs["stated"] == {"25000"}, stated  # round 12: freed per use


def test_r11_public_texts_are_the_title_the_post_and_every_message():
    r = r11_room("client says 7")
    r["messages"].append({"side": "unknown", "text": "someone says 8"})
    texts = copy_gate.public_texts(r)
    assert texts[:2] == ["Cold email for trade-show list", R11_POST]
    assert texts[2:] == ["someone says 8", "client says 7", "Here's the Loom."]  # newest first
    assert copy_gate.public_texts(None) == [] and copy_gate.public_texts({"job": "x", "messages": [None, 3]}) == []


def test_r11_public_texts_stop_at_the_cap():
    r = r11_room("x" * (copy_gate.PUBLIC_FIGURE_CHARS + 50))
    texts = copy_gate.public_texts(r)
    assert sum(len(t) for t in texts) <= copy_gate.PUBLIC_FIGURE_CHARS
    assert texts[-1].startswith("x")  # the newest message is read first, the older one falls past the cap


def test_r11_withhold_figures_leaves_public_figures_but_the_questions_lose_them():
    text = "We have approx 25k emails; setup is $1,500 and 6 hours."
    public = copy_gate.public_texts(r11_room())
    assert copy_gate.withhold_figures(text, ["\n".join(R11_NOTES)], public_texts=public) == (
        "We have approx 25k emails; setup is (figure withheld) and (figure withheld).")
    assert copy_gate.withhold_figures(text, ["\n".join(R11_NOTES)], every_figure=True, public_texts=public) == (
        "We have approx (figure withheld) emails; setup is (figure withheld) and (figure withheld).")


def test_r11_the_questions_still_lose_a_k_volume_with_no_private_notes():
    text = "How many of the 25k emails are verified, and are the 25k-30k leads one file?"
    assert copy_gate.withhold_figures(text, every_figure=True) == (
        "How many of the (figure withheld) emails are verified, and are the (figure withheld) leads one file?")
    assert copy_gate.withhold_figures(text) == text  # no private notes: no other block hides it


# ---------------------------------------------------------------- "25k emails" is a volume, "would be 25k" a price
@pytest.mark.parametrize("text", [
    "approx 25k emails", "25k verified contacts", "a 25k email list", "25k-30k leads", "25 to 30k leads",
    "a list of about 25k", "25K emails", "25k+ emails", "25k of our contacts", "25k monthly visitors", "a 25k list",
    "25k trade-show emails", "25k subscribers", "25k followers", "25k calls", "25k texts", "25k messages",
    "25k views", "25k records", "25k rows", "25k users", "25k addresses", "25k emails a month",
])
def test_r11_a_k_figure_before_a_count_noun_is_a_volume(text):
    assert copy_gate.dollar_figures(text) == []


@pytest.mark.parametrize("text", [
    "a 25k budget", "for 25k", "25k a month", "The build would be 25k.", "25k worth of leads", "25k per month",
    "a 25k email budget", "25k/mo", "25k USD", "$25k emails", "25k in ad spend", "25k for the leads", "a 25k project",
])
def test_r11_a_k_figure_as_a_price_stays_money(text):
    assert copy_gate.dollar_figures(text) == ["25000"]


def test_r11_with_no_private_notes_25k_emails_passes_and_a_25k_build_does_not():
    r = r11_room(notes=[])
    assert "figure_not_in_offers" not in r11_check("I'd run the 25k emails through a verifier first.", r, [])
    for price in ("The build would be 25k.", "It fits a 25k budget.", "I can do it for 25k.", "Call it 25k a month."):
        assert "figure_not_in_offers" in r11_check(price, r, []), price


# ================================================================ round 12
# ---------------------------------------------------------------- the room stating a number never frees a price
# The reviewer's p46 and p47, synthetic: Lorenzo's private notes price the job
# and the client names the same numbers.
R12_POST = "HVAC company with 6 techs wants a dispatch bot in ServiceTitan; we get about 400 leads a month."
R12_NOTES = ["Standard pricing: $400/mo retainer, 2,500 setup", "Time: 6 hours"]
R12_ASK = "Would 2,500 for setup and $400 a month work? Maybe 6 hours of work?"
R12_COUNTS = "We have 6 techs and 400 leads a month, 2,500 in the backlog."
R12_TAIL = " The dispatch bot would route each ServiceTitan lead to the right tech."


def r12_room(client_text=R12_ASK, notes=None):
    return {"client": "X Air", "client_first_name": None, "job_title": "Dispatch bot",
            "messages": [{"side": "freelancer", "text": "Loom"}, {"side": "client", "text": client_text}],
            "job": {"post": R12_POST, "private_notes": R12_NOTES if notes is None else notes}}


def r12_check(draft_text, client_text=R12_ASK, notes=None):
    notes = R12_NOTES if notes is None else notes
    private = ["\n".join(notes)] if notes else []
    return dict(copy_gate.check_detailed(draft_text + R12_TAIL, "reply", r12_room(client_text, notes), OFFERS, private))


@pytest.mark.parametrize("client_text", [R12_ASK, "How much would this cost?", R12_COUNTS])
@pytest.mark.parametrize("draft_text", [
    "Setup would be 2,500.", "Sure, 400 a month works.", "The retainer would be 400 a month.",
    "Setup is 2,500 and the retainer is 400 a month.", "2,500 for the setup works.", "Yes, about 6 hours.",
])
def test_r12_a_private_price_rate_or_hours_figure_stays_refused_whatever_the_client_says(client_text, draft_text):
    assert "private_fact" in r12_check(draft_text, client_text)


@pytest.mark.parametrize("draft_text", [
    "Sure, 2,500 works.", "2,500 setup fee is fine.", "400/mo works for me.", "400 per month is fine.",
    "The retainer would be 400.", "We could start at 2,500.", "I'd charge 2,500 in total.", "That's 2,500 in fees.",
    "You'd spend 400 on ads.", "Call it 2,500.", "2,500, and then 400 a month.", "400 a month for the retainer.",
    "$2,500 for the setup.", "2,500 upfront works.", "Roughly 6 hours, yes.",
    "The 6 hours you mentioned sound right.", "Your 2,500 figure works for me.", "A 2,500 project is fine.",
    "The 2,500 you mentioned works.", "A 2,500 fixed-price build is fine.",
])
def test_r12_the_same_number_as_a_price_rate_or_estimate_stays_refused(draft_text):
    assert "private_fact" in r12_check(draft_text, R12_COUNTS + " " + R12_ASK)


@pytest.mark.parametrize("draft_text", [
    "With 6 techs and 400 leads a month, the bot routes each one.", "The 2,500 backlog would go first.",
    "I'd clear the 2,500 in the backlog first.", "I'd clear all 2,500 of them first.",
    "I'd start with 400 of your leads.", "The first 400 leads get a text within a minute.",
    "A backlog of 2,500 clears in a week.", "The 2,500-ticket backlog would go first.",
    "Your 2,500 old tickets would go first.", "The 2,500 to 3,000 tickets would go first.",
    "I'd route 400 leads monthly.", "The 400 jobs a month are the ones the bot routes.",
])
def test_r12_a_count_with_its_noun_the_room_states_is_the_clients_own(draft_text):
    out = r12_check(draft_text, R12_COUNTS + " " + R12_ASK)
    assert "private_fact" not in out and "figure_not_in_offers" not in out, out


def test_r12_the_same_number_in_another_sense_frees_only_the_count():
    # p46: the client's "2,500 in the backlog" never lets "Setup would be 2,500" through
    assert "private_fact" in r12_check("Setup would be 2,500.", R12_COUNTS)
    assert "private_fact" not in r12_check("The 2,500 backlog would go first.", R12_COUNTS)
    # a count the room never states stays private
    assert "private_fact" in r12_check("The 2,500 backlog would go first.", "How much would this cost?")


def test_r12_a_percentage_the_client_states_as_one_stays_the_clients_own():
    notes = ["Standard pricing: $400/mo retainer", "Close rate: 35%"]
    draft_text = "The 35% of leads that never answer are the ones the bot texts first."
    assert "private_fact" not in r12_check(draft_text, "About 35% of our leads never answer.", notes)
    assert "private_fact" in r12_check(draft_text, "Most of our leads never answer.", notes)


def test_r12_the_real_room_shape_still_passes():
    draft_text = ("one thing worth flagging on the 25k list: since it's an old list, running it through a verifier "
                  "before the first send keeps the bounces off the new inboxes and protects the domains while they "
                  "warm. do you know roughly how old that list is?")
    assert copy_gate.check_detailed(draft_text, "reply", r11_room(), OFFERS, ["\n".join(R11_NOTES)]) == []
    assert copy_gate.check_detailed(draft_text, "reply", r11_room(notes=[]), OFFERS, []) == []


def test_r12_lorenzos_text_withholds_a_price_the_room_states_and_shows_a_count():
    figs = copy_gate.private_figures(["\n".join(R12_NOTES)], copy_gate.public_texts(r12_room(R12_COUNTS + R12_ASK)))
    text = "Setup 2,500 plus $400/mo, about 6 hours. The 2,500 backlog goes first, then 400 leads a month."
    assert copy_gate.withhold_figures(text, figures=figs) == (
        "Setup (figure withheld) plus (figure withheld)/mo, about (figure withheld). The 2,500 backlog goes first, "
        "then 400 leads a month.")
    # the questions still lose every figure
    asked = copy_gate.withhold_figures("Is 2,500 for 400 leads a month ok?", ["\n".join(R12_NOTES)], every_figure=True)
    assert asked == "Is (figure withheld) for (figure withheld) leads a month ok?"


# ---------------------------------------------------------------- bare price forms need no private notes
@pytest.mark.parametrize("draft_text", [
    "Setup would be 2,500.", "Setup is 2,500.", "Sure, 400 a month works.", "2,500 for the setup works.",
    "400/mo works for me.", "400 a month is fine.", "400 a month for the retainer.",
    "The retainer would be 400 a month.",
])
def test_r12_bare_price_forms_are_refused_with_no_private_notes(draft_text):
    assert any(p.endswith("(as a price)") for p in copy_gate.figure_problems(draft_text, OFFERS)), draft_text
    assert "figure_not_in_offers" in r12_check(draft_text, R12_ASK, notes=[])


@pytest.mark.parametrize("draft_text", [
    "The setup sends 400 a day across 20 inboxes.", "400 a month works out to about 13 a day.",
    "With 6 techs and 400 leads a month, the bot routes each one.", "The 2,500 backlog would go first.",
    "Sure, 300 works for the first batch.", "The setup handles 2,500 contacts.", "Setup takes 400 steps.",
])
def test_r12_volumes_near_setup_or_a_rate_stay_volumes(draft_text):
    assert copy_gate.figure_problems(draft_text, OFFERS) == []


# ---------------------------------------------------------------- r13: agreeing to the client's price (probe p49)
R13_POST = "Roofing company wants its estimate requests routed into GoHighLevel with a follow-up text."
R13_TAIL = " The estimate routing sends each lead a follow-up text."
R13_ASKS = ["Would 2,000 work for the whole build?", "Would 2k work for the whole build?",
            "Would $2,000 work for the whole build?"]


def r13_room(client_text, post=R13_POST):
    return {"client": "Invented Roofing", "client_first_name": None, "job_title": "GoHighLevel estimate routing",
            "job": {"post": post, "private_notes": ""},
            "messages": [{"side": "freelancer", "text": "Loom attached."}, {"side": "client", "text": client_text}]}


def r13_check(draft_text, client_text, private=()):
    return dict(copy_gate.check_detailed(draft_text + R13_TAIL, "reply", r13_room(client_text), OFFERS,
                                         list(private)))


@pytest.mark.parametrize("client_text", R13_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Sure, 2,000 works.", "Sure, 2,000 is fine for the build.",  # the p49 lines
    "$2,000 works.", "2k is fine.", "Happy with 2,000.", "Sure, 2,000 it is.",
    "2,000 is good.", "2,000 sounds good.", "2,000 is ok.", "2,000 is okay.", "Can do 2,000.",
    "2,000 for the whole thing works.", "2,000 for the setup works.", "Deal at 2,000.", "Sure, 2,000.",
])
def test_r13_agreeing_to_the_clients_price_is_refused(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)
    assert "leave pricing to Lorenzo" in out["agrees_to_client_price"]


@pytest.mark.parametrize("private", [(), ("Standard pricing: $3,500 fixed",)])
def test_r13_the_rule_applies_with_or_without_private_notes(private):
    out = r13_check("Sure, 2,000 works.", R13_ASKS[0], private)
    assert "agrees_to_client_price" in out and "private_fact" not in out


@pytest.mark.parametrize("client_text", [
    "Our budget is 2,000.", "How about 2,000?", "Is 2,000 ok for everything?", "Can you do it for 2000?",
    "The job is fixed at 2,000 all in.",
])
def test_r13_the_client_states_a_price_many_ways(client_text):
    assert copy_gate.client_price_values(copy_gate.client_source_text(r13_room(client_text))) == {"2000"}
    assert "agrees_to_client_price" in r13_check("2,000 works for me.", client_text)


def test_r13_a_price_in_the_job_post_counts_too():
    r = r13_room("Any questions?", post=R13_POST + " Budget: 2,000 fixed.")
    assert "agrees_to_client_price" in copy_gate.check("Sure, 2,000 works." + R13_TAIL, "reply", r, OFFERS)


def test_r13_the_reason_says_to_leave_pricing_to_lorenzo():
    assert copy_gate.DESCRIPTIONS["agrees_to_client_price"].endswith(
        "do not agree to or accept a price; leave pricing to Lorenzo")
    assert CODES.index("figure_not_in_offers") < CODES.index("agrees_to_client_price") < CODES.index("private_fact")


@pytest.mark.parametrize("client_text", R13_ASKS)
@pytest.mark.parametrize("draft_text", [
    "With 2,000 contacts the estimate routing needs batching.", "The 2,000 backlog goes first.",
    "The estimate routing texts each lead the same minute.",  # no number at all
    "Does 2,000 work for you?",  # asks, does not agree
    "2,000 works out to about 100 a day.",  # arithmetic, not agreement
])
def test_r13_volumes_questions_and_numberless_drafts_pass(client_text, draft_text):
    assert r13_check(draft_text, client_text) == {}, draft_text


@pytest.mark.parametrize("client_text", ["We send 2,000 emails a week.", "We have 2,000 contacts in the list.",
                                         "We have 2,000 contacts, would $1,500 work?"])
@pytest.mark.parametrize("draft_text", ["2,000 works.", "Sure, 2,000 is fine for the build.", "Happy with 2,000."])
def test_r13_a_number_the_client_used_only_as_a_volume_is_not_their_price(client_text, draft_text):
    # The client used 2,000 as a count with its noun ("2,000 emails a week"), never as a price,
    # so "2,000 works" talks about that volume: there is no client price for the draft to accept.
    assert "2000" not in copy_gate.client_price_values(copy_gate.client_source_text(r13_room(client_text)))
    assert "agrees_to_client_price" not in r13_check(draft_text, client_text)


def test_r13_a_count_in_the_draft_passes_even_when_the_client_priced_that_number():
    assert r13_check("Happy with 2,000 contacts in the first batch.", R13_ASKS[0]) == {}


# ---------------------------------------------------------------- r14: more agreeing forms, and agreeing with no figure
R14_ASKS = R13_ASKS + ["Our budget is 2,000.", "Would 2k work?", "How about $2,000 for everything?",
                       "Can you do it for 2,000?", "Is 2,000 ok?", "I can pay 2,000 for the build."]
R14_REFUSED = [
    "Yes, I can work with 2,000.", "2,000 should cover it.", "2,000 would cover it.", "2,000 will cover it.",
    "2,000 sounds about right for this scope.", "2,000 is about right.", "2,000 is reasonable.",
    "2,000 is doable.", "2,000 is workable.",
    "That budget works for me.", "Sure, that works.", "That price works for me.", "Happy with that, let's do it.",
    "That works.", "Sounds good.", "Deal.", "Yes, that's fine.", "Hi Sam,\nSure, that works for me.",
    "Thanks for the quick reply! That number works.", "I can work with that.",
]


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", R14_REFUSED)
def test_r14_more_agreeing_forms_are_refused(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)
    assert "leave pricing to Lorenzo" in out["agrees_to_client_price"]


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Thursday works for a quick call.",  # answers a time
    "That works for Thursday at 2pm.",
    "That works, I'll confirm the price with you on a call.",  # defers the price
    "Sounds good. Let me come back to you on the number after I map the routing.",
    "Sure, that works. I can go over the budget with you on a quick call.",
    "The estimate routing texts each lead the same minute.",  # does not respond to the price
    "Does that budget work for you?",
])
def test_r14_times_deferrals_and_drafts_that_skip_the_price_pass(client_text, draft_text):
    assert r13_check(draft_text, client_text) == {}, (client_text, draft_text)


def test_r14_a_count_the_client_asked_about_in_the_same_message_passes():
    client_text = "Can you do 20 domains for 2,000?"
    assert copy_gate.client_price_proposal(r13_room(client_text)) == "2,000"
    assert r13_check("Yes, I can do 20 domains.", client_text) == {}
    assert "agrees_to_client_price" in r13_check("Sure, that works.", client_text)


@pytest.mark.parametrize("client_text", [
    "We send 2,000 emails a week.", "We have approx 25k emails and 400 leads a month.",
    "Can we talk Thursday?", "Any questions?", "Last year we paid 2,000 for a site that never worked.",
])
@pytest.mark.parametrize("draft_text", ["Sure, that works.", "Sounds good.", "That works for me."])
def test_r14_figureless_agreement_needs_the_latest_client_message_to_propose_a_price(client_text, draft_text):
    assert copy_gate.client_price_proposal(r13_room(client_text)) is None
    assert "agrees_to_client_price" not in r13_check(draft_text, client_text)


def test_r14_only_the_latest_client_message_counts_for_a_figureless_agreement():
    r = r13_room("Would 2,000 work for the whole build?")
    r["messages"] += [{"side": "freelancer", "text": "Lorenzo will confirm."},
                      {"side": "client", "text": "Can we talk Thursday?"}]
    assert "agrees_to_client_price" not in copy_gate.check_detailed(
        "Sure, that works." + R13_TAIL, "reply", r, OFFERS)
    # the figure form still reads every client message
    assert "agrees_to_client_price" in dict(copy_gate.check_detailed(
        "2,000 works." + R13_TAIL, "reply", r, OFFERS))


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "I'd run the 25k emails through a verifier first.", "The 2,500 backlog goes first.",
    "At 400 leads a month it pays back fast.", "With 2,000 contacts the estimate routing needs batching.",
])
def test_r14_round_12_and_13_volume_forms_still_pass(client_text, draft_text):
    assert "agrees_to_client_price" not in r13_check(draft_text, client_text), (client_text, draft_text)


def test_r14_client_price_text_is_capped_newest_first():
    old = {"side": "client", "text": "Our budget is 3,000."}
    filler = {"side": "client", "text": "Call me at 555-123-4567 or 555-765-4321. " * 4700}
    new = {"side": "client", "text": "Would 2,000 work?"}
    r = r13_room("x")
    r["messages"] = [old, filler, new]
    src = copy_gate.client_price_source(r)
    assert len(src) <= copy_gate.CLIENT_PRICE_CHARS and src.startswith(R13_POST)
    assert "Would 2,000 work?" in src and "3,000" not in src
    copy_gate.client_price_values.cache_clear()
    t = time.time()
    out = copy_gate.check_detailed("Sure, that works." + R13_TAIL, "reply", r, OFFERS)
    assert time.time() - t < 1.0  # about 0.2s here; 1.47s before the cap
    assert "agrees_to_client_price" in dict(out)
    copy_gate.client_price_values.cache_clear()
    t = time.time()
    copy_gate.client_price_values(filler["text"] * 3)
    assert time.time() - t < 0.5


# ---------------------------------------------------------------- r15: subjectless agreement, the time exemption, "N is our max"
R15_MAX_ASKS = ["1,500 is our max.", "Our max is 1,500.", "A max of 1,500 for the whole build.",
                "1,500 is our ceiling.", "1,500 is our cap."]


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Works for me.", "Works.", "Sure thing.", "Sure thing, that works.", "Works for us!",
])
def test_r15_subjectless_works_and_sure_thing_are_refused(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Sure, that works, talk Thursday.", "That works, see you tomorrow.", "Sounds good, talk Monday at 2pm.",
])
def test_r15_a_time_in_a_separate_clause_does_not_exempt_the_agreement(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Thursday works for a quick call.", "That works for Thursday at 2pm.", "Monday works for me to start.",
    "That works for me on Thursday.", "That works for a quick call on Friday.",
])
def test_r15_a_time_the_agreement_refers_to_still_passes(client_text, draft_text):
    assert r13_check(draft_text, client_text) == {}, (client_text, draft_text)


@pytest.mark.parametrize("client_text", R15_MAX_ASKS)
def test_r15_n_is_our_max_states_a_price(client_text):
    assert copy_gate.client_price_values(copy_gate.client_source_text(r13_room(client_text))) == {"1500"}
    assert copy_gate.client_price_proposal(r13_room(client_text)) == "1,500"
    for draft_text in ("1,500 works.", "Sure, that works."):
        out = r13_check(draft_text, client_text)
        assert "agrees_to_client_price" in out, (client_text, draft_text, out)


@pytest.mark.parametrize("client_text", ["Our max is 20 domains.", "Our max is 2,000 contacts.",
                                         "2,000 contacts is our max."])
def test_r15_a_max_count_with_its_noun_stays_a_count(client_text):
    assert copy_gate.client_price_values(copy_gate.client_source_text(r13_room(client_text))) == frozenset()
    assert copy_gate.client_price_proposal(r13_room(client_text)) is None
    for draft_text in ("20 domains works.", "2,000 works.", "Sure, that works."):
        assert "agrees_to_client_price" not in r13_check(draft_text, client_text), (client_text, draft_text)


# ---------------------------------------------------------------- r16: the price as the subject of an agreement, anywhere
R16_REFUSED = [
    "That works for Thursday at 2pm, and the price is fine.",
    "Thursday works for a quick call. Your budget works for me too.",
    "Happy to start Monday. The price works for me.",
    "Thursday at 2pm works, and your rate is fine.",
    "That number should cover it.",
]


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", R16_REFUSED)
def test_r16_the_price_as_the_subject_of_an_agreement_is_refused_in_any_clause(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)
    assert "leave pricing to Lorenzo" in out["agrees_to_client_price"]
    assert copy_gate.price_subject_agreement(draft_text, r13_room(client_text))


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Does that budget work for you?",  # a question
    "The price depends on the scope.",  # the price is not agreed to
    "The price is not fine for this scope, honestly.",  # a negation
    "That works for Thursday at 2pm. I'll confirm the price with you on the call.",  # defers the price
    "I'll send the price after the call.",
])
def test_r16_questions_negations_deferrals_and_other_predicates_pass(client_text, draft_text):
    assert r13_check(draft_text, client_text) == {}, (client_text, draft_text)
    assert copy_gate.price_subject_agreement(draft_text, r13_room(client_text)) is None


@pytest.mark.parametrize("client_text", [
    "We send 2,000 emails a week.", "Can we talk Thursday?", "Any questions?",
    "Last year we paid 2,000 for a site that never worked.",
])
@pytest.mark.parametrize("draft_text", R16_REFUSED)
def test_r16_needs_the_latest_client_message_to_propose_a_price(client_text, draft_text):
    assert copy_gate.client_price_proposal(r13_room(client_text)) is None
    assert "agrees_to_client_price" not in r13_check(draft_text, client_text), (client_text, draft_text)


# ---------------------------------------------------------------- u9: "works out to", more subjects, "for everything"
@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "The budget works out to about 100 a day of build time.",
    "The number works out to roughly 100 requests a day.",
])
def test_u9_a_price_subject_that_works_out_to_is_arithmetic(client_text, draft_text):
    assert copy_gate.price_subject_agreement(draft_text, r13_room(client_text)) is None
    assert "agrees_to_client_price" not in r13_check(draft_text, client_text), (client_text, draft_text)


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "Your number is fine by me.", "Your figure works.", "That fee works.",
    "Your fee is fine.", "That figure works for me.",
])
def test_u9_more_price_subjects_are_refused(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)
    assert copy_gate.price_subject_agreement(draft_text, r13_room(client_text))


@pytest.mark.parametrize("client_text", R13_ASKS)
@pytest.mark.parametrize("draft_text", ["2,000 for everything works.", "2,000 for all of it is fine."])
def test_u9_for_everything_and_for_all_of_it_are_refused(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)


# ---------------------------------------------------------------- u9b: only "works out to" is arithmetic
@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "That works out fine.", "Sure, that works out great.", "That should work out fine.",
    "The price works out fine for me.", "Your budget works out great.",
])
def test_u9b_works_out_fine_is_agreement_not_arithmetic(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)


@pytest.mark.parametrize("client_text", R13_ASKS)
@pytest.mark.parametrize("draft_text", ["2,000 works out fine.", "2,000 works out well.",
                                        "2,000 should work out great."])
def test_u9b_a_figure_that_works_out_fine_is_agreement(client_text, draft_text):
    out = r13_check(draft_text, client_text)
    assert "agrees_to_client_price" in out, (client_text, draft_text, out)


@pytest.mark.parametrize("client_text", R14_ASKS)
@pytest.mark.parametrize("draft_text", [
    "2,000 works out to about 100 a day.",
    "The number works out to roughly 100 requests a day.",
])
def test_u9b_works_out_to_stays_arithmetic(client_text, draft_text):
    assert "agrees_to_client_price" not in r13_check(draft_text, client_text), (client_text, draft_text)
