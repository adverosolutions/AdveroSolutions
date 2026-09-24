"""E2 research line validator (section 1): research_rules.validate.

The six style examples from sections/1_email_followup/sequence_final.md
(Research line section) pass with evidence built to back them; every reason
code has a failing case; bad input never raises; rounding, determinism,
rules_sha and purity are pinned.
"""
import dataclasses
import hashlib
import socket

import pytest

from services.reply_engine import research_rules as rr
from services.reply_engine.research_rules import ResearchVerdict, validate

GOOGLE_PAGE = "https://www.google.com/maps/place/Brightline+Cleaning"


def ctx(company, spoken, branch, niche, domain, city):
    return {"company": company, "company_spoken": spoken, "offer_branch": branch,
            "niche": niche, "website_domain": domain, "city": city}


def own_site(domain, *excerpts, identity_url=GOOGLE_PAGE, matched_on="city"):
    """Evidence whose facts all come from the lead's own site."""
    return {
        "facts": [{"text": "fact %d" % i, "source_url": "https://www.%s/about" % domain,
                   "excerpt": ex} for i, ex in enumerate(excerpts)],
        "identity": {"source_url": identity_url, "matched_on": matched_on},
    }


# --- the six examples ------------------------------------------------------

BRIGHTLINE_LINE = ("Brightline has been cleaning offices around Tampa since 2011 and has over "
                   "200 Google reviews, so there's a long list of past accounts we could win "
                   "back for you.")
BRIGHTLINE_CTX = ctx("Brightline Cleaning Services LLC", "Brightline", "reactivation",
                     "cleaning", "brightlinecleaning.com", "Tampa")


def brightline_evidence(review_excerpt="Brightline Cleaning Services 4.8 (213 reviews)"):
    return {
        "facts": [
            {"text": "Cleaning offices around Tampa since 2011",
             "source_url": "https://brightlinecleaning.com/about",
             "excerpt": "Brightline Cleaning Services has been cleaning offices around "
                        "Tampa since 2011."},
            {"text": "213 Google reviews", "source_url": GOOGLE_PAGE,
             "excerpt": review_excerpt},
        ],
        "identity": {"source_url": GOOGLE_PAGE, "matched_on": "city"},
    }


EXAMPLES = [
    ("cleaning_reactivation", BRIGHTLINE_LINE, brightline_evidence(), BRIGHTLINE_CTX),
    ("bookkeeping_reactivation",
     "You offer quarterly estimates and monthly books for contractors and restaurants, so "
     "every quarterly deadline is a reason we could get your past clients back in touch.",
     own_site("ledgerwise.com", "We offer quarterly estimates and monthly books for "
                                "contractors and restaurants."),
     ctx("Ledgerwise Bookkeeping, Inc.", "Ledgerwise", "reactivation", "bookkeeping",
         "ledgerwise.com", "Austin")),
    ("recruiting_reactivation",
     "Northgate has been placing accounting and finance people around Charlotte since "
     "2009, so there's a long list of clients who've hired through you before that we "
     "could bring back.",
     own_site("northgatestaffing.com", "Northgate Staffing Group has been placing "
                                       "accounting and finance people around Charlotte "
                                       "since 2009.",
              identity_url="https://www.yelp.com/biz/northgate-staffing-charlotte",
              matched_on="phone"),
     ctx("Northgate Staffing Group LLC", "Northgate", "reactivation", "recruiting",
         "https://www.northgatestaffing.com/", "Charlotte")),
    ("cleaning_outbound",
     "You handle post-construction cleanup and nightly janitorial for offices around "
     "Denver, so every new lease and buildout in town is a job we could put in front of "
     "you.",
     own_site("summitclean.com", "Post-construction cleanup and nightly janitorial for "
                                 "offices around Denver."),
     ctx("Summit Commercial Cleaning", "Summit", "outbound", "cleaning", "summitclean.com",
         "Denver")),
    ("bookkeeping_outbound",
     "Tallgrass has a setup package for brand-new businesses in Omaha, so every new "
     "business filing there is an owner we could get talking to you.",
     own_site("tallgrassbooks.com", "Our setup package for brand-new businesses in Omaha."),
     ctx("Tallgrass Bookkeeping LLC", "Tallgrass", "outbound", "bookkeeping",
         "tallgrassbooks.com", "Omaha")),
    ("recruiting_outbound",
     "Ironclad places controls engineers and maintenance techs for manufacturers, so every "
     "plant that posts one of those roles is a hiring manager we could get you in front of.",
     own_site("ironcladtalent.com", "Ironclad places controls engineers and maintenance "
                                    "techs for manufacturers.",
              identity_url="https://www.bbb.org/us/oh/ironclad"),
     ctx("Ironclad Technical Recruiting", "Ironclad", "outbound", "recruiting",
         "ironcladtalent.com", None)),
]


@pytest.mark.parametrize("name,line,evidence,context", EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_style_examples_pass(name, line, evidence, context):
    verdict = validate(line, evidence, context)
    assert verdict.reasons == ()
    assert verdict.ok is True
    assert verdict.line == line
    assert verdict.rules_sha == rr.rules_sha()


def test_internal_spaces_are_collapsed():
    spaced = BRIGHTLINE_LINE.replace(" so ", "   so  ")
    verdict = validate(spaced, brightline_evidence(), BRIGHTLINE_CTX)
    assert verdict.ok
    assert verdict.line == BRIGHTLINE_LINE


# --- raw-line checks (before normalising) -----------------------------------

@pytest.mark.parametrize("raw,codes", [
    (BRIGHTLINE_LINE.replace(" so ", "\nso "), ("line_break", "control_char")),
    (BRIGHTLINE_LINE.replace(" so ", "\r\nso "), ("line_break", "control_char")),
    (BRIGHTLINE_LINE.replace(" so ", "\u2028so "), ("line_break",)),
    (BRIGHTLINE_LINE.replace(" so ", " \tso "), ("control_char",)),
    (BRIGHTLINE_LINE.replace("win", "wi\x00n"), ("control_char",)),
    (" " + BRIGHTLINE_LINE, ("surrounding_space",)),
    (BRIGHTLINE_LINE + " ", ("surrounding_space",)),
    (BRIGHTLINE_LINE + "\n", ("surrounding_space", "line_break", "control_char")),
    (BRIGHTLINE_LINE.replace(" so ", " " * 200 + "so "), ("too_long_chars",)),
])
def test_raw_line_codes(raw, codes):
    verdict = validate(raw, brightline_evidence(), BRIGHTLINE_CTX)
    assert verdict.ok is False
    for code in codes:
        assert code in verdict.reasons, verdict.reasons
    # The rest is still checked on the normalised line.
    if "\x00" not in raw:
        assert verdict.line == BRIGHTLINE_LINE
        assert set(verdict.reasons) <= {"line_break", "control_char", "surrounding_space",
                                        "too_long_chars"}


def _padded(total):
    """BRIGHTLINE_LINE with one long lowercase word added, ``total`` characters long."""
    filler = "x" * (total - len(BRIGHTLINE_LINE) - 1)
    return BRIGHTLINE_LINE.replace("cleaning offices", "cleaning %s offices" % filler)


def test_too_long_chars_within_word_limit():
    line = _padded(301)
    assert len(line) == 301 and len(line.split()) <= 35
    verdict = validate(line, brightline_evidence(), BRIGHTLINE_CTX)
    assert verdict.reasons == ("too_long_chars",)


def test_300_chars_is_not_too_long():
    line = _padded(300)
    assert len(line) == 300
    assert validate(line, brightline_evidence(), BRIGHTLINE_CTX).ok


def test_rules_version_is_plain_int():
    assert type(rr.RULES_VERSION) is int


# --- one failing case per reason code ---------------------------------------

def check(line, evidence=None, context=None):
    return validate(line, brightline_evidence() if evidence is None else evidence,
                    BRIGHTLINE_CTX if context is None else context)


TIE = "so there's a long list of past accounts we could win back for you."
LONG_LINE = ("Brightline has been cleaning offices, clinics, gyms, schools, warehouses, "
             "banks, dealerships and churches all around Tampa since 2011 and has over 200 "
             "Google reviews, so there's a long list of past accounts we could win back for you.")

FAILING = [
    ("too_long", LONG_LINE),
    ("too_many_sentences", "Brightline cleans offices around Tampa. It has been since 2011. "
                           "There's a long list of past accounts we could win back for you."),
    ("question", "Brightline has been cleaning offices around Tampa since 2011, so could we "
                 "win back some past accounts for you?"),
    ("exclamation", "Brightline has been cleaning offices around Tampa since 2011, " + TIE[:-1] + "!"),
    ("dash", "Brightline has been cleaning offices around Tampa since 2011 \u2014 " + TIE),
    ("dash", "Brightline has been cleaning offices around Tampa since 2011 - " + TIE),
    ("dash", "Brightline has been cleaning offices around Tampa since 2011 \u2013 " + TIE),
    ("emoji", "Brightline has been cleaning offices around Tampa since 2011, " + TIE[:-1]
     + " \U0001F642."),
    ("emoji", "Brightline has been cleaning offices around Tampa since 2011, " + TIE[:-1]
     + " \u2728."),
    ("bad_character", "Brightline has been cleaning offices around Tampa since 2011, so "
                      "there's a long list of past accounts we could win ba\u200bck for you."),
    ("url", "Brightline has been cleaning offices around Tampa since 2011, " + TIE[:-1]
     + " at brightlinecleaning.com."),
    ("url", "Brightline has been cleaning offices around Tampa since 2011, " + TIE[:-1]
     + " https://x.co/a."),
    ("placeholder", "{company} has been cleaning offices around Tampa since 2011, " + TIE),
    ("placeholder", "<Company> has been cleaning offices around Tampa since 2011, " + TIE),
    ("capitalization", "brightline has been cleaning offices around Tampa since 2011, " + TIE),
    ("capitalization", ("Brightline has been cleaning offices around Tampa since 2011, " + TIE).upper()),
    ("opener", "I noticed Brightline has been cleaning offices around Tampa since 2011, " + TIE),
    ("opener", "I think Brightline has been cleaning offices around Tampa since 2011, " + TIE),
    ("opener", "I saw Brightline has been cleaning offices around Tampa since 2011, " + TIE),
    ("mentions_booking", "Brightline has been cleaning offices around Tampa since 2011, so "
                         "there are past accounts we could win back if we get a call going."),
    ("mentions_booking", "Brightline has been cleaning offices around Tampa since 2011, so "
                         "there are past accounts we could win back, happy to meet at 2pm."),
    ("guess", "Brightline must be cleaning offices around Tampa since 2011, " + TIE),
    ("guess", "Brightline has probably been cleaning offices around Tampa since 2011, " + TIE),
    ("money_or_results", "Brightline has been cleaning offices around Tampa since 2011, so "
                         "there's $40k in past accounts we could win back for you."),
    ("money_or_results", "Brightline has been cleaning offices around Tampa since 2011, so "
                         "there's revenue in past accounts we could win back for you."),
    ("money_or_results", "Brightline has been cleaning offices around Tampa since 2011, so we "
                         "could win back 20% of your past accounts."),
    ("mentions_research", "My research says Brightline has been cleaning offices around Tampa "
                          "since 2011, " + TIE),
    ("mentions_research", "Brightline has been cleaning offices around Tampa since 2011, so "
                          "there are past accounts our AI could help us win back for you."),
    ("star_rating", "Brightline has been cleaning offices around Tampa since 2011 with 4.8 "
                    "stars, " + TIE),
    ("star_rating", "Brightline is rated 4.8/5 around Tampa since 2011, " + TIE),
    ("stale_date", "Brightline just opened a second office around Tampa this year, " + TIE),
    ("stale_date", "Brightline has been cleaning offices around Tampa since March 2011, " + TIE),
    ("stale_date", "Brightline recently started cleaning offices around Tampa, " + TIE),
    ("legal_suffix", "Brightline LLC has been cleaning offices around Tampa since 2011, " + TIE),
    ("legal_suffix", "Brightline Inc. has been cleaning offices around Tampa since 2011, " + TIE),
    ("quoted_text", "Brightline has been cleaning offices around Tampa since 2011 and "
                    "clients describe it as \"spotless\", " + TIE),
    ("quoted_text", "Brightline has been cleaning offices around Tampa since 2011 and "
                    "clients describe it as \u201cspotless\u201d, " + TIE),
    ("negative", "Brightline has been cleaning offices around Tampa since 2011 despite a "
                 "few complaints, " + TIE),
    ("claudeism", BRIGHTLINE_LINE[:-1] + ", which means more work without more ads."),
    ("claudeism", "Brightline has been cleaning offices around Tampa since 2011, " + TIE
     + " That's a real opportunity."),
    ("claudeism", "Brightline has been cleaning offices around Tampa since 2011, " + TIE
     + " Worth a look."),
    ("no_tie_back", "Brightline has been cleaning offices around Tampa since 2011, so there's "
                    "a long list of past accounts to win back."),
    ("no_offer_link", "Brightline has been cleaning offices around Tampa since 2011, so every "
                      "new office lease is a job we could put in front of you."),
    ("number_not_in_evidence", "Brightline has been cleaning offices around Tampa since 2010, "
                               + TIE),
    ("spelled_number", "Brightline has been cleaning offices around Tampa since 2011 and has "
                       "over two hundred Google reviews, " + TIE),
    ("unsupported_name", "Brightline has been cleaning offices for Maria around Tampa since "
                         "2011, " + TIE),
    ("unsupported_name", "Brightline has been cleaning offices around Tampa since 2011 for "
                         "Acme and Hilton, " + TIE),
    ("company_form", "Brightline Cleaning Services has been cleaning offices around Tampa "
                     "since 2011, " + TIE),
]


@pytest.mark.parametrize("code,line", FAILING, ids=["%s-%d" % (c, i) for i, (c, _) in enumerate(FAILING)])
def test_failing_line(code, line):
    if code == "too_long":
        assert len(line.split()) > 35
    verdict = check(line)
    assert verdict.ok is False
    assert code in verdict.reasons, verdict.reasons


def test_company_verbatim_with_suffix_is_both_codes():
    verdict = check("Brightline Cleaning Services LLC has been cleaning offices around Tampa "
                    "since 2011, " + TIE)
    assert "legal_suffix" in verdict.reasons
    assert "company_form" in verdict.reasons


def test_wrong_examples_from_sequence_final_fail():
    kicker = ("Brightline has been cleaning offices around Tampa since 2011, so there's a long "
              "list of past accounts we could win back for you. That's a real opportunity.")
    sell = ("Brightline has been cleaning offices around Tampa since 2011, so there's a long "
            "list of past accounts we could win back, which means more revenue without more "
            "ad spend.")
    assert "claudeism" in check(kicker).reasons
    reasons = check(sell).reasons
    assert "claudeism" in reasons and "money_or_results" in reasons


def test_fallback_lines_are_not_research_lines():
    # The fixed fallbacks carry no offer clause; they go out through the
    # template path, never through this validator.
    line = ("The quickest place to start is usually the accounts that already know you "
            "and went quiet.")
    assert "no_tie_back" in check(line).reasons


# --- evidence and context codes ---------------------------------------------

def _evidence(**changes):
    ev = brightline_evidence()
    ev.update(changes)
    return ev


def _fact(url="https://brightlinecleaning.com/about", excerpt="Since 2011."):
    return {"text": "a fact", "source_url": url, "excerpt": excerpt}


@pytest.mark.parametrize("evidence,code", [
    (_evidence(facts="not a list"), "evidence_malformed"),
    (_evidence(facts=[{"text": "x", "source_url": "https://brightlinecleaning.com/"}]),
     "evidence_malformed"),
    (_evidence(facts=[{"text": "", "source_url": "https://brightlinecleaning.com/",
                       "excerpt": "Since 2011"}]), "evidence_malformed"),
    (_evidence(facts=["a string"]), "evidence_malformed"),
    ("not a dict", "evidence_malformed"),
    (None, "evidence_malformed"),
    (_evidence(facts=[]), "no_facts"),
    (_evidence(facts=[_fact()] * 4), "too_many_facts"),
    (_evidence(facts=[_fact("https://www.facebook.com/brightline")]), "source_not_allowed"),
    (_evidence(facts=[_fact("https://brightlinecleaning.com.evil.net/about")]),
     "source_not_allowed"),
    (_evidence(facts=[_fact("https://yelp.com@evil.net/brightline")]), "source_not_allowed"),
    (_evidence(facts=[_fact("ftp://brightlinecleaning.com/about")]), "source_not_allowed"),
    (_evidence(facts=[_fact("https://www.google.ca/maps/place/x")]), "source_not_allowed"),
    (_evidence(identity=None), "identity_unconfirmed"),
    (_evidence(identity={"source_url": GOOGLE_PAGE, "matched_on": "name"}),
     "identity_unconfirmed"),
    (_evidence(identity={"source_url": "https://www.facebook.com/x", "matched_on": "city"}),
     "identity_unconfirmed"),
    (_evidence(identity={"matched_on": "phone"}), "identity_unconfirmed"),
])
def test_evidence_codes(evidence, code):
    verdict = validate(BRIGHTLINE_LINE, evidence, BRIGHTLINE_CTX)
    assert verdict.ok is False
    assert code in verdict.reasons, verdict.reasons


def test_sources_on_subdomains_and_listings_pass():
    ev = _evidence(facts=[
        _fact("https://blog.brightlinecleaning.com/post", "Cleaning offices around Tampa "
                                                         "since 2011."),
        _fact("https://m.yelp.com/biz/brightline", "213 reviews"),
        _fact("https://www.bbb.org/us/fl/tampa/brightline", "Brightline Cleaning Services"),
    ], identity={"source_url": "https://g.page/brightline", "matched_on": "phone"})
    line = ("Brightline has been cleaning offices around Tampa since 2011 and has over 200 "
            "reviews, " + TIE)
    assert validate(line, ev, BRIGHTLINE_CTX).reasons == ()


@pytest.mark.parametrize("context", [
    None, "a string", [], {},
    dict(BRIGHTLINE_CTX, offer_branch="upsell"),
    dict(BRIGHTLINE_CTX, niche="dental"),
    dict(BRIGHTLINE_CTX, company=""),
    dict(BRIGHTLINE_CTX, company_spoken=None),
    dict(BRIGHTLINE_CTX, website_domain=""),
    dict(BRIGHTLINE_CTX, website_domain="localhost"),
    dict(BRIGHTLINE_CTX, city=42),
])
def test_context_malformed(context):
    verdict = validate(BRIGHTLINE_LINE, brightline_evidence(), context)
    assert verdict.ok is False
    assert "context_malformed" in verdict.reasons


def test_city_none_is_allowed():
    context = dict(BRIGHTLINE_CTX, city=None)
    # Tampa is then just a capitalised word, backed by the excerpt.
    assert check(BRIGHTLINE_LINE, context=context).ok


# --- NONE, malformed input, internal errors ---------------------------------

@pytest.mark.parametrize("line", ["NONE", "none", " None. ", "", "   \n\t", None])
def test_none_and_empty(line):
    verdict = check(line)
    assert verdict == ResearchVerdict(ok=False, line="", reasons=("none",),
                                      rules_sha=rr.rules_sha())


@pytest.mark.parametrize("line", [42, b"bytes", ["a"], {"x": 1}])
def test_non_string_line(line):
    verdict = check(line)
    assert verdict.ok is False
    assert verdict.reasons == ("line_malformed",)


@pytest.mark.parametrize("evidence,context", [
    (None, None), (1, 2), ([], []), ({"facts": None, "identity": 5}, {"city": []}),
    ({"facts": [None, 3, {"text": 1}]}, {"website_domain": object()}),
    ({"facts": [{"text": "a", "source_url": "http://[::1", "excerpt": "b"}]}, BRIGHTLINE_CTX),
])
def test_malformed_input_never_raises(evidence, context):
    verdict = validate(BRIGHTLINE_LINE, evidence, context)
    assert verdict.ok is False
    assert verdict.reasons


def test_internal_error_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(rr, "_numbers", boom)
    verdict = check(BRIGHTLINE_LINE)
    assert verdict.ok is False
    assert verdict.reasons == ("validator_error",)


# --- numbers and rounding ---------------------------------------------------

REVIEWS_TIE = " Google reviews, " + TIE


@pytest.mark.parametrize("line,excerpt,ok", [
    ("Brightline has over 200" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", True),
    ("Brightline has over 300" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", False),
    ("Brightline has 213" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", True),
    ("Brightline has 214" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", False),
    ("Brightline has more than 200" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", True),
    ("Brightline has 1,200" + REVIEWS_TIE, "Brightline Cleaning (1200 reviews)", True),
    ("Brightline has over 1,000" + REVIEWS_TIE, "Brightline Cleaning (1,213 reviews)", True),
    # "over N" needs the page to say over N or to show more than N.
    ("Brightline has over 213" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", False),
    ("Brightline has over 200" + REVIEWS_TIE, "Brightline Cleaning (200 reviews)", False),
    ("Brightline has over 200" + REVIEWS_TIE, "Over 200 happy reviews", True),
    # A year or a number of another size does not back "over N".
    ("Brightline has over 2,000" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", False),
    ("Brightline has over 300" + REVIEWS_TIE, "213 reviews and 1,500 offices cleaned", False),
    ("Brightline has 200+" + REVIEWS_TIE, "Brightline Cleaning (213 reviews)", True),
])
def test_rounding(line, excerpt, ok):
    ev = brightline_evidence(review_excerpt=excerpt)
    verdict = check(line, evidence=ev)
    assert verdict.ok is ok, verdict.reasons
    if not ok:
        assert verdict.reasons == ("number_not_in_evidence",)


def test_year_quoted_as_found_passes():
    ev = own_site("brightlinecleaning.com", "Since 2011, serving offices around Tampa.")
    line = "Brightline has been cleaning offices around Tampa since 2011, " + TIE
    assert check(line, evidence=ev).ok


def test_number_absent_from_excerpts_fails():
    ev = own_site("brightlinecleaning.com", "Serving offices around Tampa.")
    line = "Brightline has been cleaning offices around Tampa since 2011, " + TIE
    assert check(line, evidence=ev).reasons == ("number_not_in_evidence",)


def test_st_louis_is_one_sentence():
    context = dict(BRIGHTLINE_CTX, city="St. Louis")
    ev = own_site("brightlinecleaning.com", "Cleaning offices around St. Louis since 2011.")
    line = "Brightline has been cleaning offices around St. Louis since 2011, " + TIE
    assert check(line, evidence=ev, context=context).ok


# --- determinism, rules_sha, purity -----------------------------------------

def test_deterministic():
    first = check(BRIGHTLINE_LINE)
    second = check(BRIGHTLINE_LINE)
    assert first == second
    bad = "I think brightline must be great! Call us?"
    assert check(bad) == check(bad)


def test_rules_sha():
    expected = hashlib.sha256(
        (rr.RULES_TEXT + "\n" + str(rr.RULES_VERSION)).encode("utf-8")).hexdigest()
    assert rr.rules_sha() == expected
    assert check(BRIGHTLINE_LINE).rules_sha == expected
    assert check("NONE").rules_sha == expected
    assert rr.RULES_VERSION == 1


def test_rules_sha_follows_rules_text(monkeypatch):
    before = rr.rules_sha()
    monkeypatch.setattr(rr, "RULES_TEXT", rr.RULES_TEXT + "10. A new rule.\n")
    after = rr.rules_sha()
    assert after != before
    assert check(BRIGHTLINE_LINE).rules_sha == after


def test_rules_text_is_plain():
    text = rr.RULES_TEXT
    for bad in ("\u2014", "\u2013", "!"):
        assert bad not in text
    assert "NONE" in text and "35 words" in text


def test_verdict_is_frozen():
    verdict = check(BRIGHTLINE_LINE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.ok = False
    assert [f.name for f in dataclasses.fields(ResearchVerdict)] == [
        "ok", "line", "reasons", "rules_sha"]
    assert isinstance(verdict.reasons, tuple)


def test_no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("validate opened a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert check(BRIGHTLINE_LINE).ok
    assert "url" in check("Brightline has been cleaning offices around Tampa since 2011, "
                          + TIE[:-1] + " at brightlinecleaning.com.").reasons
