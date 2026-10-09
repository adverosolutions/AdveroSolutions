"""Copy gate for Upwork follow-up drafts (DESIGN.md "Copy gate").

    from services.upwork_followup.copy_gate import check
    problems = check(text, "touch", room, offers_text, private_texts=[notes])

``check`` returns a list of stable problem codes, in CODES order, each at most
once. An empty list means the draft may go on a card as ready to copy; any
code sends it to "Needs edit". ``check_detailed`` returns the same codes with a
short human reason each, which draft.py feeds back to the model on its retry.

Before any check the text is decoded (HTML entities, markdown backslash
escapes and literal ``\\uXXXX`` sequences, repeated until it stops changing, at
most 3 passes) and smart quotes are normalised, so "&mdash;" and
"&amp;mdash;" are both an em dash here.

Codes (stable; tick.py and the cards key on them):

    empty                 no text at all
    em_dash               em, en or figure dash (U+2012..U+2015), or "--"
    exclamation           a "!"
    non_ascii             any other non-ASCII character
    too_long              over 900 characters (touch, checkin) or 1,500 (reply)
    off_platform_contact  explicit contact data (an email address, also
                          obfuscated, or a phone number); a CHANNEL aimed at
                          Lorenzo or the client (see "Off-platform concepts"
                          below); leaving Upwork outright ("outside the
                          contract", "a direct chat", "skip the fee", "off
                          here"); a question about the client's contact
                          details or where to reach them; "there" for a
                          channel the client named; a group Lorenzo sets up
                          for himself and the client; an invoice or payment
                          to Lorenzo outside Upwork milestones; the project
                          set up to reach the client for a test now; a
                          named platform that neither the job post nor the
                          client's messages name; or any draft while the
                          client's unanswered messages ask to move off Upwork
                          and the draft does not say it stays here (see "The
                          client's move request" below). Calls on Upwork are
                          fine.
    external_link         any URL except loom.com and URLs already in the job
                          post; upwork.com and booking or chat hosts
                          (calendly.com, cal.com, zcal, tidycal, savvycal,
                          meetings.hubspot.com, calendar.google.com, wa.me,
                          t.me, ...) are always refused, even from the post
    figure_not_in_offers  a money amount ($, a currency word or code before or
                          after, "3.5k", spelled out), a percentage or a
                          multiplier that is not a whole figure in
                          config/upwork_offers.md; a Proof figure only counts
                          inside its own proof statement, and a figure next to
                          price words must come from the Pricing section. Also
                          a bare number of 100 or more quoted as a price ("call
                          it 2,400", "the first milestone would run 900",
                          "Setup would be 2,500", "2,500 for the setup", "400 a
                          month works"; round 12) and a relative price ("half
                          the price"). A "k" figure before a count noun is a
                          volume, not money ("approx 25k emails", "a 25k list";
                          round 11). One exception (Lorenzo, 2026-10-06): a
                          framework reply is checked with ``band=(low,
                          high)``, and exactly that range, both ends together
                          in a range form ("between $750 and $1,000", "$750 to
                          $1,000"), stated once in a sentence with no rate or
                          per-unit word anywhere in it, passes this check,
                          private_fact and the price-agreement check; see
                          ``band_spans``. A framework reply (``framework=True``,
                          with or without a band) also may not name another
                          price point beside the range ("closer to 1,200",
                          "two grand", "the midpoint"; see
                          ``framework_figure_problems``)
    agrees_to_client_price
                          a number the client stated as a price or budget
                          (money, a price word near it, a price position, or
                          a question proposing it: "Would 2,000 work for the
                          whole build?") taken up in an agreeing form: "2,000
                          works", "$2,000 works", "2k is fine", "happy with
                          2,000", "2,000 it is", "can do 2,000", "deal at
                          2,000", "2,000 for the build works", "Sure, 2,000.".
                          Private notes or not. A count with its noun ("the
                          2,000 contacts") passes, and so does a number the
                          client used only as a volume (round 13, probe p49;
                          see ``client_price_agreements``). In a framework
                          reply, when any unanswered client message proposes
                          a price, an agreement with no figure in any
                          sentence ("Sure, that works.", "Happy to work
                          within your budget") is refused too, and no
                          deferral to the call cancels it (Lorenzo,
                          2026-10-06; see ``framework_price_agreement``)
    private_fact          a money amount, percentage, likelihood, hours
                          estimate or review fact from ``private_texts``, any
                          bare number of 100 or more that appears in the
                          private pricing lines, and a rate ("fifty a month")
                          whose number is in them. The job post or a room
                          message stating the same figure (the client's own,
                          matched on its value) frees a percentage or review
                          figure stated as one, and a pricing-line number only
                          where the draft uses it as a count with its noun
                          ("25k emails", "the 2,500 backlog"); never a money
                          amount, hours figure or rate (round 12; see
                          ``private_figures``)
    placeholder           [ ], {{ }}, TODO or TBD in capitals, XX, <slots>, and
                          the "(figure withheld)" marker draft.py puts where a
                          private figure was (round 10)
    first_name_unknown    with client_first_name null: any opening that
                          addresses a person by name ("Hi Dana.", "Dana, ...",
                          "Dana: ...", "Hey there Dana,", "Hello there, Dana.",
                          "Hello Mr. Whitfield,") or names a word of
                          room["client"] or a name the client signed the job
                          post or a message with. Sentence openers
                          ("Yesterday,", "Meanwhile,") and tool or product
                          names ("Airtable,", "Zapier,") are not names
    not_first_person      "we", "us", "our" outside a single- or double-quoted
                          client quote, or Lorenzo in the third person
    filler_phrase         "just checking in", "circling back", "touching base",
                          "bumping this", "following up on ..." in Lorenzo's own
                          voice. Exempt ONLY when another subject comes right
                          before the phrase in the same clause ("the bot can
                          circle back", "your front desk wanted to follow up")
                          or the phrase is aimed at a third party ("touch base
                          with the lead"). His casual voice drops "I" after
                          "hey,", so "hey, circling back on ..." is his voice
    generic_phrasing      a stock follow-up line in Lorenzo's own voice ("hope
                          all's well", "wanted to follow up", "any news on
                          ...", "any thoughts on the idea?"), or no distinctive
                          term shared with the job post or the client's own
                          messages

Off-platform concepts
---------------------
Round 3 replaced the phrase lists with two concepts, matched per clause
(sentences split at ";", ":", " - " and before so / because / if / when /
which ...):

    CHANNEL    a way to reach, meet or pay a person outside Upwork
               (_CHANNEL_SPECS; ambiguous words pass a context filter, so "a
               buying signal", "your sales teams", "a wise move" and "the
               number of leads" are not channels): email and inboxes; text,
               SMS, phone, number, cell; chat apps (WhatsApp, Telegram, Signal,
               Skype, Discord, Slack, Messenger, ...); meeting apps and their
               links (Zoom, Google Meet, Teams, FaceTime, ...); social
               networks, handles and usernames; booking links, booking pages
               and calendar invites; DMs, private messages and direct chats;
               payment rails (PayPal, Wise, Stripe, Venmo, Zelle, Cash App,
               wire or bank transfer, crypto, a check; round 9: a check only
               in its money sense, "by check", "a check works", "checks are
               fine", "mail you a check", "a check in the mail", "make the
               check out to", not "check-in", "a check to see if", "check
               your inbox").
    DIRECTION  the channel is aimed at Lorenzo or the client. Strong forms
               hold whoever speaks:
               - a person target: "call you on WhatsApp", "message me on X",
                 "call me Thursday at noon on WhatsApp", "a text from me";
               - the channel used as a verb: "WhatsApp you", "email me",
                 "I'll email the proposal over tonight";
               - a possessive: "my PayPal", "send it to my email", "our
                 WhatsApp group";
               - a request for the client's details: "what's your email",
                 "drop your number", "are you on WhatsApp";
               - a move or an offer: "let's move this to email", "here or on
                 WhatsApp", "PayPal works for me", "is WhatsApp ok for you",
                 "I'm around on WhatsApp", "the best way to reach me is email".
               Weak forms depend on the nearest actor before the channel. A
               call or meeting ("happy to hop on a call via WhatsApp", "let's
               do Zoom Thursday at noon"), a transfer ("I'll send the recap by
               email") or a payment ("I accept PayPal", "payment via PayPal
               works", "the deposit can go through PayPal") is refused when
               that actor is Lorenzo, the client or an imperative addressed to
               the client.

A channel whose nearest actor is the PROJECT (the bot, the workflow, the
sequence, the drip, the campaign, leads, customers, your front desk, they,
it), or that heads a
project noun ("your Stripe webhooks", "the WhatsApp flow", "Zoom recordings"),
is the project's subject and passes when the job post or the client's messages
name the platform: "the bot sends the lead a text", "we'd connect your Stripe
webhooks", "the workflow emails the front desk", "I'd have the bot send the
Calendly link". The same holds when the project reaches the client ("the bot
can text you when a quote lands", "customers who message you on WhatsApp");
Lorenzo doing it ("I can text you", "my assistant will WhatsApp you") is
refused.

Booking links, Calendly links and calendar invites are the project's, whoever
they are for, unless they serve contact or a call with Lorenzo: "my Calendly",
"send me your Calendly link", "book a time with me", "for a call", "if you
want to chat", a slot Lorenzo or the client books on it ("grab any slot on
your Calendly"), or a time with no project actor ("a calendar invite for
Thursday at noon"). A generic booking link on a job whose post and messages
never mention booking is refused. Slack counts as a named platform, like
WhatsApp.

Leaving Upwork outright ("outside the contract", "a direct chat", "skip the
fee", "off here", "search my name", "pay it straight to me") is refused
whoever says it, and a URL on a blocked host is refused even when the post
contains it.

Round 4 (a client asks to move off Upwork and the draft goes along) added,
per clause:

    - a question or request about the client's email, phone, number, cell,
      digits or contact info, whatever the question word: "what number should
      I call", "which email should I send it to", "is there a good number for
      you", "do you have a cell I can text", "mind if I call your cell", "is
      email ok?", "drop me your contact info", "which is better for you, email
      or phone?". The project may ask: its sender ("which email should I send
      the drip from"), its users or messages ("which email should I forward
      the replies to") or its machinery ("which number should I use for the
      bot"). Something Lorenzo sends is his, whatever it is about ("which
      email should I send the bot demo to").
    - Lorenzo, his people or the "I" he drops reaching the client's own line:
      "I'll text your cell", "my assistant will call your cell". The verb must
      be theirs: "bounces never reach your inbox" is the project.
    - the channel used as a verb with no person after it, when Lorenzo acts
      earlier in the clause or drops the "I" ("I'll write it up and email it
      tonight", "will text it over"), unless the object is an end user or the
      project's messages ("I'll text the reminder to each lead"); an
      invitation to use a channel ("feel free to text", "text anytime", "you
      can always email", "reach out whenever, by text or email"); leaving with
      no channel word ("outside of here", "elsewhere", "somewhere more
      convenient", "offline", "my other account", "my website", "off the
      books").
    - the client's inbox or phone as where Lorenzo's work arrives: "you'll
      have it in your inbox tonight", "it'll be in your inbox by Friday", "the
      scope will land in your inbox tonight", "it's in your inbox now". The
      project's stream passes ("I'd forward replies to your inbox", "you'll
      get a text on your phone when a lead books", "bounces never reach your
      inbox").
    - payment between Lorenzo and the client on every clause, whatever the
      rail or none: an invoice or bill from Lorenzo ("I'll send you an invoice
      for the deposit", "I'll invoice you through my company", "a separate
      invoice", "my invoice"), money to his account ("pay the deposit to my
      account", "pay me"), his payment details ("I'll send payment details
      separately"), direct payment, a payment link for the work (unless the
      client's own words use that money word for the project, "customers pay
      deposits") or Lorenzo being paid. Upwork milestones and escrow pass, and
      so does the project's money ("you get paid faster through Stripe", "you
      can pay your vendors through Wise"). Round 9: a cheque for him ("mail
      me a check", "mail the check to my office", "make the check out to
      me", "checks can be made payable to ..."), his mailing address or wire
      details ("I'll send you the mailing address", "I'll send over the
      details for the wire"), and "happy to take" a rail ("happy to take a
      check / a bank transfer"), like "a check is fine" and "a bank transfer
      is fine". Checks the build writes ("the bot makes the checks out to
      each supplier") and the mailing address as a field pass. Round 10:
      outside a payments job, any rail but Upwork that he offers or accepts,
      asked for or not ("send a wire", "paying by check works", "cash works
      too", "a check is fine", "you can pay by Zelle", "once the wire clears
      I'll start"), unless refused ("no wires or checks"), the means of an
      Upwork payment ("fund the milestone with a bank transfer") or the
      project's money ("customers who pay by check", "the bot logs each
      check", "do you take checks?", "roofers who take cash", "check
      numbers").
    - the project set up to reach the client for a test now: "I can have the
      bot message you on WhatsApp so you can try it", "I can have the bot text
      you so you can reply with a photo", "I can get the bot to message you so
      you can test it", "I'll add you to the WhatsApp test group", "let me add
      you as a tester", "I can join your Slack to test it", "I'll create a
      Slack channel for us". The finished system reaching the client passes,
      whoever builds it: "the bot can text you when a quote lands", "I can
      have the bot text you when a quote lands", "every morning", "a daily
      summary".
    - a booking with no channel word ("my calendar is open Thursday, grab a
      slot") and the address the client gave ("to the address you gave").
    - asking where or how to reach the client, with no channel word: "where
      should I send the scope?", "how should I get it to you?", "what's the
      best way to reach you?", "tell me where to send it". The project's
      routing passes: its actor ("where should the bot send the quote
      requests?"), its stream or users ("where should I send the new
      leads?"), a tool it runs on ("..., HubSpot or Pipedrive?") and Upwork
      itself. A test stream is the client's own address ("where do you want
      me to send the test texts?").
    - "there" for a channel a client message named ("can we move this to
      WhatsApp?"): "just message me there", "happy to continue there", "see
      you there", "I'll send it there tonight", "happy to walk you through it
      there". Checked only when a client message names a channel, and not
      when the sentence or the one before it names Upwork ("Upwork has calls
      built in. See you there"). The project and its users pass ("the bot
      will reply there", "customers who message there", "you can reply there
      to claim it", "I'll forward the new leads there").
    - a group Lorenzo sets up for himself and the client: "a Slack channel
      for us", "a shared WhatsApp group for updates", "a private Slack
      channel for the project", "a WhatsApp group for your team and me". One
      for the client's team, users or stream, or one that lives in the
      project's tool, is the project ("a shared channel for your installers",
      "a private Slack channel for the alerts", "a shared workspace in
      Airtable"). Round 5: a purpose ("for updates", "for questions") beats
      the client's team, so "a shared WhatsApp group for updates with your
      team" and "a WhatsApp group with your team for updates" are refused
      even when nobody asked; updates to the team ("for updates to your
      installers") and a project stream in the sentence stay the project.
      Round 7: a group is the project's, with or without a team word, when
      the sentence names the project (its actor, "the bot", not the client's
      team; a tool it runs on, not the weekday Monday; or a per-item stream,
      "every job", "each status change", not "each update" or "each
      project"; a lead-in before a colon is only the topic) or when the job
      post or a client message asks for that group or channel as the
      deliverable ("a shared Slack channel for updates, fed from ClickUp"
      where the post asks for one). "For us", "with you", "between us" and
      the like are still Lorenzo's group.

The client's move request (round 5)
-----------------------------------
The rules above read the draft's own words, so after "I'd rather pay you
directly by bank transfer" a plain "Sure, that works for me." passed. A
separate detector, client_move_request, reads the client's voice ("I", "we"
and "my" are the client, "you" is Lorenzo) in the client's unanswered
messages: those after Lorenzo's last message (unanswered_client_messages,
which draft.latest_client_messages also returns), room events skipped, newest
first, at most ten messages and MOVE_REQUEST_CHARS (8,000) characters in all,
each message read to ANALYSIS_MAX_CHARS. It fires when the client asks to
move something off Upwork or hands over contact details:

    payment   directly, by bank transfer, PayPal, Wise, crypto, cash or a
              check, "to avoid the fees", "invoice me directly", "what's your
              PayPal", "would Wise work for paying you"; round 6: paying
              Lorenzo "another / some other / a different way" or "besides /
              other than / instead of Upwork"; Upwork's cut, fees or charges
              given as the reason in an ask about how to pay ("Upwork takes a
              big cut, how should I pay you?", not "can I pay you a bit more
              to cover it"; round 7: the fee is Upwork's or the platform's,
              "on here" included, never a named third party's, "Stripe fees
              are brutal"); "I'd rather not pay the (Upwork) fees"; money
              sent to Lorenzo ("send you a wire", "to your account", "can I
              just send a bank transfer?", "I'll send a wire", "if I send a
              wire to your account"; round 8: the client ("I", "we", "let
              me") offering or asking to send a transfer, wire, payment or
              check, "I'd rather", "happy to", "easier if I", "why don't I",
              "to you directly" included, but not a plain habit with no
              modal and no "you", "we send a wire every Friday", "I pay by
              check" (project talk); not when "to" names someone else, "a
              bank transfer to each supplier", nor when Upwork, the platform
              or the project sends it, "Upwork will send you the payment",
              "I'd like the workflow to send"; "send you", "to your account"
              and "to your bank" always count, "to" and a verb is a purpose
              ("to get started"), and a schedule alone never clears it; not
              "a payment for the next milestone", but Upwork or milestones
              named only to leave them do not clear a sentence, "I'd rather
              not pay through Upwork", "instead of milestones", and refusing
              to pay through Upwork is itself a request); a rail for "your
              fee" even in a payments job; round 9: "rather / prefer /
              easier / sooner ... than (go / pay) through Upwork" refuses
              Upwork (neither a keep nor a venue), and a check counts like
              any rail ("mail / write / send you a check", "can I just mail a
              check?", "I'll drop a check in the mail", "do you take
              checks?", "would a check work?", "by check", "who do I make the
              check out to?"; not "check-in", "a check to see if", "check
              your inbox")
    call      Zoom, Meet, Teams, phone, Calendly: "can we do this on Zoom
              instead", "call me tomorrow", "do you have a Calendly"; round
              7: a phone number in a message that talks about a call or
              talking ("A call would be quicker. My cell is ...", "Easier to
              just talk. 512 ...")
    group     a group or workspace: "a WhatsApp group with me and my office
              manager", "add me to a Slack workspace"
    files     "what's your email so I can send the files", "send the scope to
              my email", files over Dropbox or Google Drive
    contact   email, phone, text, WhatsApp, Telegram, Slack, DMs: "are you on
              WhatsApp", "text me instead", "let's move this to our Slack";
              round 6: a named platform the job post does not name offered
              as easier ("would WhatsApp be easier?"), and one on its own as
              a question ("Zoom?" is a call, "WhatsApp?" contact; round 7:
              either only when the message names Upwork or talks about a
              call or talking, not "Which app are the recordings on? Zoom?")
    details   a number, email address or handle for Lorenzo to use: "my cell
              is ...", "I'm @name on Telegram"

Round 9's wider rule: outside a payments job, a message the rules above pass
still counts as payment when a sentence ties a money word (pay, payment,
paid, wire, transfer, check, cheque, cash, invoice, deposit, retainer, fee,
or a named rail) to Lorenzo ("pay you", "your fee", "to you", "you take /
accept", "mail / write / send you", "you ... get paid") or to Upwork
("through / via / on / than Upwork", Upwork's fees or cut, "Upwork takes a
cut", "Upwork takes 20%", not "Upwork fees aside"), unless the sentence keeps
payment on Upwork or Upwork, the platform or the project moves the money
("Upwork will send the payment to you", "the bot can send you the invoice").
It never replaces a category the rules above found; a false fire only makes
the draft keep payment on Upwork. Round 10: asking where or how the money
goes ties it to Lorenzo as well ("where should I send the money?", "how do
you want the deposit?"; not "where should I send the payment data?" or "the
payment for the Twilio number").

The newest message with a request decides; its categories rank in the order
above. The project stays the project: its machinery, stream, tools, staff and
users ("can the bot text me when a quote lands", "customers message us on
WhatsApp", "can the rep get the quote by email", "we record every sales call
on Zoom"), the project's event or schedule ("text me when a lead comes in",
"email me the report every Friday"), Upwork as the venue ("could we do a
quick Upwork call"), a negation ("no need to email"), and, in a payments job
(the title or post names a rail or a payments workflow), a rail with no
payment to Lorenzo ("is Stripe ok?", "can we accept payments via PayPal?").
"Don't mind", "wouldn't mind", "no problem", "not a problem", "why don't
we" and "wouldn't it be" are not negations, and the "it" of "would it be
easier" is not the project (round 6).

When it fires, the draft (a reply, or a check-in or touch written while the
request is unanswered) is refused as off_platform_contact unless it keeps
the requested thing on Upwork in so many words (keeps_on_upwork with the
category, rounds 6 and 7), whatever the draft opens with:

    payment   Upwork tied to the payment ("paying through Upwork", "Upwork
              milestones", "keeping it on Upwork protects us both", not "the
              scope is here on Upwork"), milestones, escrow, "pay here",
              "keep payment here" (not "the invoice here")
    call      an Upwork call, "a call here", "on here", "here on Upwork",
              "let's do it / meet / talk on Upwork"
    contact, files, details, group
              "here" or "this chat" as where the talk or the files go ("keep /
              stay / attach / send / reply / post ... here"), Upwork
              messages, or an Upwork call

and, for any category, a keep of everything ("keep things here", "let's stay
on Upwork"). A filler "here" ("one thing I'd flag here", "happy to help
here") never counts, nor does an extra copy ("a short summary here too", "a
copy here"), milestones listing the work's phases ("two milestones: intake
first, then the Slack ping"), "here's", "here is", "Upwork's fees", or those
words after "off", "outside", "instead of", "rather than", "skip", "away
from", "not on" and the like. A keep cue for another category does not
count: after a phone ask, "Thursday at noon works for me. I'll post a short
agenda here first." and "Feel free to attach the brand files right here."
are refused, and "Sure, that works, I'll split it into two milestones" passes
after a bank-transfer ask. An opening yes ("Sure", "Works for me", "That
works", "Sounds good", "No problem", "Happy to", "Will do", at the start of
any sentence) only labels the reason. Words that point back at the client's
own detail or ask refuse the draft whatever else it says: "that number",
"that address", "that email", "that link", "that invite", "that group", "that
workspace", "I'll call you", "I'll ring", "I'll text", "I'll email/send it
(over) to you", "I'll join", "join the call", "I'll add/set up the group"
("I'll call that number Thursday and post the agenda here first" is
refused), and, in a clause that does not put it here, "I'll send it over",
"send the invite" and "happy to switch". The reason names the category and
how it stays on Upwork ("client asked to move payment off Upwork, and the
draft goes along with it ('Sure'); keep it on Upwork instead (payment
through Upwork milestones or escrow)"), never the client's words. A request
Lorenzo already answered (before his last message) is not read.

Every check after the length check reads only the first ANALYSIS_MAX_CHARS
(4,000) characters, so a runaway draft costs linear time; anything that long
is already too_long.

The AI and automation word ban from the cold-email gate does NOT apply here:
Upwork clients post automation jobs.

Pure functions only: no I/O, no network, no model.
"""
import bisect
import functools
import html
import re
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

CODES = (
    "empty",
    "em_dash",
    "exclamation",
    "non_ascii",
    "too_long",
    "off_platform_contact",
    "external_link",
    "figure_not_in_offers",
    "agrees_to_client_price",
    "private_fact",
    "placeholder",
    "first_name_unknown",
    "not_first_person",
    "filler_phrase",
    "generic_phrasing",
)

DESCRIPTIONS = {
    "empty": "the draft is empty",
    "em_dash": "it contains an em or en dash (or '--'); use a comma, a period or a plain hyphen",
    "exclamation": "it contains an exclamation mark",
    "non_ascii": "it contains a non-ASCII character (emoji, accented letter, ellipsis or similar)",
    "too_long": "it is too long (touches max 900 characters, replies max 1,500)",
    "off_platform_contact": ("it moves contact or payment off Upwork: an email address, phone number or handle, "
                             "a way to reach Lorenzo or the client on another channel (email, text, phone, "
                             "WhatsApp, Zoom, LinkedIn, a booking link and so on), or paying outside Upwork. "
                             "Calls here on Upwork are fine, and a platform the job post names may appear as "
                             "part of the project"),
    "external_link": "it contains a link other than the Loom link or a link already in the job post",
    "figure_not_in_offers": ("it states a money figure, percentage or multiplier that is not in UPWORK_OFFERS, "
                             "uses a proof figure outside its proof statement, or quotes a price"),
    "agrees_to_client_price": ("it agrees to or accepts a price the client proposed: do not agree to or accept a "
                               "price; leave pricing to Lorenzo"),
    "private_fact": "it repeats a private figure, likelihood, hours estimate or review fact",
    "placeholder": "it contains a placeholder such as [ ], {{ }}, TODO, TBD or XX",
    "first_name_unknown": "it addresses the client by a name, but the client's first name is unknown",
    "not_first_person": "it is not first person singular (no 'we', 'us' or 'our' unless quoting the client)",
    "filler_phrase": ("it uses a filler phrase such as 'just checking in', 'circling back', 'touching base' or "
                      "'following up'"),
    "generic_phrasing": ("it reads like a template: a stock follow-up line, or nothing that refers to this "
                         "client's own words, project details or messages"),
}

TOUCH_MAX_CHARS = 900
REPLY_MAX_CHARS = 1500
ANALYSIS_MAX_CHARS = 4000  # checks past the length read this much; anything longer is too_long anyway
DECODE_PASSES = 3

# ------------------------------------------------------------ normalising
_SMART = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
}
_DASH_RE = re.compile("[‒–—―]")
_DOUBLE_HYPHEN_RE = re.compile(r"(?:\s|\w)--+(?:\s|\w)")
_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>|~<=])")
_U_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def unescape_text(text: Any) -> str:
    """One pass: HTML entities and markdown backslash escapes -> plain text.

    Upwork message text can carry sequences like ``\\-&gt;`` that clean_text
    leaves in. Read raw, they would feed junk tokens ("quot", "nbsp") to the
    distinctive-term match and hide URLs behind ``&amp;``."""
    out = text if isinstance(text, str) else ("" if text is None else str(text))
    return _MD_ESCAPE_RE.sub(r"\1", html.unescape(out))


def decode_escapes(text: Any, passes: int = DECODE_PASSES) -> str:
    """unescape_text plus literal ``\\uXXXX`` sequences, repeated until the
    text stops changing (at most ``passes``), so a double-escaped
    "&amp;mdash;" decodes to the dash it stands for."""
    out = text if isinstance(text, str) else ("" if text is None else str(text))
    for _ in range(max(1, passes)):
        nxt = _U_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), unescape_text(out))
        if nxt == out:
            break
        out = nxt
    return out


def normalise(text: Any) -> str:
    """Smart quotes -> ASCII quotes. Nothing else is rewritten: a dash or an
    emoji is a problem to report, not something to fix silently."""
    out = text if isinstance(text, str) else ("" if text is None else str(text))
    for smart, plain in _SMART.items():
        out = out.replace(smart, plain)
    return out


def _sentences(text: str) -> List[Tuple[int, int]]:
    """(start, end) spans of sentences. A period inside a number ('3.5') or
    after a title ('Mr.') does not end one."""
    spans = []
    start = 0
    for m in re.finditer(r"(?<!\d)[.?!](?!\d)(?=\s|$)|\n", text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _sentence_at(text: str, pos: int) -> str:
    for s, e in _sentences(text):
        if s <= pos < e:
            return text[s:e]
    return text


# ------------------------------------------------------------ figures
_MULT = {"k": 1000, "thousand": 1000, "grand": 1000, "m": 1000000, "mm": 1000000, "million": 1000000,
         "b": 1000000000, "bn": 1000000000, "billion": 1000000000}
_NUM = r"\d[\d,]*(?:\.\d+)?"
_SUFFIX = r"(?:\s?(?:k|mm|m|bn|b|thousand|million|billion|grand)\b)?"
_CUR_BEFORE = r"(?:\$|us\$|usd|eur|gbp|cad|aud|€|£)"
_CUR_AFTER = r"(?:dollars?|bucks|usd|eur|euros?|gbp|pounds?|cad|aud)"
_MONEY_BEFORE_RE = re.compile(r"(?<![\w$])%s\s?(%s)(%s)" % (_CUR_BEFORE, _NUM, _SUFFIX), re.I)
_MONEY_AFTER_RE = re.compile(r"(?<![\w$.,])(%s)(%s)\s?%s\b" % (_NUM, _SUFFIX, _CUR_AFTER), re.I)
_K_RE = re.compile(r"(?<![\w$.,])(\d+(?:\.\d+)?)\s?(k)\b", re.I)
# Round 11: a "k" figure before a count noun is a volume, like "300 leads" in
# the bare-number rule: "approx 25k emails", "25k verified contacts", "a 25k
# email list", "25k-30k leads", "a list of about 25k". "a 25k budget", "for
# 25k", "25k a month", "25k worth of leads" and "would be 25k" stay money.
_K_COUNT_NOUN = (
    r"(?:e-?mails|contacts|leads|addresses|records|rows|users|subscribers|followers|calls|texts|messages|visitors|"
    r"views|lists|orders|customers|members|patients|prospects|companies|businesses|domains|mailboxes|inboxes|"
    r"accounts|profiles|listings|products|skus|items|units|tickets|sessions|clicks|impressions|opens|replies|sends|"
    r"downloads|installs|sign-?ups|registrations|applicants|candidates|students|homeowners|entries|pages|posts|"
    r"visits|requests|submissions|conversations|chats|numbers|dms|"
    r"(?:e-?mail|contact|lead|subscriber|customer|member|patient|prospect|phone|sms|text|user|address|mailing|"
    r"call)\s+(?:lists?|database|db|file|sheet|csv|export|segment|audience|base|blast|campaigns?)|"
    r"list|database|audience)")
_K_VOLUME_AFTER_RE = re.compile(
    r"\+?(?:\s*(?:-|to|or)\s*\d+(?:\.\d+)?\s?k\b\+?)?[\s-]+(?:of\s+(?:(?:our|my|their|your|the|those|these)\s+)?)?"
    r"(?:(?!(?:budget|budgets|price|prices|cost|costs|fee|fees|rate|rates|retainer|dollars?|bucks|usd|worth|a|an|"
    r"per|for|and|or|to|in|on|at|of|the|with|from|into|plus)\b)[a-z][\w'-]*\s+){0,2}%s\b"
    r"(?!\s+(?:budget|spend|costs?|prices?|fees?|retainer)\b)" % _K_COUNT_NOUN, re.I)
_K_VOLUME_BEFORE_RE = re.compile(
    r"\b(?:list|lists|database|audience|batch|pool|file|sheet|csv)\s+of\s+(?:(?:about|around|roughly|"
    r"approximately|approx\.?|over|under|nearly|almost|some|just\s+over|just\s+under)\s+|~\s*)?$", re.I)
# "$1,500-2,000" and "$1,500 to 2,000": the upper end carries no second "$".
_RANGE_TAIL_RE = re.compile(r"\A\+?\s*(?:-|to)\s*(?:%s)?\s?(%s)(%s)" % (_CUR_BEFORE, _NUM, _SUFFIX), re.I)
_PCT_WORD = r"(?:\s?%|\s*\bper\s?cent\b|\s*\bpct\b)"
# "20-30%" / "20 to 30 percent": the lower end has no sign of its own.
_PCT_RE = re.compile(r"(?<![\d.,$])(\d+(?:\.\d+)?)(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?(%s)" % _PCT_WORD, re.I)
_MULTIPLIER_RE = re.compile(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)x\b", re.I)

_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_SPELLED_PCT_RE = re.compile(
    r"\b(?:(%s)(?:[\s-]+(%s))?|(%s)|(%s)|(a|one)\s+hundred)\s+per\s?cent\b" % (
        "|".join(_TENS), "|".join(_UNITS), "|".join(_TEENS), "|".join(_UNITS)), re.I)
_NUMBER_WORDS = sorted(list(_UNITS) + list(_TEENS) + list(_TENS) + ["a", "hundred", "thousand", "million", "and"],
                       key=len, reverse=True)
_NUMBER_HEADS = "|".join(sorted(list(_UNITS) + list(_TEENS) + list(_TENS), key=len, reverse=True))
# At most ten number words before the head: "nine hundred ninety nine thousand
# nine hundred ninety nine dollars" is nine. An unbounded run made "one one
# one ..." cost quadratic time.
_SPELLED_MONEY_RE = re.compile(
    r"\b((?:(?:%s)[\s-]+){0,10}(?:%s|hundred|thousand|million))\s+(dollars?|bucks|grand|usd)\b" % (
        "|".join(_NUMBER_WORDS), _NUMBER_HEADS), re.I)
# Round 11: a spelled amount, percentage or rate needs its last word, so a text
# with none skips that slower scan (the room's public text is read whole, and
# a flood of "a a a" or "one two three" must stay cheap). Each hint matches
# wherever its pattern could.
_SPELLED_MONEY_HINT_RE = re.compile(r"(?:dollars?|bucks|grand|usd)\b", re.I)
_SPELLED_PCT_HINT_RE = re.compile(r"per\s?cent\b", re.I)
_RATE_HINT_RE = re.compile(r"(?:day|week|wk|month|mo|year|yr|monthly|weekly|yearly|annually)\b", re.I)


def _canon(raw: str, suffix: str = "") -> Optional[str]:
    """'1,500' -> '1500'; '5', 'M' -> '5000000'; '2.50' -> '2.5'."""
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    word = (suffix or "").strip().lower()
    if word:
        value *= _MULT.get(word, 1)
    return ("%.2f" % value).rstrip("0").rstrip(".")


def _spelled_value(words: str) -> Optional[int]:
    total, cur, seen = 0, 0, False
    for w in re.split(r"[\s-]+", words.lower()):
        if not w or w == "and":
            continue
        if w == "a":
            cur = cur or 1
        elif w in _UNITS:
            cur += _UNITS[w]
        elif w in _TEENS:
            cur += _TEENS[w]
        elif w in _TENS:
            cur += _TENS[w]
        elif w == "hundred":
            cur = (cur or 1) * 100
        elif w in ("thousand", "million"):
            total += (cur or 1) * (1000 if w == "thousand" else 1000000)
            cur = 0
        else:
            return None
        seen = True
    return (total + cur) if seen else None


def money_spans(text: str) -> List[Tuple[int, int, str]]:
    """(start, end, canonical value) of every money amount: "$3,500", "US$3,500",
    "USD 3,500", "3,500 dollars", "3500 USD", "3.5k", "3,500 bucks", "five
    thousand dollars", "five grand", and the upper end of a range. A bare "k"
    figure before a count noun is a volume, not money ("approx 25k emails")."""
    body = text or ""
    out = []  # type: List[Tuple[int, int, str]]
    used = bytearray(len(body) + 1)  # characters already inside an amount

    def add(s, e, val):
        if val is None or used.find(1, s, e) != -1:
            return
        used[s:e] = b"\x01" * (e - s)
        out.append((s, e, val))

    for m in _MONEY_BEFORE_RE.finditer(body):
        add(m.start(), m.end(), _canon(m.group(1), m.group(2)))
        tail = _RANGE_TAIL_RE.match(body[m.end():])
        if tail:
            add(m.end() + tail.start(1), m.end() + tail.end(), _canon(tail.group(1), tail.group(2)))
    for m in _MONEY_AFTER_RE.finditer(body):
        add(m.start(), m.end(), _canon(m.group(1), m.group(2)))
    for m in _K_RE.finditer(body):
        lead_in = body[max(0, m.start() - 40):m.start()]
        if _K_VOLUME_AFTER_RE.match(body, m.end()) or _K_VOLUME_BEFORE_RE.search(lead_in):
            continue  # round 11: "approx 25k emails" counts things, it is not a price
        add(m.start(), m.end(), _canon(m.group(1), m.group(2)))
    for m in (_SPELLED_MONEY_RE.finditer(body) if _SPELLED_MONEY_HINT_RE.search(body) else ()):
        val = _spelled_value(m.group(1))
        if val is not None:
            if m.group(2).lower() == "grand":
                val *= 1000
            add(m.start(), m.end(), _canon(str(val)))
    return sorted(out)


def dollar_figures(text: str) -> List[str]:
    """Every money amount as a whole token, canonical. '$1,500' and '$1500' are
    the same figure; '$1' inside '$1,500' is never read on its own."""
    return [v for _, _, v in money_spans(text)]


def percent_spans(text: str) -> List[Tuple[int, int, str]]:
    body = text or ""
    out = []  # type: List[Tuple[int, int, str]]
    for m in _PCT_RE.finditer(body):
        for raw in (m.group(1), m.group(2)):
            if raw:
                val = _canon(raw)
                if val is not None:
                    out.append((m.start(), m.end(), val))
    for m in (_SPELLED_PCT_RE.finditer(body) if _SPELLED_PCT_HINT_RE.search(body) else ()):
        if m.group(5):
            val = "100"
        elif m.group(1):
            val = str(_TENS[m.group(1).lower()] + (_UNITS[m.group(2).lower()] if m.group(2) else 0))
        elif m.group(3):
            val = str(_TEENS[m.group(3).lower()])
        else:
            val = str(_UNITS[m.group(4).lower()])
        out.append((m.start(), m.end(), val))
    return sorted(out)


def percent_figures(text: str) -> List[str]:
    """Every percentage as a whole number token ('35%' never yields '5')."""
    return [v for _, _, v in percent_spans(text)]


def multiplier_spans(text: str) -> List[Tuple[int, int, str]]:
    return [(m.start(), m.end(), _canon(m.group(1)) or "") for m in _MULTIPLIER_RE.finditer(text or "")]


_BARE_NUM_RE = re.compile(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)(\s?k\b)?", re.I)


def bare_numbers(text: str, minimum: float = 100) -> Set[str]:
    """Every number of ``minimum`` or more, with or without a currency sign."""
    out = set()  # type: Set[str]
    for m in _BARE_NUM_RE.finditer(text or ""):
        val = _canon(m.group(1), (m.group(2) or "").strip())
        try:
            if val is not None and float(val) >= minimum:
                out.add(val)
        except ValueError:
            continue
    return out


# A number followed by a rate ("fifty a month", "50/mo", "1,200 per year").
_RATE_AFTER = r"(?=\s*(?:a|an|per|/)\s*(?:day|week|wk|month|mo|year|yr)\b|\s*(?:monthly|weekly|yearly|annually)\b)"
_RATE_DIGITS_RE = re.compile(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)" + _RATE_AFTER, re.I)
_RATE_SPELLED_RE = re.compile(r"\b((?:(?:%s)[\s-]+){0,10}(?:%s|hundred|thousand))%s" % (
    "|".join(_NUMBER_WORDS), _NUMBER_HEADS, _RATE_AFTER), re.I)


def rate_values(text: str) -> Set[str]:
    """Canonical values of numbers stated as a rate, in digits or in words."""
    out = set()  # type: Set[str]
    for m in _RATE_DIGITS_RE.finditer(text or ""):
        val = _canon(m.group(1))
        if val is not None:
            out.add(val)
    for m in (_RATE_SPELLED_RE.finditer(text) if text and _RATE_HINT_RE.search(text) else ()):
        val = _spelled_value(m.group(1))
        if val is not None:
            out.add(str(val))
    return out


_HOURS_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?\s*(?:hours?|hrs?|h)\b", re.I)
_REVIEW_RE = re.compile(
    r"(?<![\d.])(\d(?:\.\d{1,2})?)\s*(?:stars?|/\s?5\b|star rating)|"
    r"(?<![\d.])(\d+)\s+(?:reviews?|ratings?|hires?|jobs posted)\b", re.I)
_LIKELIHOOD_RE = re.compile(r"\blikelihood\b", re.I)
_ODDS_RE = re.compile(r"\blikelihood\b|\b(?:my|the|our|your)\s+(?:odds|chances)\b|\bodds (?:are|of)\b", re.I)
_REVIEW_WORDS_RE = re.compile(r"\b(hire rate|total spent|payment verified|member since)\b", re.I)
_PRICING_HEADER_RE = re.compile(r"pric|rate|cost|budget|fee|quote|money|estimate \$", re.I)
_HEADER_RE = re.compile(r"^\s*[-*]?\s*([A-Za-z][A-Za-z /&]{1,40}):\s*(.*)$")


def _hours(text: str) -> Set[str]:
    out = set()  # type: Set[str]
    for m in _HOURS_RE.finditer(text or ""):
        for raw in (m.group(1), m.group(2)):
            if raw:
                val = _canon(raw)
                if val is not None:
                    out.add(val)
    return out


def _reviews(text: str) -> Set[str]:
    out = set()  # type: Set[str]
    for m in _REVIEW_RE.finditer(text or ""):
        raw = m.group(1) or m.group(2)
        val = _canon(raw) if raw else None
        if val is not None:
            out.add(val)
    return out


def private_pricing_lines(private: str) -> List[str]:
    """Lines of the private notes that state pricing: any line with a '$', and
    every line of a section whose header names pricing ("Standard pricing:"),
    whether the figures sit on the header line or below it."""
    out = []  # type: List[str]
    in_pricing = False
    for line in (private or "").splitlines():
        header = _HEADER_RE.match(line)
        if header:
            in_pricing = bool(_PRICING_HEADER_RE.search(header.group(1)))
        if in_pricing or "$" in line:
            out.append(line)
    return out


# Round 10: draft.py hides these figures from the model (withhold_figures), so
# a figure from the private "For you" material never reaches a draft to be
# refused there. The private_fact check below stays as the backstop.
# Round 11: a figure the job post or the room states is the client's own
# ("approx 25k emails"): draft.py shows the client's text as written.
# Round 12: that never frees Lorenzo's price, rate or hours figure. A number
# from his private pricing lines is freed only where a text uses it as a
# count with its noun ("25k emails", "the 2,500 backlog"), never as a price.
WITHHELD_FIGURE = "(figure withheld)"
_WITHHELD_RE = re.compile(r"\bfigures?\s+withheld\b", re.I)
_RANGE_GAP_RE = re.compile(r"\s*(?:-|to)\s*\Z", re.I)


# The public text read for figures: the title and the post, then the newest
# messages, this many characters in all (a real room is far smaller; an older
# figure past it only stays private, the safe side).
PUBLIC_FIGURE_CHARS = 100000


def public_texts(room: Optional[Dict[str, Any]]) -> List[str]:
    """The job title, the job post and every room message, whoever wrote it
    (newest first, PUBLIC_FIGURE_CHARS in all): text the client wrote or has
    read, so its figures are public."""
    room = room if isinstance(room, dict) else {}
    job = room.get("job")
    texts = [room.get("job_title"), job.get("post") if isinstance(job, dict) else None]
    texts += [m.get("text") for m in reversed(room.get("messages") or []) if isinstance(m, dict)]
    out, budget = [], PUBLIC_FIGURE_CHARS
    for text in texts:
        if budget <= 0:
            break
        if isinstance(text, str) and text.strip():
            out.append(text[:budget])
            budget -= len(text)
    return out


_WORD_SCALE_RE = re.compile(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)\s?(thousand|million|billion)\b", re.I)


def stated_numbers(text: str) -> Set[str]:
    """The canonical value of every number ``text`` states, in any form:
    "25k", "25,000", "25000" and "25 thousand" are all "25000"; spelled money
    and rates ("five grand", "fifty a month") count too."""
    return _stated(text, set(dollar_figures(text)), rate_values(text))


def _stated(text: str, money: Set[str], rates: Set[str]) -> Set[str]:
    scaled = {_canon(m.group(1), m.group(2)) for m in _WORD_SCALE_RE.finditer(text or "")}
    return bare_numbers(text, minimum=0) | money | rates | {v for v in scaled if v is not None}


def _joined(texts: Sequence[Any]) -> str:
    return "\n".join(normalise(decode_escapes(t)) for t in (texts or ()) if t)


# Round 12: how a text uses a number. A count names what it counts right after
# it ("2,500 contacts", "the 2,500 backlog", "400 leads a month", "2,500 in the
# backlog", "all 2,500 of them") or right before it ("a list of about 2,500");
# a "k" figure is a count where money_spans reads it as a volume ("25k
# emails"). Anything else is a price, rate or time use: a money marker, a rate
# ("400 a month", "400/mo", "per"), a time unit ("6 hours"), a price word
# ("setup", "retainer", "fee") or no noun at all ("would be 2,500", "2,500
# works", "2,500 for the setup").
# A singular value noun reads as a price too ("a 2,500 project", "your 2,500
# figure"); its plural counts things ("400 jobs", "2,500 numbers").
_VALUE_NOUNS = """
figure amount sum number offer deal bid proposal investment project job build engagement contract gig milestone phase
option ask check cheque transfer bill tab subscription license licence
"""
_PRICE_WORDS = frozenset(("""
setup setups set-up retainer retainers fee fees budget budgets price prices pricing priced cost costs deposit deposits
dollar dollars buck bucks usd eur euro euros gbp pound pounds cad aud spend spending payment payments invoice invoices
charge charges rate rates quote quotes quoted total totals estimate estimates ballpark flat fixed upfront monthly weekly
yearly annually daily hourly commission commissions margin margins profit profits revenue sales savings worth value
plan plans package packages tier tiers discount discounts grand figures amounts
""" + _VALUE_NOUNS).split())
# The second word of the noun phrase: "2,500 setup fee", "400 ad spend", "a
# 2,500 fixed-price build".
_PRICE_NOUNS = frozenset(("""
setup set-up retainer retainers fee fees budget budgets price prices cost costs deposit deposits dollars bucks spend
spending payment payments invoice invoices charge charges rate rates quote quotes
""" + _VALUE_NOUNS).split())
_TIME_WORDS = frozenset("""
hour hours hr hrs h minute minutes min mins day days week weeks wk wks month months mo mos year years yr yrs
""".split())
# Words right after a number that do not name what it counts, besides the
# bare-price rule's _NOT_A_UNIT ("for", "and", "works", ...).
_NOT_A_NOUN = frozenset("""
about around approximately approx some more less fewer over under above below first last next now today tomorrow
again apiece minimum maximum it its you your we our i they their he she me us them his her my is are be been being do
does did has have had get gets got go goes went give gives take takes make makes sure yes no not only just even also
too very really maybe perhaps probably likely exactly than like via into onto from of inside within among without
between through across versus vs out off back x
""".split())
_NOUN_AFTER_RE = re.compile(
    r"^(?:\s*(?:-|to)\s*\d[\d,]*(?:\.\d+)?)?\+?[\s-]+([a-z][\w'-]*)(?:\s+([a-z][\w'-]*))?", re.I)
_COUNT_OF_RE = re.compile(
    r"^\+?\s+(in|of|on|from|across|inside|within|among)\s+(?:(?:the|our|your|their|those|these|that|this|each|"
    r"every|all|my|his|her)\s+)?([a-z][\w'-]*)(?:\s+([a-z][\w'-]*))?", re.I)
_RATE_USE_RE = re.compile(
    r"^\s*(?:per\b|/|(?:a|an|each|every)\s+(?:day|week|wk|month|mo|year|yr|hour|hr)\b|"
    r"(?:monthly|weekly|yearly|annually|daily|hourly)\b)", re.I)
_COUNT_BEFORE_RE = re.compile(
    r"\b(?:list|lists|database|audience|batch|pool|file|sheet|csv|backlog|queue|pipeline)\s+of\s+(?:(?:about|around|"
    r"roughly|approximately|approx\.?|over|under|nearly|almost|some|just\s+over|just\s+under)\s+|~\s*)?$", re.I)
# A payment verb before "N on/in ..." makes it money: "spend 400 on ads".
_PAID_BEFORE_RE = re.compile(
    r"\b(?:spend|spends|spent|spending|pay|pays|paid|paying|charge|charges|charged|charging|cost|costs|invest|invests|"
    r"invested|budget|budgeted|priced|quote|quoted|invoice|invoiced|bill|billed|billing)\b[^.?!\n]{0,40}$", re.I)


def _not_a_noun(word: str) -> bool:
    return word in _NOT_A_NOUN or word in _NOT_A_UNIT


def _count_use(body: str, start: int, end: int, money: bytearray) -> bool:
    """True when the number at ``body[start:end]`` counts things with its noun
    (see above). ``money`` marks the characters inside a money amount."""
    if money.find(1, start, end) != -1:
        return False  # "$2,500", "the build would be 25k"
    if body[end - 1:end] in ("k", "K"):
        return "," not in body[start:end]  # money_spans left it: a volume before its noun ("25k emails")
    tail = body[end:end + 120]
    if _RATE_USE_RE.match(tail):
        return False  # "400 a month", "400/mo", "400 per lead"
    lead_in = body[max(0, start - 60):start]
    if _COUNT_BEFORE_RE.search(lead_in):
        return True  # "a list of about 2,500"
    m = _NOUN_AFTER_RE.match(tail)
    if m and not _not_a_noun(m.group(1).lower()):
        head, nxt = m.group(1).lower(), (m.group(2) or "").lower()
        return head not in _PRICE_WORDS and head not in _TIME_WORDS and nxt not in _PRICE_NOUNS
    m = _COUNT_OF_RE.match(tail)
    if not m:
        return False  # no noun: "would be 2,500", "2,500 works", "2,500 for the setup"
    prep, head, nxt = m.group(1).lower(), m.group(2).lower(), (m.group(3) or "").lower()
    if prep == "of" and head in ("them", "those", "these"):
        return True  # "all 2,500 of them"
    return not (_not_a_noun(head) or head in _PRICE_WORDS or head in _TIME_WORDS or nxt in _PRICE_NOUNS
                or _PAID_BEFORE_RE.search(lead_in))  # "2,500 in the backlog", not "spend 400 on ads"


def _private_pricing_uses(body: str, priced: FrozenSet[str], stated: FrozenSet[str],
                          money: Sequence[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """(start, end, value) of every number in ``body`` from Lorenzo's private
    pricing lines (``priced``) that is not a count with its noun of a value
    the post or the room states (``stated``)."""
    if not priced:
        return []
    cover = bytearray(len(body) + 1)
    for s, e, _ in money:
        cover[s:e] = b"\x01" * (e - s)
    out = []  # type: List[Tuple[int, int, str]]
    for m in _BARE_NUM_RE.finditer(body):
        val = _canon(m.group(1), (m.group(2) or "").strip())
        if val not in priced:
            continue
        end = m.end() if m.group(2) else m.start(1) + len(m.group(1).rstrip(","))
        if val in stated and _count_use(body, m.start(), end, cover):
            continue
        out.append((m.start(), end, val))
    return out


FIGURE_KINDS = ("money", "percent", "hours", "reviews", "priced", "rated")


def private_figures(private_texts: Sequence[str] = (), public_texts: Sequence[str] = ()) -> Dict[str, FrozenSet[str]]:
    """The canonical values the private_fact check refuses, by kind (see
    FIGURE_KINDS), and "stated": the "priced" values the public texts
    (``public_texts(room)``) state in any form ("25k" is "25,000").

    Round 12: a money amount, hours figure or rate the private texts state
    stays private however the public texts state it (in a draft it is a
    price, a time estimate or a rate). A number of 100 or more on a private
    pricing line ("priced") is freed only where a text uses it as a count
    with its noun and "stated" holds it (``_private_pricing_uses``). A
    percentage or review figure is public when the public texts state it
    as the same kind (round 11)."""
    kinds = FIGURE_KINDS + ("stated",)
    return dict(zip(kinds, _private_figure_kinds(_joined(private_texts), _joined(public_texts))))


@functools.lru_cache(maxsize=32)
def _private_figure_kinds(private: str, public: str) -> Tuple[FrozenSet[str], ...]:
    """private_figures on joined texts. Cached: a draft asks for the same room
    once for its prompt and once per gate check."""
    if not private.strip():
        return tuple(frozenset() for _ in range(len(FIGURE_KINDS) + 1))
    pricing = "\n".join(private_pricing_lines(private))
    priced = frozenset(bare_numbers(pricing))
    stated = _stated(public, set(dollar_figures(public)), rate_values(public)) if priced and public.strip() else set()
    return (frozenset(dollar_figures(private)),
            frozenset(set(percent_figures(private)) - set(percent_figures(public))),
            frozenset(_hours(private)),
            frozenset(_reviews(private) - _reviews(public)),
            priced,
            frozenset(bare_numbers(pricing, minimum=1)),
            priced & frozenset(stated))


def private_figure_spans(text: str, private_texts: Sequence[str] = (), every_figure: bool = False,
                         public_texts: Sequence[str] = (),
                         figures: Optional[Dict[str, FrozenSet[str]]] = None) -> List[Tuple[int, int]]:
    """(start, end) of every figure in ``text`` that the private_fact check
    would refuse in a draft (``private_figures``; pass ``figures`` to reuse
    one): a money amount, hours figure or rate the private texts state, a
    number on a private pricing line unless ``text`` uses it as a count with
    its noun that the public texts state, and a percentage or review figure
    they do not state. With ``every_figure``, every money amount, percentage,
    multiplier, hours figure and "k" figure as well (a "25k emails" volume
    too, as before round 11), and nothing is freed. Spans are merged, a range
    ("$3,500-5,000") into one."""
    body = text or ""
    if figures is None:
        figures = private_figures(private_texts, () if every_figure else public_texts)
    if not body or not (every_figure or any(figures[k] for k in FIGURE_KINDS)):
        return []
    money, pct, hours, reviews = figures["money"], figures["percent"], figures["hours"], figures["reviews"]
    priced, rated = figures["priced"], figures["rated"]
    stated = frozenset() if every_figure else figures.get("stated", frozenset())
    mspans = money_spans(body)
    spans = [(s, e) for s, e, v in mspans if every_figure or v in money or v in priced]
    spans += [(s, e) for s, e, v in percent_spans(body) if every_figure or v in pct]
    if every_figure:
        spans += [(s, e) for s, e, _ in multiplier_spans(body)]
        spans += [(m.start(), m.end()) for m in _K_RE.finditer(body)]  # the questions still lose "25k emails"
    for m in _HOURS_RE.finditer(body):
        if every_figure or {_canon(r) for r in (m.group(1), m.group(2)) if r} & hours:
            spans.append((m.start(), m.end()))
    for m in _REVIEW_RE.finditer(body):
        raw = m.group(1) or m.group(2)
        if raw and _canon(raw) in reviews:
            spans.append((m.start(), m.end()))
    spans += [(s, e) for s, e, _ in _private_pricing_uses(body, priced, stated, mspans)]
    for m in _RATE_DIGITS_RE.finditer(body):
        if _canon(m.group(1)) in rated:
            spans.append((m.start(1), m.end(1)))
    for m in (_RATE_SPELLED_RE.finditer(body) if rated and _RATE_HINT_RE.search(body) else ()):
        val = _spelled_value(m.group(1))
        if val is not None and str(val) in rated:
            spans.append((m.start(1), m.end(1)))
    merged = []  # type: List[Tuple[int, int]]
    for s, e in sorted(spans):
        while e > s + 1 and body[e - 1] == ",":
            e -= 1  # "$1,500, about": the number pattern takes a trailing comma, the text keeps it
        if merged and (s <= merged[-1][1] or _RANGE_GAP_RE.match(body[merged[-1][1]:s])):
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def withhold_figures(text: str, private_texts: Sequence[str] = (), every_figure: bool = False,
                     public_texts: Sequence[str] = (), figures: Optional[Dict[str, FrozenSet[str]]] = None) -> str:
    """``text`` with each private_figure_spans span replaced by WITHHELD_FIGURE."""
    body = text or ""
    out, last = [], 0
    for s, e in private_figure_spans(body, private_texts, every_figure, public_texts, figures):
        out.append(body[last:s])
        out.append(WITHHELD_FIGURE)
        last = e
    out.append(body[last:])
    return "".join(out)


# ------------------------------------------------------------ offers
def _offer_sections(offers_text: str) -> Dict[str, str]:
    sections = {}  # type: Dict[str, str]
    current = ""
    for line in (offers_text or "").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1).strip().lower()
            sections.setdefault(current, "")
            continue
        sections[current] = sections.get(current, "") + line + "\n"
    return sections


def _figures(text: str) -> Set[str]:
    return ({"$" + v for v in dollar_figures(text)} | {v + "%" for v in percent_figures(text)} |
            {v + "x" for _, _, v in multiplier_spans(text)})


def offer_proof_lines(offers_text: str) -> List[Dict[str, Any]]:
    """Each Proof line with its figures and its distinctive terms."""
    rows = []  # type: List[Dict[str, Any]]
    for line in _offer_sections(offers_text).get("proof", "").splitlines():
        figs = _figures(line)
        if figs:
            rows.append({"line": line.strip(), "figures": figs, "terms": distinctive_terms(line)})
    return rows


def offer_pricing_figures(offers_text: str) -> Set[str]:
    return _figures(_offer_sections(offers_text).get("pricing", ""))


PROOF_CONTEXT_TERMS = 2
# Price words. "rate limit" is an API limit and a "quote request" (or quote
# photos, the quote form) is the project's own thing, not a price.
_QUOTE_NOUN = (r"(?:requests?|forms?|photos?|intake|flow|pipeline|bot|tool|page|builder|calculator|templates?|emails?|"
               r"texts?|messages?|process|stages?|steps?|status|system|queue|volume)")
_PRICE_BEFORE_STRONG_RE = re.compile(
    r"\b(?:rates?(?!\s+limits?\b)|cost|costs|price|prices|priced|pricing|budget|quote(?!\s+%s\b)|quoted|deposit|"
    r"charge|charges|charging|invoice|invoiced|fee|fees|pay|paid|total|estimate|ballpark|retainer|hourly)\b"
    r"[^.?!\n]{0,40}$" % _QUOTE_NOUN, re.I)
_PRICE_BEFORE_NEAR_RE = re.compile(r"\b(?:for|at|call it)\s*$", re.I)
_PRICE_AFTER_RE = re.compile(
    r"^\s*(?:fixed|flat|per\s+hour|an\s+hour|/\s?hr|/\s?h\b|/\s?hour|hourly|deposit|upfront|up\s+front|"
    r"total|budget|rate|fee|retainer|down|all[\s-]+in|all\s+told|altogether|for\s+(?:everything|the\s+(?:whole|full|"
    r"entire)\b))\b", re.I)
# Words that put a bare number in price position when nothing else follows
# it: "call it 2,400", "the first milestone would run 900", "I'd put the whole
# build at around 3,000", "it would come to about 2,800 all in".
_BARE_PRICE_NEAR_RE = re.compile(
    r"\b(?:for|at|at\s+(?:around|about|roughly|approximately)|call\s+it|runs?|would\s+run|will\s+run|should\s+run|"
    r"comes?\s+(?:to|in\s+at|out\s+to)|came\s+to|would\s+come\s+to|lands?\s+(?:at|around)|"
    r"put\s+(?:it|this|that|the\s+[\w-]+(?:\s+[\w-]+)?)\s+at(?:\s+(?:around|about|roughly))?|quote|quoted|charge|"
    r"charging|price\s+(?:it|this)\s+at|budget\s+of|cost\s+of|price\s+of)\s+"
    r"(?:about\s+|around\s+|roughly\s+|approximately\s+|just\s+|only\s+|under\s+|~\s*)?$", re.I)
_RATE_TAIL_RE = re.compile(r"^\s*(?:a|an|per|/)\s*(?:day|week|wk|month|mo|year|yr|hour|hr)\b|"
                           r"^\s*(?:monthly|weekly|yearly|annually|daily)\b", re.I)
# Round 12: price forms with no price word in _PRICE_BEFORE_STRONG_RE: "Setup
# would be 2,500", "2,500 for the setup" and a rate agreed to or tied to the
# setup or retainer ("400 a month works", "400 a month for the retainer").
# "The setup sends 400 a day" and "400 a month works out to 13 a day" stay
# volumes.
_SETUP_PRICE_BEFORE_RE = re.compile(
    r"\b(?:setup|set-up)\s+(?:(?:would|will|should|could|can|might)\s+)?(?:be|is|runs?|comes?\s+to|costs?|"
    r"lands?\s+at)\s+(?:about\s+|around\s+|roughly\s+|approximately\s+|just\s+|only\s+|under\s+|~\s*)?$", re.I)
_SETUP_PRICE_AFTER_RE = re.compile(
    r"^\s*(?:for\s+(?:the\s+|a\s+|your\s+)?)?(?:setup|set-up)\b|^\s*for\s+(?:the\s+|a\s+|your\s+)?retainer\b", re.I)
_RATE_AGREED_RE = re.compile(
    r"^\s*(?:(?:a|an|per|/)\s*(?:day|week|wk|month|mo|year|yr|hour|hr)|monthly|weekly|yearly|annually|daily)\b"
    r"[\s,]*(?:works\b(?!\s+out)|(?:would|will|should)\s+work\b|is\s+(?:fine|ok|okay|doable|great|perfect|fair|"
    r"reasonable|good)\b|sounds\s+(?:good|great|fine|fair|right|reasonable)\b|it\s+is\b|"
    r"for\s+(?:the\s+|a\s+|your\s+)?(?:setup|set-up|retainer)\b)", re.I)
# The word right after a number that is NOT a unit: "for 1,200 and ...",
# "for 1,200 if ...". A noun there ("for 300 leads", "3,000 contacts") makes
# the number a volume, not a price.
_NOT_A_UNIT = frozenset("""
and or but if so for to with all in on at by flat fixed total upfront up down per a an the this that which
including plus max tops ish then once when because since as is was would will could should can each every
excluding before after until unless while though although otherwise instead ok okay works work sounds sound
feels feel seems seem range ballpark roughly overall altogether together net gross including covers cover
""".split())
_UNIT_AFTER_RE = re.compile(r"^(?:\s*(?:-|to)\s*\d[\d,]*(?:\.\d+)?)?\s*([A-Za-z][\w'-]*)?")
_YEAR_RE = re.compile(r"^(?:19|20)\d\d$")
_RELATIVE_PRICE_RE = re.compile(
    r"\b(?:half|double|twice|triple|a\s+third\s+of|a\s+quarter\s+of|a\s+fraction\s+of|\d+\s*times)\s+"
    r"(?:the\s+|your\s+|their\s+|my\s+|what\s+you'?d\s+)?(?:price|cost|rate|fee|budget|quote)\b", re.I)
# A number of things per unit of work is a volume: "500 at a time", "100 per
# second", "40 per request".
_VOLUME_TAIL_RE = re.compile(
    r"^\s*(?:at\s+a\s+time|per\s+batch|in\s+(?:a|one|each)\s+batch|(?:a|an|per|/)\s*(?:second|sec|minute|min|"
    r"request|call|lead|message|text|email|user|seat|contact|record|row|item|order|run|batch|page|query|hit)s?)\b",
    re.I)
# "400 total showroom requests" and "300 down to 40" are volumes; "2,400
# total" and "1,000 down" are prices.
_AFTER_TOTAL_RE = re.compile(r"^\s*(?:total|all[\s-]+in|all\s+told|altogether|overall)\b", re.I)
_DOWN_TO_RE = re.compile(r"^\s*down\s+(?:to|from)\s+(?:about\s+|around\s+|roughly\s+|~\s*)?\d", re.I)
_BEFORE_CHARS = 200  # the price words sit at most ~50 characters before the number
# After a number: a time ("2:30", "3 pm"), a percentage, a multiplier or a phone number, never a price.
_NOT_PRICE_TAIL_RE = re.compile(r"^(?::\d|\s*(?:am|pm)\b|\s*%|x\b|[-.\s]\d{3}[-.\s]\d{4}\b)", re.I)


def _sentence_starts(body: str) -> Tuple[List[Tuple[int, int]], List[int]]:
    spans = _sentences(body)
    return spans, [s for s, _ in spans]


def _sentence_span(spans: List[Tuple[int, int]], starts: List[int], pos: int) -> Tuple[int, int]:
    """The (start, end) of the sentence holding ``pos``: one lookup, not a scan."""
    i = bisect.bisect_right(starts, pos) - 1
    if i >= 0 and spans[i][0] <= pos < spans[i][1]:
        return spans[i]
    return (0, 0)


def _price_context(body: str, start: int, end: int, sent_start: int = -1) -> bool:
    if sent_start < 0:
        spans, starts = _sentence_starts(body)
        sent_start = _sentence_span(spans, starts, start)[0]
    before = body[max(sent_start, start - _BEFORE_CHARS):start]
    return bool(_PRICE_BEFORE_STRONG_RE.search(before) or _PRICE_BEFORE_NEAR_RE.search(before)
                or _PRICE_AFTER_RE.match(body[end:end + 80]))


def _bare_price(body: str, m: Any, sent_start: int = -1) -> bool:
    """A bare number (100 or more, no currency) quoted as a price."""
    raw = m.group(1).replace(",", "")
    if "," not in m.group(1) and _YEAR_RE.match(raw):
        return False  # "in 2026"
    tail = body[m.end():m.end() + 120]
    if _NOT_PRICE_TAIL_RE.match(tail):
        return False  # a time, a percentage, a multiplier or a phone number
    if _VOLUME_TAIL_RE.match(tail) or _DOWN_TO_RE.match(tail):
        return False  # "500 at a time", "100 per second", "300 down to 40"
    if sent_start < 0:
        spans, starts = _sentence_starts(body)
        sent_start = _sentence_span(spans, starts, m.start())[0]
    before = body[max(sent_start, m.start() - _BEFORE_CHARS):m.start()]
    total = _AFTER_TOTAL_RE.match(tail)
    if total:
        # "400 total showroom requests" counts things; "2,400 total" is a price
        noun = _UNIT_AFTER_RE.match(tail[total.end():]).group(1)
        return not (noun and noun.lower() not in _NOT_A_UNIT)
    if _PRICE_AFTER_RE.match(tail) or _SETUP_PRICE_AFTER_RE.match(tail):
        return True
    unit = _UNIT_AFTER_RE.match(tail).group(1)
    if unit and unit.lower() not in _NOT_A_UNIT:
        return False  # "for 300 leads", "3,000 contacts", "300-1200 leads"
    strong = bool(_PRICE_BEFORE_STRONG_RE.search(before) or _SETUP_PRICE_BEFORE_RE.search(before))
    near = _BARE_PRICE_NEAR_RE.search(before)
    if _RATE_TAIL_RE.match(tail):
        # "at 150 a week" is a volume as often as a price; "for 1,200 a month" is a price,
        # and so is a rate agreed to ("400 a month works").
        return strong or bool(near and not re.search(r"\bat\s*$", before, re.I)) or bool(_RATE_AGREED_RE.match(tail))
    return strong or bool(near)


def figure_problems(body: str, offers_text: str) -> List[str]:
    """Figures the draft may not state. A Pricing-section figure is fine
    anywhere. A Proof figure is fine only inside its proof statement (the
    sentence shares PROOF_CONTEXT_TERMS distinctive terms with that proof line)
    and never next to price words. Anything else is refused."""
    pricing = offer_pricing_figures(offers_text)
    proofs = offer_proof_lines(offers_text)
    spans = ([(s, e, "$" + v) for s, e, v in money_spans(body)] +
             [(s, e, v + "%") for s, e, v in percent_spans(body)] +
             [(s, e, v + "x") for s, e, v in multiplier_spans(body)])
    sentences, starts = _sentence_starts(body)
    covered = bytearray(len(body) + 1)  # characters inside a $, % or x figure
    for s, e, _ in spans:
        covered[s:e] = b"\x01" * (e - s)
    bad = []  # type: List[str]
    # A bare number of 100 or more quoted as a price ("a 3500 budget", "my
    # rate is 3,500", "for 3500.", "call it 2,400", "would run 900"). A noun
    # right after it makes it a volume ("for 300 leads", "3,000 contacts").
    for m in _BARE_NUM_RE.finditer(body):
        if covered[m.start()]:
            continue
        val = _canon(m.group(1), (m.group(2) or "").strip())
        try:
            big = val is not None and float(val) >= 100
        except ValueError:
            big = False
        if not big or m.group(2):
            continue
        sent_start = _sentence_span(sentences, starts, m.start())[0]
        if _bare_price(body, m, sent_start) and val not in {f.lstrip("$") for f in pricing}:
            bad.append(m.group(0).strip() + " (as a price)")
    rel = _RELATIVE_PRICE_RE.search(body)
    if rel:
        bad.append("%r (a relative price)" % rel.group(0))
    terms_of = {}  # type: Dict[Tuple[int, int], Set[str]]
    for start, end, fig in sorted(spans):
        if fig in pricing:
            continue
        owners = [p for p in proofs if fig in p["figures"]]
        if not owners:
            bad.append(fig)
            continue
        sentence = _sentence_span(sentences, starts, start)
        if _price_context(body, start, end, sentence[0]):
            bad.append(fig + " (as a price)")
            continue
        if sentence not in terms_of:
            terms_of[sentence] = distinctive_terms(body[sentence[0]:sentence[1]] if sentence[1] else body)
        if not any(len(terms_of[sentence] & p["terms"]) >= PROOF_CONTEXT_TERMS for p in owners):
            bad.append(fig + " (outside its proof statement)")
    return bad


# ------------------------------------------------------------ agreeing to the client's price
# Round 13 (probe p49): after "Would 2,000 work for the whole build?", "Sure,
# 2,000 works." passed. A bare number with no price word next to it is not a
# quote to figure_problems, and with no private notes nothing else read it.
# Agreeing to a price is Lorenzo's call, so a draft that takes up a number the
# client stated as a price or budget in an agreeing form is refused, private
# notes or not (agrees_to_client_price).
#
# The client states N as a price when the job post, the title or a client
# message has it as money (a currency marker, "2k"; money_spans), with a price
# word near it in its sentence, in a price position the bare-price rule knows
# ("for 2,000", "call it 2,000"), or in a question that proposes it ("would
# 2,000 work?", "how about 2,000?", "is 2,000 ok?"). A number the client uses
# as a count with its noun ("2,000 contacts", "2,000 emails a week";
# _count_use) is never the client's price, whatever else the sentence says.
_CLIENT_PRICE_WORD_RE = re.compile(
    r"\b(?:prices?|priced|pricing|budget(?:s|ed)?|pay|pays|paying|paid|payment|rates?(?!\s+limits?\b)|costs?|"
    r"quotes?(?!\s+%s\b)|quoted|fixed|flat|fees?|dollars?|bucks|usd|spend|invest|"
    r"work\s+for|do\s+(?:it|this|that|the\s+[\w-]+)\s+for)\b" % _QUOTE_NOUN, re.I)
_CLIENT_PRICE_WINDOW = 80  # characters either side of the number, inside its sentence
_PROPOSE_BEFORE_RE = re.compile(
    r"\b(?:how\s+about|what\s+about|would|could|will|does|do|is|say|at|for)\s+"
    r"(?:(?:about|around|roughly|maybe|just|only)\s+)?$", re.I)
_PROPOSE_AFTER_RE = re.compile(
    r"^\s*(?:\?|(?:work|works|do|ok|okay|fine|sound|sounds)\b|be\s+(?:ok|okay|fine|good|enough)\b)", re.I)
# The draft side. After the number: "works", "would work", "is fine / good /
# ok / okay", "sounds good", "it is", "for the whole build works", "for
# everything / for all of it works", "is fine for
# the build", "deal", and (round 14) "should / would / will cover it", "sounds
# about right", "is about right", "is reasonable / doable / workable". Only
# "works out to" is arithmetic ("2,000 works out fine" agrees), and "does 2,000
# work?" asks rather than agrees.
_AGREE_AFTER_RE = re.compile(
    r"^[\s,]*(?:(?:for|on)\s+(?:(?:the|a|your|this|that|my)\s+)?(?:(?:whole|full|entire|complete)\s+)?"
    r"(?:build|setup|set-up|project|thing|job|scope|work|package|engagement|lot|bot|system|site|website)\s+|"
    r"for\s+(?:everything|all\s+of\s+it)\s+)?"
    r"(?:(?:totally|definitely|absolutely|really|honestly|also|still)\s+)?"
    r"(?:works\b(?!\s+out\s+to\b)|(?:should|would|will|can|could)\s+work\b(?!\s+out\s+to\b)|"
    r"is\s+(?:(?:totally|perfectly|completely|definitely|absolutely|really)\s+)?(?:fine|good|ok|okay|great|perfect|"
    r"fair|doable|reasonable|workable|acceptable|agreed|a\s+deal)\b|"
    r"'s\s+(?:fine|good|ok|okay|great|perfect|fair|doable|a\s+deal)\b|"
    r"sounds?\s+(?:good|great|fine|fair|right|about\s+right|reasonable|ok|okay|perfect)\b|"
    r"(?:is|'s)\s+(?:just\s+)?about\s+right\b|"
    r"(?:(?:should|would|will|can|could)\s+(?:easily\s+)?cover|covers)\s+(?:it|this|that|everything)\b|"
    r"it\s+is\b|(?:it's\s+)?a\s+deal\b|deal\b)",
    re.I)
# Before the number: "happy with", "fine with", "ok with", "can do (it for)",
# "deal at", "agree to", "accept", "let's go with", "lock in at", "yes to".
# Round 14: "(I can) work with".
_AGREE_BEFORE_RE = re.compile(
    r"\b(?:(?:happy|glad|fine|ok|okay|good|content|comfortable|cool|set)\s+with|"
    r"(?:happy|glad)\s+to\s+(?:do(?:\s+(?:it|this|that|the\s+[\w-]+))?\s+(?:for|at)|go\s+with|take|accept|lock\s+in)|"
    r"work\s+with|"
    r"(?:can|could|will|i'll|i'd)\s+do(?:\s+(?:it|this|that|the\s+[\w-]+))?(?:\s+(?:for|at))?|"
    r"deal\s+(?:at|for)|agreed?\s+(?:to|on|at)|accept(?:s|ed|ing)?|take\s+it\s+(?:for|at)|"
    r"let's\s+(?:do|go\s+with|say|call\s+it|lock\s+in|settle\s+on|stick\s+with)|go(?:ing)?\s+with|stick\s+with|"
    r"settle\s+(?:on|at|for)|lock(?:ed)?(?:\s+it)?\s+in(?:\s+at)?|done\s+(?:at|for)|yes\s+to|sure\s+to)"
    r"\s+(?:(?:the|a|your)\s+)?(?:(?:about|around|roughly)\s+)?$", re.I)
# "Sure, 2,000." / "Great, 2,000 then."
_YES_BEFORE_RE = re.compile(
    r"(?:^|[^\w'])(?:yes|yep|yeah|sure|ok|okay|deal|agreed|perfect|great|done)[,:]?\s+(?:to\s+)?$", re.I)
_BARE_END_RE = re.compile(r"^\s*(?:[.;]|$|,?\s*(?:then|deal|done|agreed)\b)", re.I)
# Round 15 (probe p52): "1,500 is our max." stated no price to
# client_price_values, although DESIGN.md lists the form. "N is our max /
# maximum / ceiling / cap", "our max is N" and "a max / maximum of N" state N
# as a price; a count with its noun ("our max is 20 domains") is still
# skipped by _count_use before these are read.
_CLIENT_MAX_AFTER_RE = re.compile(
    r"^\s*(?:is|would\s+be|will\s+be|'s)\s+(?:our|my|the)\s+(?:(?:absolute|hard|total|top)\s+)?"
    r"(?:max(?:imum)?|ceiling|cap)\b", re.I)
_CLIENT_MAX_BEFORE_RE = re.compile(
    r"\b(?:max(?:imum)?|ceiling|cap)\s+(?:is|of|would\s+be|will\s+be|at|:)\s*"
    r"(?:(?:about|around|roughly|approximately|only|just)\s+)?$", re.I)


def _number_uses(body: str) -> Tuple[List[Tuple[int, int, str, Any]], bytearray]:
    """(start, end, canonical value, bare match or None) of every money amount
    (money_spans) and every bare number outside one, and the money cover. A
    "k" figure money_spans left alone is a volume ("25k emails") and is
    skipped, as is a trailing comma."""
    money = money_spans(body)
    cover = bytearray(len(body) + 1)
    out = [(s, e, v, None) for s, e, v in money]  # type: List[Tuple[int, int, str, Any]]
    for s, e, _ in money:
        cover[s:e] = b"\x01" * (e - s)
    for m in _BARE_NUM_RE.finditer(body):
        if cover[m.start()] or m.group(2):
            continue
        val = _canon(m.group(1))
        if val is not None:
            out.append((m.start(), m.start(1) + len(m.group(1).rstrip(",")), val, m))
    return sorted(out, key=lambda t: t[:3]), cover


# Round 14: the client text read for prices is capped, like public_texts:
# every bare number costs a few regex searches, and 190KB of phone numbers
# took 1.47s. client_price_source puts the title and the post first, then the
# client's messages newest first, this many characters in all (a real room is
# far smaller; an older price past the cap is simply not read, and the
# figureless check below only reads the latest client message anyway).
CLIENT_PRICE_CHARS = 20000


def client_price_source(room: Optional[Dict[str, Any]]) -> str:
    """The job post, the job title and the client-side messages newest first,
    decoded, CLIENT_PRICE_CHARS in all: the text ``client_price_values``
    reads for a room."""
    room = room if isinstance(room, dict) else {}
    job = room.get("job")
    texts = [job.get("post") if isinstance(job, dict) else None, room.get("job_title")]
    texts += [m.get("text") for m in reversed(room.get("messages") or [])
              if isinstance(m, dict) and m.get("side") == "client"]
    out, budget = [], CLIENT_PRICE_CHARS
    for text in texts:
        if budget <= 0:
            break
        if isinstance(text, str) and text.strip():
            text = decode_escapes(text[:budget])
            out.append(text)
            budget -= len(text) + 1
    return "\n".join(out)[:CLIENT_PRICE_CHARS]


def client_price_spans(client_text: str) -> List[Tuple[int, int, str]]:
    """(start, end, canonical value) of every figure ``client_text`` states
    as a price or budget (see above), in text order: every money amount
    ("$2,000", "EUR 1,000", "2k", "five grand") and every bare number of 100
    or more in a price position ("Would 1,200 work?", "Our budget is 1500").
    Offsets are into ``normalise(client_text)``, which keeps every offset
    (each smart quote becomes one ASCII quote)."""
    body = normalise(client_text or "")[:CLIENT_PRICE_CHARS]
    if not body.strip():
        return []
    spans, starts = _sentence_starts(body)
    out = []  # type: List[Tuple[int, int, str]]
    uses, cover = _number_uses(body)
    for s, e, val, m in uses:
        if m is None:
            out.append((s, e, val))  # "$2,000", "2k", "2,000 dollars"
            continue
        if float(val) < 100:
            continue  # a year is not skipped: "would 2000 work?" is a price, and "in 2026" never agrees to one
        if _NOT_PRICE_TAIL_RE.match(body[e:e + 40]) or _count_use(body, s, e, cover):
            continue  # a time, a phone number, "2,000 contacts", "2,000 emails a week"
        sent_start, sent_end = _sentence_span(spans, starts, s)
        sent_end = sent_end or len(body)
        near = body[max(sent_start, s - _CLIENT_PRICE_WINDOW):min(sent_end, e + _CLIENT_PRICE_WINDOW)]
        before = body[max(sent_start, s - _CLIENT_PRICE_WINDOW):s]
        question = "?" in body[sent_start:sent_end]
        if (_CLIENT_PRICE_WORD_RE.search(near) or _bare_price(body, m, sent_start)
                or _CLIENT_MAX_AFTER_RE.match(body[e:e + 40]) or _CLIENT_MAX_BEFORE_RE.search(before)
                or (question and (_PROPOSE_BEFORE_RE.search(before) or _PROPOSE_AFTER_RE.match(body[e:e + 40])))):
            out.append((s, e, val))
    return out


@functools.lru_cache(maxsize=32)
def client_price_values(client_text: str) -> FrozenSet[str]:
    """Canonical values the client states as a price or budget in
    ``client_text`` (``client_source_text(room)``); see above."""
    return frozenset(v for _, _, v in client_price_spans(client_text))


def client_price_agreements(body: str, room: Optional[Dict[str, Any]]) -> List[str]:
    """The figures in ``body`` that agree to or accept a price the client
    stated (``client_price_values``): "2,000 works", "$2,000 works", "2k is
    fine", "happy with 2,000", "2,000 it is", "can do 2,000", "deal at 2,000",
    "Sure, 2,000.". A number the draft uses as a count with its noun ("the
    2,000 contacts") never agrees to anything, and a number the client used
    only as a volume is not a price here: after "2,000 emails a week", "2,000
    works" talks about volume."""
    prices = client_price_values(client_price_source(room))
    if not prices or not body:
        return []
    spans, starts = _sentence_starts(body)
    uses, cover = _number_uses(body)
    out = []  # type: List[str]
    for s, e, val, m in uses:
        if val not in prices or (m is not None and _count_use(body, s, e, cover)):
            continue
        sent_start = _sentence_span(spans, starts, s)[0]
        before, after = body[max(sent_start, s - 80):s], body[e:e + 80]
        if (_AGREE_AFTER_RE.match(after) or _AGREE_BEFORE_RE.search(before)
                or (_YES_BEFORE_RE.search(before) and _BARE_END_RE.match(after))):
            out.append(body[s:e].strip())
    return out


# ------------------------------------------------------------ agreeing without the figure
# Round 14: after "Would 2,000 work for the whole build?", "Sure, that works."
# and "That budget works for me." passed: no number, so nothing above read
# them. Same code (agrees_to_client_price), and deliberately narrow.
#
# Exact trigger, all three must hold:
#  1. The client's LATEST message proposes a price: it holds a value from
#     client_price_values (read over client_price_source) that is not a count
#     with its noun, either in a question sentence where the number sits in a
#     proposing position ("would 2,000 work", "how about 2,000", "can you do it
#     for 2,000", "is 2,000 ok", "2,000?") or in a statement that offers it
#     ("our budget is 2,000", "budget of 2,000", "I can pay 2,000", "we can do
#     2,000", "we can offer / spend 2,000", "2,000 is our budget / max").
#  2. The draft's OPENING sentence (a greeting or thanks-only sentence such as
#     "Hi Sam," or "Thanks for the quick reply!" is skipped) agrees with no
#     figure: after optional "yes / sure / ok / great / perfect / absolutely,",
#     it is "that / this / it / your budget / the price / that number" plus
#     "works", "would / should / will work" (not "works out to", which is
#     arithmetic; "works out fine / great / well" agrees), "is fine / good / ok / fair /
#     reasonable / doable / workable / acceptable / about right", "sounds good /
#     fair / about right", "should cover it"; or "sounds good", "deal",
#     "agreed", "done", "(I'm) happy / fine / ok / comfortable with that / your
#     budget / the price", "(I) can work with that / your budget", "let's do
#     it.", or a bare "yes." / "sure." / "sounds good." sentence.
#  3. That opening sentence names no time (a weekday, today, tomorrow, next
#     week, morning, "3pm", noon), and no sentence of the draft defers the price
#     to Lorenzo ("I'll confirm pricing with you on a call", "let me come back
#     to you on the number", "we can discuss the budget on a call").
# A draft that answers a time ("Thursday works for a quick call.") or a count
# or scope ("Yes, I can do 20 domains.") has another subject, so it never
# matches 2; a draft that does not respond to the price never matches 2.
_PROPOSE_STATEMENT_BEFORE_RE = re.compile(
    r"(?:\b(?:budget|price|rate|offer|max(?:imum)?|ceiling|limit|cap)\s*(?:is|was|would\s+be|will\s+be|of|at|:|=)|"
    r"\b(?:i|we)\s+(?:(?:can|could|would|will|'d|'ll)\s+)?(?:(?:only|probably|happily)\s+)?"
    r"(?:pay|offer|spend|afford|do|go(?:\s+up)?\s+to)|"
    r"\b(?:willing|able|looking|happy|prepared)\s+to\s+(?:pay|spend|offer|invest))"
    r"\s*(?:(?:about|around|roughly|approximately|up\s+to|only|just|a\s+max(?:imum)?\s+of)\s+)?$", re.I)
_PROPOSE_STATEMENT_AFTER_RE = re.compile(
    r"^\s*(?:is|would\s+be|will\s+be)\s+(?:our|my|the)\s+(?:(?:total|whole|max(?:imum)?|full)\s+)?"
    r"(?:budget|max(?:imum)?|limit|ceiling|cap|offer|price)\b", re.I)
_OPENING_SKIP_RE = re.compile(
    r"^\s*(?:(?:hi|hey|hello|dear|good\s+(?:morning|afternoon|evening))\b[^.!?\n]{0,40}|"
    r"(?:thanks|thank\s+you|thx|appreciate\s+it)\b[^.!?\n]{0,60})[,.!:]?\s*$", re.I)
_YES_WORD = r"(?:yes|yep|yeah|sure\s+thing|sure|ok|okay|great|perfect|absolutely|definitely|of\s+course|cool|awesome|sounds\s+good)"
_AGREE_SUBJECT = (r"(?:that|this|it|(?:your|the|that|this)\s+(?:budget|price|number|figure|rate|amount|offer|quote|"
                  r"fee|pricing))")
_AGREE_PREDICATE = (
    r"(?:works\b(?!\s+out\s+to\b)|(?:would|should|will|can|could)\s+(?:definitely\s+)?work\b(?!\s+out\s+to\b)|"
    r"(?:is|'s)\s+(?:(?:totally|perfectly|completely|definitely|absolutely|really|more\s+than)\s+)?"
    r"(?:fine|good|ok|okay|great|perfect|fair|reasonable|doable|workable|acceptable|agreed|a\s+deal|"
    r"(?:just\s+)?about\s+right|enough)|"
    r"sounds\s+(?:good|great|fine|fair|right|about\s+right|reasonable|ok|okay|perfect)|"
    r"(?:(?:should|would|will|can|could)\s+(?:easily\s+)?cover|covers)\s+(?:it|this|that|everything))\b")
_FIGURELESS_AGREE_RE = re.compile(
    r"^\s*(?:" + _YES_WORD + r"[,!.:]?\s+)*(?:"
    r"(?:i\s+think\s+)?" + _AGREE_SUBJECT + r"(?:\s+|(?='s\b))" + _AGREE_PREDICATE + r"|"
    r"sounds\s+(?:good|great|fine|fair|about\s+right|reasonable|perfect)\b|"
    r"(?:it's\s+a\s+)?deal\b|agreed\b|done\b|"
    r"(?:(?:i'm|i\s+am|we're|we\s+are)\s+)?(?:(?:totally|very|more\s+than)\s+)?"
    r"(?:happy|fine|good|ok|okay|comfortable|glad|cool)\s+with\s+" + _AGREE_SUBJECT + r"\b|"
    r"(?:(?:i|we)\s+)?(?:can|could)\s+(?:definitely\s+)?work\s+with\s+" + _AGREE_SUBJECT + r"\b|"
    r"let's\s+do\s+it\s*[.!]?\s*$|"
    r"works(?:\s+for\s+(?:me|us))?\s*[.!]*\s*$|"
    r"" + _YES_WORD + r"\s*[.!]*\s*$)", re.I)
_TIME_WORD = (r"(?:(?:mon|tues|wednes|thurs|fri|satur|sun)days?\b|(?:today|tonight|tomorrow|morning|afternoon|"
              r"evening|noon|midday|weekend)\b|(?:next|this)\s+week\b|\d{1,2}(?::\d{2})?\s*(?:am|pm)\b)")
# Round 15 (probe p52): "Sure, that works, talk Thursday." passed because the
# opening sentence named a time anywhere. The time exempts the sentence only
# when it is what the agreement refers to: right after the agreeing words,
# "(that works) for / on / at Thursday", "(that works) for me on Thursday at
# 2pm", "(that works) for a quick call on Thursday". A time in a separate
# clause ("..., talk Thursday.") does not. A sentence whose subject is the
# time ("Thursday works for a quick call.", "Monday works for me to start.")
# never matches _FIGURELESS_AGREE_RE, so it needs no exemption.
_TIME_TARGET_RE = re.compile(
    r"^\s*(?:for|on|at)\s+(?:(?:me|us)\s+(?:(?:for|on|at)\s+)?)?"
    r"(?:(?:a|the|our)\s+(?:(?:quick|short|brief)\s+)?(?:call|chat|meeting)\s+(?:(?:on|at)\s+)?)?"
    r"(?:(?:the|this|next)\s+)?" + _TIME_WORD, re.I)
_PRICE_NOUN = r"(?:pric(?:e|es|ing)|numbers?|figures?|budget|costs?|rates?|quotes?|fees?)"
_DEFER_PRICE_RE = re.compile(
    r"\b(?:confirm|discuss|talk\s+(?:through|about)|go\s+(?:over|through)|come\s+back\s+to\s+you|"
    r"get\s+back\s+to\s+you|circle\s+back|finali[sz]e|sort\s+out|work\s+out|firm\s+up|nail\s+down|"
    r"lock\s+down|run\s+through|review|look\s+(?:at|over))\b[^.!?\n]{0,60}\b" + _PRICE_NOUN + r"\b|"
    r"\b" + _PRICE_NOUN + r"\b[^.!?\n]{0,60}\b(?:on|over|during)\s+(?:a|the|our)\s+(?:quick\s+|short\s+)?call\b",
    re.I)


def _latest_client_text(room: Optional[Dict[str, Any]]) -> str:
    for msg in reversed((room if isinstance(room, dict) else {}).get("messages") or []):
        if isinstance(msg, dict) and msg.get("side") == "client" and isinstance(msg.get("text"), str) \
                and msg.get("text").strip():
            return normalise(decode_escapes(msg.get("text")))[:CLIENT_PRICE_CHARS]
    return ""


def _proposal_in(text: str, prices: FrozenSet[str]) -> Optional[str]:
    """The figure ``text`` (one client message, normalised) proposes as a
    price (trigger 1 above), or None. ``prices`` is client_price_values over
    the room's client text."""
    if not text.strip() or not prices:
        return None
    spans, starts = _sentence_starts(text)
    uses, cover = _number_uses(text)
    for s, e, val, m in uses:
        if val not in prices or (m is not None and _count_use(text, s, e, cover)):
            continue
        sent_start, sent_end = _sentence_span(spans, starts, s)
        sent_end = sent_end or len(text)
        before, after = text[max(sent_start, s - _CLIENT_PRICE_WINDOW):s], text[e:e + 40]
        if "?" in text[sent_start:sent_end] and (_PROPOSE_BEFORE_RE.search(before) or _PROPOSE_AFTER_RE.match(after)):
            return text[s:e].strip()
        if _PROPOSE_STATEMENT_BEFORE_RE.search(before) or _PROPOSE_STATEMENT_AFTER_RE.match(after):
            return text[s:e].strip()
    return None


def client_price_proposal(room: Optional[Dict[str, Any]]) -> Optional[str]:
    """The figure the client's latest message proposes as a price (trigger 1
    above), or None."""
    latest = _latest_client_text(room)
    if not latest.strip():
        return None
    return _proposal_in(latest, client_price_values(client_price_source(room)))


def unanswered_price_proposal(room: Optional[Dict[str, Any]]) -> Optional[str]:
    """The figure any of the client's unanswered messages proposes as a
    price (trigger 1 above, read message by message, newest first), or None.
    A framework reply reads them all: "Would $750 work?" followed by "Also,
    how long would it take?" still proposes $750."""
    prices = client_price_values(client_price_source(room))
    if not prices:
        return None
    for msg in reversed(unanswered_client_messages(room)):
        text = msg.get("text")
        if isinstance(text, str) and text.strip():
            found = _proposal_in(normalise(decode_escapes(text))[:CLIENT_PRICE_CHARS], prices)
            if found:
                return found
    return None


def figureless_price_agreement(body: str, room: Optional[Dict[str, Any]]) -> Optional[str]:
    """The opening sentence of ``body`` when it agrees, without naming the
    figure, to a price the client's latest message proposes (see above), or
    None. A draft that defers the price anywhere passes. A framework reply
    is read by framework_price_agreement instead, with no deferral escape."""
    if not body or _DEFER_PRICE_RE.search(body):
        return None
    opening = ""
    for s, e in _sentences(body[:2000]):
        sentence = body[s:e].strip()
        if sentence and not _OPENING_SKIP_RE.match(sentence):
            opening = sentence
            break
    agree = _FIGURELESS_AGREE_RE.match(opening) if opening else None
    if not agree or _TIME_TARGET_RE.match(opening[agree.end():]):
        return None
    if client_price_proposal(room) is None:
        return None
    return opening


# Round 16: the figureless check above reads only the opening sentence, and a
# time right after the agreement exempts it, so "That works for Thursday at
# 2pm, and the price is fine." and "Thursday works for a quick call. Your
# budget works for me too." passed. Same code (agrees_to_client_price).
#
# Exact trigger, all must hold:
#  1. The client's latest message proposes a price (client_price_proposal).
#  2. Some clause of the draft, in ANY sentence that is not a question, starts
#     (at the sentence start, or after "," ";" ":" or a dash, then optional
#     "and / but / so / also / plus / then", yes-words and "I think") with the
#     price as its subject: "the / your / that price", "the / your / that
#     budget", "the / your / that number", "the / your rate", "the / your /
#     that fee", "the / your / that figure", "the amount"; directly followed
#     by an agreeing predicate: "works" ("works for me / us"), "would /
#     should / will work" (never followed by "out to": "the budget works out
#     to about 100 a day" is arithmetic, while "works out fine / great / well"
#     agrees), "is / 's
#     (totally / perfectly / ...) fine / good / ok / okay / fair / reasonable /
#     doable / workable / acceptable / about right / enough / no problem",
#     "sounds good / fine / about right", "should / would / will cover it".
#  3. No sentence of the draft defers the price (_DEFER_PRICE_RE).
# The time exemption never applies here. A negation ("the price is not
# fine"), a question ("Does that budget work for you?") and a price that is
# not the subject of the agreement ("the price depends on scope", "I'll send
# the price after the call") never match.
_PRICE_SUBJECT = (r"(?:(?:the|your|that)\s+(?:price|budget|number|figure|fee)|(?:the|your)\s+rate|"
                  r"the\s+amount)")
_PRICE_SUBJECT_PREDICATE = (
    r"(?:works\b(?!\s+out\s+to\b)|(?:would|should|will)\s+work\b(?!\s+out\s+to\b)|"
    r"(?:is|'s)\s+(?:(?:totally|perfectly|completely|definitely|absolutely|really)\s+)?"
    r"(?:fine|good|ok|okay|fair|reasonable|doable|workable|acceptable|about\s+right|enough|no\s+problem)|"
    r"sounds\s+(?:good|fine|about\s+right)|"
    r"(?:should|would|will)\s+cover\s+it)\b")
_PRICE_SUBJECT_AGREE_RE = re.compile(
    r"(?:^|[,;:]|\s[-\u2013\u2014])\s*(?:(?:and|but|so|also|plus|then)\s+)?"
    r"(?:" + _YES_WORD + r"[,!.:]?\s+)*(?:i\s+think\s+)?(?:also\s+)?"
    + _PRICE_SUBJECT + r"(?:\s+|(?='s\b))" + _PRICE_SUBJECT_PREDICATE, re.I)


def price_subject_agreement(body: str, room: Optional[Dict[str, Any]]) -> Optional[str]:
    """The first sentence of ``body`` with a clause that has the price as its
    subject in an agreeing form ("the price is fine", "your budget works for
    me"), when the client's latest message proposes a price (see above), or
    None. A draft that defers the price anywhere passes; questions pass."""
    if not body or _DEFER_PRICE_RE.search(body):
        return None
    hit = None
    for s, e in _sentences(body[:5000]):
        sentence = body[s:e].strip()
        if not sentence or "?" in sentence:
            continue
        if _PRICE_SUBJECT_AGREE_RE.search(sentence):
            hit = sentence
            break
    if hit is None or client_price_proposal(room) is None:
        return None
    return hit


# ------------------------------------------------------------ agreeing in a framework reply
# Lorenzo, 2026-10-06: a framework reply (draft.is_framework_reply) answers a
# client who asked questions, often after naming a figure ("Would $750 work
# for the showroom intake?"). It always defers the exact price to the call,
# so a deferral frees nothing there, with or without a range, and it must
# never agree to their figure anywhere in the message, not only in the
# opening sentence. In a framework reply this check takes the place of the
# opening-sentence and price-subject checks above (it reads every sentence
# with their forms and more, and has no deferral escape); the number check
# (client_price_agreements) still runs. Same code (agrees_to_client_price).
#
# Trigger, all must hold:
#  1. One of the client's unanswered messages proposes a price
#     (unanswered_price_proposal).
#  2. A sentence of the draft agrees, either
#     a. as a whole: yes-words only ("Sure.", "Yes, absolutely.");
#     b. anywhere in it: the work done for, at or within their figure ("I can
#        do it for your budget", "I can do the showroom intake at your
#        budget", "I can do the showroom intake for that.", "work within your
#        budget", "I can work with that."); or
#     c. at the start of one of its clauses (the sentence start, after "," ";"
#        ":" "(" or a spaced dash, before a capitalised word that follows a
#        lower-case one, after "and / but / so / also / plus / then",
#        yes-words and "I think"): "that / this / it / your budget / the
#        price / that number" plus "works", "would work", "will be fine",
#        "is fine / good / doable / fair / ...", "sounds good", "should cover
#        it"; "deal", "agreed", "done", "fair enough", "works for me", "let's
#        do it", "doable", "no problem", "sounds good"; "(I'm) happy / fine /
#        ok with that / your budget"; "(I) can do / work with / work within /
#        go with / accept / match / meet / stick to / stay within that / your
#        budget"; "(I can) make that work"; "(I'm) happy / able / willing to
#        work within / go with / accept / do it for that / your budget".
#     A clause-start agreement does not count when what follows it is a time
#     ("I can do that by Friday", "it's doable in about 2 weeks", "that works
#     for Thursday at 2pm"), a tool ("it works with HubSpot Starter", "I can
#     do that in Zapier"), unless that is their figure again ("that works
#     with your budget"), or an explanation ("this works by tagging each
#     request", "it works the same way"). "that" and "this" count only as
#     pronouns ("I can meet that deadline" passes). A real question never
#     starts with the agreement, so it passes ("Does that work for you?",
#     "Would that budget work?"); "Sure, that works, does Thursday suit
#     you?" does not.
_FW_PRICE_REF = (r"(?:(?:your|the|that|this)\s+(?:budget|price|pricing|number|figure|amount|offer|quote|rate|fee)s?|"
                 r"what\s+you\s+(?:mentioned|offered|proposed|suggested|named))")
_FW_PRICE_REF_RE = re.compile(r"\b" + _FW_PRICE_REF + r"\b", re.I)
# "that" / "this" / "it" as a pronoun: the clause ends, or a function word follows.
_FW_REF_END = (r"(?:" + _FW_PRICE_REF + r"|(?:that|this|it)(?=\s*(?:[.,;:!?)]|$)|\s+(?:for|at|in|too|as|then|now|"
               r"easily|no|happily|gladly|on|with|within|under|by|before|from|starting|this|next|tomorrow|today|"
               r"completely|fully|perfectly|right)\b))")
_FW_P_WORK = (r"(?:works\b(?!\s+out\s+to\b)|(?:'ll|would|should|will|can|could)\s+(?:definitely\s+|totally\s+|"
              r"easily\s+)?work\b(?!\s+out\s+to\b))")
_FW_P_BE = (
    r"(?:(?:'ll|would|should|will|can|could)\s+(?:definitely\s+|totally\s+|easily\s+)?be\s+(?:fine|good|ok|okay|great|"
    r"perfect|doable|workable|no\s+problem)\b|"
    r"(?:is|'s)\s+(?:(?:totally|perfectly|completely|definitely|absolutely|really|more\s+than|very|quite|pretty)\s+)?"
    r"(?:fine|good|ok|okay|great|perfect|fair|reasonable|doable|workable|acceptable|agreed|a\s+deal|"
    r"(?:just\s+)?about\s+right|enough|no\s+problem|manageable|feasible|realistic|achievable)\b|"
    r"sounds\s+(?:good|great|fine|fair|right|about\s+right|reasonable|ok|okay|perfect|doable)\b|"
    r"(?:(?:should|would|will|can|could)\s+(?:easily\s+)?cover|covers)\s+(?:it|this|that|everything)\b)")
_FW_P_TAIL = r"(?!\s+(?:to\s+(?:hear|know|see|read)|news|questions?|points?|ideas?|catch)\b)"
_FW_ADV = r"(?:also\s+|still\s+|honestly\s+|definitely\s+)?"
_FW_MODAL = r"(?:i\s+)?(?:(?:can|could|will|would|'ll|'d)\s+)?(?:(?:definitely|easily|certainly|absolutely|happily|gladly|still|also)\s+)?"
_FW_YES = r"(?:yes|yep|yeah|sure\s+thing|sure|ok|okay|great|perfect|absolutely|definitely|of\s+course|cool|awesome)"
_FW_AGREE_START_RE = re.compile(
    r"^(?:"
    r"(?:that|this|it|" + _FW_PRICE_REF + r")(?:\s+|(?='))" + _FW_ADV + r"(?:" + _FW_P_WORK + r"|" + _FW_P_BE + r")"
    + _FW_P_TAIL + r"|"
    r"(?:it's\s+a\s+)?deal\b|agreed\b|done\b|fair\s+enough\b|works(?:\s+for\s+(?:me|us))?\b|fine\s+by\s+me\b|"
    r"let's\s+(?:do\s+it|go\s+with\s+(?:that|it|" + _FW_PRICE_REF + r")|lock\s+(?:it|that)\s+in)\b|"
    r"(?:(?:totally|definitely|absolutely|completely)\s+)?(?:doable|workable|no\s+problem)\b|"
    r"sounds\s+(?:good|great|fine|fair|about\s+right|reasonable|perfect)\b|"
    r"(?:(?:i'm|i\s+am|i'd\s+be|i\s+would\s+be|i'll\s+be)\s+)?(?:(?:totally|very|more\s+than|really|perfectly)\s+)?"
    r"(?:happy|fine|good|ok|okay|comfortable|glad|cool)\s+with\s+" + _FW_REF_END + r"|"
    r"(?:i\s+)?accept\s*[.!]*$|"
    + _FW_MODAL + r"(?:do|work\s+with(?:in)?|live\s+with|go\s+with|accept|honou?r|match|meet|hit|stick\s+(?:to|with)|"
    r"stay\s+(?:within|under|at)|keep\s+(?:it|this|things)\s+(?:within|under|at)|fit\s+(?:within|into|in))\s+"
    + _FW_REF_END + r"|"
    + _FW_MODAL + r"make\s+(?:that|it|this|" + _FW_PRICE_REF + r")\s+work\b|"
    r"(?:(?:i'm|i\s+am|i'd\s+be|i\s+would\s+be|i'll\s+be)\s+)?(?:happy|glad|able|willing|more\s+than\s+happy|ready)\s+to\s+"
    r"(?:work\s+with(?:in)?|go\s+with|accept|do\s+(?:it|this|that)\s+(?:for|at)|stay\s+(?:within|under)|"
    r"keep\s+(?:it|this)\s+(?:within|under))\s+" + _FW_REF_END
    + r")", re.I)
_FW_AGREE_ANY_RE = re.compile(
    r"\b(?:do|build|deliver|handle|finish|complete|take\s+on|get)\s+(?:(?:it|this|that|everything|all\s+of\s+it)\s+|"
    r"(?:the|your|this)\s+[\w-]+(?:\s+[\w-]+)?\s+)?(?:done\s+)?(?:for|at|within|under|inside)\s+" + _FW_PRICE_REF
    + r"\b|"
    r"\b(?:work|stay|keep\s+(?:it|this|things|everything)|fit|come\s+in)\s+(?:within|under|inside|at)\s+"
    + _FW_PRICE_REF + r"\b|"
    r"\bwithin\s+(?:your|that|the)\s+(?:budget|price|number|figure|amount)\b|"
    r"\b(?:at|for)\s+that\s+(?:price|budget|number|figure|rate|amount)\b|"
    r"\b(?:got|have)\s+(?:yourself\s+)?a\s+deal\b|"
    r"\b(?:work|live)\s+with(?:in)?\s+(?:that|this|it)\s*(?:[.,;:!)]|$)|"
    r"\b(?:do|build|deliver|handle)\s+(?:it|this|that|the\s+[\w-]+(?:\s+[\w-]+)?)\s+(?:for|at)\s+(?:that|this)"
    r"\s*(?:[.,;:!)]|$)", re.I)
# Where a clause can start inside a sentence: after "," ";" ":" "(" ")" or a
# spaced dash, and before a capitalised word that follows a lower-case one.
_FW_CLAUSE_START_RE = re.compile(r"[,;:()]|\s-\s|(?<=[a-z0-9])\s+(?=[A-Z](?:[a-z']|\s))")
_FW_LEAD_RE = re.compile(
    r"^(?:(?:and|but|so|also|plus|then|honestly|anyway|well)\s+|" + _FW_YES + r"[!.:]?\s+|i\s+think\s+)+", re.I)
# What follows a clause-start agreement that makes it about a time or a tool.
_FW_DURATION = (r"(?:(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|a\s+couple\s+of|a\s+few|"
                r"\d+(?:\.\d+)?(?:\s*(?:-|to)\s*\d+(?:\.\d+)?)?)\s+(?:business\s+|calendar\s+|working\s+)?"
                r"(?:days?|weeks?|hours?))")
_FW_AFTER_EXEMPT_RE = re.compile(
    r"^\s*(?:"
    r"(?:for|on|at|by|before|from|starting|in|within|under|inside|this|next)?\s*"
    r"(?:(?:me|us)\s+(?:(?:for|on|at)\s+)?)?"
    r"(?:(?:a|the|our)\s+(?:(?:quick|short|brief)\s+)?(?:upwork\s+)?(?:call|chat|meeting)\s+(?:(?:on|at)\s+)?)?"
    r"(?:(?:the|this|next|about|around|roughly|approximately)\s+)*(?:" + _TIME_WORD + r"|" + _FW_DURATION + r")|"
    r"(?:in|with|on|inside|using|through|via|from)\s+(?!" + _FW_PRICE_REF + r")|"
    r"(?:by\s+\w+ing|like|the\s+same|when|whenever|because|automatically|out\s+of\s+the\s+box|behind\s+the\s+scenes|"
    r"end\s+to\s+end|so\s+that)\b)", re.I)
_FW_SENTENCE_END_RE = re.compile(r"[.?!](?=\s|$)|\n")
# A sentence of yes-words only: "Sure.", "Yes, absolutely."
_FW_BARE_YES_RE = re.compile(r"^(?:%s)(?:[,\s]+(?:%s))*\s*[.!]*$" % (_YES_WORD, _YES_WORD), re.I)


def _fw_sentences(body: str) -> List[Tuple[int, int]]:
    """(start, end) of each sentence: a "." "?" or "!" before whitespace or
    the end, or a newline. A period inside a number ("3.5k") does not end
    one; a period after one ("for $3,500. Thanks") does."""
    out, start = [], 0
    for m in _FW_SENTENCE_END_RE.finditer(body):
        out.append((start, m.end()))
        start = m.end()
    if start < len(body):
        out.append((start, len(body)))
    return out


def framework_price_agreement(body: str, room: Optional[Dict[str, Any]]) -> Optional[str]:
    """The first sentence of a framework reply that agrees to a price one of
    the client's unanswered messages proposes (see above), or None."""
    if not body or unanswered_price_proposal(room) is None:
        return None
    for s, e in _fw_sentences(body[:5000]):
        sentence = body[s:e].strip()
        if not sentence:
            continue
        if _FW_BARE_YES_RE.match(sentence) or _FW_AGREE_ANY_RE.search(sentence):
            return sentence
        starts = [0] + [m.end() for m in _FW_CLAUSE_START_RE.finditer(sentence)]
        for start in starts:
            rest = sentence[start:].lstrip()
            rest = rest[_FW_LEAD_RE.match(rest).end():] if _FW_LEAD_RE.match(rest) else rest
            m = _FW_AGREE_START_RE.match(rest)
            if m and (_FW_PRICE_REF_RE.search(m.group(0)) or not _FW_AFTER_EXEMPT_RE.match(rest[m.end():])):
                return sentence  # naming their figure ("work with your budget") is never excused
    return None


# ------------------------------------------------------------ other price points in a framework reply
# Lorenzo, 2026-10-06: a framework reply states one price, the band, both
# ends together ("never a single number, never only one end"). Anything else
# that names a price point is refused (figure_not_in_offers), with or
# without a band: a bare number of 100 or more that is not a count with its
# noun, a time, a percentage, a multiplier or a year after "in / by / since"
# ("probably closer to 1,200", "roughly 1500 for this one", "likely around
# 2,000"); a spelled amount ("a bit over two thousand", "fifteen hundred",
# "two grand"; "thousands of leads" counts things); and a word that points
# inside the range ("the midpoint", "near the top end", "the low end",
# "closer to the bottom").
_FW_YEAR_BEFORE_RE = re.compile(
    r"\b(?:in|since|by|until|till|of|from|before|after|early|mid|late|spring|summer|fall|autumn|winter|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?)\s*$", re.I)
_FW_SPELLED_RE = re.compile(r"\b(?:hundreds?|thousands?|grand)\b(?!\s+of\b)", re.I)
_FW_POSITION_RE = re.compile(
    r"\b(?:mid-?point|middle\s+of\s+(?:the|that|this|my)\s+range|mid-?range|"
    r"(?:top|high|higher|upper|low|lower|bottom)\s+end|(?:lower|upper|top|bottom)\s+half|"
    r"(?:closer|close|nearer|near)\s+to\s+the\s+(?:top|bottom|high|low|upper|lower)|"
    r"near\s+the\s+(?:top|bottom)|(?:high|low)\s+side)\b", re.I)


def framework_figure_problems(body: str) -> List[str]:
    """Price points in a framework reply other than the band (see above).
    ``body`` has the band masked already (mask_band)."""
    out = []  # type: List[str]
    cover = bytearray(len(body) + 1)
    for s, e, _ in money_spans(body):
        cover[s:e] = b"\x01" * (e - s)  # a money amount is figure_problems' to judge
    for m in _BARE_NUM_RE.finditer(body):
        if cover[m.start()] or m.group(2):
            continue
        raw = m.group(1).rstrip(",")
        val = _canon(raw)
        try:
            if val is None or float(val) < 100:
                continue
        except ValueError:
            continue
        end = m.start(1) + len(raw)
        if _NOT_PRICE_TAIL_RE.match(body[end:end + 40]):
            continue  # a time, a percentage, a multiplier or a phone number
        if ("," not in raw and _YEAR_RE.match(raw.replace(",", ""))
                and _FW_YEAR_BEFORE_RE.search(body[max(0, m.start() - 20):m.start()])):
            continue  # "by 2027"
        if _count_use(body, m.start(), end, cover):
            continue  # "the 2,000 contacts"
        out.append("%s (a price beside the range)" % raw)
    out += ["%r (a spelled amount)" % m.group(0) for m in _FW_SPELLED_RE.finditer(body)]
    out += ["%r (points inside the range)" % m.group(0) for m in _FW_POSITION_RE.finditer(body)]
    return out


# ------------------------------------------------------------ contact: explicit data
# Lengths are bounded (a local part is at most 64 characters, a domain label
# 63) so a long run like "a.a.a.a..." costs linear time, not quadratic.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,8}\.[A-Za-z]{2,24}")
_EMAIL_NO_TLD_RE = re.compile(r"(?<![\w@])[A-Za-z0-9._%+-]{0,63}[A-Za-z0-9]@[A-Za-z0-9-]{2,63}\b")
_OBFUSCATED_EMAIL_RE = re.compile(
    r"\b[\w.+-]{1,64}\s*(?:\(at\)|\[at\]|\sat\s)\s*[\w-]{1,63}\s*(?:\(dot\)|\[dot\]|\sdot\s)\s*(?:com|net|org|io|co)\b|"
    r"\b(?:at|@)\s*(?:gmail|yahoo|hotmail|outlook|icloud|proton(?:mail)?)\b", re.I)
# A phone number: 10-15 digits in phone shape, or a leading "+". A 7 to 9
# digit shape ("555-0142") only counts next to a contact word, so a range
# like "300-1200 leads a month" is not a phone number.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![\w$.,])(\+?\(?\d[\d\s().-]{5,40}\d)(?![\w%])")
_PHONE_WORD_RE = re.compile(r"\b(?:call|text|phone|cell|mobile|number|tel|reach|whats\s?app|me|my)\b", re.I)


def _phone_numbers(text: str) -> List[str]:
    found = []  # type: List[str]
    body = text or ""
    for m in _PHONE_CANDIDATE_RE.finditer(body):
        raw = m.group(1).strip()
        digits = re.sub(r"\D", "", raw)
        if raw.startswith("+") and len(digits) >= 7:
            found.append(raw)
        elif 10 <= len(digits) <= 15 and re.search(r"[\s().-]", raw) or (len(digits) in (10, 11) and raw.isdigit()):
            found.append(raw)
        elif 7 <= len(digits) <= 9 and re.fullmatch(r"\(?\d{3}\)?[\s.-]\d{4}|\d{3}[\s.-]\d{2}[\s.-]\d{2}", raw):
            # the contact word must sit in the same sentence, before or just after
            before = re.split(r"[.?!\n]", body[max(0, m.start() - 30):m.start()])[-1]
            after = re.split(r"[.?!\n]", body[m.end():m.end() + 15])[0]
            if _PHONE_WORD_RE.search(before + " " + after):
                found.append(raw)
    return found


# A handle counts only with contact context next to it: "the Slack message
# tags @frontdesk" is a feature, "@lorenzo_v on Telegram" and "follow
# @advero_ai" are contact. A handle carrying Lorenzo's name is always contact.
_HANDLE_RE = re.compile(r"(?<![\w.@])@[A-Za-z0-9_][A-Za-z0-9_.]{1,30}\b")
_HANDLE_CONTEXT_RE = re.compile(
    r"\b(?:whats\s?app|telegram|skype|signal|wechat|viber|discord|imessage|facetime|messenger|kik|linkedin|"
    r"instagram|insta|facebook|twitter|tiktok|snapchat|threads|x\.com|i'?m|i\s+am|my|me|handle|username|follow|"
    r"add|dm|find|search|look\s+up|reach|contact)\b|\bon\s+X\b", re.I)
_LORENZO_ID_RE = re.compile(r"\b(?:lorenzo|advero|villarreal)[\w.]*", re.I)

# ------------------------------------------------------------ contact: the channel lexicon
_TOKEN_RE = re.compile(r"[A-Za-z0-9@$][A-Za-z0-9'._@-]*")


def _prev_words(text: str, pos: int, n: int = 2) -> List[str]:
    words = [w.lower().strip(".'-") for w in _TOKEN_RE.findall(text[max(0, pos - 80):pos])]
    return words[-n:]


def _next_words(text: str, pos: int, n: int = 2) -> List[str]:
    return [w.lower().strip(".'-") for w in _TOKEN_RE.findall(text[pos:pos + 80])][:n]


def _around(text: str, m: Any) -> Tuple[str, str, str, str]:
    """(word before, the one before it, word after, the one after it)."""
    prev = _prev_words(text, m.start(), 2)
    nxt = _next_words(text, m.end(), 2)
    return ((prev[-1] if prev else ""), (prev[-2] if len(prev) > 1 else ""),
            (nxt[0] if nxt else ""), (nxt[1] if len(nxt) > 1 else ""))


# The direction rules read a bounded window around each channel word, so a
# 4,000-character clause full of channel words costs linear time. Every rule
# pattern reaches at most ~150 characters from the word.
_WINDOW = 240
_WS_RE = re.compile(r"\s")


def _tail(text: str, pos: int, size: int = _WINDOW) -> str:
    """text[:pos], or its last ``size`` characters. A cut window starts at a
    space behind a NUL, so patterns anchored at the end see whole words and
    "^" never matches mid-clause."""
    start = pos - size
    if start <= 0:
        return text[:pos]
    ws = _WS_RE.search(text, start, pos)
    return "\x00" + text[ws.start():pos] if ws else "\x00 "


def _head(text: str, pos: int, size: int = _WINDOW) -> str:
    """text[pos:], or its first ``size`` characters and a NUL, so "$" never
    matches at the cut."""
    if pos + size >= len(text):
        return text[pos:]
    return text[pos:pos + size] + "\x00"


_NUMBER_OWNERS = frozenset("my your our best good right direct personal work contact whatsapp telegram signal "
                           "phone cell mobile text sms private preferred own".split())
_REACH_WORDS = frozenset("reach call text contact message whatsapp ping email send use".split())


def _phone_ok(t: str, m: Any) -> bool:
    low = m.group(0).lower()
    p, _, n1, n2 = _around(t, m)
    if re.match(r"numbers?$", low):
        if n1 in ("of", "one", "two", "three", "1", "2", "3"):
            return False
        # "what number should I call", "which number works"
        return (p in _NUMBER_OWNERS or p in ("what", "which", "what's", "whats")
                or (n1 in ("to", "for", "i", "you", "where") and n2 in _REACH_WORDS | {"can"}))
    if low == "digits":
        return p in ("my", "your", "our")  # "send over your digits"; "the last 4 digits" is data
    if low == "cell":
        # "your cell", "a cell I can text"; "a cell in the sheet" is data
        return (p in ("my", "your", "our", "on", "via", "by", "personal", "work", "private") or n1 in ("is", "number")
                or (p in ("a", "any") and n1 in ("i", "we", "to", "you", "phone")))
    if low == "mobile":
        return (p in ("my", "your", "our", "on", "via", "by", "personal", "work", "private")
                and n1 not in ("app", "apps", "site", "friendly", "version", "view", "layout", "users", "traffic",
                               "devices", "device", "browser", "screen", "form"))
    if low.startswith("phone") and " " not in low:
        return n1 not in ("system", "systems", "tree", "support", "bot", "bots", "agent", "agents", "menu", "screen",
                          "app", "lines", "line", "tag", "field", "fields", "column", "verification", "validation")
    return True


def _chat_ok(t: str, m: Any) -> bool:
    word = m.group(0)
    low = word.lower()
    p, _, n1, _ = _around(t, m)
    if low == "signal":
        if p in ("on", "via", "over", "using", "my", "your", "our") or n1 in ("app", "me", "you", "us", "number"):
            return True
        if word == "Signal" and p == "" and n1 in ("works", "is", "or", "and", "too", "also", "would", "could"):
            return True  # "Signal works for me", "Signal or WhatsApp"
        return word == "Signal" and p not in ("", "a", "the", "buying", "strong", "weak", "clear", "no", "any")
    if low == "messenger":
        return word[0] == "M" or p == "facebook"
    if low == "slack":
        return p not in ("some", "of", "more", "less", "no", "cut")
    return True


def _meet_ok(t: str, m: Any) -> bool:
    word = m.group(0)
    low = word.lower()
    p, _, n1, _ = _around(t, m)
    if low == "zoom":
        return n1 not in ("in", "out", "into", "level", "lens")
    if low == "meet":
        if p in ("on", "via", "over", "using"):
            return True
        return word == "Meet" and (p in ("a", "quick", "short", "brief", "the", "your", "my", "our", "or", "and")
                                   or n1 in ("call", "link", "invite", "room", "meeting", "or", "and"))
    if low == "teams":
        if p in ("on", "via", "over", "using") and n1 not in ("of", "that", "who", "which", "and", "with", "to"):
            return True
        return word == "Teams" and (p in ("a", "quick", "short", "the", "your", "my", "our", "or", "and", "in")
                                    or n1 in ("call", "meeting", "invite", "link", "chat", "room", "calls",
                                              "meetings", "or", "and"))
    return True


def _social_ok(t: str, m: Any) -> bool:
    word = m.group(0)
    low = word.lower()
    p, _, n1, _ = _around(t, m)
    if low == "x":
        return word == "X" and (p in ("on", "via") or n1 in ("handle", "account", "profile", "dms", "dm", "page"))
    if low == "ig":
        return word == "IG" or p in ("on", "via", "my", "your", "our")
    if low in ("handle", "username", "user name", "socials"):
        return p in ("my", "your", "our", "instagram", "twitter", "x", "telegram", "skype", "linkedin", "tiktok",
                     "discord", "insta", "ig", "signal") or (n1 == "is" and p in ("the", ""))
    return True


def _dm_ok(t: str, m: Any) -> bool:
    low = m.group(0).lower()
    p, _, n1, _ = _around(t, m)
    if low == "pm":
        return n1 in ("me", "you", "us")
    return not p.isdigit()


_WISE_NOT = frozenset("choice move idea decision call investment enough words thing one guy man to".split())
_CHECK_PAY_BEFORE_RE = re.compile(
    r"(?:\b(?:by|via|paper|personal|cashier's|certified)|\bpay(?:ing)?\s+(?:(?:you|u|me|us)\s+)?(?:with|by|in)\s+"
    r"(?:a|the)|\b(?:mail|mailing|mailed|write|writing|wrote|send|sending|sent|cut|cutting|pay|paying|give|giving|"
    r"hand|post|overnight|take|taking|takes|accept|accepting|accepts|deposit|cash)\s+(?:(?:you|u|me|us)\s+)?"
    r"(?:a|the|my|your|our|one)?)\s*$", re.I)
_CHECK_NOT_PAY_AFTER = frozenset("on of if whether in up out with that your my".split())
# "make the check out to", "write the check payable to", "a check in the mail"
# (the postal mail, not "the mail step" or "the post-processing step")
_IN_THE_MAIL = (r"in\s+the\s+(?:mail|post)(?=\s*(?:[.,;:!?)]|$)|\s+(?:to|for|today|tomorrow|tonight|this|next|on|by|"
                r"first|later|soon|asap|now|when|once|if|and|so|as|after|before|with|each|every|monthly|weekly)\b)")
_CHECK_PAYEE_RE = re.compile(r"\s+(?:payable\s+to\b|%s)" % _IN_THE_MAIL, re.I)
_CHECK_MAKE_BEFORE_RE = re.compile(r"\b(?:make|makes|making|made|write|writes|writing|wrote|written)\s+(?:(?:the|a|"
                                   r"my|our|your|this|that|these|those|one)\s+)?$", re.I)
_CHECK_TEST_WORDS = frozenset("see make confirm verify test ensure catch find check".split())
_CHECK_OK_WORDS = frozenset("fine ok okay good great alright acceptable possible easier better work be welcome".split())


def _pay_ok(t: str, m: Any) -> bool:
    word = m.group(0)
    low = word.lower()
    p, pp, n1, n2 = _around(t, m)
    if low == "wise":
        if m.start() > 0 and t[m.start() - 1] == "-" or n1 in _WISE_NOT:
            return False
        return word == "Wise" or p in ("on", "via", "through", "thru", "by", "with", "using", "over", "to", "my",
                                       "your", "our", "and", "or", "paypal")
    if low == "wire":
        if p in ("by", "via", "over", "through", "thru", "a"):
            return True
        return (n1 in ("me", "you", "us", "money", "funds", "payment", "deposit", "balance")
                or (n1 == "the" and n2 in ("money", "funds", "payment", "deposit", "balance", "rest")))
    if low in ("check", "checks"):
        # the money sense: "by check", "mail you a check", "take checks", "a
        # check works", "checks are fine"; not "check-in", "a check to see if",
        # "a check on the webhook" or "check your inbox"
        if _CHECK_PAYEE_RE.match(t, m.end()) or (n1 == "out" and n2 == "to" and _CHECK_MAKE_BEFORE_RE.search(
                t[max(0, m.start() - 30):m.start()])):
            return True
        if t[m.end():m.end() + 1] == "-" or n1 in _CHECK_NOT_PAY_AFTER or (n1 == "to" and n2 in _CHECK_TEST_WORDS):
            return False
        if _CHECK_PAY_BEFORE_RE.search(t[max(0, m.start() - 40):m.start()]):
            return True
        if low == "checks":
            return n1 == "work" or (n1 in ("are", "would", "will") and n2 in _CHECK_OK_WORDS)
        return p in ("a", "one") and (n1 in ("works", "work") or (
            n1 in ("is", "would", "will", "should", "could", "might") and n2 in _CHECK_OK_WORDS))
    if low == "ach":
        return word == "ACH" or p in ("by", "via")
    return True


# (category, pattern, filter). Matched case-insensitively per clause; the
# longest match wins where two overlap ("Zoom link" over "Zoom").
_CHANNEL_SPECS = (
    # a meeting-app link is a meeting: "a Zoom link", "the Meet invite"; a
    # voice call is a phone call unless the clause puts it on Upwork
    ("meet", r"\b(?:google\s+)?meet\s+(?:links?|invites?|invitations?|urls?)\b|"
             r"\b(?:zoom|teams|microsoft\s+teams|facetime|webex|whereby)\s+(?:links?|invites?|invitations?|urls?)\b|"
             r"\bvoice\s+(?:calls?|chats?)\b",
     None),
    # the client's or Lorenzo's details as such: "drop me your contact info"
    ("contact", r"\bcontact\s+(?:info(?:rmation)?|details?|numbers?|cards?)\b", None),
    ("book", r"\b(?:booking|scheduling|calendar|meeting|invite)\s+(?:links?|pages?|urls?|invites?|invitations?)\b|"
             r"\bcalendly\b|\bcal\.com\b|\bzcal\b|\btidycal\b|\bsavvycal\b|\bacuity\b|\bhubspot\s+meetings\b", None),
    ("email", r"\be-?mail(?:s|ed|ing)?\b(?:\s+address(?:es)?\b)?|\bgmail\b|\binbox(?:es)?\b|\bmailbox\b", None),
    ("text", r"\btext(?:s|ed|ing)?\b(?:\s+messages?\b)?|\bsms\b|\bimessage\b", None),
    ("phone", r"\bphones?\b(?:\s+numbers?\b)?|\bcell\s?phones?\b|\bcell\b(?:\s+numbers?\b)?|"
              r"\bmobile\b(?:\s+(?:numbers?|phones?)\b)?|\blandline\b|\bdirect\s+line\b|\bvoicemail\b|\bnumbers?\b|"
              r"\bdigits\b",
     _phone_ok),
    ("chat", r"\bwhats\s?app\b|\btelegram\b|\bskype\b|\bdiscord\b|\bslack\b|\bwechat\b|\bviber\b|\bkik\b|"
             r"\bmessenger\b|\bsignal\b", _chat_ok),
    ("meet", r"\bzoom\b|\bgoogle\s+meet\b|\bmeet\b|\b(?:microsoft|ms)\s+teams\b|\bteams\b|\bface\s?time\b|\bwebex\b|"
             r"\bgo\s?to\s?meeting\b|\bwhereby\b|\b(?:google\s+)?hangouts\b", _meet_ok),
    ("social", r"\blinked\s?in\b|\btwitter\b|\binstagram\b|\binsta\b|\big\b|\bfacebook\b|\bfb\b|\btik\s?tok\b|"
               r"\byoutube\b|\bgithub\b|\bsnapchat\b|\bx\.com\b|\bx\b|\bhandle\b|\busername\b|\buser\s+name\b|"
               r"\bsocials\b", _social_ok),
    ("dm", r"\bdms?\b|\bpm\b|\bdirect\s+(?:messages?|chat)\b|\bprivate\s+(?:messages?|chat)\b", _dm_ok),
    ("pay", r"\bpay\s?pal\b|\bstripe\b|\bvenmo\b|\bzelle\b|\bcash\s?app\b|\bpayoneer\b|\brevolut\b|"
            r"\bwestern\s+union\b|\bmoneygram\b|\bcrypto(?:currency)?\b|\bbitcoin\b|\bbtc\b|\busdt\b|\busdc\b|"
            r"\bethereum\b|\bwise\b|\bwire\s+transfers?\b|\bwire\b|\bbank\s+(?:transfers?|accounts?|details|wires?|"
            r"info)\b|\bdirect\s+deposit\b|\bach\b|\bcheques?\b|\bchecks?\b", _pay_ok),
)
_CHANNEL_RES = tuple((cat, re.compile(pat, re.I), ok) for cat, pat, ok in _CHANNEL_SPECS)

# Canonical keys. A key in NAMED_PLATFORMS is a named platform: it may appear
# as the project's subject only when the job post or the client names it.
_KEY_ALIASES = {
    "whats app": "whatsapp", "linked in": "linkedin", "pay pal": "paypal", "cash app": "cashapp", "insta": "instagram",
    "ig": "instagram", "fb": "facebook", "x": "twitter", "x.com": "twitter", "face time": "facetime",
    "google meet": "googlemeet", "meet": "googlemeet", "microsoft teams": "microsoftteams",
    "ms teams": "microsoftteams", "teams": "microsoftteams", "google hangouts": "hangouts",
    "go to meeting": "gotomeeting", "goto meeting": "gotomeeting", "go tomeeting": "gotomeeting",
    "cal.com": "calcom", "tik tok": "tiktok", "bitcoin": "crypto", "btc": "crypto", "usdt": "crypto", "usdc": "crypto",
    "ethereum": "crypto", "cryptocurrency": "crypto", "western union": "westernunion",
    "hubspot meetings": "hubspotmeetings",
}
NAMED_PLATFORMS = frozenset("""
whatsapp telegram signal skype discord slack wechat viber messenger kik zoom googlemeet microsoftteams facetime webex
gotomeeting whereby hangouts calendly calcom zcal tidycal savvycal acuity hubspotmeetings linkedin twitter instagram
facebook tiktok youtube github snapchat paypal venmo zelle wise stripe payoneer revolut cashapp westernunion moneygram
crypto
""".split())


class Mention(object):
    """One channel term in a piece of text."""
    __slots__ = ("start", "end", "cat", "key", "text")

    def __init__(self, start: int, end: int, cat: str, key: str, text: str) -> None:
        self.start, self.end, self.cat, self.key, self.text = start, end, cat, key, text

    def __repr__(self) -> str:
        return "Mention(%r, %s, %s)" % (self.text, self.cat, self.key)


def _channel_key(cat: str, text: str) -> str:
    low = re.sub(r"\s+", " ", text.lower().strip())
    if cat in ("book", "meet"):
        stripped = re.sub(r"\s+(?:links?|invites?|invitations?|urls?|pages?)$", "", low)
        if stripped in ("booking", "scheduling", "calendar", "meeting", "invite"):
            return "bookinglink"
        low = stripped
    if cat == "phone":
        return "phone"
    if cat in ("email", "text", "dm", "social") and low not in _KEY_ALIASES and low not in NAMED_PLATFORMS:
        return low.replace(" ", "")
    low = _KEY_ALIASES.get(low, low)
    return low.replace(" ", "")


def channel_mentions(text: str) -> List[Mention]:
    """Every channel term in ``text``, left to right, overlaps resolved to the
    longest match."""
    body = text or ""
    cands = []  # type: List[Tuple[int, int, str]]
    for cat, rx, ok in _CHANNEL_RES:
        for m in rx.finditer(body):
            if ok is None or ok(body, m):
                cands.append((m.start(), m.end(), cat))
    cands.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken = []  # type: List[Tuple[int, int, str]]
    used = bytearray(len(body) + 1)  # characters already inside a longer mention
    for s, e, cat in cands:
        if used.find(1, s, e) == -1:
            used[s:e] = b"\x01" * (e - s)
            taken.append((s, e, cat))
    return [Mention(s, e, cat, _channel_key(cat, body[s:e]), body[s:e]) for s, e, cat in sorted(taken)]


def platforms_named(text: str) -> Set[str]:
    """Named platforms in ``text``, canonical ('whatsapp', 'googlemeet', ...)."""
    return {m.key for m in channel_mentions(decode_escapes(text)) if m.key in NAMED_PLATFORMS}


# ------------------------------------------------------------ contact: clauses and actors
_SUBJECT_START = (r"(?:i|i'm|i'll|i'd|i've|you|you'll|you're|you'd|you've|we|we'll|we're|we'd|we've|it|it's|"
                  r"it'll|they|they'll|they're|let's|lets|let\s+me|happy\s+to|glad\s+to|feel\s+free|please|just)\b")
_CLAUSE_SPLIT_RE = re.compile(
    r"(?<!\d)[.?!]+(?!\d)(?=\s|$)|[;\n]|:(?=\s)|\s-+\s|"
    r",?\s+(?=(?:so\s+that|so|because|since|while|whereas|which|when|whenever|once|until|unless|if|otherwise|"
    r"although|then)\b)|"
    r",\s+(?=%s)|\s+(?:and|but|or|plus)\s+(?=%s)" % (_SUBJECT_START, _SUBJECT_START), re.I)


def _clauses(text: str) -> List[str]:
    return [c for _, c in _clause_spans(text)]


def _clause_spans(text: str) -> List[Tuple[int, str]]:
    """(offset in ``text``, clause) for every clause, stripped of spaces and commas."""
    out = []  # type: List[Tuple[int, str]]
    body = text or ""
    pos = 0
    bounds = [(m.start(), m.end()) for m in _CLAUSE_SPLIT_RE.finditer(body)] + [(len(body), len(body))]
    for start, end in bounds:
        part = body[pos:start]
        stripped = part.strip(" ,")
        if stripped:
            out.append((pos + len(part) - len(part.lstrip(" ,")), stripped))
        pos = end
    return out


def _sentence_texts(text: str) -> List[str]:
    return [text[s:e] for s, e in _sentences(text or "")]


# Who is doing the contacting. The nearest actor before a channel decides: a
# Lorenzo or client actor (or an imperative addressed to the client) makes
# the channel a move off Upwork, a project actor makes it the project.
#
# The conditional exemption in _acting_lorenzo is inactive on purpose for these
# actors. The alternation tries "i" before "i'd" (and "we" before "we'd"), and
# the \b after "i" already holds at the apostrophe, so "I'd", "I would" and
# "I could" are recorded as "i" and count as Lorenzo acting. In a message to
# the client a conditional "I'd" is usually a soft offer, not a build
# description: "I'd send the recap by email" is refused only because of this.
# The build descriptions the exemption was meant to spare ("I'd send the first
# text from your Twilio number", "I'd forward replies to your inbox") already
# pass through the project, end-user and stream checks. Leave the order as it
# is; making the exemption live would let those soft offers through.
# _LZ_CONDITIONAL_RE stays active where it is matched directly (_pay_reason).
_LZ_ACTOR_RE = re.compile(
    r"\b(?:i|i'm|i'll|i'd|i've|i\s+am|let\s+me|let's|we|we'll|we're|we'd|we've|happy\s+to|glad\s+to|keen\s+to|"
    r"down\s+to|more\s+than\s+happy\s+to)\b|^\s*lets\b", re.I)
_LZ_CONDITIONAL_RE = re.compile(r"^(?:i'd|we'd|i\s+would|i\s+could|we\s+would|we\s+could)$", re.I)
_CL_ACTOR_RE = re.compile(
    r"\byou(?:'ll|'d|'re|'ve)?\s+(?=(?:can|could|will|would|might|may|should|must|just|only|also|then|pay|settle|"
    r"send|get|book|pick|choose|prefer|use|want|need|have|reach|find|message|text|email|call|ping|drop|share|grab|"
    r"let|tell|decide|go|click|open|reply|respond|do|don't|dont|already|wire|transfer|venmo|zelle)\b)|"
    r"\bfeel\s+free\s+to\b", re.I)
_IMPERATIVE_RE = re.compile(
    r"^\s*(?:(?:just|also|please|so|and|then|or|but|pls|kindly|now|ok|okay|otherwise|easiest\s+is\s+to)[,\s]+)*"
    r"(?:send|drop|share|give|put|leave|reach|ping|call|ring|message|dm|pm|follow|pay|settle|invoice|forward|"
    r"text|email|e-mail|whatsapp|add|find|search|look|google|hit|shoot|connect|venmo|zelle|wire|transfer|book|"
    r"grab|pick|use|join|hop|jump|check|tell|let|feel|go|head|click|visit|open|try|write|contact|buzz|chat|talk|"
    r"speak|meet|schedule|choose|select|reply|respond|confirm|accept|post|type|enter|fill|submit|upload|attach|"
    r"move|take|switch|continue|keep|bring|mail|tag|mention|slide|save|note|jot)\b", re.I)
_PROJECT_HEADS = (
    r"bots?|chatbots?|system|systems|workflows?|flows?|sequences?|drips?|campaigns?|automations?|agents?|assistants?|"
    r"ai|forms?|crm|"
    r"scenarios?|zaps?|scripts?|webhooks?|triggers?|integrations?|apps?|page|site|widgets?|pipelines?|dashboards?|"
    r"tools?|api|models?|nodes?|reminders?|confirmations?|alerts?|notifications?|summary|digest|reports?|records?|"
    r"deals?|tickets?|tasks?|queue|n8n|make|zapier|hubspot|ghl|gohighlevel|highlevel|pipedrive|salesforce|"
    r"airtable|twilio|leads?|customers?|patients?|clients?|members?|users?|buyers?|prospects?|contacts?|callers?|"
    r"visitors?|guests?|homeowners?|tenants?|owners?|vendors?|reps?|front\s+desk|team|staff|office|techs?|"
    r"technicians?|dispatchers?|nurses?|providers?|doctors?|coordinators?|managers?|admins?|anyone|someone|"
    r"somebody|nobody|no\s+one|everyone|everybody|whoever|invites?|links?|emails?|texts?|sms|messages?|replies|"
    r"calls|bookings?|appointments?|consults?|payments?|deposits?|invoices?|requests?|submissions?|entries|orders?|"
    r"signups?|sign-ups?|inquiries|enquiries|photos|files|quotes?|estimates?|receipts?|refunds?|charges?")
_DETERMINER = r"(?:the|a|an|each|every|any|all|your|their|its|this|that|those|these|new|incoming|inbound|missed)"
_PROJECT_NP_RE = re.compile(
    r"\b(?:%s\s+(?:[\w'-]+\s+){0,2}?(?:%s)|(?:%s)|it|they|he|she|it's|they're|it'll|they'll|they've|they'd)\b"
    % (_DETERMINER, _PROJECT_HEADS, _PROJECT_HEADS), re.I)
_ENGAGEMENT_HEADS = frozenset(("payment", "payments", "deposit", "deposits", "invoice", "invoices"))
_NON_VERB = frozenset("""
a an the this that these those my your our their his her its me you us them him and or but so of in on at by via
over through from into onto with for as than if when while because since until about after before per like each
every any all some no not to up out off here there who whom whose which what where why how
tonight today tomorrow yesterday later soon again anyway instead too either anytime asap line
""".split())  # a time word is not a verb ("you'll have it in your inbox tonight"), nor is "line" ("your office line")


_PP_SKIP_RE = re.compile(
    r"^\s+(?:from|in|on|at|of|with|via|through|by)\s+(?:the\s+|a\s+|an\s+|your\s+|their\s+|its\s+|each\s+)?"
    r"[\w'.-]+(?:\s+(?:ads?|forms?|page|site|number|app|inbox|account|calendar|campaigns?))?(?=\s)", re.I)


def _verbish(rest: str) -> bool:
    """The text after a noun phrase starts with a verb: 'sends', 'can send',
    'to post'. An article, preposition or pronoun means the phrase is an
    object ('send it to my email'), not a subject. One prepositional phrase
    is skipped first: 'customers on WhatsApp get a reply', 'demo requests from
    LinkedIn could book'."""
    pp = _PP_SKIP_RE.match(rest)
    if pp:
        after = re.match(r"\s+([A-Za-z][\w']*)", rest[pp.end():])
        if after and after.group(1).lower() not in _NON_VERB and not after.group(1)[:1].isupper():
            return True
    m = re.match(r"\s+([A-Za-z][\w']*)(?:\s+([A-Za-z][\w']*))?", rest)
    if not m:
        return False
    w1 = m.group(1).lower()
    if w1 == "to":
        w2 = (m.group(2) or "").lower()
        return bool(w2) and w2 not in _NON_VERB and not (m.group(2) or "")[:1].isupper()
    if w1 == "who":
        return True
    return w1 not in _NON_VERB


# A noun phrase right after one of these is an object or sits in a
# prepositional phrase: "send you the bot summary", "show you the bot live",
# "reply to the lead". Causatives ("have the bot send", "let the bot book")
# keep the noun phrase as the actor.
_OBJECT_SLOT_RE = re.compile(
    r"\b(?:you|me|us|them|him|her|send|sends|sending|sent|show|shows|showing|showed|give|gives|giving|gave|share|"
    r"shares|sharing|shared|forward|forwarding|email|emailing|build|building|built|connect|connecting|test|testing|"
    r"see|use|using|walk|through|about|with|on|in|to|for|from|into|onto|of|at|by|via|over|under|between|like|than)"
    r"\s+$", re.I)


def _actors(clause: str) -> List[Tuple[int, int, str, str]]:
    """(start, end, kind, text) of every actor in the clause: lorenzo, client,
    project or imperative."""
    found = []  # type: List[Tuple[int, int, str, str]]
    for m in _LZ_ACTOR_RE.finditer(clause):
        found.append((m.start(), m.end(), "lorenzo", m.group(0).strip().lower()))
    for m in _CL_ACTOR_RE.finditer(clause):
        found.append((m.start(), m.end(), "client", m.group(0).strip().lower()))
    for m in _PROJECT_NP_RE.finditer(clause):
        before = _tail(clause, m.start(), 120)
        if _OBJECT_SLOT_RE.search(before):
            continue
        head = m.group(0).split()[-1].lower()
        if head in _ENGAGEMENT_HEADS and not re.match(r"(?:each|every|any|all|their|incoming|inbound|new)\b",
                                                      m.group(0), re.I):
            continue  # "the deposit", "an email": Lorenzo's own, not the project's
        if _verbish(_head(clause, m.end(), 120)):
            # "my assistant", "our team": Lorenzo's side, not the project
            owner = re.search(r"\b(?:my|our)\s+(?:[\w'-]+\s+){0,2}$", before, re.I)
            kind = "lorenzo" if owner and not re.match(_DETERMINER + r"\b", m.group(0), re.I) else "project"
            found.append((m.start(), m.end(), kind, m.group(0).lower()))
    if _IMPERATIVE_RE.match(clause):
        found.append((0, 0, "imperative", ""))
    return found


def _actor_before(actors: List[Tuple[int, int, str, str]], pos: int) -> Tuple[str, str]:
    """(kind, text) of the actor nearest before ``pos``, or ('none', '')."""
    best = None  # type: Optional[Tuple[int, int, str, str]]
    for actor in actors:
        if actor[1] <= pos and (best is None or actor[0] >= best[0]):
            best = actor
    return (best[2], best[3]) if best else ("none", "")


def _acting_lorenzo(kind: str, text: str) -> bool:
    """Lorenzo doing it himself now, not describing the build ('I'd tag each one')."""
    return kind == "lorenzo" and not _LZ_CONDITIONAL_RE.match(text)


# ------------------------------------------------------------ contact: direction rules
_END_USERS = (r"(?:leads?|customers?|patients?|clients?|members?|users?|buyers?|prospects?|callers?|visitors?|guests?|"
              r"homeowners?|tenants?|shoppers?|students?|candidates?|subscribers?|followers?|attendees?|donors?|"
              r"applicants?|people|contacts?|consumers?|diners?|residents?|families|parents?|riders?|drivers?)")
_END_USER_RE = re.compile(r"(?<!\bmy\s)(?<!\bour\s)\b%s\b" % _END_USERS, re.I)
_THEY_RE = re.compile(r"\b(?:they|them|their|they're|they'll|they've|they'd)\b", re.I)
_TIME = (r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tonight|tomorrow|this\s+(?:week|"
         r"afternoon|morning|evening)|next\s+week|all\s+week|later\s+today|noon|\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
         r"at\s+\d{1,2}(?::\d{2})?|anytime|any\s+time|after\s+\d{1,2}|before\s+\d{1,2})")
_TIME_CUE_RE = re.compile(r"\b(?:%s|live)\b(?!'s)" % _TIME, re.I)
_TIME_VENUE_L_RE = re.compile(r"\b%s\s+(?:on|via|over|by)\s+(?:the\s+|a\s+)?$" % _TIME, re.I)
_TIME_VENUE_R_RE = re.compile(r"^\s+(?:on\s+|at\s+|this\s+|next\s+)?%s\b" % _TIME, re.I)
_OBJ_VERBS = (r"(?:call|calls|called|calling|text|texts|texted|texting|email|emails|emailed|e-mail|message|messages|"
              r"msg|ping|pings|pinged|reach|catch|see|meet|send|sends|show|walk|give|hit|contact|add|find|follow|dm|pm|"
              r"buzz|ring|join|invite|update|notify|remind|tell|brief|loop|forward|pay|thank|facetime|whatsapp|"
              r"skype|slack|zoom|to|with)")
_ME = r"(?:me|(?-i:us|Us|US))"
_L_PERSON_PREP_RE = re.compile(
    r"(?:\b%s|\b%s\s+you|^\s*you)\b(?:\s+[\w'-]+){0,2}?\s+(?:on|via|over|through|thru|by|at|using)\s+"
    r"(?:the\s+|a\s+|an\s+|my\s+|your\s+|our\s+)?$" % (_ME, _OBJ_VERBS), re.I)
_L_PERSON_IN_RE = re.compile(
    r"\b(?:ping|message|msg|dm|reach|find|add|catch|call|text|email|hit|contact|chat|talk|speak|see|join|follow|"
    r"meet)\s+(?:%s|you)\b(?:\s+(?:up|directly|there|anytime|later))?\s+(?:in|into)\s+"
    r"(?:the\s+|a\s+|my\s+|your\s+|our\s+)?$" % _ME, re.I)
# A contact verb on a person with a longer gap before the channel: "call me
# Thursday at noon on WhatsApp", "send me the lead form export by email", "I'll
# update you by email once it's live".
_L_PERSON_VIA_RE = re.compile(
    r"\b(?:send|sends|sending|sent|forward|forwarding|email|emailing|text|texting|share|sharing|drop|shoot|pass|"
    r"get|call|calling|ring|message|messaging|ping|reach|catch|meet|see|dm|update|notify|remind|brief|loop|"
    r"contact|hit)\s+(?:it\s+|this\s+|that\s+|them\s+|over\s+|back\s+)?(?:to\s+)?(?:%s|you)\b(?:\s+[\w':,-]+){0,6}?"
    r"\s+(?:on|via|over|through|thru|by|using)\s+(?:the\s+|a\s+|an\s+|my\s+|your\s+|our\s+)?$" % _ME, re.I)
_R_PERSON_RE = re.compile(r"^\s+(?:me|you|(?-i:us|Us))\b", re.I)
_L_NOUN_BEFORE_RE = re.compile(
    r"\b(?:the|a|an|this|that|each|every|your|my|our|their|his|her|its|first|second|third|next|last|same|one|"
    r"follow-up|followup|confirmation|reminder|welcome|intro|initial|final|automated|auto|quick|short|any|no)\s*$",
    re.I)
_VERB_CATS = frozenset(("email", "text", "chat", "meet", "dm", "pay", "phone"))
_L_GIVE_PERSON_RE = re.compile(
    r"\b(?:give|gave|giving|send|sent|sending|shoot|shot|drop|fire|flick|leave|leaving|ping)\s+(?:%s|you)\s+"
    r"(?:a|an)\s+(?:quick\s+|short\s+|brief\s+)?$" % _ME, re.I)
# "a shared WhatsApp group with you", "a Slack channel with you", "an email
# thread between us".
_R_WITH_PERSON_RE = re.compile(
    r"^\s+(?:(?:group|channel|workspace|chat|thread|room|server|call|meeting|huddle|space|dm|conversation|convo)s?\s+)?"
    r"(?:with|between)\s+(?:you|me|(?-i:us|Us))\b", re.I)
# "here or on WhatsApp", "on Upwork, or email if that's easier"
_L_HERE_OR_RE = re.compile(r"\b(?:here|on\s+upwork|upwork)\s*,?\s+or\s+(?:on\s+|via\s+|over\s+|by\s+|through\s+|in\s+)?"
                           r"(?:a\s+|an\s+)?$", re.I)
# "is WhatsApp ok for you", "would email be easier for you"
_R_OK_FOR_PERSON_RE = re.compile(
    r"^\s+(?:be\s+)?(?:ok|okay|fine|good|easier|easiest|better|best|possible|an\s+option|alright|easy|convenient|"
    r"quicker|faster|simpler)\s+(?:for|with|on)\s+(?:you|me|(?-i:us)|your\s+end|my\s+end)\b", re.I)
_SOCIAL_PERSON_RE = re.compile(
    r"\b(?:connection|friend|follow)\s+request\b|"
    r"\b(?:connect|connecting|follow|following|add|adding|friend|find|finding|message|dm)\s+(?:with\s+)?"
    r"(?:me|you|(?-i:us))\b", re.I)
_MODS = (r"(?:own\s+|personal\s+|private\s+|work\s+|direct\s+|business\s+|best\s+|main\s+|usual\s+|other\s+|"
         r"preferred\s+|contact\s+)?")
_L_MINE_RE = re.compile(r"\b(?:my|our)\s+%s$" % _MODS, re.I)
_L_YOURS_RE = re.compile(r"\byour\s+%s$" % _MODS, re.I)
_L_REQUEST_RE = re.compile(
    r"\b(?:what'?s|what\s+is|whats|share|send(?:\s+(?:me|us|over))?|drop|give(?:\s+(?:me|us))?|put|leave|"
    r"pass(?:\s+along)?|forward(?:\s+me)?|dm(?:\s+me)?|text(?:\s+me)?|email(?:\s+me)?|post|type|write|add|confirm|"
    r"need|have|grab|get|take|note|jot\s+down|let\s+me\s+(?:have|know))\s+(?:me\s+|us\s+|over\s+)?"
    r"(?:(?:the|a)\s+(?:best|good|right|preferred|quickest|easiest|direct)\s+|your\s+%s)$" % _MODS, re.I)
_L_BEST_RE = re.compile(r"\b(?:the|a|your)\s+(?:best|good|right|preferred|quickest|easiest|direct)\s+$", re.I)
_R_REACH_RE = re.compile(r"^\s+(?:to|for|i\s+can|we\s+can)\s+(?:reach|contact|call|text|email|message|get\s+hold|send|"
                         r"use|ping|whatsapp)\b", re.I)
_L_ARE_YOU_ON_RE = re.compile(r"(?:\bare\s+you|\byou're|\byou\s+are|^\s*you)\s+(?:also\s+|still\s+)?on\s+$|"
                              r"\bdo\s+you\s+(?:have|use)\s+(?:a\s+|an\s+)?$", re.I)
_L_DEST_YOURS_RE = re.compile(r"\b(?:to|at|into|in|on|via|over|through|thru)\s+your\s+%s$" % _MODS, re.I)
_TRANSFER_VERB_RE = re.compile(
    r"\b(?:send|sends|sending|sent|forward|forwarding|forwarded|email|emailing|text|texting|mail|share|sharing|drop|"
    r"pass|deliver|shoot|message|ping|reach|call|ring|dm|whatsapp|get\s+(?:it|this|that|them)|put|post|reply|"
    r"respond|give|giving|hand)\b", re.I)
_ACCESS_VERB_RE = re.compile(r"\b(?:have|has|got|use|find|grab|take|save|add|write\s+down|note|reach|contact|"
                             r"hit|ping|call|text|ring|email|message|dm|whatsapp)\b[^.?!\n]{0,20}$", re.I)
_R_CONTACT_DATA_RE = re.compile(r"^\s*(?:is\b|:|address\b|number\b|#|below\b|above\b|here\b|\(|\+?\d)", re.I)
_PROJECT_AFTER = (
    r"'s\b|\s+(?:flows?|bots?|workflows?|automations?|sequences?|campaigns?|templates?|lists?|integrations?|apis?|"
    r"webhooks?|triggers?|events?|alerts?|notifications?|business|ads?|ad\s+accounts?|pages?|lead\s+forms?|forms?|"
    r"groups?|channels?|workspaces?|checkout|payouts?|payments?|payment\s+links?|subscriptions?|charges?|receipts?|"
    r"refunds?|disputes?|dashboards?|data|records?|sync|connectors?|nodes?|modules?|recordings?|transcripts?|"
    r"summar(?:y|ies)|notes|replies|threads|comments|posts|followers|reviews|catalogs?|shop|pixel|apps?|portals?|"
    r"plugins?|widgets?|buttons?|terminals?|readers?|keys?|accounts?|tools?|stack|setup|parser|signatures?|marketing|"
    r"outreach|reminders?|confirmations?|drips?|nurture|responders?|autoresponders?|chatbots?|assistants?|scheduler|"
    r"calendars?|ids?|meetings|calls|bookings?|messages\s+(?:from|to)|numbers?\s+(?:for|of)|links\s+(?:for|to)|"
    r"invites\s+(?:for|to)|leads?|customers?|contacts?|marketplace|storefront|dms|tool|intakes?|inbox|consults|"
    r"consultations|sessions|appointments|classes|lessons|demos|interviews|webinars|visits|"
    r"meeting\s+(?:notes|recordings?|transcripts?|summar(?:y|ies)|data|details|minutes|records?|history|ids?)|"
    r"invoices?\s+(?:from|for|to|that|get|go|are|land))\b")
_R_PROJECT_RE = re.compile(r"^(?:%s)" % _PROJECT_AFTER, re.I)
_COORD_PLATFORM_RE = re.compile(
    r"^\s*(?:,\s*|\s+(?:and|or|&)\s+|\s*/\s*)(?:the\s+)?[\w.]+(?:\s+(?:app|transfers?|pay))?", re.I)


def _project_right(right: str) -> bool:
    """The channel heads a project noun: "Stripe webhooks", "Zoom recordings",
    also past a second platform: "Stripe and PayPal payments"."""
    if _R_PROJECT_RE.match(right):
        return True
    co = _COORD_PLATFORM_RE.match(right)
    return bool(co and _R_PROJECT_RE.match(right[co.end():]))


_R_ACTION_RE = re.compile(
    r"^\s+(?:(?:can|could|will|would|should|then|also|automatically|just)\s+)*(?:sends?|takes?|charges?|collects?|handles?|processes|fires|creates?|issues?|marks?|emails?|texts?|"
    r"holds?|captures?|confirms?|updates?|notifies|triggers?|pays\s+out|settles?|refunds?|syncs?|pushes|posts?|"
    r"logs?|books?|replies|answers?|routes?|drops?|lands?|shows?|stores?|keeps?|tags?|moves?|adds?|reads?|"
    r"parses?|pulls?|checks?|counts?|reports?|hold|take|send|charge|collect|mark|issue|refund|settle|sync|log|"
    r"store|keep|tag|move|add|read|pull|check|route|confirm|update|notify|trigger|create|capture|process)\b", re.I)
# "each", "their", and data qualifiers: "a recorded Zoom meeting" is test data
_L_PROJECT_DET_RE = re.compile(r"\b(?:each|every|all|any|their|its|incoming|inbound|new|a\s+customer's|"
                               r"a\s+patient's|the\s+lead's|the\s+customer's|recorded|past|previous|old|sample|"
                               r"existing|archived|saved|finished|completed|real)\s+$", re.I)
_MEETING_NOUN = (r"(?:call|chat|meeting|meet|walkthrough|walk-through|demo|screen\s?share|screenshare|session|"
                 r"catch[- ]up|sync|huddle|hangout|conversation|convo|intro|interview|consult|consultation|video|"
                 r"talk|few\s+minutes|\d+\s*[- ]?min(?:ute)?s?)")
_L_MEETING_PREP_RE = re.compile(
    r"\b(?P<noun>%s)\b(?:\s+[\w'-]+){0,3}?\s+(?:on|via|over|through|thru|in|using)\s+"
    r"(?:the\s+|a\s+|an\s+|my\s+|your\s+|our\s+)?$" % _MEETING_NOUN, re.I)
_PLURAL_PROCESS_RE = re.compile(
    r"\b(?:calls|meetings|consults|consultations|sessions|appointments|interviews|demos|visits|classes|lessons|"
    r"webinars|check-?ins|recordings|chats)\s+(?:on|via|over|through|in|from)\s+(?:the\s+|their\s+|your\s+)?$",
    re.I)
_L_PERSON_THROUGH_RE = re.compile(
    r"\b(?:walk|show|take|run|talk|go|demo|present|screen\s?share|guide)\s+(?:you|%s)\b(?P<mid>[^.?!\n]{0,40}?)\s+"
    r"(?:on|over|via|in|using|through)\s+(?:the\s+|a\s+)?$" % _ME, re.I)
_L_A_QUICK_RE = re.compile(r"\b(?:a|an|one|quick|short|brief|\d+[- ]?min(?:ute)?)\s+(?:quick\s+|short\s+|brief\s+|"
                           r"video\s+|voice\s+|live\s+)?$", re.I)
_R_MEETING_NOUN_RE = re.compile(r"^\s+(?:call|chat|meeting|session|video|convo|catch[- ]up|sync|huddle|hangout|"
                                r"walkthrough|demo)\b|^\s*(?:[.,?!;:]|$)", re.I)
_L_LETS_RE = re.compile(
    r"\b(?:let'?s|lets|we\s+(?:can|could)|can\s+we|could\s+we|shall\s+we|how\s+about|what\s+about|happy\s+to|"
    r"glad\s+to|i\s+can|i\s+could|(?:i'?m\s+)?(?:free|available|around|good|open)\s+(?:on|for)|do|use|try|"
    r"jump\s+on|hop\s+on|get\s+on|join|prefer|or)\s+(?:a\s+|an\s+|the\s+)?(?:quick\s+|short\s+|brief\s+)?$", re.I)
_EASY_REACH = (r"(?:easy|easier|easiest|quick|quicker|quickest|fast|faster|fastest|best|simplest|simpler)\s+to\s+"
               r"(?:reach|get|contact|find|catch|ping|get\s+hold\s+of)(?:\s+me)?")
_L_AVAILABLE_RE = re.compile(
    r"\b(?:i'?m|i\s+am|i'?ll\s+be|i\s+will\s+be|we'?re|we\s+are)\s+(?:(?:usually|always|mostly|also|pretty|very|much|"
    r"super|%s|around|available|reachable|online|active|free|contactable|responsive|quick|quicker|faster|findable)\s+)*"
    r"(?:on|via|over|at|through|by)\s+$" % _EASY_REACH, re.I)
_L_MOVE_RE = re.compile(
    r"\b(?:move|moving|moved|take|taking|switch|switching|shift|shifting|bring|bringing|continue|continuing|carry|"
    r"carrying|keep|keeping|chat|chatting|talk|talking|speak|speaking|connect|connecting|catch\s+up|reach\s+out|hop|"
    r"jump|head)\b(?:\s+(?:this|it|things|that|us|the\s+(?:conversation|chat|discussion|thread|convo)|"
    r"this\s+(?:conversation|chat|discussion|thread|convo)|our\s+(?:conversation|chat|discussion|convo)))?"
    r"(?:\s+(?:over|directly|privately))?\s+(?:to|on|onto|into|via|by|over|through|thru|in)\s+"
    r"(?:a\s+|an\s+|the\s+)?$", re.I)
_R_MOVE_PROJECT_RE = re.compile(
    r"\b(?:sequences?|flows?|workflows?|campaigns?|cadences?|bots?|automations?|leads?|customers?|patients?|drips?|"
    r"nurture|steps?\s+of)\b", re.I)
# "Telegram works too", "PayPal works for me", "email is easiest", "email works
# better for me", "a voice call might be quicker", "WhatsApp works better for
# voice notes". A bare "works well for the photos" is the project.
_WORKS_RE = re.compile(
    r"^\s+(?:also\s+|too\s+|just\s+|really\s+)?(?:(?:both|either)\s+)?(?:works?|would\s+work|could\s+work|"
    r"(?:is|are)\s+(?:both\s+)?(?:fine|easiest|easier|best|"
    r"better|good|great|ok|okay|quicker|faster|simplest|perfect|quickest)|(?:might|would|could|may|should)\s+be\s+"
    r"(?:quicker|easier|faster|better|simpler|smoother|best|easiest|quickest)|suits\s+me)(?:\s+(?:better|best))?"
    r"(?:\s+(?:too|also|as\s+well|either|for\s+(?:me|(?-i:us)|you)|with\s+me|by\s+me|if\s+(?:you|that|it's|it\s+is|"
    r"easier)|on\s+my\s+end|for\s+(?:the\s+)?(?:deposit|payment|call|chat|calls|meetings|updates|questions|rest|"
    r"this|that|now|balance|milestone|voice\s+(?:notes?|messages?|memos?)|screenshots?|screen\s+(?:recordings?|"
    r"shares?)|quick\s+(?:questions?|updates?|chats?|calls?)|back[- ]and[- ]forth|sharing\s+(?:files|screenshots|"
    r"photos)|files|feedback|revisions?|attachments?|docs?|documents?|contracts?|paperwork))\b|\s*[.,;!?]|\s*$)",
    re.I)
_L_CLAUSE_START_RE = re.compile(r"^\s*(?:(?:and|also|or|but|otherwise|plus|else)[,\s]+)?"
                                r"(?:(?:a\s+)?[A-Za-z][\w.]*\s+(?:or|and|/)\s+)?(?:a\s+)?$", re.I)
# "WhatsApp is the fastest way to get me", "the best way to reach me is email"
_REACH_ME_RE = re.compile(
    r"\b(?:reach|get\s+hold\s+of|contact|catch|ping)\s+(?:me|(?-i:us))\b|"
    r"\b(?:get|find)\s+(?:me|(?-i:us))\b(?=\s*(?:[.,;?!]|$|on\b|via\b|at\b|by\b|over\b|through\b|is\b|fastest\b))", re.I)
# "invite me to your Slack", "add me to your WhatsApp group"
_L_INVITE_ME_RE = re.compile(r"\b(?:invite|add|bring|let)\s+(?:me|(?-i:us))\s+(?:in\s+)?(?:to|into|on)\s+"
                             r"(?:your\s+|the\s+|a\s+)?$", re.I)
# "we could go over it by phone", "happy to discuss the details on WhatsApp"
_L_CONVERSE_RE = re.compile(
    r"\b(?:go\s+over|going\s+over|walk\s+through|discuss|discussing|review|reviewing|run\s+through|cover|talk|"
    r"talking|chat|chatting|speak|speaking|catch\s+up|sync|meet|meeting)\b(?:\s+(?:it|this|that|things|them|"
    r"details|scope|everything|the\s+[\w-]+))?(?:\s+(?:quickly|live|together|properly|more|further))?\s+"
    r"(?:by|over|on|via|in|through)\s+(?:the\s+|a\s+)?$", re.I)
# "a text from me", "an email from me"
_R_FROM_ME_RE = re.compile(r"^\s+from\s+(?:me|(?-i:us))\b", re.I)
# Lorenzo using a channel as a verb on anyone but the project's end users:
# "I'll email the proposal over tonight", "I'll text the front desk".
_L_LZ_VERB_SLOT_RE = re.compile(
    r"\b(?:i'll|i\s+will|i\s+can|let\s+me|happy\s+to|glad\s+to|i'?m\s+going\s+to|i\s+am\s+going\s+to|"
    r"i'?m\s+about\s+to|i'd\s+be\s+happy\s+to|we'll|we\s+can)\s+(?:just\s+|also\s+|quickly\s+|then\s+|still\s+)?$",
    re.I)
_R_END_USER_OBJ_RE = re.compile(r"^(?:\s+(?:or|and|/)\s+[\w-]+)?\s+(?:each\s+|every\s+|the\s+|your\s+|new\s+|all\s+|"
                                r"any\s+|a\s+)?(?:[\w-]+\s+)?%s\b" % _END_USERS, re.I)
# "I'd rather use email for the scope"
_L_PREFER_RE = re.compile(r"\b(?:rather|prefer|prefers|preferred)\s+(?:to\s+)?(?:use\s+|do\s+|go\s+with\s+|"
                          r"switch\s+to\s+|stick\s+(?:to|with)\s+|keep\s+it\s+(?:on|to)\s+)?(?:a\s+|an\s+|the\s+)?$",
                          re.I)
_PREFER_TOPIC = (r"for\s+(?:updates|the\s+scope|scope|questions|talking|chatting|the\s+call|calls|next\s+steps|"
                 r"the\s+details|the\s+rest|our\s+chat|the\s+conversation)\s*(?:[.,;?!]|$)|if\s+(?:that's|that\s+is|"
                 r"it's|you)\b|going\s+forward\b|from\s+here\b")
_R_PREFER_TAIL_RE = re.compile(r"^\s*(?:[.,;?!]|$|%s)" % _PREFER_TOPIC, re.I)
_R_PREFER_TOPIC_RE = re.compile(r"^\s*(?:%s)" % _PREFER_TOPIC, re.I)
# "... in the reminder text", "... into each confirmation email": a project destination
_R_PROJECT_DEST_RE = re.compile(
    r"^[^.?!\n]{0,30}?\b(?:in|into|inside|on|to)\s+(?:the|each|every|your|their|a)\s+(?:[\w-]+\s+)?"
    r"(?:reminders?|texts?|sms|emails?|messages?|invites?|invitations?|confirmations?|sequences?|flows?|workflows?|"
    r"templates?|pages?|forms?|bookings?|records?|calendar|events?|notes?|fields?|deals?|contacts?)\b", re.I)
# Call intent anywhere in the sentence: "here's the booking link if you want to chat"
_CALL_INTENT_RE = re.compile(
    r"\bif\s+you\s+(?:want|'d\s+like|would\s+like|wanna)\s+to\s+(?:chat|talk|meet|hop\s+on|jump\s+on|connect|"
    r"speak|go\s+over)|\bto\s+(?:chat|talk|meet|connect|speak)\s+(?:live|with\s+me|more|further)\b", re.I)
_MEETING_PLURAL_RE = re.compile(r"^\s+(?:calls|meetings|consults|consultations|sessions|demos|interviews|webinars|"
                                r"huddles|chats)\b", re.I)
# Words for Lorenzo's own engagement money. One the client's post or messages
# use is the project's ("the booking deposit" in a med spa post).
_ENGAGEMENT_PAY_RE = re.compile(
    r"\b(?:deposit|deposits|retainer|upfront|up\s+front|balance|the\s+rest|remainder|milestones?|first\s+half|"
    r"second\s+half|my\s+(?:rate|fee|invoice)|payment\s+for\s+(?:this|the)\s+(?:work|build|project|job))\b", re.I)
_L_PAYMENT_VIA_RE = re.compile(r"\b(?:the\s+)?(?:payment|payments|deposit|the\s+rest|balance|invoice|invoicing|"
                               r"billing)\s+(?:via|by|through|thru|on|over|in|with|using)\s+(?:a\s+|the\s+)?$", re.I)
# The client paying its own payees or tools is the project: "you can pay your
# vendors through Wise", "you'd pay Twilio per text".
_THIRD_PAYEE = (r"(?:(?:your|the|their|all|each|any|those|these|its)\s+)?(?:[\w'-]+\s+)?(?:vendors?|suppliers?|staff|"
                r"contractors?|subcontractors?|subs|employees?|team|reps?|techs?|technicians?|crew|workers?|"
                r"freelancers?|partners?|affiliates?|drivers?|cleaners?|providers?|payroll|landlords?|people|them|"
                r"bills|twilio|hubspot|zapier|processing\s+fees)\b")
# Lorenzo is the one paid: "I'd rather be paid via PayPal", "happy to get paid
# on Wise". "That way you get paid faster through Stripe" is the project.
_LZ_PAID_RE = re.compile(
    r"\b(?:i|i'm|i'd|i'll|i\s+am|i\s+would|i\s+will|i\s+can|i\s+could|happy\s+to|glad\s+to)\s+"
    r"(?:(?:rather|prefer\s+to|like\s+to|love\s+to|need\s+to|want\s+to|usually|normally|always|only|just|also|"
    r"to)\s+)*(?:be|get|getting|being)\s+paid\b", re.I)
_LZ_PAY_YOU_RE = re.compile(r"\b(?:i|i'll|i\s+can|happy\s+to|glad\s+to)\s+(?:[\w']+\s+){0,2}?"
                            r"(?:pay|refund|reimburse)\s+(?:you|u)\b", re.I)
# A cheque for Lorenzo: "mail me a check", "send the check to my office",
# "make the check out to me", "checks can be made payable to Advero". Checks
# made out to the client's vendors or staff are the project.
_LZ_CHECK_RE = re.compile(
    r"\b(?:mail|mails|mailing|send|sending|write|writing|cut|cutting|give|giving|hand|post|overnight|fedex|drop)\s+"
    r"%s\s+(?:over\s+)?(?:(?:a|the|your|one)\s+)?(?:paper\s+|personal\s+|company\s+|business\s+|certified\s+)?"
    r"(?:check|cheque)s?\b(?!-|\s+(?:on|of|if|whether|in|up|out|with|that|to\s+(?:see|make|confirm|verify|test))\b)|"
    r"\b(?:mail|mails|mailing|send|sending|post|overnight|fedex|drop)\s+(?:(?:the|a|your|that|any)\s+)?(?:paper\s+|"
    r"personal\s+)?(?:checks?|cheques?|payment)\s+(?:off\s+|over\s+|straight\s+|directly\s+)?(?:to|at)\s+(?:%s\b|"
    r"my\s+(?:[\w-]+\s+)?(?:office|address|home|house|place|mailbox|po\s+box|p\.?o\.?\s+box|company|business)\b)|"
    # "make the check out to", "make it payable to" ("make it out to the site" is a visit)
    r"(?:\b(?:make|makes|making|made|write|writing|written)\s+(?:(?:(?:the|a|any|your|all|each)\s+)?(?:checks?|"
    r"cheques?)\s+(?:out\s+to|payable\s+to)|(?:it|them)\s+payable\s+to)|\b(?:checks?|cheques?)\s+(?:(?:can|"
    r"should|may|must|would|will)\s+)?(?:be\s+|are\s+|is\s+)?(?:made\s+)?(?:out\s+to|payable\s+to))\b(?!\s+%s)"
    % (_ME, _ME, _THIRD_PAYEE), re.I)
# Payment between Lorenzo and the client, whatever the rail.
_PAY_STRONG_RES = (
    re.compile(r"\b(?:pay|paid|paying|send|sending|transfer|transferring|wire|wiring|settle|settling|tip|refund|"
               r"remit|venmo|zelle)\s+%s\b" % _ME, re.I),
    re.compile(r"\b(?:pay|send|transfer|wire|deposit|remit|settle)\w*\b[^.?!\n]{0,40}\bto\s+(?:me|my\b)", re.I),
    re.compile(r"\b(?:invoice|bill|charge)\s+(?:you|u)\b", re.I),
    re.compile(r"\byou\s+(?:(?:can|could|would|'d|will|'ll|just|then|also|want\s+to|prefer\s+to|like\s+to|"
               r"rather)\s+)*(?:pay|settle|transfer|wire|tip|venmo|zelle|cover)\b(?!\s+%s)" % _THIRD_PAYEE, re.I),
    re.compile(r"\b(?:happy|glad|able)\s+to\s+(?:take|accept|receive|get)\s+(?:the\s+)?(?:payment|deposit|money|"
               r"funds)\b", re.I),
    _LZ_PAY_YOU_RE,
    re.compile(r"\b(?:works?|is\s+(?:fine|easiest|easier|best|better|good|great|ok|okay|preferred|simplest|quickest))"
               r"\s+(?:for|with|by)\s+%s\b" % _ME, re.I),
    _LZ_PAID_RE,
)
# ---- payment talk with no rail named, checked on every clause (round 4).
# Upwork's own milestones, escrow and invoices stay allowed.
_UPWORK_PAY_RE = re.compile(
    r"\b(?:through|via|on|in|using|with|inside|over)\s+(?:the\s+)?upwork\b|\bupwork(?:'s)?\s+(?:milestones?|escrow|"
    r"invoic\w*|payments?|contract|system|checkout)\b|\bmilestones?\b|\bescrow\b", re.I)
_INVOICE_WORDS = (r"(?:invoice|bill|payment\s+(?:request|link)|pay\s+link)(?!\s+(?:templates?|flows?|automations?|"
                  r"emails?|reminders?|steps?|modules?|nodes?|fields?|numbers?|status|sync|data|records?|line\s+items?|"
                  r"pdfs?|design|layout)\b)")
_INVOICE_MODS = (r"(?:(?:a|an|the|my|one|separate|final|first|second|deposit|upfront|up-front|proper|formal|quick)"
                 r"\s+){0,3}")
# "I'll send you an invoice for the deposit", "I can send a separate invoice".
# A conditional with no "you" describes the build ("I'd send an invoice from
# QuickBooks when the job closes").
_LZ_INVOICE_RE = re.compile(
    r"\b(?P<who>i'll|i\s+will|i\s+can|i\s+could|let\s+me|happy\s+to|glad\s+to|i'?m\s+going\s+to|i\s+am\s+going\s+to|"
    r"i'd\s+be\s+happy\s+to|i\s+would\s+be\s+happy\s+to|i'd|i\s+would)\s+(?:(?:just|also|then|simply|quickly|"
    r"gladly|happily|first)\s+)?(?:send|issue|raise|cut|email|draw\s+up|do|write\s+up|put\s+together|shoot\s+over|"
    r"shoot)\s+(?P<you>(?:you|u)\s+)?(?:over\s+)?%s%s\b" % (_INVOICE_MODS, _INVOICE_WORDS), re.I)
# "I'll invoice you through my company", "a separate invoice", "pay the
# deposit to my account", "pay me", "I'd rather be paid", "I'll refund you".
_PAY_ANY_RES = (
    re.compile(r"\b(?:invoice|bill|charge)\s+(?:you|u)\b|\bseparate\s+(?:invoice|bill|payment)\b|"
               r"\b(?:invoice|invoicing|bill|billing|charge|charging)\b[^.?!\n]{0,30}?\b(?:through|via|from|under|"
               r"with)\s+my\s+(?:[\w-]+\s+)?(?:company|agency|business|llc|firm|studio|account|bank)\b", re.I),
    re.compile(r"\b(?:pay|pays|paid|paying|transfer|transferring|wire|wiring|remit|send\s+(?:the\s+)?(?:money|funds|"
               r"payment|deposit|balance|rest|fee))\b(?!\s+attention)[^.?!\n]{0,40}?\b(?:to|into)\s+me\b|"
               r"\b(?:pay|pays|paid|paying|payment|payments|transfer|transfers|transferring|wire|wires|wiring|remit|"
               r"deposit|deposits|money|funds|send\s+(?:the\s+)?(?:money|funds|payment|deposit|balance|rest|fee))\b"
               r"(?!\s+attention)[^.?!\n]{0,40}?\b(?:to|into|in|on)\s+my\s+"
               r"(?!(?:test|sandbox|dev|demo|staging|trial)\b)"
               r"(?:[\w-]+\s+)?(?:account|bank|company|business|llc|agency|card|wallet|paypal|stripe|wise|venmo|zelle|"
               r"payoneer|revolut|iban|details|name)\b", re.I),
    re.compile(r"\b(?:pay|paid|paying|transfer|transferring|wire|wiring|remit|tip|venmo|zelle)\s+%s\b" % _ME, re.I),
    _LZ_PAID_RE,
    _LZ_PAY_YOU_RE,
    _LZ_CHECK_RE,
    # "my invoice will cover the deposit", "my bank details"
    re.compile(r"\bmy\s+(?:own\s+)?invoices?\b(?!\s+(?:templates?|flows?|automations?|emails?|reminders?|numbers?))|"
               r"\bmy\s+(?:bank(?:ing)?|payment|billing|wire|remittance)\s+(?:details|info|information|account|"
               r"address|link)\b", re.I),
)
# "I'll send payment details separately", "send you my bank details", "the
# details for the wire", "I'll send you the mailing address" (for a check)
_SEND_PAY_DETAILS_RE = re.compile(
    r"\b(?:send|sending|share|sharing|give|giving|pass|forward|drop|email|text|dm)\b(?:\s+(?:you|u|over|along|"
    r"across))*\s+(?:(?:the|my|our)\s+)?(?:(?:payment|bank(?:ing)?|billing|wire|remittance|paypal|venmo|zelle|wise|"
    r"payoneer)\s+(?:details|info|information|instructions)|(?:details|info|information|instructions)\s+for\s+"
    r"(?:the\s+|a\s+|your\s+)?(?:wire|transfer|bank\s+transfer|payment|check|cheque|deposit)|(?:mailing|postal|"
    r"remittance|remit-to)\s+address(?!\s+(?:fields?|columns?|data|propert(?:y|ies)|values?|of|from|into|in|on|"
    r"to\s+(?!you\b))))\b|"
    r"\b(?:send|sending|share|sharing|give|giving|pass|forward|drop|email|text|dm)\b(?:\s+(?:you|u|over|along|"
    r"across))+\s+(?:my|our)\s+address\b", re.I)
# "a payment link for the deposit": Lorenzo's own money, unless the client's
# words use that word for the project's money ("customers pay deposits")
_PAY_LINK_FOR_RE = re.compile(
    r"\b(?:payment|pay|checkout|stripe|paypal|square|invoice)\s+links?\b[^.?!\n]{0,30}?\bfor\s+(?:the\s+|my\s+|"
    r"your\s+|a\s+)?(?:(?P<shared>deposit|balance|rest|remainder|fee|fees|first\s+half|second\s+half|retainer)|"
    r"build|work|project|job)\b", re.I)
# "Stripe will charge you 2.9%": a platform charging the client is the project.
_PAY_SUBJECT_RE = re.compile(
    r"\b(?:stripe|paypal|square|quickbooks|xero|wise|payoneer|twilio|hubspot|the\s+(?:bank|processor|platform|"
    r"gateway|app|bot|system|workflow|card))\s+"
    r"(?:(?:will|would|can|could|may|might|also|then|automatically|still)\s+)*$", re.I)
# The channel is the object of Lorenzo accepting or billing: "I accept PayPal",
# "I take crypto", "I invoice through PayPal", "I'll bill you on Stripe".
_L_PAY_ACCEPT_RE = re.compile(
    r"(?:\b(?:i|we)(?:'ll|'d|'m|\s+can|\s+could|\s+will|\s+would|\s+also|\s+usually|\s+always|\s+normally|\s+just|"
    r"\s+only|\s+happily|\s+am|\s+happy\s+to|\s+glad\s+to|\s+rather)*|\b(?:more\s+than\s+)?happy\s+to|\bglad\s+to)"
    r"\s+(?:accept|take|prefer|receive|go\s+through|"
    r"invoice|bill|charge)(?:\s+(?:you|u))?\s+(?:(?:payments?|the\s+(?:deposit|payment|balance|rest)|it)\s+)?"
    r"(?:(?:by|via|through|thru|on|over|in|with|using)\s+)?(?:a\s+|the\s+|my\s+)?$", re.I)
_L_SEND_INVOICE_RE = re.compile(r"\bsend\s+(?:you|u)\s+(?:a|an|the|my)\s+$", re.I)
_R_INVOICE_RE = re.compile(r"^\s+(?:invoice|payment\s+(?:link|request)|pay\s+link|bill|link|request)\b", re.I)
_BOOK_WITH_ME_RE = re.compile(
    r"\b(?:book|grab|pick|find|schedule|reserve|choose|take|set\s+up|lock\s+in)\s+(?:a|an|any|one|the|some)?\s*"
    r"(?:time|slot|call|spot|meeting|session|chat)\b[^.?!\n]{0,30}\b(?:with\s+%s\b|(?:on|in|from|via|through|using)\s+"
    r"(?:my|our)\s+(?:calendar|schedule|scheduler|booking\s+page|availability))" % _ME, re.I)
_L_BOOK_ACTION_RE = re.compile(
    r"\b(?:grab|grabbed|pick|picked|book|booked|find|choose|chose|take|took|reserve|reserved|lock\s+in|snag|snagged)"
    r"\s+(?:a|an|any|one|the|some|your)?\s*(?:time|slot|spot|call|meeting|session|chat)\b[^.?!\n]{0,20}?"
    r"\s+(?:on|in|from|via|through|using)\s+(?:the\s+|your\s+|my\s+|our\s+)?$", re.I)
_FOR_A_CALL_RE = re.compile(
    r"\bfor\s+(?:a|our|the|this|that|your|my)?\s*(?:quick\s+|short\s+|brief\s+|\d+[- ]?min(?:ute)?\s+)?"
    r"(?:call|chat|meeting|intro|demo|walkthrough|catch[- ]up)\b|\bfor\s+us\s+to\s+(?:talk|chat|meet|speak)\b|"
    r"\bto\s+(?:book|schedule|set\s+up|grab)\s+(?:a|our|the)\s+(?:quick\s+|short\s+)?(?:call|meeting|chat)\b", re.I)
_BOOKING_TOPIC_RE = re.compile(
    r"\b(?:book|books|booked|booking|bookings|appointments?|schedul\w*|calendars?|calendly|consults?|"
    r"consultations?|reservations?|reserve|slots?|meetings?|demos?|inspections?|visits?|showings?|tours?|"
    r"sessions?|classes|lessons|invites?)\b", re.I)
_SOCIAL_OWNER_RE = re.compile(r"\b(?:instagram|insta|ig|facebook|fb|linkedin|twitter|x|tiktok|whatsapp|telegram|"
                              r"messenger|social)\s+$", re.I)
_MY_IDENTITY_RE = re.compile(r"\b(?:my|our)\s+(?:name|company|agency|business\s+page|page|profile|handle|username|"
                             r"account|channel|brand)\b", re.I)
_HANDLE_SHAPED_RE = re.compile(r"(?:^|\s)@?[A-Za-z0-9._]*[_\d][A-Za-z0-9._]*\s+(?:on|at)\s+$")
# A phone number spelled out: "five one two, five five five, zero one four two".
_DIGIT_WORD = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"
_SPELLED_PHONE_RE = re.compile(r"\b%s(?:[\s,.-]+%s){6,}\b" % (_DIGIT_WORD, _DIGIT_WORD), re.I)

# Leaving Upwork outright: refused whoever says it.
_LEAVE_RES = (
    re.compile(r"\b(?:outside|out\s+of)\s+(?:of\s+)?(?:the\s+)?(?:upwork|platform|contract|escrow|"
               r"this\s+(?:site|app|platform|room|thread)|the\s+(?:site|app))\b", re.I),
    re.compile(r"(?<!\bsign\s)(?<!\bsigned\s)(?<!\blog\s)(?<!\bdrop\s)(?<!\bkick\s)(?<!\bpay\s)(?<!\bcut\s)"
               r"\boff\s+(?:of\s+)?(?:upwork|the\s+platform|this\s+platform|platform|here|this\s+(?:site|app|thread|"
               r"chat|room)|the\s+(?:site|app))\b", re.I),
    re.compile(r"\boff[- ](?:platform|site|upwork)\b", re.I),
    re.compile(r"\b(?:skip|skipping|avoid|avoiding|save|saving|dodge|dodging|bypass|bypassing|cut\s+out|go\s+around|"
               r"get\s+around|around)\s+(?:on\s+)?(?:the\s+|those\s+|all\s+the\s+)?(?:upwork(?:'s)?\s+)?(?:fees?|cut|"
               r"commission|service\s+fees?|platform\s+fees?|middleman)\b", re.I),
    re.compile(r"\b(?:skip|skipping|bypass|bypassing|avoid|avoiding|leave|leaving|without|cut\s+out|go\s+around|"
               r"get\s+around|not\s+(?:through|via|on))\s+upwork\b", re.I),
    re.compile(r"\b(?:not|never|no\s+need\s+to|rather\s+not)\s+(?:pay|paying|give|giving)\s+upwork\b", re.I),
    re.compile(r"\b(?:direct|separate|private|side)\s+(?:contract|deal|agreement|arrangement|hire|chat)\b", re.I),
    re.compile(r"\b(?:chat|talk|speak|message|connect|continue|discuss|reach\s+out)\w*\s+(?:[\w']+\s+){0,2}?"
               r"(?:privately|in\s+private)\b", re.I),
    re.compile(r"\b(?:google|look\s+up|search(?:\s+for)?)\s+(?:me|us|my\s+name|my\s+company|my\s+agency|lorenzo\w*|"
               r"advero\w*|villarreal)\b|\blook\s+(?:me|us)\s+up\b", re.I),
    re.compile(r"\bhmu\b", re.I),
    re.compile(r"\b(?:easier|faster|quicker|better|simpler|more\s+reliable|smoother)\s+than\s+(?:on\s+)?"
               r"(?:upwork(?:'s)?(?:\s+(?:chat|app|messages?|messaging|inbox))?|here|"
               r"this\s+(?:chat|thread|platform|site))\b", re.I),
    re.compile(r"\bcall\s+me\s+at\b|\bcall\s+me\s+on\s+(?!upwork\b|here\b)", re.I),
    re.compile(r"\b(?:reach|contact|find|ping|text|email|message|whatsapp)\s+(?:me|us)\s+at\s+"
               r"(?!(?:any|noon|\d|the\s+same|once|all|upwork|here)\b)", re.I),
    re.compile(r"\b(?:drop|shoot|send)\s+(?:me|us)\s+a\s+line\b", re.I),
    re.compile(r"\b(?:give|gave|giving)\s+(?:me|you|us)\s+a\s+(?:quick\s+)?(?:ring|buzz|bell)\b|"
               r"\bring\s+(?:me|you|us)\b", re.I),
    re.compile(r"\b(?:pay|paid|paying|send|sending|wire|wiring|transfer|transferring|deposit)\w*\s+(?:[\w']+\s+){0,4}?"
               r"(?:straight|directly|direct)\s+to\s+(?:me|my|us|our)\b", re.I),
    # round 4: "happy to connect outside of here", "off the books", "my other
    # account", "reach me through my website"
    re.compile(r"\boutside\s+(?:of\s+)?here\b", re.I),
    re.compile(r"\boff\s+the\s+books\b|\bunder\s+the\s+table\b", re.I),
    re.compile(r"\bmy\s+(?:other|second|backup|alt|alternate|personal|private)\s+(?:account|profile|handle|line|inbox|"
               r"number|phone|email)\b", re.I),
    re.compile(r"\bmy\s+(?:own\s+|personal\s+|company\s+|agency\s+|business\s+)?(?:website|web\s+site)\b", re.I),
    re.compile(r"\b(?:reach|contact|find|message|email|call|book|hire|ping|text|pay)\s+(?:me|(?-i:us))\s+"
               r"(?:directly\s+)?(?:through|via|on|at|from|using)\s+my\s+(?!upwork\b)[\w-]+", re.I),
)
# "happy to take this elsewhere", "let me send you a message elsewhere":
# refused unless the project or its end users do it ("leads who message you
# elsewhere").
_ELSEWHERE_RE = re.compile(
    r"\b(?:connect|connecting|chat|chatting|talk|talking|speak|speaking|message|messaging|take\s+(?:this|it|things|"
    r"that)|taking\s+(?:this|it|things|that)|move\s+(?:this|it|things|that|us)|moving\s+(?:this|it|things|that)|"
    r"continue|continuing|carry\s+on|reach(?:\s+out)?|meet|discuss|discussing|pick\s+(?:this|it)\s+up|follow\s+up|"
    r"reply|respond|email|text|call|ping|dm|catch\s+up|sync|get\s+in\s+touch|send\s+(?:you|me)\b)"
    r"\b[^.?!\n]{0,40}?\b(?:elsewhere|somewhere\s+(?:else|more\s+[\w-]+|easier|quicker|faster|better|simpler|"
    r"private|direct)|offline|off-line)\b", re.I)
# "reach out whenever, by text or email": a way to reach Lorenzo offered across
# a clause break. The project's users reaching out pass ("leads can reach out
# by text").
_REACH_OUT_VIA_RE = re.compile(
    r"\b(?:reach\s+out|get\s+in\s+touch|contact\s+me|ping\s+me|message\s+me|hit\s+me\s+up|get\s+hold\s+of\s+me)\b"
    r"[^.?!\n]{0,40}?\b(?:by|via|over|through|on)\s+(?:the\s+|a\s+)?(?:text|sms|email|e-mail|phone|whatsapp|telegram|"
    r"signal|slack|linkedin|dm|call)\b", re.I)
_SOMEONE_RE = re.compile(r"\b(?:someone|anyone|somebody|anybody|everyone|everybody|nobody|no\s+one|the\s+(?:bot|form|"
                         r"workflow|system|flow|sequence))\b", re.I)
# "pay directly": refused unless the project or its end users pay
# ("customers pay the deposit directly on the booking page").
_DIRECTLY_RE = re.compile(
    r"\b(?:pay|paid|paying|payment|payments|invoice|invoicing|invoiced|bill|billing|billed|charge|charging|contract|"
    r"contracting|hire|hiring|settle|settled|work\s+together)\s+(?:[\w']+\s+){0,3}?directly\b|"
    r"\bdirect\s+(?:payment|payments|pay|transfer|transfers|invoice|invoices|invoicing|billing|contract|hire|"
    r"hiring)\b", re.I)


# ---- round 4: contact details, sending, inviting, testing, groups
# Asking for the client's details, whatever the question word: "what number
# should I call", "which email should I send it to", "is there a good number
# for you". The project may ask ("which number should the bot text from").
_L_ASK_WH_RE = re.compile(
    r"\b(?:what|which|what's|whats|what\s+is|what\s+would\s+be)\s+(?:(?:a|the|your)\s+)?"
    r"(?:(?:good|best|better|right|preferred|easiest|quickest|direct|main|usual|personal|work|other)\s+)?$", re.I)
_R_ASK_USE_RE = re.compile(
    r"^\s*(?:(?:should|shall|can|could|do|would|will|may|might)\s+(?:i|we)\b|"
    r"(?:to|for)\s+(?:call|text|reach|use|send|email|contact|ping|message|whatsapp|get|try|ring|dial)\b|"
    r"(?:is|'s|would\s+be|works?)\s+(?:best|good|easiest|right|fine|ok|okay|better|quickest)\b|"
    r"for\s+(?:you|u)\b|\?)", re.I)
_L_IS_THERE_RE = re.compile(
    r"(?:\b(?:is|are)\s+there|\b(?:do|did)\s+you\s+have|\bhave\s+you\s+got|\byou\s+got|^\s*got)\s+"
    r"(?:a|an|any|some|one)\s+(?:(?:good|best|better|preferred|direct|quick|easy|easier|other|personal|work)\s+)?$",
    re.I)
# "which is better for you, email or phone?", "do you prefer email or a call?"
_ASK_PREFER_RE = re.compile(
    r"\b(?:(?:which|what)(?:'s|\s+is|\s+would\s+be|\s+works)?\s+(?:better|best|easier|easiest|preferred|quicker|"
    r"simpler)\s+for\s+you|(?:do|would)\s+you\s+(?:prefer|rather)|you\s+prefer)\b", re.I)
_R_PROJECT_NEXT_RE = re.compile(
    r"^\s+(?:(?:that|which)\s+)?(?:(?:the|each|every|a|an|your|their|new|any)\s+(?:[\w'-]+\s+)?(?:%s)|%s)\b"
    % (_PROJECT_HEADS, _END_USERS), re.I)
# The project asking about a contact detail, later in the clause: its sender
# ("which email should I send the drip from"), its machinery or accounts
# ("which number should I use for the bot", "what email should I use for the
# Instantly account", "as the reply-to"). Its users and messages count too
# (_project_asks). A deliverable is Lorenzo's, whatever it is about ("the bot
# demo", "the workflow diagram").
_DELIVERABLE = (r"(?:demos?|diagrams?|walkthroughs?|mockups?|looms?|videos?|recordings?|previews?|screenshots?|docs?|"
                r"documents?|scope|proposals?|plans?|maps?|outlines?|drafts?|files?|samples?|tests?|overviews?|specs?|"
                r"breakdowns?|estimates?|json|exports?|backups?|cop(?:y|ies)|summary|summaries|reports?|recap)")
_PROJECT_USE_RE = re.compile(
    r"\bfrom\s*(?:[?.,;!]|$)|\b(?:senders?|reply-?to|accounts?|log-?ins?|domains?|workspaces?|caller\s+id|port|"
    r"porting|a2p|10dlc|warm-?up|drips?|campaigns?|sequences?|bots?|chatbots?|workflows?|automations?|"
    r"integrations?|webhooks?|crm|templates?|auto-?repl(?:y|ies)|twilio|instantly|hubspot|gohighlevel|highlevel|"
    r"ghl|zapier|n8n|airtable|pipedrive|salesforce|mailchimp|klaviyo|smartlead|lemlist)\b(?!'s)(?!\s+%s\b)"
    % _DELIVERABLE, re.I)
# "which email should I send it to", "is there an email I can send the demo
# to": the contact detail is where Lorenzo sends something. Only the project's
# users or stream make that the project's question ("which email should I
# forward the replies to").
_R_SEND_TO_RE = re.compile(
    r"^\s+(?:(?:should|shall|can|could|do|would|will|may|might)\s+)?(?:i|we)\s+(?:(?:can|could|should|will|would|"
    r"may|might|also|just)\s+)*(?:send|forward|email|e-mail|mail|text|share|deliver|drop|pass|get|put|dm|message|"
    r"whatsapp)\b[^.?!\n\x00]{0,60}?\bto\s*(?:[?.!,;]|$)", re.I)
# Lorenzo reaching the client's own line: "mind if I call your cell", "I'll
# text your number". The verb must be Lorenzo's (_lorenzo_subject):
# "bounces never reach your inbox" and "cold emails that reach your inbox"
# are the project.
_L_CONTACT_YOURS_RE = re.compile(
    r"\b(?:call|calling|ring|ringing|text|texting|email|emailing|message|messaging|ping|reach|try|dial|buzz|hit|"
    r"contact|whatsapp)\s+(?:you\s+(?:on|at)\s+)?your\s+%s$" % _MODS, re.I)
# What comes right before a verb that makes it Lorenzo's: "I", "we" (with
# modals: "I could", "can I", "mind if I"), his own people or things ("my
# assistant will", "my VA can") or an infinitive after a word of his intent
# ("happy to", "ok to", "I'd like to").
_LZ_MODAL = r"(?:can|could|will|would|should|may|might|shall|must)"
_LZ_ADVERB = r"(?:also|just|then|quickly|probably|still|maybe|first|gladly|happily)"
_LZ_SUBJECT_END_RE = re.compile(
    r"\b(?:i|we|i'll|i'd|i'm|we'll|we'd|we're)\s+(?:(?:%s|%s)\s+)*$|"
    r"\b(?:my|our)\s+(?:[\w'-]+\s+){1,2}?%s\s+(?:%s\s+)*$|"
    r"\b(?:happy|glad|able|ok|okay|fine|free|want|wanted|like|love|going|about|planning|plan|try|trying|need|"
    r"mean|meant)\s+to\s+(?:(?:also|just|quickly|briefly|first)\s+)*$"
    % (_LZ_MODAL, _LZ_ADVERB, _LZ_MODAL, _LZ_ADVERB), re.I)
# Something of Lorenzo's arriving in the client's inbox or phone at a set
# time: "it'll be in your inbox by Friday", "the scope will land in your
# inbox tonight", "it'll hit your inbox tonight". A recurring time ("every
# Monday", "on Mondays") is the project's.
_ARRIVE_RE = re.compile(r"(?<=\w)'s\b|\b(?:be|is|hit|hits|land|lands|arrive|arrives|show\s+up|shows\s+up|pop\s+up|"
                        r"pops\s+up|reach|reaches|come\s+through|comes\s+through|sit|sits|wait|waits)\b", re.I)
_WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_ONE_OFF_TIME_RE = re.compile(
    r"\b(?:tonight|today|tomorrow|this\s+(?:afternoon|morning|evening|week)|later\s+today|first\s+thing|shortly|"
    r"soon|in\s+(?:an?\s+)?(?:hour|few\s+(?:minutes|hours))|within\s+the\s+hour|by\s+(?:eod|end\s+of\s+(?:the\s+)?"
    r"day|the\s+weekend|noon)|(?:just|right)\s+now|now(?=\s*$)|(?<!every\s)(?<!each\s)%s\b(?!s))" % _WEEKDAY, re.I)
_R_ARRIVE_HIT_RE = re.compile(r"\b(?:hit|hits|reach|reaches)\s+your\s+%s$" % _MODS, re.I)
# The finished system, not a test set up now: an event ("when a quote lands",
# "each time a lead books", "as soon as it lands"), the project's own stream
# ("a copy of each reply") or a recurring time ("a daily summary").
_EVENT_CLAUSE_RE = re.compile(
    r"\b(?:when|whenever|each\s+time|every\s+time|as\s+soon\s+as|once|any\s+time|anytime)\s+"
    r"(?:a|an|the|each|every|any|new|your|their|someone|somebody|one|it(?!')|they)\b", re.I)
_RECURRING_RE = re.compile(r"\b(?:daily|weekly|nightly|hourly|monthly|(?:every|each)\s+(?:morning|day|night|evening|"
                           r"afternoon|week|weekday|hour|month|%s))\b" % _WEEKDAY, re.I)
_NOW_TIME_RE = re.compile(
    r"\b(?:now|right\s+now|today|tonight|tomorrow|this\s+(?:afternoon|morning|evening|week)|later\s+today|noon|"
    r"%s|\d{1,2}(?::\d{2})?\s*(?:am|pm))\b" % _WEEKDAY, re.I)
# Lorenzo setting the project up to reach the client, channel word or not: "I
# can get the bot to message you so you can test it".
_PROJECT_REACH_YOU_RE = re.compile(
    r"\b(?:the|a|an|my|our|this|that|your)\s+(?:[\w'-]+\s+){0,2}?(?:%s)\s+(?:(?:to|can|could|will|would|should|"
    r"may|might)\s+)?(?:message|messages|text|texts|"
    r"call|calls|ring|rings|ping|pings|email|emails|dm|dms|whatsapp|whatsapps|reach|reaches|contact|contacts|send|"
    r"sends)\s+you\b" % _PROJECT_HEADS, re.I)
# A phone number or line that belongs to the project: "text the test number
# to try it", "call the Twilio line".
_R_PROJECT_LINE_RE = re.compile(
    r"^\s+(?:the|a|your)\s+(?:test|demo|bot'?s?|twilio|business|shop|showroom|office|main|company|toll-?free|"
    r"tracking|sandbox|new)\s+(?:phone\s+)?(?:number|line)\b", re.I)
# "is email ok?", "would text be easier?", "does email work?"
_L_ASK_OK_RE = re.compile(r"^\s*(?:(?:and|or|but|so|also|just)[,\s]+)?(?:is|would|will|does|could|can|should)\s+"
                          r"(?:a\s+|an\s+)?$", re.I)
_R_OK_RE = re.compile(r"^\s+(?:(?:be|also|still)\s+)*(?:ok|okay|fine|good|alright|all\s+right|easier|easiest|better|"
                      r"best|possible|an\s+option|quicker|faster|simpler|preferred|work|works|suit\s+you|suits\s+you)"
                      r"\b", re.I)
# "email or here, whichever you prefer"
_R_OR_HERE_RE = re.compile(r"^\s*,?\s*(?:or|and|/)\s+(?:(?:on|via|in|through)\s+)?(?:here|upwork)\b", re.I)
# The channel used as a verb: "email it tonight", "text it over".
_VERB_WORDS = frozenset(("email", "e-mail", "emailed", "emailing", "text", "texted", "texting", "whatsapp",
                         "whats app", "whatsapped", "dm", "dmed", "dm'd", "slack", "slacked", "skype", "telegram",
                         "signal", "imessage", "sms", "smsed"))
_R_VERB_OBJ_RE = re.compile(r"^\s+(?:it|this|that|these|those|everything|both|over|across|back|out|along|the|a|an|my|"
                            r"your)\b", re.I)
# "email it to you", "text the link over to me"
_R_TO_PERSON_RE = re.compile(
    r"^\s+(?:it|this|that|these|those|them|everything|(?:the|a|an|my)\s+[\w'-]+(?:\s+[\w'-]+)?)\s+(?:over\s+|"
    r"across\s+|back\s+)?to\s+(?:you|me|(?-i:us))\b", re.I)
# "will email it tonight": Lorenzo with the "I" dropped
_L_DROPPED_LZ_RE = re.compile(
    r"^\s*(?:(?:sure|ok|okay|yes|yep|yeah|absolutely|of\s+course|no\s+problem|will\s+do|great|perfect|"
    r"sounds\s+good)[,.!\s]+)*(?:will|can|could|gonna|going\s+to|about\s+to|happy\s+to|glad\s+to)\s+"
    r"(?:also\s+|just\s+|then\s+|quickly\s+)?$", re.I)
# A stream of the project's own messages: "replies", "each new lead", "new
# requests". A single notice ("a text", "an alert") counts only when Lorenzo
# is not the one sending it ("you'll get a text on your phone").
_STREAM_PLURAL = (r"(?:alerts|notifications|reminders|replies|responses|leads|requests|messages|texts|emails|"
                  r"bookings|appointments|quotes|orders|submissions|payments|invoices|receipts|confirmations|tickets|"
                  r"deals|calls|recordings|transcripts|summaries|reports|digests|inquiries|enquiries|signups|sign-ups|"
                  r"reviews|voicemails|pings)")
_STREAM_SINGULAR = (r"(?:alert|notification|reminder|reply|response|lead|request|message|text|email|booking|"
                    r"appointment|quote|order|submission|payment|invoice|receipt|confirmation|ticket|deal|call|"
                    r"recording|transcript|summary|report|digest|inquiry|enquiry|signup|review|voicemail|ping)")
_STREAM_RE = re.compile(
    r"\b(?:(?:each|every|all|any|new|incoming|inbound|missed|those|these|their)\s+(?:[\w'-]+\s+){0,2}?%s|%s)\b"
    % (_STREAM_SINGULAR, _STREAM_PLURAL), re.I)
_NOTICE_RE = re.compile(r"\b(?:a|an)\s+(?:quick\s+|short\s+|new\s+)?(?:text|sms|email|alert|notification|message|ping|"
                        r"reminder)\b", re.I)
_R_STREAM_OBJ_RE = re.compile(r"^\s+(?:(?:the|each|every|all|any|new|those|these|their)\s+)?(?:[\w'-]+\s+)?%s\b"
                              % _STREAM_PLURAL, re.I)
# The project's own message types and machinery as an object: "text a reminder
# to each lead", "email the welcome sequence".
_PROJECT_MSG_RE = re.compile(
    r"^\s+(?:(?:the|a|an|each|every|your|their)\s+)?(?:[\w'-]+\s+)?(?:reminders?|confirmations?|alerts?|"
    r"notifications?|follow-?ups?|nudges?|welcome\s+(?:emails?|texts?|messages?)|auto-?repl(?:y|ies)|drips?|"
    r"sequences?|bots?|workflows?|automations?|flows?|forms?)\b", re.I)
_R_TO_END_USER_RE = re.compile(r"^[^.?!\n\x00]{0,40}?\b(?:to|for)\s+(?:(?:each|every|the|your|new|all|any|those)\s+)?"
                               r"(?:[\w'-]+\s+)?%s\b" % _END_USERS, re.I)
_RECEIVE_VERB_RE = re.compile(r"\b(?:have|has|had|get|gets|got|getting|receive|receives|received|see|sees|saw|find|"
                              r"finds|found|expect|expecting|look\s+for|watch\s+for|look\s+out\s+for|watch\s+out\s+"
                              r"for|keep\s+an\s+eye\s+out\s+for|check\s+for)\b", re.I)
# "feel free to text", "text anytime", "you can email it over"
_L_INVITE_TO_RE = re.compile(
    r"(?:\bfeel\s+free\s+to|\bdon'?t\s+hesitate\s+to|\byou'?re\s+(?:always\s+)?welcome\s+to|\bhappy\s+for\s+you\s+to|"
    r"\byou\s+(?:can|could|may)\s+(?:always\s+|also\s+|just\s+|still\s+)?)\s*$|"
    r"^\s*(?:(?:just|please|pls|also|so|then|anytime|otherwise|or|and)[,\s]+)*$", re.I)
_R_BARE_VERB_END_RE = re.compile(
    r"^\s*(?:$|\x00|[.,;:!?)]|(?:me|(?-i:us))\b|(?:anytime|any\s+time|whenever|if|when|once|with|about|for|over|"
    r"back|it|this|that|instead|too|as\s+well|directly|later|tonight|today|tomorrow|now|first|then)\b)", re.I)
_R_KEYWORD_RE = re.compile(r"^\s+[A-Z]{2,}\b")  # "text STOP to opt out"
# "easier over email", "easier to share screenshots over WhatsApp"
_L_EASIER_RE = re.compile(
    r"\b(?:easier|easiest|quicker|quickest|faster|fastest|simpler|simplest|smoother|better|best)\b"
    r"(?:\s+(?:to|for)\s+[\w'-]+(?:\s+[\w'-]+){0,3}?)?\s+(?:over|by|on|via|through|in|with|using)\s+"
    r"(?:the\s+|a\s+)?$", re.I)
# "just replied by email", "sent it over WhatsApp": Lorenzo with the "I" dropped
_L_DONE_VIA_RE = re.compile(
    r"^\s*(?:(?:just|already|also|and)\s+)*(?:replied|responded|answered|sent|emailed|texted|forwarded|messaged|"
    r"wrote|shared|dropped|posted|pinged)\b[^.?!\n\x00]{0,40}?\s+(?:by|via|over|through|on|in|to)\s+"
    r"(?:the\s+|a\s+|an\s+|your\s+)?$", re.I)
# "got your email", "check your inbox", "I saw your text"
_L_GOT_YOURS_RE = re.compile(
    r"\b(?:got|received|saw|seen|read|check|checked|checking|look\s+(?:at|in)|looked\s+(?:at|in)|watch|keep\s+an\s+"
    r"eye\s+on|refresh|open|opened)\s+your\s+%s$" % _MODS, re.I)
# "my calendar is open Thursday, grab a slot", "grab a slot"
_MY_CALENDAR_RE = re.compile(r"\b(?:my|our)\s+(?:calendar|schedule|availability|diary|calendar\s+link|booking\s+page|"
                             r"scheduling\s+page)\b", re.I)
_SLOT_WORD_RE = re.compile(r"\b(?:slots?|grab|snag|link|(?:book|pick|choose|reserve)\s+(?:a|any|one)\s+(?:time|slot|"
                           r"spot))\b", re.I)
_GRAB_SLOT_RE = re.compile(
    r"^\s*(?:(?:just|so|then|and|please|feel\s+free\s+to)[,\s]+)*(?:(?:grab|book|snag|reserve|pick|choose)\s+"
    r"(?:a|any|one|the)\s+(?:open\s+|free\s+)?(?:slot|spot)|(?:grab|book|snag|reserve)\s+(?:a|any|one)\s+"
    r"(?:time|call))\b", re.I)
_UPWORK_RE = re.compile(r"\bupwork\b", re.I)
# "I'll send the details to the address you gave"
_GIVEN_ADDRESS_RE = re.compile(
    r"\b(?:to|at|on|into)\s+the\s+(?:e-?mail\s+|phone\s+)?(?:address|number|email|inbox|phone)\s+(?:that\s+)?you\s+"
    r"(?:gave|shared|sent|mentioned|provided|listed|left|used|put|wrote|have\s+on\s+file)\b", re.I)
# Lorenzo adding the client to, or joining, a group, workspace or channel:
# "I'll add you to the WhatsApp test group", "I can join your Slack".
_ADD_YOU_TO_RE = re.compile(
    r"\b(?:add|adding|invite|inviting|bring|bringing|put|putting|loop|looping|pull|pulling)\s+you\s+(?:in\s+)?"
    r"(?:to|into|in|on|onto)\s+(?:the\s+|a\s+|an\s+|my\s+|our\s+|your\s+|this\s+|that\s+)?(?:[\w#'-]+\s+){0,3}?"
    r"(?:group|groups|channel|channels|workspace|workspaces|server|servers|community|space|chat|thread|slack|"
    r"discord|whatsapp|telegram|teams|signal|skype)\b", re.I)
_ADD_YOU_AS_RE = re.compile(
    r"\b(?:add|adding|invite|inviting|set\s+you\s+up|make)\s+(?:you\s+)?(?:up\s+)?as\s+(?:a|an|the)?\s*(?:beta\s+)?"
    r"(?:tester|test\s+user|test\s+contact|user|contact|member|admin|guest|collaborator)\b", re.I)
# A group or channel Lorenzo sets up for himself and the client: "I'll create
# a Slack channel for us", "I'll set up a shared WhatsApp group for updates",
# "a private Slack channel for the project". One for the client's team or
# customers is the project ("a shared WhatsApp group for your installers").
_OPEN_GROUP_RE = re.compile(
    r"\b(?:set\s+up|setup|create|make|start|open|spin\s+up)\s+(?:a|an|the|our)\s+(?P<mods>(?:[\w-]+\s+){0,3}?)"
    r"(?:group(?:\s+chat)?|channel|workspace|chat|thread|server|space)\b(?P<rest>[^.?!\n\x00]{0,40})", re.I)
_GROUP_FOR_US_RE = re.compile(
    r"^[^.?!\n]{0,30}?\b(?:for\s+(?:us|you\s+and\s+me|the\s+two\s+of\s+us|our\s+\w+)|with\s+you|between\s+us|"
    r"so\s+(?:we|you\s+and\s+i)\s+can|and\s+(?:me|us|myself)|(?:me|us)\s+and\s+your)\b", re.I)
_GROUP_PURPOSE_RE = re.compile(
    r"^\s+for\s+(?:(?:the|our|any|all|project|progress|build|status|quick|daily|weekly)\s+)*(?:updates|questions|"
    r"feedback|check-?ins|communication|comms|coordination|collaboration|project|build|this|revisions|approvals|"
    r"files|screenshots|voice\s+notes)\b", re.I)
_SHARED_MOD_RE = re.compile(r"\b(?:shared|private|joint|common|dedicated)\b", re.I)
_TEAM_WORD_RE = re.compile(r"\b(?:team|teams|reps?|staff|installers?|techs?|technicians?|crews?|front\s+desk|agents?|"
                           r"employees|dispatchers?|managers?|drivers?|office)\b", re.I)
# Right after a purpose, updates that go *to* the client's people: "a WhatsApp
# group for updates to your installers" is the project's dispatch group.
_GROUP_AUDIENCE_RE = re.compile(r"\s+to\s+(?:(?:your|the|our|each|every|all|any)\s+)?(?:[\w'-]+\s+){0,2}?"
                                + _TEAM_WORD_RE.pattern, re.I)
_GROUP_PLATFORM_RE = re.compile(r"\b(?:whats\s?app|slack|telegram|discord|teams|signal|google\s+chat|imessage|"
                                r"messenger|skype)\b", re.I)
# The client's people named before the purpose: "a WhatsApp group with your
# team for updates".
_GROUP_WITH_TEAM_RE = re.compile(r"\s+with\s+(?:(?:your|the|our)\s+)?(?:[\w'-]+\s+){0,2}?"
                                 + _TEAM_WORD_RE.pattern, re.I)
# Asking where or how to reach the client, with no channel named: "where
# should I send the scope?", "how should I get it to you?", "what's the best
# way to reach you?", "tell me where to send it". The project's routing
# passes: its own actor ("where should the bot send the quote requests?"), its
# stream or users ("where should I send the new leads?") or a tool it runs on
# ("..., HubSpot or Pipedrive?"), and so does anything said here on Upwork.
_SEND_VERB = r"(?:send|forward|share|deliver|drop|pass|mail|email|e-mail)"
# "... to you", "... with you", or "you" plus the thing sent ("send you the
# Loom"), not "get you started"
_TO_YOU = (r"(?:[^.?!\n\x00]{0,40}?\b(?:to|with)\s+you\b|\s+you\s+(?:the|a|an|this|that|these|those|it|them|my|our|"
           r"everything)\b)")
_ASK_DESTINATION_RES = (
    re.compile(r"\bwhere(?:'s|\s+is)?\b[^.?!\n\x00]{0,40}?\b(?:i|we|me)\b[^.?!\n\x00]{0,20}?\b(?P<verb>%s)\b"
               % _SEND_VERB, re.I),
    re.compile(r"\bwhere\s+(?:to|you(?:'d)?\s+(?:want|like)\s+(?:me|us)\s+to)\s+(?P<verb>%s)\b" % _SEND_VERB, re.I),
    re.compile(r"\bwhere\s+(?:would|do)\s+you\s+(?:want|like)\s+(?P<obj>it|this|that|them|the\s+[\w-]+(?:\s+[\w-]+)?)"
               r"\s+(?P<verb>sent|delivered|emailed|forwarded|shared|dropped|mailed)\b", re.I),
    re.compile(r"\bwhere(?:'s|\s+is)\s+(?:the\s+)?(?:best|easiest|right|preferred|quickest)\s+(?:place|spot)\s+to\s+"
               r"(?P<verb>%s)\b" % _SEND_VERB, re.I),
    re.compile(r"\bhow\b[^.?!\n\x00]{0,30}?\b(?:i|we|me)\b[^.?!\n\x00]{0,20}?\b(?P<verb>send|forward|share|deliver|"
               r"get|pass|mail)\b%s" % _TO_YOU, re.I),
    re.compile(r"\b(?:best|easiest|quickest|simplest|preferred|right|good)\s+way\s+(?:for\s+(?:me|us)\s+)?to\s+"
               r"(?P<verb>(?:send|forward|share|deliver|get|pass|mail)\b%s|(?:reach|contact|get\s+(?:hold\s+of|in\s+"
               r"touch\s+with)|ping|message|catch)\s+you\b)" % _TO_YOU, re.I),
    re.compile(r"\b(?:how|where)\b[^.?!\n\x00]{0,30}?\b(?:i|we|me)\b[^.?!\n\x00]{0,20}?\b(?P<verb>reach|contact|"
               r"get\s+(?:hold\s+of|in\s+touch\s+with)|catch|find|ping)\s+you\b(?!\s+(?:a|an|the|some|more|any)\b)",
               re.I),
)
_PROJECT_TOOLS = (r"(?:hubspot|pipedrive|salesforce|airtable|gohighlevel|highlevel|ghl|zapier|n8n|make\.com|twilio|"
                  r"instantly|smartlead|lemlist|mailchimp|klaviyo|quickbooks|xero|servicetitan|jobber|monday|asana|"
                  r"trello|notion|clickup|crm|pipeline|sheet|spreadsheet|dashboard)")
_PROJECT_TOOL_RE = re.compile(r"\b%s\b" % _PROJECT_TOOLS, re.I)
# A test stream is still the client's own address: "where should I send the
# test texts?" asks for the client's number, as a test number would.
_TEST_STREAM_RE = re.compile(r"\btest\s+(?:[\w-]+\s+)?(?:%s|%s)\b" % (_STREAM_PLURAL, _STREAM_SINGULAR), re.I)
# A workspace that lives in the project's tool: "a shared workspace in
# Airtable", "an Airtable workspace for the project".
_TOOL_HOME_RE = re.compile(r"(?:^\s+on|\b(?:in|inside|within))\s+(?:(?:the|your|our|a|an|its)\s+)?%s\b"
                           % _PROJECT_TOOLS, re.I)
_HERE_RE = re.compile(r"\b(?:upwork|here)\b(?!')", re.I)
# "There" standing for a channel a client message named ("can we move this
# to WhatsApp?"): "just message me there", "happy to continue there", "see
# you there", "I'll send it there tonight". Checked only when a client message
# names a channel, and not when the sentence or the one before it names
# Upwork ("Upwork has calls built in, see you there"). The project and its
# users pass ("the bot will reply there", "customers who message there").
# "there" as a place, not "there is" or "there's"
_THERE_PLACE = (r"(?:over\s+)?there\b(?!\s*(?:is|are|was|were|isn't|aren't|wasn't|weren't|will|won't|would|could|"
                r"should|might|may|must|can|seems?|has|have|had)\b|'(?:s|re|ll|d)\b)")
_THERE = r"\s+" + _THERE_PLACE
_THERE_WORD_RE = re.compile(r"\bthere\b", re.I)
_THERE_ME_RE = re.compile(
    r"\b(?:message|msg|text|ping|email|e-mail|call|ring|dm|pm|reach|contact|find|catch|hit|buzz|write|drop|add)\s+"
    r"(?:me|us)(?:\s+(?:up|a\s+(?:line|note|message|text)))?" + _THERE, re.I)
_THERE_TALK_RE = re.compile(
    r"\b(?:continue|carry\s+on|chat|talk|speak|reply|respond|follow\s+up|pick\s+(?:this|it|things)\s+up|"
    r"keep\s+(?:talking|chatting|going)|connect|move\s+(?:this|it|things|the\s+conversation))" + _THERE, re.I)
_THERE_MEET_RE = re.compile(r"\b(?:see|talk\s+to|speak\s+(?:to|with)|chat\s+with|meet|catch)\s+you" + _THERE, re.I)
_THERE_SEND_RE = re.compile(
    r"\b(?:send|forward|share|email|drop|deliver|pass|mail)\s+(?:over\s+)?(?:it|this|that|them|everything|"
    r"the\s+[\w-]+(?:\s+[\w-]+)?)" + _THERE, re.I)
# Lorenzo doing something with the client there: "happy to walk you through
# it there", "I'll keep you posted there", "I'll send you a copy there".
_THERE_YOU_RE = re.compile(
    r"\b(?:walk|show|keep|get|send|update|brief|ping|message|text|call|email|meet|catch|give|tell|remind|loop|guide|"
    r"contact|reach|invite|add|with)\s+you\b[^.?!\n\x00]{0,30}?" + _THERE_PLACE, re.I)
# "each reply there", "the chat there": a noun, not the conversation moving
_THERE_NOUN_BEFORE_RE = re.compile(r"\b(?:each|every|the|a|an|any|your|their|its|my|our|no|this|that|first|next|last)"
                                   r"\s+$", re.I)
_JOIN_RE = re.compile(
    r"\b(?:join|joining|hop\s+into|jump\s+into|get\s+into|(?:be|get)\s+(?:added|invited)\s+(?:to|into))\s+"
    r"(?:your\s+|the\s+|a\s+)?(?:[\w#'-]+\s+){0,2}?(?:slack|discord|teams|whatsapp|telegram|signal|workspace|server|"
    r"channel|group|community)\b", re.I)
# Lorenzo setting the project up to reach the client now: "I can have the bot
# message you", "I'll set it up so the bot texts you". Describing the finished
# system ("the bot can text you when a quote lands") stays allowed.
_LZ_SETUP_NOW_RE = re.compile(
    r"\b(?:i\s+can|i'll|i\s+will|i\s+could|let\s+me|happy\s+to|glad\s+to|i'?m\s+going\s+to|i\s+am\s+going\s+to|"
    r"i'?m\s+about\s+to|want\s+me\s+to|shall\s+i|should\s+i|can\s+i|could\s+i)\s+"
    r"(?:(?:also|just|quickly|easily|then)\s+)*(?:have|get|set\s+up|setup|set|configure|make|"
    r"point|hook\s+up|program|wire\s+up|spin\s+up|turn\s+on|switch\s+on)\b", re.I)
_TRY_IT_RE = re.compile(
    r"\bso\s+(?:that\s+)?you\s+(?:can|could)\s+(?:try|test|trial|play\s+with|poke\s+at|kick\s+the\s+tires|"
    r"see\s+(?:it|how\s+it)\s+(?:work|working|live|in\s+action)|watch\s+it\s+(?:work|run))\b", re.I)
_PERSON_WORD_RE = re.compile(r"\b(?:me|you|(?-i:us))\b", re.I)
# A meeting that is the subject of a project event: "once a Zoom meeting
# ends". "if a phone call is easier" is an offer, not an event.
_EVENT_LEFT_RE = re.compile(r"^\s*(?:once|when|whenever|after|before|until|each\s+time|every\s+time|as\s+soon\s+as)"
                            r"\s+(?:(?:a|an|the|each|every|any|your)\s+)?(?:[\w'-]+\s+)?$", re.I)
_R_EVENT_VERB_RE = re.compile(
    r"^\s+(?:(?:meeting|call|session|recording|chat|demo)s?\s+)?(?:ends?|ended|finish(?:es|ed)?|starts?|started|"
    r"wraps?\s+up|is\s+over|gets?\s+recorded|is\s+recorded|happens|runs|closes|begins|is\s+done|(?:is|gets?)\s+"
    r"(?:booked|scheduled|created|cancell?ed|moved|rescheduled|missed))\b", re.I)


def _third_party(text: str) -> bool:
    return bool(_END_USER_RE.search(text) or _THEY_RE.search(text))


def _say(m: Mention, why: str) -> str:
    return "off-platform contact (%s): %r" % (why, m.text)


def _person_in(match_text: str) -> str:
    """'me' when the matched words name Lorenzo (me, us), else 'you'."""
    return "me" if re.search(r"\bme\b|\b(?-i:us|Us)\b", match_text, re.I) else "you"


class _Clause(object):
    """One clause, its sentence and the facts its channel words share. Every
    clause-wide search runs once, so a clause full of channel words stays
    linear."""
    __slots__ = ("text", "sentence", "prev", "source_low", "room", "actors", "question", "_memo")

    def __init__(self, text: str, sentence: str = "", prev: str = "", source_low: str = "",
                 room: Optional[Dict[str, Any]] = None) -> None:
        self.text = text
        self.sentence = sentence or text
        self.prev = prev  # the clause before this one in the same sentence
        self.source_low = source_low
        self.room = room
        self.actors = _actors(text)
        self.question = self.sentence.rstrip().endswith("?")
        self._memo = {}  # type: Dict[Any, Any]

    def search(self, rx: Any, where: str = "clause") -> Any:
        key = (rx, where)
        if key not in self._memo:
            self._memo[key] = rx.search(self.sentence if where == "sentence" else self.text)
        return self._memo[key]

    def matches(self, rx: Any) -> List[Any]:
        key = (rx, "all")
        if key not in self._memo:
            self._memo[key] = list(rx.finditer(self.text))
        return self._memo[key]

    def before(self, rx: Any, pos: int) -> bool:
        """rx matches in the clause, ending at or before ``pos``."""
        found = self.matches(rx)
        return bool(found) and found[0].end() <= pos

    def after(self, rx: Any, pos: int) -> bool:
        """rx matches in the clause, starting at or after ``pos``."""
        found = self.matches(rx)
        return bool(found) and found[-1].start() >= pos

    def between(self, rx: Any, start: int, end: int) -> bool:
        return any(start <= f.start() and f.end() <= end for f in self.matches(rx))

    def third_party(self, where: str = "clause") -> bool:
        return bool(self.search(_END_USER_RE, where) or self.search(_THEY_RE, where))

    def setup_now(self, pos: int) -> bool:
        """Lorenzo sets the project up now, before ``pos``: "I can have the bot
        message you", or "I'll set up a test number" followed by "so ..."."""
        if self.before(_LZ_SETUP_NOW_RE, pos):
            return True
        return bool(re.match(r"so\b", self.text, re.I) and _LZ_SETUP_NOW_RE.search(self.prev))

    def design_event(self) -> bool:
        """The sentence describes the finished system rather than a test now:
        an event ("I can have the bot text you when a quote lands"), the
        project's stream ("a copy of each reply") or a recurring time ("a daily
        summary"), with no time for a test now ("tonight", "Thursday") and
        nothing to try ("so you can test it")."""
        if "design" not in self._memo:
            self._memo["design"] = bool(
                (self.search(_EVENT_CLAUSE_RE, "sentence") or self.search(_STREAM_RE, "sentence")
                 or self.search(_RECURRING_RE, "sentence"))
                and not self.search(_NOW_TIME_RE, "sentence") and not self.search(_TRY_IT_RE, "sentence"))
        return self._memo["design"]

    def setup_test(self, pos: int) -> bool:
        """Lorenzo sets the project up before ``pos`` for a test now, not as a
        description of the finished system."""
        return self.setup_now(pos) and not self.design_event()


def _actor_at(actors: List[Tuple[int, int, str, str]], pos: int) -> Optional[Tuple[int, int, str, str]]:
    """The actor nearest before ``pos``, or None."""
    best = None  # type: Optional[Tuple[int, int, str, str]]
    for actor in actors:
        if actor[1] <= pos and (best is None or actor[0] >= best[0]):
            best = actor
    return best


def _lorenzo_acting_before(actors: List[Tuple[int, int, str, str]], pos: int) -> bool:
    """Lorenzo acts (not a conditional "I'd") anywhere in the clause before ``pos``."""
    return any(a[1] <= pos and _acting_lorenzo(a[2], a[3]) for a in actors)


def _lorenzo_subject(lead_in: str) -> bool:
    """The verb right after ``lead_in`` is Lorenzo's: "mind if I", "I'll",
    "happy to", or the "I" dropped at the clause start ("will call")."""
    return bool(_LZ_SUBJECT_END_RE.search(lead_in) or _L_DROPPED_LZ_RE.search(lead_in))


def _project_asks(ctx: "_Clause", pos: int, machinery: bool = True) -> bool:
    """After ``pos`` the clause names the project's users or messages (or,
    with ``machinery``, its sender, accounts or tools), so a question about a
    contact detail is the project's."""
    return bool(ctx.after(_END_USER_RE, pos) or ctx.after(_THEY_RE, pos) or ctx.after(_STREAM_RE, pos)
                or (machinery and ctx.after(_PROJECT_USE_RE, pos)))


_MODAL_GAP_RE = re.compile(r"\s*(?:(?:can|could|will|would|should|may|might|also|just|then|automatically|always|"
                           r"instantly|immediately|still|only)\s+)*$", re.I)
_VERB_BEFORE_YOUR_RE = re.compile(r"(?:^|\s)([\w'-]+)\s+your\s+%s$" % _MODS, re.I)


def _project_subject_of(ctx: "_Clause", pos: int) -> bool:
    """The project is the subject of the verb at ``pos`` ("the bot can text
    ..."), as the finished system, not set up by Lorenzo for a test now."""
    actor = _actor_at(ctx.actors, pos)
    return bool(actor and actor[2] == "project" and _MODAL_GAP_RE.match(ctx.text[actor[1]:pos])
                and not ctx.setup_test(pos))


def _stream_before(ctx: "_Clause", pos: int) -> bool:
    """Between the nearest actor and ``pos`` the clause names the project's
    stream or end users ("replies", "each new lead"), or a single notice
    that Lorenzo does not send ("you'll get a text")."""
    actor = _actor_at(ctx.actors, pos)
    zone = actor[1] if actor else 0
    return bool(ctx.between(_STREAM_RE, zone, pos) or ctx.between(_END_USER_RE, zone, pos)
                or (not _lorenzo_acting_before(ctx.actors, pos) and ctx.between(_NOTICE_RE, zone, pos)))


def _strong_reason(ctx: _Clause, m: Mention) -> Optional[str]:
    """Direction that holds whoever acts: a person target, a possessive, a
    request for contact details, a move of the conversation, the channel used
    as a verb by Lorenzo or offered to the client. One exception: when the
    project acts and the target is the client ("the bot can text you when a
    lead books", "customers who message you on WhatsApp"), the channel is the
    project's subject, unless Lorenzo sets it up now ("I can have the bot text
    you") or it is there for the client to try ("so you can test it")."""
    clause, actors = ctx.text, ctx.actors
    left, right = _tail(clause, m.start), _head(clause, m.end)
    kind, _ = _actor_before(actors, m.start)
    project = kind == "project"
    number_word = m.cat == "phone" and not re.match(r"phones?\b", m.text, re.I)
    contact_cats = ("chat", "meet", "social", "dm", "email", "text", "phone", "contact")
    low = m.text.lower()

    def at(i: int) -> int:
        """Clause position of index ``i`` of ``left``."""
        return m.start - len(left) + i

    def project_to_you(pos: int, words: str) -> bool:
        """The project acts at ``pos`` and the target is the client, as the
        finished system does it (not set up now for a test)."""
        return (_actor_before(actors, pos)[0] == "project" and _person_in(words) == "you"
                and not ctx.setup_test(pos) and not ctx.search(_TRY_IT_RE, "sentence"))

    # "WhatsApp you", "email me", "text you the link", "email it to you"
    rp = _R_PERSON_RE.match(right) or (_R_TO_PERSON_RE.match(right) if low in _VERB_WORDS else None)
    if m.cat in _VERB_CATS and rp and not _L_NOUN_BEFORE_RE.search(left) and not number_word:
        if not project_to_you(m.start, rp.group(0)):
            return _say(m, "used as a way to reach a person")
    # "send me an email", "send you a Teams invite", "give me a WhatsApp"
    gp = _L_GIVE_PERSON_RE.search(left)
    if m.cat != "phone" and gp and not project_to_you(at(gp.start()), gp.group(0)):
        return _say(m, "sent to Lorenzo or the client")
    # "message me on WhatsApp", "call you on WhatsApp", "get back to you via
    # email", "call me Thursday at noon on WhatsApp"
    pp = _L_PERSON_PREP_RE.search(left) or _L_PERSON_IN_RE.search(left) or _L_PERSON_VIA_RE.search(left)
    if pp and not (m.cat == "phone" and low.startswith("number")):
        if not project_to_you(at(pp.start()), pp.group(0)):
            return _say(m, "Lorenzo or the client reached through it")
    # "walk you through it on Zoom", "show you the bot live on WhatsApp"
    through = _L_PERSON_THROUGH_RE.search(left)
    if (through and m.cat in ("meet", "chat", "phone", "social")
            and _actor_before(actors, at(through.start()))[0] != "project"):
        mid = through.group("mid")
        if (m.cat == "meet" or ctx.search(_TIME_CUE_RE) or not _PROJECT_NP_RE.search(mid)):
            return _say(m, "a walkthrough with the client on it")
    # "a shared WhatsApp group with you", "a Slack channel with you"
    wp = _R_WITH_PERSON_RE.match(right)
    if m.cat in contact_cats and wp and not project_to_you(m.start, wp.group(0)):
        return _say(m, "a channel shared with the client")
    # "here or on WhatsApp", "on Upwork, or email if that's easier", "email or here"
    if m.cat in contact_cats and (_L_HERE_OR_RE.search(left) or (_R_OR_HERE_RE.match(right) and not project)):
        return _say(m, "offered as an alternative to Upwork")
    # "WhatsApp is the fastest way to get me", "the best way to reach me is email"
    if m.cat in contact_cats and ctx.search(_REACH_ME_RE) and not _project_right(right):
        return _say(m, "the way to reach Lorenzo")
    # "invite me to your Slack"
    if m.cat in contact_cats + ("book",) and _L_INVITE_ME_RE.search(left):
        return _say(m, "Lorenzo joining the client's")
    # "a text from me", "an email from me"
    if m.cat in contact_cats and _R_FROM_ME_RE.match(right):
        return _say(m, "a message from Lorenzo")
    # "we could go over it by phone", "happy to discuss the details on WhatsApp"
    conv = _L_CONVERSE_RE.search(left)
    if (m.cat in ("phone", "meet", "chat", "email", "text") and conv
            and _actor_before(actors, at(conv.start()))[0] != "project" and not _project_right(right)):
        return _say(m, "a conversation with the client on it")
    # "I'll email the proposal over tonight", "I'll text the front desk"
    if (m.cat in ("email", "text", "chat", "dm") and _L_LZ_VERB_SLOT_RE.search(left)
            and not _R_END_USER_OBJ_RE.match(right) and not _R_PROJECT_RE.match(right)
            and re.match(r"^\s+(?:[\w'-]+)", right)):
        return _say(m, "Lorenzo reaching the client through it")
    # The channel as a verb with Lorenzo acting anywhere earlier in the clause:
    # "I'll write it up and email it tonight", "will email it over". Passes for
    # an end user or the project's own messages ("I'll text the reminder to
    # each lead").
    if (low in _VERB_WORDS and _R_VERB_OBJ_RE.match(right) and not _L_NOUN_BEFORE_RE.search(left) and not project
            and (_lorenzo_acting_before(actors, m.start) or _L_DROPPED_LZ_RE.search(left))
            and not (_R_END_USER_OBJ_RE.match(right) or _R_PROJECT_RE.match(right) or _R_STREAM_OBJ_RE.match(right)
                     or _PROJECT_MSG_RE.match(right) or _R_TO_END_USER_RE.match(right))):
        return _say(m, "Lorenzo sending through it")
    # An invitation to use the channel: "feel free to text", "text anytime",
    # "you can email it over". "you can text the bot yourself" is the project,
    # unless Lorenzo is setting that test line up now.
    if (low in _VERB_WORDS and low not in ("sms", "smsed") and not _L_NOUN_BEFORE_RE.search(left)
            and kind in ("imperative", "client", "none") and _L_INVITE_TO_RE.search(left)):
        if _R_BARE_VERB_END_RE.match(right):
            return _say(m, "offered as a way to reach Lorenzo")
        project_obj = (_R_END_USER_OBJ_RE.match(right) or _R_PROJECT_NEXT_RE.match(right)
                       or _R_KEYWORD_RE.match(right) or _R_PROJECT_RE.match(right) or _PROJECT_MSG_RE.match(right)
                       or _R_PROJECT_LINE_RE.match(right))
        if _R_VERB_OBJ_RE.match(right) and not project_obj:
            return _say(m, "offered as a way to reach Lorenzo")
        if project_obj and ctx.setup_now(m.start):
            return _say(m, "a test line Lorenzo sets up for the client")
    # "I'd rather use email for the scope"
    if (m.cat in contact_cats and _L_PREFER_RE.search(left) and not project
            and (_R_PREFER_TOPIC_RE.match(right) or (m.cat != "text" and _R_PREFER_TAIL_RE.match(right)))):
        return _say(m, "offered as the way to talk")
    # "is WhatsApp ok for you", "would email be easier for you"
    if (m.cat in contact_cats + ("pay",) and _R_OK_FOR_PERSON_RE.match(right) and not project):
        return _say(m, "offered as the way to talk or pay")
    # "is email ok?", "would text be easier?", unless it is for the project's
    # end users, messages or machinery ("is SMS ok for the leads?", "is email
    # ok for the drip?")
    if (m.cat in contact_cats and _L_ASK_OK_RE.search(left) and _R_OK_RE.match(right) and not project
            and not _project_asks(ctx, m.end)):
        return _say(m, "offered as the way to talk")
    # "which is better for you, email or phone?", "do you prefer email or a
    # call?", unless it is about the project's users, messages or machinery
    if (m.cat in contact_cats and ctx.question and not project and ctx.search(_ASK_PREFER_RE, "sentence")
            and not ctx.third_party() and not ctx.search(_STREAM_RE) and not ctx.search(_PROJECT_USE_RE)):
        return _say(m, "asks which way the client wants to talk")
    # "easier over email", "easier to share screenshots over WhatsApp"
    if (m.cat in contact_cats and _L_EASIER_RE.search(left) and not project and not ctx.third_party()
            and not ctx.search(_STREAM_RE) and not _project_right(right)):
        return _say(m, "offered as the easier way to talk")
    # "just replied by email", "sent it over WhatsApp"
    if (m.cat in contact_cats and _L_DONE_VIA_RE.search(left) and not ctx.third_party()
            and not ctx.search(_STREAM_RE) and not _project_right(right)):
        return _say(m, "Lorenzo's message sent through it")
    # "got your email", "check your inbox", "I saw your text"
    if (m.cat in ("email", "text", "phone", "chat", "dm", "contact") and _L_GOT_YOURS_RE.search(left) and not project
            and not _R_PROJECT_RE.match(right) and not ctx.after(_END_USER_RE, m.end)
            and not ctx.after(_STREAM_RE, m.end)):
        return _say(m, "the client's own inbox or phone")
    # possessive: "my PayPal", "send it to my email", "our WhatsApp"
    mine = _L_MINE_RE.search(left)
    if mine:
        before_my = left[:mine.start()]
        device = m.key in ("inbox", "mailbox") or low in ("phone", "phones")
        if m.cat in ("chat", "social", "book", "pay", "dm", "meet", "contact"):
            return _say(m, "Lorenzo's own")
        if _R_PROJECT_RE.match(right):
            pass  # "my email sequences"
        elif (_R_CONTACT_DATA_RE.match(right) or ctx.before(_TRANSFER_VERB_RE, at(mine.start()))
              or _ACCESS_VERB_RE.search(before_my)
              or (not device and re.match(r"^\s*[.,?!]?\s*$", right))):
            return _say(m, "Lorenzo's own")
    # a request for the client's details: "what's your email", "drop your number"
    if m.cat in ("email", "phone", "chat", "social", "book", "pay", "dm", "meet", "contact"):
        # The finished system using the client's line passes when the project
        # is the verb's own subject: "the bot can text your cell when a quote
        # lands", "can the bot text your cell?" ("the bot works fine, what's
        # your email?" is still Lorenzo asking).
        req = _L_REQUEST_RE.search(left)
        if (req and not _R_PROJECT_RE.match(right) and not ctx.after(_END_USER_RE, m.end)
                and not ctx.after(_THEY_RE, m.end) and not _project_subject_of(ctx, at(req.start()))):
            return _say(m, "asks for the client's contact details")
        if _L_YOURS_RE.search(left) and re.match(r"^\s*\?", right):
            verb = _VERB_BEFORE_YOUR_RE.search(left)
            if not (verb and _project_subject_of(ctx, at(verb.start(1)))):
                return _say(m, "asks for the client's contact details")
        if _L_BEST_RE.search(left) and _R_REACH_RE.match(right):
            return _say(m, "asks for the client's contact details")
        if (m.cat in ("chat", "social", "meet", "email", "phone", "text") and _L_ARE_YOU_ON_RE.search(left)
                and not _R_PROJECT_RE.match(right) and not project):
            return _say(m, "asks for the client's contact details")
    # Any question or request about the client's email, phone, number, cell
    # or contact info, whatever the question word: "what number should I
    # call", "which email should I send it to", "is there a good number for
    # you", "mind if I call your cell Thursday?"
    # The project may ask ("which email should I send the drip from", "which
    # number should I use for the bot", "is there an inbox the replies should
    # go to").
    if m.cat in ("email", "phone", "contact") and not project and not _R_PROJECT_RE.match(right):
        asks_project = _project_asks(ctx, m.end, machinery=not _R_SEND_TO_RE.match(right))
        if _L_ASK_WH_RE.search(left) and _R_ASK_USE_RE.match(right) and not asks_project:
            return _say(m, "asks for the client's contact details")
        if _L_IS_THERE_RE.search(left) and not _R_PROJECT_NEXT_RE.match(right) and not asks_project:
            return _say(m, "asks for the client's contact details")
        yours = _L_CONTACT_YOURS_RE.search(left)
        if yours and (_lorenzo_subject(left[:yours.start()]) or ctx.setup_test(at(yours.start()))):
            return _say(m, "Lorenzo reaching the client's own line")
        if _L_YOURS_RE.search(left) and ctx.question and not asks_project:
            actor = _actor_at(actors, m.start)
            zone = actor[1] if actor else 0
            if not (ctx.between(_STREAM_RE, zone, m.start) or ctx.between(_END_USER_RE, zone, m.start)):
                return _say(m, "asks about the client's contact details")
    # The client's inbox or phone as the destination: "I'll send it to your
    # email", "you'll have it in your inbox tonight". The project's own stream
    # passes ("I'd forward replies to your inbox", "you'll get a text on your
    # phone when a lead books").
    dest = _L_DEST_YOURS_RE.search(left)
    if (m.cat in ("email", "phone", "chat", "dm", "social", "pay", "text", "contact") and dest and not project
            and not _R_PROJECT_RE.match(right)):
        dest_pos = at(dest.start())
        if (not _stream_before(ctx, dest_pos)
                and (ctx.before(_TRANSFER_VERB_RE, dest_pos) or ctx.before(_RECEIVE_VERB_RE, dest_pos)
                     or ctx.setup_test(dest_pos)  # "I'll point the test number at your cell"
                     or ctx.search(_TRY_IT_RE, "sentence"))):  # "hook the bot up to your WhatsApp so you can test it"
            return _say(m, "sent to the client's own")
    # Something arriving there at a set time: "it'll be in your inbox by
    # Friday", "the scope will land in your inbox tonight", "it'll hit your
    # inbox tonight". The project's messages and machinery pass ("replies land
    # in your inbox", "the daily summary lands in your inbox at 8am"); a bare
    # "it" with a one-off time is Lorenzo's.
    spot = dest or _R_ARRIVE_HIT_RE.search(left)
    if (m.cat in ("email", "phone", "text", "contact") and spot and ctx.search(_ONE_OFF_TIME_RE)
            and not _R_PROJECT_RE.match(right) and not ctx.search(_RECURRING_RE)):
        spot_pos = at(spot.start())
        actor = _actor_at(actors, spot_pos)
        project_actor = actor is not None and actor[2] == "project" and actor[3] not in ("it", "it'll", "it's")
        arriving = spot is not dest or ctx.before(_ARRIVE_RE, spot_pos)
        if arriving and not project_actor and not _stream_before(ctx, spot_pos):
            return _say(m, "Lorenzo's own arriving there")
    # "I'm around on WhatsApp", "I'm easier to reach on WhatsApp"
    if m.cat in ("chat", "meet", "social", "phone", "email", "text", "dm") and _L_AVAILABLE_RE.search(left):
        if not _R_PROJECT_RE.match(right):
            return _say(m, "Lorenzo reachable on it")
    # "let's move this to email", "continue by email", "a direct chat"
    if (m.cat in ("email", "text", "phone", "chat", "meet", "social", "dm") and _L_MOVE_RE.search(left)
            and not ctx.after(_R_MOVE_PROJECT_RE, m.end) and not project):
        return _say(m, "the conversation moved to it")
    # "Telegram works too", "PayPal works for me", "if Upwork is slow, WhatsApp
    # works too", "a voice call might be quicker", "WhatsApp works better for
    # voice notes"
    works = _WORKS_RE.match(right)
    if (_L_CLAUSE_START_RE.match(left.split(",")[-1]) and works and not ctx.after(_R_MOVE_PROJECT_RE, m.end)
            and (re.search(r"\b(?:me|you|(?-i:us)|my)\b", works.group(0), re.I) or not ctx.third_party())):
        return _say(m, "offered as the way to talk or pay")
    # on a network: "lorenzov on LinkedIn", "search my name on LinkedIn",
    # "connect with me on LinkedIn", "I sent you a connection request"
    if m.cat in ("social", "chat"):
        if ctx.search(_LORENZO_ID_RE) or ctx.search(_MY_IDENTITY_RE) or _HANDLE_SHAPED_RE.search(left):
            return _say(m, "Lorenzo's profile on it")
    if m.cat == "social" and ctx.search(_SOCIAL_PERSON_RE) and not project and not _project_right(right):
        return _say(m, "a connection with Lorenzo on it")
    return None


def _weak_reason(ctx: _Clause, m: Mention) -> Optional[str]:
    """Direction that depends on who acts: refused when the nearest actor is
    Lorenzo, the client or an imperative, passed when it is the project."""
    clause, actors = ctx.text, ctx.actors
    left, right = _tail(clause, m.start), _head(clause, m.end)
    kind, text = _actor_before(actors, m.start)
    project = kind == "project"
    if m.cat == "pay":
        for rx in _PAY_STRONG_RES:
            if ctx.search(rx):
                return _say(m, "payment between Lorenzo and the client")
        if _project_right(right) or _R_ACTION_RE.match(right) or _L_PROJECT_DET_RE.search(left) or project:
            return None
        if _L_PAY_ACCEPT_RE.search(left):
            return _say(m, "payment to Lorenzo")
        if _L_SEND_INVOICE_RE.search(left) and _R_INVOICE_RE.match(right):
            return _say(m, "an invoice from Lorenzo")
        # "payment via PayPal works", "the deposit through Wise is fine"
        if _L_PAYMENT_VIA_RE.search(left) and (_WORKS_RE.match(right) or _R_OK_FOR_PERSON_RE.match(right)
                                               or re.match(r"^\s*(?:[.,;?!]|$)", right)):
            return _say(m, "payment for the work")
        # "PayPal for the deposit", "the rest can go through Wise": money for
        # Lorenzo's engagement, unless the client's own words use that word
        for word in ctx.matches(_ENGAGEMENT_PAY_RE):
            if word.group(0).lower() not in ctx.source_low and not ctx.third_party("sentence"):
                return _say(m, "payment for the work")
        return None
    if m.cat == "book":
        # A booking link or invite is the project's unless it serves a call
        # with Lorenzo: "for a call", a slot Lorenzo or the client books on it
        # ("grab any slot on your Calendly"), or a time with no project actor.
        if (ctx.search(_FOR_A_CALL_RE) or ctx.search(_CALL_INTENT_RE, "sentence")) and not project:
            return _say(m, "a booking link for a call")
        if (_L_BOOK_ACTION_RE.search(left)
                and (_acting_lorenzo(kind, text) or kind in ("client", "imperative"))):
            return _say(m, "a slot booked with Lorenzo on it")
        if not project and ctx.search(_TIME_CUE_RE) and not ctx.third_party():
            return _say(m, "a booking link or invite for a time with Lorenzo")
        return None
    if m.cat == "dm":
        if project or _SOCIAL_OWNER_RE.search(left) or _R_PROJECT_RE.match(right) or ctx.search(_END_USER_RE):
            return None
        return _say(m, "a private channel with Lorenzo")
    if m.cat in ("meet", "chat", "phone"):
        # "Zoom calls" is the project's process, unless Lorenzo is the one on them
        proj_r = _project_right(right) and not (_MEETING_PLURAL_RE.match(right) and _acting_lorenzo(kind, text))
        # "once a Zoom meeting ends, the summary goes to Slack": an event, not a call
        event = (_EVENT_LEFT_RE.match(left) and _R_EVENT_VERB_RE.match(right) and not ctx.search(_PERSON_WORD_RE)
                 and not ctx.search(_TIME_CUE_RE))
        anchored = (project or proj_r or ctx.search(_END_USER_RE) or event
                    or (_PLURAL_PROCESS_RE.search(left) and kind != "lorenzo"))
        here = ctx.search(_UPWORK_RE, "sentence") or re.search(r"\bhere\b", clause, re.I)
        if m.key.startswith("voicecall") and here:
            anchored = True  # "a quick voice call here on Upwork"
        meeting = _L_MEETING_PREP_RE.search(left)
        if meeting and not anchored:
            return _say(m, "a call or meeting on it")
        if (_L_A_QUICK_RE.search(left) and _R_MEETING_NOUN_RE.match(right) and not anchored
                and (m.cat != "phone" or re.match(r"^\s+call", right, re.I))):
            return _say(m, "a call or meeting on it")
        if m.cat in ("meet", "chat") and _L_LETS_RE.search(left) and not anchored:
            return _say(m, "a call or meeting on it")
        # "Thursday at noon on WhatsApp", "on the phone Thursday at noon"
        if (not anchored and (m.cat == "chat" or m.text.lower() in ("phone", "phones"))
                and (_TIME_VENUE_L_RE.search(left) or _TIME_VENUE_R_RE.match(right))):
            return _say(m, "a time to talk on it")
        # A meeting app with no project role, used by Lorenzo, the client or
        # an imperative, or next to a time or a person: "I'll send a Zoom
        # link", "Zoom tomorrow?". "I'd put the Zoom link in the reminder
        # text", "a text with the Zoom link" and "I'd test it on a recorded
        # Zoom meeting first" are the project.
        if m.cat == "meet" and not anchored and not _L_PROJECT_DET_RE.search(left):
            acting = ((_acting_lorenzo(kind, text) and not _R_PROJECT_DEST_RE.match(right))
                      or kind in ("client", "imperative"))
            if acting or ctx.search(_TIME_CUE_RE) or ctx.search(_PERSON_WORD_RE):
                return _say(m, "a meeting app with no project role")
    if m.cat in ("email", "text", "chat", "dm", "social", "phone") and m.key not in ("number",):
        # "I'll send the recap by email", "happy to share it over WhatsApp"
        transfer = re.search(r"\b(?:send|sending|share|sharing|forward|drop|pass|deliver|mail|post|put|shoot|get\s+"
                             r"(?:it|this|that|them)|reach\s+out|reply|respond|answer|write|message|ping|chat|talk|"
                             r"speak|connect|confirm|follow\s+up)\b[^.?!\n]{0,40}\b(?:by|via|over|through|thru|on|in|"
                             r"to|into|using)\s+(?:the\s+|a\s+)?$", left, re.I)
        actual = _acting_lorenzo(kind, text) or kind in ("client", "imperative")
        if transfer and actual and not ctx.search(_END_USER_RE) and not _R_PROJECT_RE.match(right):
            return _say(m, "Lorenzo's message sent through it")
    # "so you can try it on WhatsApp": a live test on the client's own channel
    tried = ctx.search(_TRY_IT_RE)
    if (m.cat in ("chat", "text", "phone", "email", "meet", "dm") and tried and tried.end() <= m.start
            and not _project_right(right)):
        return _say(m, "a live test on the client's own channel")
    return None


def _pay_reason(ctx: _Clause) -> Optional[str]:
    """Payment between Lorenzo and the client whatever the rail, checked on
    every clause: an invoice from Lorenzo ("I'll send you an invoice for the
    deposit", "I'll invoice you through my company", "a separate invoice"),
    money to his account ("pay the deposit to my account", "pay me"), or
    Lorenzo being paid. Payment through Upwork milestones stays allowed, and
    so does the project's own money ("Stripe will charge you", "the bot can
    invoice you")."""
    if ctx.search(_UPWORK_PAY_RE):
        return None
    details = ctx.search(_SEND_PAY_DETAILS_RE)
    if details and _actor_before(ctx.actors, details.start())[0] != "project" and not ctx.third_party():
        return "off-platform contact (payment details from Lorenzo): %r" % details.group(0).strip()
    link = ctx.search(_PAY_LINK_FOR_RE)
    if (link and _actor_before(ctx.actors, link.start())[0] != "project" and not ctx.third_party("sentence")
            and not (link.group("shared") and link.group("shared").lower() in ctx.source_low)):
        return "off-platform contact (a payment link for the work): %r" % link.group(0).strip()
    for inv in ctx.matches(_LZ_INVOICE_RE):
        who = re.sub(r"\s+", " ", inv.group("who").lower())
        if (inv.group("you") or not _LZ_CONDITIONAL_RE.match(who)) and not _R_TO_END_USER_RE.match(
                ctx.text[inv.end():inv.end() + 80]):
            return "off-platform contact (an invoice from Lorenzo): %r" % inv.group(0).strip()
    for rx in _PAY_ANY_RES:
        for hit in ctx.matches(rx):
            if (_actor_before(ctx.actors, hit.start())[0] != "project"
                    and not _PAY_SUBJECT_RE.search(_tail(ctx.text, hit.start(), 80))):
                return "off-platform contact (payment between Lorenzo and the client): %r" % hit.group(0).strip()
    return None


# Round 10: outside a job about payments, a rail other than Upwork in the draft
# is Lorenzo's own payment, offered or accepted, whether the client asked or
# not: "just send a wire", "paying by check works", "cash works too", "a bank
# transfer is fine", "you can pay by Zelle", "PayPal works for me". The rails
# are the pay channel words (bank transfer, wire, ACH, check or cheque, Zelle,
# Venmo, PayPal, Wise, Cash App, crypto, ...) and the ones that list leaves out:
# cash in its money sense ("cash works too", "hand me cash"), an e-transfer, a
# money order, Apple Pay, Google Pay, "wire it over", "send the wire", "once
# the check clears", and a bare pair ("wire or check, either works").
_RAIL_EXTRA_RE = re.compile(
    r"\bcash\b(?!\s*app\b|[\s-]+(?:flows?|registers?|drawers?|back|out|in|on\s+hand|advances?|value|position|"
    r"balances?|basis|reserves?|accounting|sales?|buyers?|offers?|deals?|prices?|discounts?|jobs?|customers?|clients?|"
    r"management|reports?|crunch|cow|prizes?|bonus(?:es)?|rewards?|machines?|box|strapped)\b)|"
    r"\bmoney\s+orders?\b|\be-transfers?\b|\binterac\b|\bapple\s+pay\b|\bgoogle\s+pay\b|"
    r"\bwire\s+(?:it|that|this|them|the\s+(?:money|funds|payment|deposit|balance|rest|fee))\s+(?:over|across)\b|"
    r"\b(?:send|sends|sending|sent|get|got|receive|received|confirm|schedule|initiate)\s+(?:the|your)\s+wire\b|"
    r"\bthe\s+(?:wire|check|cheque)\s+(?:clears?|cleared|lands?|landed|arrives?|arrived|comes\s+(?:in|through)|"
    r"came\s+(?:in|through)|goes\s+through|went\s+through|hits)\b|"
    r"(?<![-\w])(?:wire|check|cheque)\s*(?:/|\bor\b)\s*(?:a\s+)?(?:wire|check|cheque|cash|ach|bank\s+transfer)\b(?!-)"
    r"(?=\s*(?:[,.;:!?)]|$)|\s+(?:is|are|works?|would|both|either|whichever|whatever|fine|ok|okay|also|too)\b)", re.I)
# "cash" as money, not "cash is tight": a pay word before it or a verdict after it
_CASH_MONEY_BEFORE_RE = re.compile(
    r"\b(?:pay|pays|paid|paying|in|by|with|take|takes|taking|took|accept|accepts|accepting|prefer|or|and|plus|via|"
    r"bring|hand|handing)\s+$|\b(?:pay|paid|paying|hand|handing|give|giving|bring|bringing|send|sending)\s+"
    r"(?:me|us|you)\s+$", re.I)
_CASH_MONEY_AFTER_RE = re.compile(
    r"^\s*(?:works?\b|would\s+work\b|(?:is|'s|are)\s+(?:fine|ok|okay|good|great|easiest|easier|best|better|perfect|"
    r"welcome)\b|would\s+be\b|also\b|too\b|as\s+well\b|or\b|and\b|only\b|please\b|payments?\b|up\s*front\b|"
    r"upfront\b|on\s+(?:delivery|pickup|completion)\b|at\s+(?:pickup|delivery|the\s+end)\b|[,;:!?)]|\.|$)", re.I)
# refused, not offered: "no wires, checks or cash", "rather than a wire", "I
# don't take checks", "a check won't be needed" ("no problem", "don't mind",
# "not sure" and "why not" are not refusals)
_RAIL_REFUSED_BEFORE_RE = re.compile(
    r"(?<!\bwhy\s)\b(?:not|no|never|nor|neither|without|instead\s+of|rather\s+than|than|skip(?:ping)?|"
    r"avoid(?:ing)?|cannot|[a-z]+n't|dont|wont|cant|none\s+of)\b"
    r"(?!\s+(?:problem|problems|worries|worry|issue|issues|rush|pressure|trouble|bother|mind|minding|care|object|"
    r"doubt|wonder|surprise|matter|sure|only|just|yet|quite)\b)(?!\s+(?:a|an)\s+(?:problem|big\s+deal|bother|issue)\b)"
    r"(?:(?:\s+|\s*,\s*)(?!(?:but|though|however|although|yet|except|apart|so)\b)[\w'$&/-]+){0,5}[\s,]*$", re.I)
_RAIL_REFUSED_AFTER_RE = re.compile(
    r"^\s*(?:(?:is|are|was|were|would|will|does|do|did|can|could|should)(?:\s+not|n't)|isn't|aren't|won't|"
    r"wouldn't|doesn't|don't|can't|cannot)\b", re.I)
# the means of an Upwork payment: "fund the milestone with a bank transfer",
# "fund it on Upwork with a card or a bank transfer", "PayPal through
# Upwork", "Upwork accepts cards, PayPal and bank transfers" (not "pay
# outside Upwork by wire": _CM_LEAVE_UPWORK_RE)
_RAIL_UPWORK_BEFORE_RE = re.compile(
    r"\b(?:fund|funds|funding|funded|pay|pays|paying|paid|top\s+up|load)\b[^.?!\n]{0,40}?\b(?:milestones?|escrow|"
    r"contract|upwork)\b[^.?!\n]{0,40}?\b(?:with|by|via|using|through|from|in)\s+(?:(?:a|an|the|your)\s+)?"
    r"(?:[\w-]+(?:\s*,\s*|\s+or\s+|\s+and\s+)(?:(?:a|an|the|your)\s+)?){0,3}$|"
    r"\bupwork(?:'s)?\s+(?:also\s+|now\s+)?(?:accepts?|supports?|lets\s+(?:you|clients)\s+(?:pay|fund)\s+(?:with|"
    r"by|via|through|using))\s+(?:[\w-]+(?:,|\s+or|\s+and)?\s+){0,4}$", re.I)
_RAIL_UPWORK_AFTER_RE = re.compile(
    r"^\s*(?:transfers?\s+|payments?\s+)?(?:on|through|via|in|inside|within|into)\s+(?:the\s+)?(?:upwork|"
    r"milestones?|escrow)\b|^\s*(?:to|for)\s+(?:fund\s+)?(?:the\s+|each\s+|your\s+|a\s+)?(?:milestones?|escrow)\b",
    re.I)
# the project's money: "each check", "their wire", "do you take checks?", "your
# front desk accepts cash" (the client's business receiving it)
_RAIL_PROJECT_DET_RE = re.compile(
    r"\b(?:each|every|their|its|incoming|inbound|(?:a|the)\s+(?:customer|patient|homeowner|client|lead|buyer|"
    r"tenant|member|guest)'s)\s+$", re.I)
_RAIL_CLIENT_TAKES_RE = re.compile(
    r"\b(?:you|your\s+(?:team|office|front\s+desk|business|shop|company|staff|crew|reps?|techs?|store))\s+"
    r"(?:(?:also|usually|normally|ever|still|currently|already|mostly|only|even|typically|often|sometimes)\s+)?"
    r"(?:take|takes|accept|accepts|receive|receives|collect|collects|get|gets|see|sees|handle|handles|process|"
    r"processes|record|records|log|logs|track|tracks|reconcile|reconciles|match|matches|deposit|deposits|cash|"
    r"cashes)\b[^.?!\n]{0,40}$", re.I)
# a rail heading a project noun ("check numbers", "wire details field"), but
# "cash payments" and "a wire payment" are the rail itself
_RAIL_NOT_PROJECT_AFTER_RE = re.compile(r"^\s+payments?\b", re.I)
# someone else's habit in a relative clause: "roofers who take cash on site",
# "homeowners that pay by check" (not "anyone who pays me by check")
_RAIL_WHO_RE = re.compile(
    r"\b(?:who|that)\s+(?:(?:also|usually|normally|still|only|often|sometimes|mostly|always|typically)\s+)?(?:pay|pays|"
    r"paid|take|takes|took|accept|accepts|send|sends|mail|mails|bring|brings|hand|hands)\b(?:\s+(?!(?:me|us|lorenzo|"
    r"advero)\b)[\w'-]+){0,3}?\s+$", re.I)
_RAIL_QUICK_RE = re.compile(
    r"\b(?:pay\s?pal|stripe|venmo|zelle|cash|payoneer|revolut|western\s+union|moneygram|crypto|bitcoin|btc|usdt|"
    r"usdc|ethereum|wise|wire|wires|bank|direct\s+deposit|ach|cheques?|checks?|money\s+orders?|e-transfers?|interac|"
    r"apple\s+pay|google\s+pay)\b", re.I)


def _rail_mentions(clause: str) -> List[Tuple[int, int, str]]:
    """(start, end, text) of every rail in its money sense in ``clause``."""
    out = [(m.start, m.end, m.text) for m in channel_mentions(clause) if m.cat == "pay"]
    used = bytearray(len(clause) + 1)  # characters inside a pay channel mention
    for s, e, _ in out:
        used[s:e] = b"\x01" * (e - s)
    for hit in _RAIL_EXTRA_RE.finditer(clause):
        if hit.group(0).lower() == "cash" and not (
                _CASH_MONEY_BEFORE_RE.search(_tail(clause, hit.start(), 40))
                or _CASH_MONEY_AFTER_RE.match(clause[hit.end():hit.end() + 60])):
            continue  # "cash is tight this month", "short on cash in winter"
        if used.find(1, hit.start(), hit.end()) == -1:
            out.append((hit.start(), hit.end(), hit.group(0)))
    return sorted(out)


def _rail_reason(ctx: _Clause) -> Optional[str]:
    """Round 10, outside a payments job: a rail other than Upwork offered or
    accepted for Lorenzo's own payment. It passes when the clause refuses it
    ("no wires", "rather than a check"), makes it the means of an Upwork
    payment ("fund the milestone with a bank transfer"), or makes it the
    project's money: the project or its users act ("customers who pay by
    check", "the bot logs each check", "roofers who take cash"), the client's
    business receives it ("do you take checks?"), it heads a project noun
    ("check numbers"), or a clause with no actor of its own follows one where
    the project acts on its users ("the bot texts the homeowner a thank-you
    once the check clears")."""
    clause = ctx.text
    third = ctx.third_party()
    prev = []  # type: List[bool]  # the clause before is the project's, read once when needed
    for start, end, word in _rail_mentions(clause):
        left, right = _tail(clause, start, 80), _head(clause, end, 80)
        if _RAIL_REFUSED_BEFORE_RE.search(left) or _RAIL_REFUSED_AFTER_RE.match(right):
            continue
        up = _RAIL_UPWORK_BEFORE_RE.search(left)
        if (up and not _CM_LEAVE_UPWORK_RE.search(up.group(0))) or _RAIL_UPWORK_AFTER_RE.match(right):
            continue
        kind = _actor_before(ctx.actors, start)[0]
        if (third or kind == "project" or _RAIL_PROJECT_DET_RE.search(left) or _RAIL_CLIENT_TAKES_RE.search(left)
                or _RAIL_WHO_RE.search(left)
                or (_project_right(right) and not _RAIL_NOT_PROJECT_AFTER_RE.match(right))):
            continue
        if kind == "none" and ctx.prev:
            # "The bot texts the homeowner a thank-you once the check clears":
            # no actor of its own, after a clause where the project acts on
            # its users (not "I'll text the homeowners once the check clears")
            if not prev:
                prev.append(_actor_before(_actors(ctx.prev), len(ctx.prev))[0] == "project" and bool(
                    _END_USER_RE.search(ctx.prev) or _THEY_RE.search(ctx.prev)))
            if prev[0]:
                continue
        return "off-platform contact (payment offered or accepted outside Upwork): %r" % word
    return None


# The project named in the sentence makes a group the project's: its
# actor ("the bot"), a tool it runs on, or a per-item stream ("every job",
# "each GoHighLevel status change").
_PER_ITEM_RE = re.compile(
    r"\b(?:every|each)\s+(?:new\s+)?(?:[\w'-]+\s+){0,2}?(?:jobs?|leads?|quotes?|requests?|orders?|tickets?|deals?|"
    r"bookings?|appointments?|tasks?|installs?|estimates?|invoices?|payments?|submissions?|records?|events?|calls?|"
    r"visits?|shifts?|routes?|deliveries|delivery|photos?)\b|"
    r"\b(?:every|each)\s+(?:new\s+)?(?:[\w'-]+\s+)?(?:status|stage|job|order|lead|quote|ticket|deal|booking|"
    r"appointment|record|field|pipeline|deposit|payment|invoice|shipment|delivery|task|customer|crew|tech|%s)\s+"
    r"(?:changes?|updates?|messages?)\b" % _PROJECT_TOOLS.replace("|monday|", "|"),
    re.I)
# A tool the project runs on, for a group: the weekday is not monday.com
_GROUP_TOOL_RE = re.compile(r"\b%s\b" % _PROJECT_TOOLS.replace(
    "|monday|", r"|monday(?:\.com|\s+(?:board|boards|crm|workspace|items?|account|automations?))|"), re.I)


def _project_named(ctx: _Clause) -> bool:
    """The sentence names the project: its actor (the bot, not the client's
    team), a tool it runs on or a per-item stream. A lead-in before a colon is
    a topic, not the group's content ("one idea on the HubSpot intake: a
    WhatsApp group ...")."""
    if "project_named" not in ctx._memo:
        start = max(ctx.sentence.find(ctx.text), 0)
        head = ctx.sentence[:start]
        cut = max(head.rfind(":"), head.rfind(";"), head.rfind(" - "))
        region = ctx.sentence[cut + 1:] if cut >= 0 else ctx.sentence
        ctx._memo["project_named"] = bool(
            _GROUP_TOOL_RE.search(region) or _PER_ITEM_RE.search(region)
            or any(kind == "project" and not _TEAM_WORD_RE.search(text) for _, _, kind, text in _actors(region)))
    return ctx._memo["project_named"]


def _group_asked_for(ctx: _Clause, hit: Any) -> bool:
    """The job post, the title or a client message (not a request to move off
    Upwork) asks for this kind of group or channel: "post to a WhatsApp group
    for our crews", "a Slack channel with updates on every job"."""
    text = hit.group(0)
    noun = text[hit.end("mods") - hit.start():hit.start("rest") - hit.start()].strip().lower()
    platform = _GROUP_PLATFORM_RE.search(hit.group("mods"))
    if platform:
        rx = re.compile(r"\b%s\s+(?:[\w-]+\s+)?%s\b" % (re.escape(platform.group(0).lower()), re.escape(noun)), re.I)
    else:
        rx = re.compile(r"\b(?:a|an|the|our|one)\s+(?:[\w-]+\s+){0,2}%s\b" % re.escape(noun), re.I)
    room = ctx.room or {}
    job = room.get("job")
    texts = [decode_escapes(job.get("post") or "") if isinstance(job, dict) else "",
             decode_escapes(room.get("job_title") or "")]
    if any(rx.search(t) for t in texts):
        return True
    for msg in room.get("messages") or []:
        if isinstance(msg, dict) and msg.get("side") == "client" and isinstance(msg.get("text"), str):
            body = normalise(decode_escapes(msg["text"]))[:ANALYSIS_MAX_CHARS]
            if rx.search(body) and "group" not in _cm_message_categories(body):
                return True
    return False


def _setup_reason(ctx: _Clause) -> Optional[str]:
    """Bookings, groups and addresses that need no channel word: "my calendar
    is open Thursday, grab a slot", "I'll add you to the WhatsApp test group",
    "I can join your Slack", "to the address you gave"."""
    upwork = ctx.search(_UPWORK_RE, "sentence")
    if not upwork:
        cal = ctx.search(_MY_CALENDAR_RE, "sentence")
        if cal and ctx.search(_SLOT_WORD_RE, "sentence"):
            return "off-platform contact (a booking with Lorenzo): %r" % cal.group(0)
        grab = _GRAB_SLOT_RE.match(ctx.text)
        if grab:
            return "off-platform contact (a booking with Lorenzo): %r" % grab.group(0).strip()
        for rx in (_ADD_YOU_TO_RE, _JOIN_RE, _ADD_YOU_AS_RE):
            for hit in ctx.matches(rx):
                if _actor_before(ctx.actors, hit.start())[0] != "project":
                    return "off-platform contact (a shared group or workspace): %r" % hit.group(0).strip()
        for hit in ctx.matches(_OPEN_GROUP_RE):
            if _actor_before(ctx.actors, hit.start())[0] == "project":
                continue
            rest, mods = hit.group("rest"), hit.group("mods")
            if not _GROUP_FOR_US_RE.match(rest):
                if _PROJECT_TOOL_RE.search(mods) or _TOOL_HOME_RE.search(rest):
                    continue  # "a workspace in Airtable"
                if _project_named(ctx) or _group_asked_for(ctx, hit):
                    continue  # the project's group: "a shared Slack channel for updates, fed from ClickUp"
                purpose = _GROUP_PURPOSE_RE.match(rest)
                with_team = None if purpose else _GROUP_WITH_TEAM_RE.match(rest)
                # a purpose beats the client's team: "a shared WhatsApp group for
                # updates with your team" (or "with your team for updates") is
                # still Lorenzo's group with them; "for updates to your
                # installers" and a project stream are not
                purpose_wins = bool((purpose and not _GROUP_AUDIENCE_RE.match(rest, purpose.end()))
                               or (with_team and _GROUP_PURPOSE_RE.match(rest[with_team.end():])))
                # ... unless a project stream is in the sentence (a group the
                # sentence ties to the project, or one the post or the client
                # asks for, is the project's with or without a team word)
                purpose_wins = purpose_wins and not ctx.search(_STREAM_RE, "sentence")
                if (not purpose_wins and ctx.search(_TEAM_WORD_RE, "sentence")) or ctx.third_party("sentence"):
                    continue  # "a shared channel so your installers see each job"
                if not (purpose_wins or purpose
                        or (_SHARED_MOD_RE.search(mods) and not ctx.search(_STREAM_RE, "sentence"))):
                    continue
            return "off-platform contact (a group for Lorenzo and the client): %r" % hit.group(0).strip()
        if not ctx.search(_HERE_RE):
            for rx in _ASK_DESTINATION_RES:
                hit = ctx.search(rx)
                if hit:
                    pos = hit.start("obj") if "obj" in rx.groupindex else hit.start("verb")
                    stream = ctx.after(_STREAM_RE, pos) and not ctx.after(_TEST_STREAM_RE, pos)
                    if (_actor_before(ctx.actors, pos)[0] != "project" and not stream
                            and not ctx.after(_END_USER_RE, pos) and not ctx.after(_THEY_RE, pos)
                            and not ctx.after(_PROJECT_TOOL_RE, pos)):
                        return "off-platform contact (asks where to reach the client): %r" % hit.group(0).strip()
    # "I can get the bot to message you so you can test it": no channel word,
    # but Lorenzo sets the project up to reach the client for a test now
    reach = ctx.search(_PROJECT_REACH_YOU_RE)
    if reach and ctx.setup_test(reach.start()):
        return "off-platform contact (the project set up to reach the client now): %r" % reach.group(0).strip()
    given = ctx.search(_GIVEN_ADDRESS_RE)
    if given and _actor_before(ctx.actors, given.start())[0] != "project" and not ctx.search(_END_USER_RE):
        return "off-platform contact (sent to the client's own address): %r" % given.group(0).strip()
    return None


def _there_reason(ctx: _Clause) -> Optional[str]:
    """"There" pointing at the channel a client message named: "message me
    there", "happy to continue there", "see you there", "I'll send it there"."""
    if ctx.third_party():
        return None
    for rx in (_THERE_ME_RE, _THERE_MEET_RE, _THERE_TALK_RE, _THERE_SEND_RE, _THERE_YOU_RE):
        hit = ctx.search(rx)
        if not hit:
            continue
        actor = _actor_before(ctx.actors, hit.end() if rx is _THERE_YOU_RE else hit.start())[0]
        if actor == "project":
            continue
        if rx is _THERE_TALK_RE and (actor == "client"
                                     or _THERE_NOUN_BEFORE_RE.search(_tail(ctx.text, hit.start(), 40))):
            continue  # "you can reply there to claim the lead", "a copy of each reply there"
        if rx is _THERE_SEND_RE and ctx.after(_STREAM_RE, hit.start()):
            continue  # "I'll forward the new leads there": the project's routing
        if rx is _THERE_YOU_RE and actor != "lorenzo":
            continue  # "the bot will text you there", "you can see it there"
        return "off-platform contact (there, the channel the client named): %r" % hit.group(0).strip()
    return None


def _clause_reason(ctx: _Clause) -> Optional[str]:
    clause = ctx.text
    for rx in _LEAVE_RES:
        hit = rx.search(clause)
        if hit:
            return "leaves Upwork: %r" % hit.group(0).strip()
    actors = ctx.actors
    for rx in (_DIRECTLY_RE, _ELSEWHERE_RE):
        hit = rx.search(clause)
        if hit and _actor_before(actors, hit.start())[0] != "project" and not ctx.search(_END_USER_RE):
            return "leaves Upwork: %r" % hit.group(0).strip()
    hit = _BOOK_WITH_ME_RE.search(clause)
    if hit:
        return "off-platform contact (a booking with Lorenzo): %r" % hit.group(0).strip()
    reason = _setup_reason(ctx) or _pay_reason(ctx)
    if reason:
        return reason
    for m in channel_mentions(clause):
        reason = _strong_reason(ctx, m) or _weak_reason(ctx, m)
        if reason:
            return reason
    return None


# ------------------------------------------------------------ the client's move request
# A draft can go along with a client's ask in words that carry no channel of
# their own: after "I'd rather pay you directly by bank transfer", "Sure, that
# works for me." is only agreement. So the gate also reads the client's
# messages Lorenzo has not answered yet (those after his last message, the
# ones a reply answers) and asks one question of them: does the client ask to
# move contact, a call, files, a group or workspace, or payment off Upwork, or
# give a number, address or handle to use? When yes, a draft of any kind is
# refused unless it keeps things on Upwork in so many words (keeps_on_upwork).
# A request Lorenzo already answered (before his last message) is not read.
#
# This detector reads the client's voice: "I", "we" and "my" are the client,
# "you" is Lorenzo. The draft rules above are not reused on client text: they
# read "we use Zoom for sales calls" as a meeting. The project stays the
# project here too: "can the bot text me", "customers message us on
# WhatsApp", "can the rep get the quote by email", "our Zoom recordings".
MOVE_REQUEST_MESSAGES = 10  # the newest unanswered client messages read
MOVE_REQUEST_CHARS = 2 * ANALYSIS_MAX_CHARS  # and at most this much of their text, newest first
MOVE_REASONS = {
    "payment": "client asked to move payment off Upwork",
    "call": "client asked to move a call off Upwork",
    "group": "client asked to move to a group or workspace off Upwork",
    "files": "client asked to move files off Upwork",
    "contact": "client asked to move contact off Upwork",
    "details": "client gave contact details to use off Upwork",
}
_MOVE_ORDER = ("payment", "call", "group", "files", "contact", "details")


def unanswered_client_messages(room: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The client's messages after Lorenzo's last one, oldest first: what a
    reply answers. Room events (neither side) are skipped."""
    out = []  # type: List[Dict[str, Any]]
    for msg in reversed((room or {}).get("messages") or []):
        if not isinstance(msg, dict):
            continue
        if msg.get("side") == "freelancer":
            break
        if msg.get("side") == "client":
            out.append(msg)
    return list(reversed(out))


# Who acts, in the client's voice: the client ("I", "we", "let's"), Lorenzo
# ("you"), the project or its users ("the bot", "customers"), or the client's
# own people ("my team", "our reps").
_CM_SELF_ACTORS = frozenset(("i", "i'm", "i'll", "i'd", "i've", "i am", "let me", "let's", "lets", "we", "we'll",
                             "we're", "we'd", "we've", "happy to", "glad to", "keen to", "down to",
                             "more than happy to"))
# "I don't mind paying via PayPal", "not a problem", "wouldn't mind" and "would
# it not be easier" agree or suggest; they are not negations.
_CM_NEGATED_RE = re.compile(
    r"(?<!\bwhy\s)(?<!\bit\s)\b(?:don't|dont|do\s+not|doesn't|does\s+not|won't|will\s+not|never|"
    r"no\s+need\s+(?:to|for)|rather\s+not|prefer\s+not(?:\s+to)?|not|instead\s+of)\b"
    r"(?!\s+(?:mind|minding|care|object|a\s+(?:problem|big\s+deal|bother|issue)|an\s+issue|an\s+option)\b)"
    r"(?:\s+[\w']+){0,3}\s*$", re.I)
# Upwork as where it happens ("an Upwork call", "here on Upwork"), not what to
# leave ("instead of Upwork", "outside Upwork", "Upwork fees"). It covers only
# its own part of the clause: "keep payment on Upwork but chat on WhatsApp".
_CM_VENUE_RE = re.compile(
    r"\b(?:on|via|through|in|inside|within|over|using|use)\s+(?:the\s+)?upwork\b(?!(?:'s)?\s+fee)|"
    r"\bupwork(?:'s)?\s+(?:call|video\s+call|video|chat|messages?|messaging|meeting|room|thread|milestones?|escrow|"
    r"contract|app)\b", re.I)
_CM_LEAVE_UPWORK_RE = re.compile(
    r"\b(?:instead\s+of|rather\s+than|than|outside(?:\s+of)?|off(?:\s+of)?|skip|skipping|avoid|avoiding|bypass|"
    r"bypassing|without|leave|leaving|away\s+from|not\s+(?:on|through|via|in))\b[^.?!\n\x00]{0,30}?\bupwork\b",
    re.I)
_CM_SEGMENT_SPLIT_RE = re.compile(r"[,;]|\b(?:but|and|or|then|while|though|although|plus)\b", re.I)
_CM_PAY_WORD_RE = re.compile(r"\b(?:pay|pays|paid|paying|payment|payments|invoice|invoices|invoiced|deposit|fees?|"
                             r"money|funds|commission)\b", re.I)
# Round 9's money words: a rail word or "a check" (not "a check-in", "a check
# to see if" or "check your inbox"); named rails come from channel_mentions.
_CM_MONEY_WORD_RE = re.compile(
    r"\b(?:pay|pays|paying|paid|payment|payments|wire|wires|wired|wiring|transfer|transfers|transferred|"
    r"transferring|e-?transfers?|cheques?|cash|invoices?|invoiced|invoicing|deposits?|retainers?|fees?)\b|"
    r"\b(?:a|the|my|your|our|one|by|with|paper|personal|certified)\s+checks?\b(?!-|\s+(?:to\s+(?:see|make|confirm|"
    r"verify|test)|on|of|if|whether|in|up|out|with|that)\b)|\bchecks\b(?!-)", re.I)
_CM_FILE_WORD_RE = re.compile(
    r"\b(?:files?|docs?|documents?|pdfs?|photos?|pictures?|images?|assets?|logos?|attachments?|brand\s+(?:kit|guide|"
    r"guidelines|book)|deliverables?|designs?|mockups?|screenshots?|videos?|scope|proposal|spreadsheets?|"
    r"folders?)\b", re.I)
# "a quick chat" is a call; "chat on WhatsApp" is messages
_CM_CALL_CUE_RE = re.compile(r"\b(?:call|calls|calling|ring|talk|talking|speak|speaking|meet|meeting|hop|jump|dial|"
                             r"voice|video|(?:a|quick|short|brief)\s+(?:quick\s+|short\s+)?chat)\b", re.I)
# The project's machinery, messages, tools and users: "can the daily report go
# to my email", "SMS is easier for our patients", "move the alerts to Slack".
# The project's tools, but "Monday" the weekday is not monday.com: "let's
# meet on Zoom every Monday".
_CM_TOOLS = _PROJECT_TOOLS.replace(
    "|monday|", r"|monday(?:\.com|\s+(?:board|boards|crm|workspace|items?|account|automations?))|")
_CM_PROJECT_NOUN_RE = re.compile(
    r"\b(?:bots?|chatbots?|workflows?|automations?|flows?|sequences?|drips?|campaigns?|zaps?|scenarios?|webhooks?|"
    r"forms?|alerts?|notifications?|reminders?|reports?|summar(?:y|ies)|digests?|quotes?|requests?|repl(?:y|ies)|"
    r"confirmations?|bookings?|appointments?|orders?|tickets?|receipts?|submissions?|recordings?|transcripts?|"
    r"pings?|tasks?|deals?|records?|entries|payments|deposits|refunds|payouts|charges|subscriptions|checkout|invoices|"
    r"transactions|messages|texts|emails|calls|chats|conversations|threads|inboxes|accounts|integrations?|apis?|tests?|"
    r"reps?|installers?|techs?|technicians?|staff|front\s+desk|dispatch(?:ers?)?|vendors?|suppliers?|contractors?|"
    r"employees|partners?|%s|%s)\b" % (_END_USERS, _CM_TOOLS),
    re.I)

# ---- payment
_CM_FEES_RE = re.compile(
    r"\b(?:skip|skipping|avoid|avoiding|save|saving|dodge|dodging|bypass|bypassing|cut\s+out|go\s+around|get\s+around|"
    r"around|without)\s+(?:on\s+)?(?:the\s+|those\s+|all\s+the\s+|any\s+)?(?:upwork(?:'s)?\s+)?(?:fees?|cut|"
    r"commission|service\s+fees?|platform\s+fees?|middleman)\b", re.I)
_CM_DIRECT_DEAL_RE = re.compile(
    r"\b(?:direct|separate|private|side)\s+(?:contract|deal|agreement|arrangement)\b|"
    r"\bwork\s+(?:together\s+)?directly\b(?!\s+(?:on|in|inside|within|into|from)\b)|"
    r"\b(?:hire|contract)\s+you\s+directly\b|\boff\s+the\s+books\b|\bunder\s+the\s+table\b|"
    r"\binvoice\s+(?:me|us)\s+(?:directly|separately|through|via|by|outside|from|with)\b|"
    r"\b(?:send|email|e-mail|text)\s+(?:me|us)\s+(?:an?\s+|the\s+|your\s+)?invoice\b|"
    r"\bpay(?:ing)?\s+(?:you\s+)?(?:in\s+|by\s+|with\s+)?(?:a\s+)?(?:cash|check|cheque)\b(?!-)|"
    r"\b(?:take|takes|taking|accept|accepts|accepting)\s+(?:a\s+|personal\s+|paper\s+)?(?:checks?|cheques?|cash)"
    r"\b(?!-)|\bby\s+(?:a\s+)?(?:paper\s+|personal\s+)?(?:check|cheque)\b(?!-)|"
    r"\bpay(?:ing)?\b[^.?!\n\x00]{0,30}?\b(?:on|through|via|at|from)\s+your\s+(?:own\s+)?(?:website|site|link|"
    r"portal|page)\b", re.I)
_CM_PAY_VERB_BEFORE_RE = re.compile(
    r"\b(?:pay|paying|send|sending|transfer|transferring|wire|wiring|settle|settling|payment|payments|invoice|"
    r"invoicing|deposit|fund|funding)\b[^.?!\n\x00]{0,40}?\b(?:via|through|by|with|on|using|over|in|to|into)\s+"
    r"(?:a\s+|an\s+|your\s+|my\s+|the\s+)?$", re.I)
_CM_YOU_TAKE_BEFORE_RE = re.compile(
    r"\b(?:do|can|could|would|will)\s+you\s+(?:also\s+)?(?:accept|take|use|do|have|work\s+with|prefer|want)\s+"
    r"(?:a\s+|an\s+)?$", re.I)
_CM_RAIL_OK_AFTER_RE = re.compile(
    r"^\s*(?:is|would\s+be|be|works?|'s|might\s+be|seems)?\s*(?:ok|okay|fine|good|great|easier|better|faster|"
    r"quicker|simpler|best|preferred|instead|possible|alright|an\s+option|for\s+you|for\s+this|"
    r"for\s+(?:the\s+)?(?:deposit|payment|invoice|balance|first\s+half|second\s+half|rest|first\s+milestone))\b",
    re.I)
# Paying Lorenzo in so many words: "pay you via Wise", "send you the money on
# Cash App", "would Wise work for paying you", "PayPal you", "your PayPal".
_CM_PAY_YOU_BEFORE_RE = re.compile(
    r"\b(?:pay|paying|send|sending|transfer|transferring|wire|wiring)\s+(?:you|u)\b[^.?!\n\x00]{0,40}?\b(?:via|"
    r"through|by|with|on|using|over|in|to|into)\s+(?:a\s+|an\s+|your\s+|my\s+|the\s+)?$", re.I)
_CM_PAY_YOU_AFTER_RE = re.compile(
    r"^\s*(?:is|would\s+be|be|works?|'s|might\s+be|seems)?\s*(?:ok\s+|okay\s+|fine\s+|good\s+|easier\s+|"
    r"better\s+|best\s+|an\s+option\s+)?(?:for\s+paying|to\s+pay)\s+(?:you|u)\b|^\s+(?:you|u)\b", re.I)
# A job about payments: the post names a rail or a payments workflow. There
# "is Stripe ok?" and "can we accept payments via PayPal?" are the project,
# and only paying Lorenzo in so many words counts.
_CM_PAY_PROJECT_RE = re.compile(r"\b(?:payments|invoices|invoicing|deposits|refunds?|payouts?|checkout|billing|"
                                r"subscriptions|transactions|quickbooks|xero|square|shopify|bookkeeping|"
                                r"accounting)\b", re.I)
_CM_PAID_PASSIVE_RE = re.compile(r"\b(?:get|gets|got|getting|are|is|was|were|be|been|being)\s+paid\b|"
                                r"\b(?:accept|accepting|take|taking|collect|collecting|receive|receiving|process|"
                                r"processing)\s+(?:(?:customer|client|online|card|more|the|their|our)\s+)?"
                                r"(?:payments|deposits)\b", re.I)
_CM_THIRD_PAYEE_RE = re.compile(
    r"\bpay(?:s|ing)?\s+(?:the\s+|our\s+|my\s+|their\s+)?(?:vendors?|suppliers?|staff|employees|contractors?|"
    r"installers?|techs?|team|reps?|drivers?|workers|crews?|partners?|landlords?|payroll)\b", re.I)
_CM_REQUEST_USE_BEFORE_RE = re.compile(
    r"(?:\b(?:can|could|shall|should|may|might)\s+(?:we|i)|\blet'?s|^\s*lets)\s+(?:just\s+|maybe\s+|also\s+)?"
    r"(?:use|do|try|go\s+with|switch\s+to|move\s+to|pay\s+with|go\s+over\s+to|head\s+over\s+to|continue\s+on|"
    r"take\s+(?:this|it)\s+to)\s+(?:a\s+|an\s+)?$", re.I)

# Paying Lorenzo some other way: "can I pay you another way?", "any other way
# to pay you?", "a different way to pay besides Upwork".
_CM_OTHER_WAY_RE = re.compile(
    r"\bpay(?:ing)?\s+(?:you\s+|u\s+)?(?:(?:in|by|via|through|with|using)\s+)?(?:another|some\s+other|a\s+different|"
    r"any\s+other|other|different)\s+(?:way|method|route|option|platform|channel)s?\b|"
    r"\b(?:another|some\s+other|a\s+different|any\s+other|other|different|cheaper)\s+(?:way|method|option|route)s?\s+"
    r"(?:to|of|for)\s+(?:pay(?:ing)?|get(?:ting)?\s+(?:you\s+)?paid|send(?:ing)?\s+(?:you\s+)?(?:the\s+)?"
    r"(?:money|payment))(?:\s+(?:you|u)\b|\s*[?.!,]|\s*$|\s+(?:besides|other\s+than|outside|instead\s+of|"
    r"apart\s+from)\b)|"
    r"\b(?:another|some\s+other|a\s+different|any\s+other)\s+way\s+(?:that\s+)?(?:i|we)\s+(?:can|could|might|may)\s+"
    r"pay\b",
    re.I)
# Upwork's cut, fees or charges given as the reason ("Upwork takes a big cut",
# "the fees on here are brutal", "Upwork charges me a lot") make an ask about
# paying a request to pay another way.
_CM_FEE_ADJ = (r"(?:(?:so|pretty|really|way|too|very|super|just|insanely)\s+){0,2}(?:brutal|steep|high|huge|crazy|"
               r"insane|a\s+lot|much|killing\s+(?:me|us)|expensive|painful|ridiculous|outrageous|excessive)")
_CM_FEE_REASON_RE = re.compile(
    r"\bupwork(?:'s)?\s+(?:takes?|taking|keeps?|eats?)\s+(?:a\s+|an\s+|its\s+|such\s+a\s+)?(?:big\s+|huge\s+|large\s+|"
    r"massive\s+|hefty\s+)?(?:cut|fee|chunk|percentage|share|\d+\s*%%)|"
    r"\bupwork\s+(?:charges?|charging)\s+(?:me|us|so|too|a\s+lot|\d+)|"
    # the fee is Upwork's or the platform's ("the fees on here"), never a named
    # third party's ("Stripe fees", "card fees", "the fees on our payroll app")
    r"\b(?:(?:upwork(?:'s)?|(?:the\s+)?platform(?:'s)?)\s+(?:fees?|cut|commission|charges|service\s+fees?)|"
    r"(?:fees?|cut|commission|charges|service\s+fees?)\s+(?:on\s+here|here|on\s+upwork|on\s+the\s+platform))\s+"
    r"(?:is|are|seem|seems|feel|feels|get|gets)\s+%s\b" % _CM_FEE_ADJ, re.I)
# The ask is how to pay, not how much: "how should I pay you?", "can I just
# pay you?", "is there another option?"; "can I pay you a bit more to cover
# it?" and "I can only pay you $500" are not asks to pay another way.
_CM_PAY_ASK_RE = re.compile(
    r"\b(?:can|could|may|should|shall)\s+(?:i|we)\s+(?:just\s+|also\s+|simply\s+)?(?:pay|transfer|wire|settle)\b"
    r"(?!(?:\s+(?:you|u)\b)?\s*(?:(?:a\s+(?:bit|little)\s+)?(?:more|extra|less|the\s+difference|a\s+bonus|a\s+tip|"
    r"bonus|upfront|up\s+front|now|today|early)\b|\$|\d|for\s+the\s+(?:milestone|contract)\b|to\s+cover\b))|"
    r"\bhow\s+(?:do|can|should|would|could)\s+(?:i|we)\s+(?:best\s+)?pay\b|"
    r"\b(?:is|are)\s+there\s+(?:any|another|other|a\s+different)\s+(?:way|option|method)s?\b(?!\s+(?:to|of|for)\s+"
    r"(?!pay|get(?:ting)?\s+(?:you\s+)?paid|send))|"
    r"\b(?:what|which)\s+(?:other\s+)?(?:payment\s+)?(?:options|methods|ways)\b|"
    r"\bwhere\s+(?:do|should|can|could)\s+(?:i|we)\s+send\s+(?:the\s+)?(?:money|payment|funds)\b", re.I)
_CM_KEEP_PAY_RE = re.compile(r"\b(?:milestones?|escrow)\b|\b(?:through|via|on|in|using)\s+(?:the\s+)?upwork\b", re.I)
# ... unless named only to leave it: "I'd rather not pay through Upwork", "I
# don't want to pay via Upwork", "not on Upwork", "instead of milestones",
# "skip the milestones", "without escrow" ("why not", "don't mind" keep it).
_CM_KEEP_REFUSED_RE = re.compile(
    r"(?<!\bwhy\s)\b(?:rather\s+not|prefer\s+not(?:\s+to)?|(?:do|does|did|would|will|can|could|should)\s+not|"
    r"[a-z]+n't|dont|cannot|not|never|no\s+need\s+(?:to|for)|no\s+longer|instead\s+of|rather\s+than|than|"
    r"outside(?:\s+of)?|skip(?:ping)?|avoid(?:ing)?|bypass(?:ing)?|without|away\s+from|tired\s+of|sick\s+of)\b"
    r"(?:\s+(?!(?:mind|minding|care|object|against|problem|problems|issue|issues|trouble|hesitate|wait|help)\b)"
    r"[\w']+){0,5}\s*$", re.I)
# Refusing to pay through Upwork is itself a payment request: "I'd rather not
# pay through Upwork", "we can't pay via Upwork" ("why not pay through
# Upwork?" and "I don't mind paying through Upwork" are not).
_CM_REFUSED_UPWORK_PAY_RE = re.compile(
    r"(?<!\bwhy\s)\b(?:rather\s+not|prefer\s+not(?:\s+to)?|(?:do|does|would|will|can|could)\s+not|[a-z]+n't|dont|"
    r"cannot|not|never|no\s+longer|tired\s+of|sick\s+of|avoid|avoiding)\b"
    r"(?:\s+(?!(?:mind|minding|care|object|against|problem|problems|issue|issues|trouble|hesitate|wait)\b)[\w']+)"
    r"{0,4}?\s+pay(?:ing|s)?\s+(?:(?:you|u)\s+)?(?:through|via|on|in|using|over)\s+(?:the\s+)?upwork\b", re.I)
# "I'd rather not pay the Upwork fees", "I don't want to pay the fees": a
# refusal of Upwork's fees, not a negation of the request.
_CM_AVOID_FEES_RE = re.compile(
    r"\b(?:rather\s+not|prefer\s+not\s+to|(?:do\s+not|don't|dont)\s+(?:want|like)\s+to|would\s+like\s+to\s+avoid|"
    r"want\s+to\s+avoid|hate\s+(?:to\s+pay|paying)|not\s+keen\s+on)\s+(?:pay(?:ing)?\s+)?(?:the\s+|those\s+|"
    r"all\s+the\s+|any\s+)?(?:(?:upwork(?:'s)?|platform|service)\s+(?:fees?|cut|commission)|fees|cut|commission)\b"
    r"(?!\s+(?:for|of|on)\s+(?!upwork\b|here\b|the\s+platform\b|this\s+(?:platform|site)\b))", re.I)
# "Can I just send a bank transfer?", "I'll send you a wire", "send the
# payment": money sent to Lorenzo (a reminder or link is the project's)
_CM_SEND_NOT_AFTER = (r"(?!\s+(?:reminders?|links?|requests?|confirmations?|receipts?|notifications?|alerts?|emails?|"
                      r"texts?|details|info|screenshots?|forms?|pages?|buttons?|status|data|files?|"
                      r"(?:through|via|on)\s+(?:upwork|here|the\s+platform)))")
# a check or cheque, not a "check-in" or "a check to see if it works"
_CM_CHECK = r"(?:check|cheque)\b(?!-|\s+(?:to\s+see|whether|if)\b)"
_CM_SEND_OBJ = (r"(?:(?:a|an|the|my|our)\s+)?(?:bank\s+transfer|wire(?:\s+transfer)?|e-?transfer|transfer|payment|"
                r"money|funds|%s)\b" % _CM_CHECK)
# sent with no "you": a rail or a check, or "a payment" (not "the payment", which is Upwork's)
_CM_SEND_ASK_OBJ = (r"(?:(?:(?:a|an|the|my|our)\s+)?(?:bank\s+transfer|wire(?:\s+transfer)?|e-?transfer|transfer|"
                    r"%s)|(?:a|an)\s+(?:payment|money|funds))\b" % _CM_CHECK)
# The client as the sender, whatever the opening: "can I", "I'll", "we can",
# "I'd rather", "let me", "happy to", "easier if I", "for me to". The words up
# to "send" never hold another sender or a negation ("I think Upwork will
# send", "I can't send"), and the bot, the workflow or the system as the
# sender is the project's (_CM_PROJECT_SENDS_RE, _CmClause.live).
_CM_SENDER_ME = (r"(?:\b(?:i'm|i'll|i'd|i've|i|we'll|we're|we'd|we've|we|let\s+me|let's|let\s+us|"
                 r"(?:more\s+than\s+)?happy\s+to|glad\s+to|keen\s+to|for\s+(?:me|us)\s+to)\b|^lets\b)")
_CM_SENDER_GAP = r"(?:\s+(?!(?:you|u|upwork|platform|not|never|no|cannot)\b)(?![\w-]*n't\b)[\w'-]+){0,6}?"
# Money sent to Lorenzo: "send you a wire" (you), "send a wire to your
# account" or "to you" (account), or the client sending it ("can I just send
# a bank transfer?", "I'd rather send a wire", "let me send a check", "can I
# just mail a check?", "I'll drop a check in the mail") (ask).
# Only the ask form can be money the client sends to someone else ("a bank
# transfer to each supplier"): _cm_payment checks that.
_CM_SEND_PAYMENT_RE = re.compile(
    r"(?P<you>\bsend(?:ing)?\s+(?:you|u)\s+(?:over\s+)?%s%s)|"
    r"(?P<account>\bsend(?:ing)?\s+(?:over\s+)?(?:(?:a|an|the|my|our)\s+)?(?:bank\s+transfer|wire(?:\s+transfer)?|"
    r"e-?transfer|transfer|payment|money|funds|%s)\s+(?:straight\s+|directly\s+)?to\s+(?:your\s+(?:[\w-]+\s+){0,2}?"
    r"(?:bank|account)\b|(?:you|u)\b(?!')))|"
    r"(?P<ask>%s%s\s+(?P<ask_send>send(?:ing)?|mail(?:ing)?|(?:drop|put|pop|stick)(?=\s+(?:a|the|my|our)\s+"
    r"(?:check|cheque)\s+%s))\s+(?:over\s+)?%s%s)"
    % (_CM_SEND_OBJ, _CM_SEND_NOT_AFTER, _CM_CHECK, _CM_SENDER_ME, _CM_SENDER_GAP, _IN_THE_MAIL, _CM_SEND_ASK_OBJ,
       _CM_SEND_NOT_AFTER), re.I)
# The project as the sender: "I'd like the workflow to send", "have the bot send".
_CM_PROJECT_SENDS_RE = re.compile(
    r"\b(?:%s|it|they|he|she)\s+(?:(?:to|will|would|can|could|should|then|just|automatically|also|always|itself|"
    r"be|able|going)\s+){0,4}$" % _PROJECT_HEADS, re.I)
# Upwork or the platform as the sender: "Upwork will send you the payment".
_CM_PLATFORM_SENDS_RE = re.compile(
    r"\b(?:upwork|(?:the|this)\s+(?:platform|site|marketplace))\s+(?:(?:will|would|can|could|should|then|just|"
    r"automatically|also|usually|normally|always|directly|simply|only|already|typically)\s+){0,3}$", re.I)
# A send offered or asked, not how the client pays people today ("we send a
# wire every Friday"): an offer sender ("I'll", "I'd", "let me", "happy to",
# "for me to"), a modal or offer word before "send" ("can", "want to",
# "going to", "rather"), a question ("can I", "do we", "why don't I"), an "if"
# after "easier", "ok", "what" or "would it work", "to you" as the recipient,
# or "is that ok" or "can you start" in the sentence.
_CM_SENDER_ME_RE = re.compile(_CM_SENDER_ME, re.I)
_CM_OFFER_WHO_RE = re.compile(r"(?:i'll|i'd|we'll|we'd|let\s+me|let's|let\s+us|lets|(?:more\s+than\s+)?happy\s+to|"
                              r"glad\s+to|keen\s+to|for\s+(?:me|us)\s+to)$", re.I)
_CM_OFFER_WORD_RE = re.compile(r"\b(?:can|could|will|would|shall|should|may|might|want|wants|wanna|prefer|rather|"
                               r"like|love|going|gonna|happy|glad|willing|able|plan|planning|try|trying|hope|hoping|"
                               r"ready|intend)\b", re.I)
_CM_OFFER_LEAD_RE = re.compile(
    r"\b(?:can|could|would|will|shall|should|may|might|do|does|did|[a-z]+n't)\s+$|"
    r"\b(?:easier|easiest|better|best|simpler|simplest|faster|quicker|cheaper|safer|ok|okay|fine|alright|possible|"
    r"work|works|help|mind|what|about|rather|prefer|preferable)\b[^.?!\n\x00]{0,20}?\bif\s+$", re.I)
_CM_TO_YOU_RE = re.compile(r"^(?:\s+(?!(?:to|you|your|u)\b)[\w'-]+){0,4}?\s+to\s+(?:you|u|your)\b", re.I)
_CM_ASKS_YOU_RE = re.compile(
    r"\b(?:is|would|will|does|do|could)\s+(?:that|this|it)\s+(?:be\s+)?(?:ok|okay|fine|alright|all\s+right|work|good|"
    r"acceptable|possible)\b|\b(?:ok|okay|fine|alright)\s+(?:with|for)\s+(?:you|u)\b|\bworks?\s+for\s+(?:you|u)\b|"
    r"\bif\s+that'?s\s+(?:ok|okay|fine|alright)\b|"
    r"\b(?:can|could|will|would|do|does)\s+(?:you|u)\s+(?:please\s+|then\s+)?(?:start|begin|get\s+started|kick\s+off|"
    r"get\s+going|accept|take)\b|\b(?:you|we)\s+(?:can|could)\s+(?:then\s+)?(?:start|begin|get\s+started|kick\s+off)\b",
    re.I)
# How the client pays people today, in plain present with no "you": "we pay by
# wire every Friday", "I pay by check", "so we usually send a transfer".
_CM_HABITUAL_RE = re.compile(
    r"(?:^|[,;:]\s*|\b(?:and|so|but|then)\s+)(?:(?:right\s+now|currently|today|usually|normally|typically|"
    r"these\s+days|at\s+the\s+moment),?\s+)?(?:i|we)\s+(?:(?:usually|always|normally|typically|generally|currently|"
    r"often|also|just|still|already|mostly|now|then|simply|all|only|sometimes)\s+){0,2}"
    r"(?:pay|send|wire|transfer|mail|take|takes|accept|accepts)\b", re.I)
_CM_YOU_WORD_RE = re.compile(r"\b(?:you|u|your|yours)\b", re.I)
# The first "to" after an asked or offered send names someone else as the
# payee: "a bank transfer to each supplier", "a wire to our installers every
# Friday", "to payroll", "to each of them", "to pay our techs". "To" and a verb
# is a purpose ("to get started", "to cover the deposit", "to speed things
# up"), "to you" and "to your account" are Lorenzo, and a schedule on its own
# ("every month") never clears a send.
_CM_THIRD_PARTY = (r"(?:suppliers?|installers?|techs?|technicians?|vendors?|staff|payroll|subcontractors?|subs|"
                   r"crews?|employees?|workers?|drivers?|landlords?|tenants?|manufacturers?|distributors?|"
                   r"wholesalers?|accountants?|bookkeepers?|brokers?|customers?|clients?|patients?|cleaners?|"
                   r"couriers?|reps?|upwork)")
# after "each / every / all" or "our / my": any person ("each of them", "our team")
_CM_ANY_PERSON = (r"(?:%s|contractors?|freelancers?|partners?|members?|agents?|people|persons?|guys?|ones?|them|"
                  r"teams?|individuals?)" % _CM_THIRD_PARTY)
_CM_NOT_YOU = r"(?:(?!(?:you|your|yours|u)\b)[\w-]+\s+)?"
_CM_SEND_ELSEWHERE_RE = re.compile(
    r"^(?:\s+(?!(?:to|you|your|u)\b)[\w'-]+){0,4}?\s+to\s+(?:(?:pay|reimburse|cover|fund)\s+)?(?:"
    r"(?:each|every|all|both)\s+(?:one\s+)?(?:of\s+)?(?:(?:our|my|the|their|those|these)\s+)?%s%s|"
    r"(?:our|my|their|his|her)\s+(?:own\s+)?%s(?:%s|bank|account)|"
    r"(?:(?:the|those|these|a|an)\s+)?%s%s)\b"
    % (_CM_NOT_YOU, _CM_ANY_PERSON, _CM_NOT_YOU, _CM_ANY_PERSON, _CM_NOT_YOU, _CM_THIRD_PARTY), re.I)
# A cheque for Lorenzo: "mail / write / send you a check", "mail a check to
# you", "who do I make the check out to?", "would a check work?", "a check is
# fine", "checks are fine".
_CM_CHECK_YOU_RE = re.compile(
    r"\b(?:mail|mails|mailing|mailed|write|writes|writing|cut|cuts|cutting|send|sends|sending|give|giving|hand|post|"
    r"overnight|fedex)\s+(?:you|u)\s+(?:over\s+)?(?:(?:a|the|your|my|our|one)\s+)?(?:paper\s+|personal\s+|company\s+|"
    r"business\s+|certified\s+)?(?:check|cheque)s?\b(?!-)|"
    r"\b(?:mail|mailing|send|sending|post|overnight|fedex)\s+(?:(?:a|the|my|our)\s+)?(?:paper\s+|personal\s+)?"
    r"(?:check|cheque)\s+(?:over\s+|straight\s+|directly\s+)?to\s+(?:you|u|your)\b|"
    r"\b(?:make|makes|making|made|write|writing|wrote)\s+(?:(?:the|a|my|our|this|that|these|those|one)\s+)?"
    r"(?:checks?|cheques?)\s+(?:out\s+)?(?:payable\s+)?to\b(?=\s*(?:[?.!]|$|(?:you|u|your|yours|who|whom|what|"
    r"which)\b))", re.I)
_CM_CHECK_OK_RE = re.compile(
    r"\b(?:a|one|paper|personal)\s+(?:paper\s+|personal\s+)?(?:check|cheque)\b(?!-)\s+(?:(?:would|will|should|could|"
    r"might|also)\s+)?(?:works?|be\s+(?:ok|okay|fine|alright|acceptable|possible|easier|better)|is\s+(?:ok|okay|fine|"
    r"alright|acceptable|possible|easier|better)|ok|okay|fine|alright)\b|"
    r"\b(?:checks|cheques)\s+(?:would\s+|will\s+)?(?:work|be\s+(?:ok|okay|fine)|are\s+(?:ok|okay|fine|alright|"
    r"acceptable))\b", re.I)
# Lorenzo's own fee, rate or invoice: "for your fee, would a bank transfer
# work?" pays Lorenzo even in a payments job.
_CM_YOUR_FEE_RE = re.compile(r"\byour\s+(?:fee|fees|rate|rates|invoice|invoices|price|quote|deposit|payment)\b", re.I)

# ---- leaving Upwork with no channel word
_CM_LEAVE_RES = (
    re.compile(r"\b(?:outside|out\s+of)\s+(?:of\s+)?(?:the\s+)?(?:upwork|platform|this\s+(?:site|app|platform))\b",
               re.I),
    re.compile(r"\boff\s+(?:of\s+)?(?:upwork|the\s+platform|this\s+platform|platform)\b|\boff[- ](?:platform|site|"
               r"upwork)\b", re.I),
    re.compile(r"\b(?:take|taking|move|moving|continue|go|switch|chat|talk|communicate|work|hop)\w*\s+(?:this\s+|it\s+|"
               r"things\s+|the\s+conversation\s+)?off\s+(?:of\s+)?(?:here|this\s+(?:site|app|thread|chat))\b", re.I),
    re.compile(r"\b(?:skip|skipping|bypass|bypassing|avoid|avoiding|leave|leaving|without|cut\s+out|go\s+around|"
               r"get\s+around|instead\s+of|rather\s+than|than|away\s+from|not\s+(?:through|via|on)|besides|"
               r"other\s+than|apart\s+from|aside\s+from|except\s+(?:for\s+)?)\s+(?:(?:to\s+)?(?:go|going|pay|paying|do|"
               r"doing|use|using|work|working|keep|keeping|run|running|send|sending)\s+(?:it\s+|this\s+|everything\s+|"
               r"things\s+)?)?(?:through\s+|via\s+|on\s+)?(?:the\s+)?upwork\b", re.I),
    re.compile(r"\b(?:talk|chat|speak|continue|discuss|connect|communicate|message|correspond)\w*\s+(?:[\w']+\s+){0,2}?"
               r"(?:privately|in\s+private|offline|elsewhere|somewhere\s+else|directly)\b", re.I),
    re.compile(r"\b(?:reach|contact|find|ping|text|email|message|call|ring)\s+(?:me|us)\s+(?:directly\s+)?"
               r"(?:at|on|via|through)\s+(?!upwork\b|here\b|any\b|noon\b|night\b|\d{1,2}(?::\d\d)?\s*(?:am|pm)\b)",
               re.I),
)

# ---- a group or workspace
_CM_GROUP_SETUP_RE = re.compile(
    r"\b(?:set\s+up|setup|create|start|make|open|spin\s+up)\s+(?:a|an|the|our|one)\s+(?:[\w-]+\s+){0,3}?"
    r"(?:group(?:\s+chat)?|channel|workspace|chat|thread|server|space)\b(?P<rest>[^.?!\n\x00]{0,50})", re.I)
_CM_GROUP_PARTY_RE = re.compile(
    r"\b(?:with\s+(?:me|us|you|my\s+team|our\s+team|the\s+team|everyone|my\s+(?:partner|manager|staff|office)|"
    r"our\s+(?:staff|office|managers?))|for\s+(?:us|you\s+and\s+me|the\s+two\s+of\s+us|updates|questions|feedback|"
    r"check-?ins|communication|comms|coordination|collaboration|the\s+project|this\s+project|this|the\s+build|"
    r"progress)|between\s+us|so\s+(?:we|you\s+and\s+i|i)\s+can)\b", re.I)
_CM_GROUP_QUALIFIED_RE = re.compile(r"^\s*(?:for|where|so|that|to|which|in|on)\b", re.I)
_CM_GROUP_INVITE_RE = re.compile(
    r"\b(?:add|invite|bring|put)\s+(?:you|me|us)\s+(?:in)?to\s+(?:our|my|the|a|your)\s+(?:[\w-]+\s+){0,2}?"
    r"(?:group|channel|workspace|chat|server|slack|discord|whats\s?app|telegram|teams|space|thread|signal)\b", re.I)
_CM_GROUP_JOIN_RE = re.compile(
    r"\b(?:join|hop\s+into|jump\s+into|come\s+into)\s+(?:our|my|the|a)\s+(?:[\w-]+\s+){0,2}?(?:group|channel|"
    r"workspace|chat|server|slack|discord|whats\s?app|telegram|teams|space)\b", re.I)

# ---- a channel between the client and Lorenzo
_CM_YOUR_BEFORE_RE = re.compile(r"\b(?:your|ur)\s+(?:(?:work|personal|direct|private|main|business|cell|mobile|best|"
                                r"usual|company|own|preferred|contact)\s+)?$", re.I)
_CM_MY_BEFORE_RE = re.compile(r"\b(?:my|our)\s+(?:(?:work|personal|direct|private|main|business|cell|mobile|best|"
                              r"usual|company|own|preferred|contact|office)\s+)?$", re.I)
# "my WhatsApp" is the client's own line only with someone to use it: "send
# it to my email", "can you text my cell", "here's my Zoom link"
_CM_MY_PARTY_RE = re.compile(r"\b(?:me|you|your|here's|here\s+is)\b", re.I)
_CM_HAVE_BEFORE_RE = re.compile(
    r"(?:\b(?:do|did)\s+you\s+(?:have|use|got)|\bhave\s+you\s+got|\byou\s+got|\bare\s+you\s+(?:also\s+|still\s+)?"
    r"(?:on|using|available\s+on|active\s+on|reachable\s+(?:on|by|via))|\byou\s+on|\b(?:i'm|i\s+am|we're|we\s+are)\s+"
    r"(?:also\s+|always\s+|usually\s+|more\s+|mostly\s+)?(?:on|active\s+on|reachable\s+on|available\s+on))\s+"
    r"(?:a\s+|an\s+)?$", re.I)
_CM_MOVE_VERB_RE = re.compile(
    r"\b(?:move|moving|continue|continuing|switch|switching|take|taking|shift|shifting|hop|jump|chat|chatting|"
    r"talk|talking|speak|speaking|discuss|discussing|communicate|communicating|carry\s+on|keep\s+(?:talking|chatting|"
    r"in\s+touch)|correspond|coordinate|coordinating|meet|meeting|catch\s+up|call)\b(?P<mid>[^.?!\n\x00]{0,30}?)\s"
    r"(?:to|on|onto|over|via|through|by|in|into|using|with)\s+(?:the\s+|a\s+|an\s+|my\s+|your\s+|our\s+)?"
    r"(?:quick\s+|short\s+)?$|\bconnect(?:ing)?\s+(?:on|via|over)\s+(?:the\s+)?$", re.I)
_CM_REACH_BEFORE_RE = re.compile(
    r"\b(?:message|msg|ping|reach|contact|write|find|add|hit|catch|call|text|email|dm|follow|get\s+in\s+touch\s+with|"
    r"get\s+hold\s+of)\s+(?:me|us|you)(?:\s+up)?(?:\s+[\w']+){0,2}?\s+(?:on|via|over|through|by|at|in)\s+"
    r"(?:the\s+|my\s+|your\s+|a\s+)?$", re.I)
_CM_SENT_BEFORE_RE = re.compile(
    r"\b(?:sent|send|sending|shoot|shot|drop|dropped|forward|forwarded|leave|left|give|gave)\s+(?:you|me|us)\s+"
    r"(?:an?\s+|the\s+)?(?:quick\s+|short\s+)?$", re.I)
_CM_LETS_BEFORE_RE = re.compile(r"(?:\b(?:can|could|shall|should)\s+we|\blet'?s|^\s*lets)\s+(?:just\s+|maybe\s+|"
                                r"quickly\s+)?$", re.I)
_CM_PREP_BEFORE_RE = re.compile(r"\b(?:on|over|via|through|by)\s+(?:the\s+|a\s+|an\s+)?$", re.I)
_CM_PARTY_RE = re.compile(r"\b(?:you|your|we|let's|lets)\b", re.I)
# The project's own events and schedules: "text me when a lead comes in",
# "email me the report every Friday" are the finished system, not Lorenzo.
_CM_STREAM_EVENT_RE = re.compile(
    r"\b(?:when|whenever|each\s+time|every\s+time|as\s+soon\s+as|once|any\s+time|anytime|if)\s+(?:a|an|the|each|"
    r"every|any|new|someone|somebody|one|they)\s+(?:[\w'-]+\s+){0,2}?(?:%s|leads?|quotes?|requests?|bookings?|"
    r"appointments?|orders?|messages?|texts?|emails?|repl(?:y|ies)|forms?|submissions?|calls?|payments?|deposits?|"
    r"tickets?|inquir(?:y|ies)|jobs?|estimates?|reviews?|someone|somebody)\b" % _END_USERS, re.I)
# Every one of the business's calls or visits, not one with Lorenzo: "we
# record every sales call on Zoom", "all our consults happen on Google Meet".
_CM_EVERY_ONE_RE = re.compile(
    r"\b(?:every|each|all)\s+(?:(?:of\s+)?(?:our|the|their|my)\s+)?(?:[\w'-]+\s+)?(?:calls?|meetings?|chats?|"
    r"sessions?|demos?|consults?|consultations?|appointments?|jobs?|visits?|classes|lessons?|interviews?)\b", re.I)
_CM_DETERMINER_BEFORE_RE = re.compile(r"\b(?:the|a|an|this|that|each|every|any|my|your|our|their|its)\s+$", re.I)
_CM_TARGET_AFTER_RE = re.compile(r"^\s+(?:me|us|you)\b", re.I)
_CM_CALL_TARGET_RE = re.compile(
    r"\b(?:call|ring|phone|dial|facetime)\s+(?:me|us|you)\b|\b(?:give|gave)\s+(?:me|us|you)\s+a\s+(?:quick\s+)?"
    r"(?:call|ring|buzz|shout)\b", re.I)
_CM_SHAPE_BEFORE_RE = re.compile(
    r"\b(?:a|an|one|quick|short|brief)\s+(?:quick\s+|short\s+|brief\s+|video\s+|voice\s+)?$|"
    r"\b(?:do|have|set\s+up|schedule|book|arrange|plan)\s+(?:a|an)\s+(?:quick\s+|short\s+)?$", re.I)
_CM_CALL_AFTER_RE = re.compile(r"^\s*(?:call|chat|meeting|session|sync|catch-?up|video\s+call)\b", re.I)
_CM_PREFER_BEFORE_RE = re.compile(
    r"\b(?:easier|better|faster|quicker|simpler|smoother)\s+(?:for\s+(?:me|us)\s+)?(?:to\s+\w+\s+)?(?:over|on|via|"
    r"by|through|with|in)\s+(?:the\s+)?$|\b(?:i|we)(?:'d)?\s+(?:much\s+|really\s+)?(?:prefer|rather\s+use|rather|"
    r"like\s+to\s+use)\s+(?:to\s+\w+\s+(?:on|over|via|by)\s+)?(?:the\s+)?$", re.I)
# "email is easier for me", "is WhatsApp ok for you": a preference with a
# party in it ("text is better" alone may be the project's channel)
_CM_PREFER_AFTER_RE = re.compile(
    r"^\s*(?:is|would\s+be|be|works?|'s|might\s+be|seems)?\s*(?:a\s+lot\s+|much\s+|way\s+|so\s+much\s+|probably\s+)?"
    r"(?:ok|okay|fine|good|great|easier|better|faster|quicker|simpler|best|preferred|alright)?\s*(?:for\s+(?:me|us|"
    r"you)|to\s+(?:reach|talk|chat|message|contact|get\s+hold|communicate|get\s+in\s+touch))\b", re.I)

# ---- files, and contact details given
_CM_FILE_HOST = (r"(?:google\s+drive|g\s?drive|drive\s+(?:folder|link)|dropbox|we\s?transfer|one\s?drive|box\.com|"
                 r"icloud(?:\s+drive)?|google\s+docs?|google\s+sheets?)")
_CM_FILE_HOST_RE = re.compile(r"\b%s\b" % _CM_FILE_HOST, re.I)
_CM_FILE_SHARE_RE = re.compile(
    r"\b(?:share|sharing|shared|send|sending|upload|uploading|drop|put|transfer|invite|add|give|grant)\w*\b"
    r"[^.?!\n\x00]{0,40}?\b(?:with\s+you|to\s+you|you\s+access|your\s+(?:email|gmail|google\s+account|account|"
    r"address|dropbox|drive))\b|\b(?:you|can\s+you|could\s+you|please)\s+(?:upload|put|drop|save|send)\b"
    r"[^.?!\n\x00]{0,40}?\b(?:to|in|into|on)\s+(?:our|my|the)\s+|\b(?:via|through|by|over|using)\s+(?:a\s+|the\s+)?"
    r"%s\b" % _CM_FILE_HOST, re.I)
_CM_ROUTE_RE = re.compile(
    r"\b(?:leads?|alerts?|notifications?|reminders?|quotes?|requests?|repl(?:y|ies)|reports?|digests?|"
    r"summar(?:y|ies)|bookings?|appointments?|orders?|tickets?|submissions?|forms?|bots?|workflows?|automations?|"
    r"zaps?|scenarios?|webhooks?|sender|from\s+(?:address|number|name)|reply-?to|forwarding|twilio|hubspot|"
    r"salesforce|pipedrive|gohighlevel|highlevel|ghl|crm|test\s+(?:lead|data)|(?<!\byour\s)invoices|"
    r"(?:the|our)\s+(?:main|office|business|shop|store|support|front\s+desk|company|sales|service|booking|"
    r"customer\s+service)\s+(?:line|number|inbox|email|address|phone))\b", re.I)
_CM_PERSONAL_RE = re.compile(
    r"\b(?:my\s+(?:cell|phone|number|email|e-mail|personal|direct|mobile|whats\s?app|work\s+email|private|handle|"
    r"telegram|skype)|reach\s+me|call\s+me|text\s+me|email\s+me|contact\s+me|ping\s+me|message\s+me|i'?m\s+at|"
    r"i\s+am\s+at|you\s+can\s+(?:reach|call|text|email|find)\b)", re.I)
_CM_CHAT_HOSTS = ("wa.me", "api.whatsapp.com", "chat.whatsapp.com", "t.me", "telegram.me", "m.me")


# "Would it be easier ...": a dummy "it", not the project
_CM_DUMMY_IT_AFTER_RE = re.compile(
    r"^\s*(?:(?:'d|would|will|might|could|should)\s*)?(?:not\s+)?(?:(?:be|'s|is)\s+)?(?:(?:much|a\s+lot|way|so\s+much|"
    r"probably|definitely)\s+)?(?:easier|better|quicker|faster|simpler|smoother|more\s+convenient|ok|okay|fine|"
    r"possible|alright|nicer|cheaper)\b", re.I)


class _CmClause(object):
    """One clause of client text: its actors and its Upwork segments."""
    __slots__ = ("text", "actors", "mentions", "_cuts", "_venue")

    def __init__(self, text: str) -> None:
        self.text = text
        self.actors = [a for a in _actors(text)
                       if not (a[2] == "project" and a[3] == "it" and _CM_DUMMY_IT_AFTER_RE.match(text[a[1]:]))]
        self.mentions = channel_mentions(text)
        self._cuts = [0] + [m.end() for m in _CM_SEGMENT_SPLIT_RE.finditer(text)]
        self._venue = {}  # type: Dict[int, bool]

    def on_upwork(self, pos: int) -> bool:
        """The part of the clause around ``pos`` names Upwork as the venue."""
        i = bisect.bisect_right(self._cuts, pos) - 1
        if i not in self._venue:
            start = self._cuts[i]
            end = self._cuts[i + 1] if i + 1 < len(self._cuts) else len(self.text)
            seg = self.text[start:end]
            self._venue[i] = bool(_CM_VENUE_RE.search(seg)) and not _CM_LEAVE_UPWORK_RE.search(seg)
        return self._venue[i]

    def blocked(self, pos: int, to_lorenzo: bool = False) -> bool:
        """The nearest actor before ``pos`` is the project or its users ("can
        the bot text me", "customers message us"), or the client's own people
        ("my team", "our reps") doing something that does not reach Lorenzo."""
        kind, text = _actor_before(self.actors, pos)
        if kind == "project":
            return True
        if kind == "lorenzo" and re.sub(r"\s+", " ", text) not in _CM_SELF_ACTORS:
            return not to_lorenzo
        return False

    def negated(self, pos: int) -> bool:
        return bool(_CM_NEGATED_RE.search(_tail(self.text, pos, 40)))

    def live(self, pos: int, to_lorenzo: bool = False) -> bool:
        """A cue at ``pos`` counts: not negated, not the project's, not on Upwork."""
        return not (self.negated(pos) or self.on_upwork(pos) or self.blocked(pos, to_lorenzo))


# Round 9's wider rule: a money word tied to Lorenzo ("pay you", "your fee",
# "to you", "do you take checks", "mail / write / send you") or to Upwork
# ("than through Upwork", "not via Upwork", "Upwork's cut").
_CM_TIED_LORENZO_RE = re.compile(
    r"\bpa(?:y|ys|ying|id)\s+(?:you|u)\b|"
    r"\byour\s+(?:[\w-]+\s+){0,2}?(?:fees?|invoices?|deposits?|payments?|retainers?|rates?|prices?|quotes?|bank|"
    r"paypal|venmo|zelle|wise|checks?|cheques?|account\s+(?:details|info|number))\b|"
    r"\bto\s+(?:you|u)\b(?!')|"
    r"\b(?:you|u)\s+(?:(?:also|still|even|ever|usually|normally|guys)\s+)?(?:take|takes|taking|accept|accepts|"
    r"accepting)\b|"
    r"\b(?:mail|mails|mailing|mailed|write|writes|writing|send|sends|sending|give|gives|giving|hand|cut|wire|wiring|"
    r"transfer|transferring|get|getting|owe)\s+(?:you|u)\b|"
    r"\b(?:you|u)(?:'d|'ll)?\s+(?:[\w']+\s+){0,3}?(?:be|get|getting|being)\s+paid\b", re.I)
_CM_TIED_UPWORK_RE = re.compile(
    r"\b(?:through|via|on|than|over|using|in|outside(?:\s+of)?|off(?:\s+of)?|besides|instead\s+of)\s+"
    r"(?:the\s+)?upwork\b|"
    # Upwork's fees or cut: "Upwork's fee", "Upwork takes a cut", "Upwork takes 20%"
    r"\bupwork(?:'s)?\s+(?:[\w%-]+\s+){0,3}?(?:fees?|cut|commission|charges?|percentage)\b(?!\s+(?:aside|apart)\b)|"
    r"\bupwork(?:'s)?\s+(?:(?:takes?|taking|took|keeps?|keeping|charges?|charging|gets?|grabs?|eats?|skims?)\s+)?"
    r"(?:(?:about|around|almost|nearly|over|like)\s+)?\d+(?:\.\d+)?\s*(?:%|percent\b)|"
    r"\b(?:fees?|cut|commission)\s+(?:on|from|of|at|that)\s+(?:the\s+)?upwork\b|"
    r"\b(?:fees?|cut|commission|percentage)\s+(?:that\s+)?upwork\s+(?:takes|charges|keeps|gets|grabs|skims|eats)\b",
    re.I)
# Upwork or the platform moving the money is Upwork's: "Upwork will send the
# payment to you", "the platform holds the deposit".
_CM_PLATFORM_PAYS_RE = re.compile(
    r"\b(?:upwork|(?:the|this)\s+(?:platform|site|marketplace))(?:'s\s+(?:system|escrow))?\s+(?:(?:will|would|can|"
    r"could|should|then|just|automatically|also|usually|normally|always|directly|simply|only|already|"
    r"typically)\s+){0,3}(?:send|sends|sending|pay|pays|paying|release|releases|releasing|transfer|transfers|"
    r"deposit|deposits|hold|holds|holding|handle|handles|handling|process|processes)\b", re.I)

# Round 10: asking where or how the money goes names Lorenzo as the payee
# with no "you": "Where should I send the money?", "where do we wire the
# deposit?", "Where should the payment go?", "How do you want the deposit?",
# "How would you like the payment sent?"; not "Where should I send the
# payment data?", "Where do I send the payment for the Twilio number?" or
# "How do you want the deposit reminder worded?".
_CM_PAY_OBJ = (r"(?:(?:the|my|our|a|your|this|that)\s+)?"
               r"(?:money|payment|deposit|funds|check|cheque|balance|fee|retainer)")
_CM_WHERE_HOW_PAY_RE = re.compile(
    r"\bwhere\s+(?:do|should|can|could|would|shall|will|to)\s+(?:(?:i|we)\s+)?(?:send|wire|mail|transfer|pay|drop|"
    r"put|deposit)\s+%s\b(?=\s*(?:[?.!,;:)]|$)|\s+(?:to\s+(?:you|u)|for\s+(?:the\s+)?(?:work|project|build|job|"
    r"deposit|first\s+(?:milestone|half|part))|when|once|if|now|today|tomorrow|this|next|by)\b)|"
    r"\bwhere\s+(?:should|do|does|would|will|can)\s+(?:the|my|our)\s+(?:money|payment|deposit|funds|check|cheque)\s+go"
    r"\b|"
    r"\bhow\s+(?:do|would|should|will|can)\s+(?:you|u)\s+(?:want|like|prefer|need)\s+%s(?:\s+(?:sent|paid|made|"
    r"handled|to\s+be\s+(?:sent|paid|made|handled)))?(?=\s*(?:[?.!,;:)]|$))" % (_CM_PAY_OBJ, _CM_PAY_OBJ), re.I)


def _cm_money_tied(body: str) -> bool:
    """Round 9's wider rule, for a message the narrow rules pass in a job that
    is not about payments: a sentence ties a money word (pay, payment, wire,
    transfer, check, cash, invoice, deposit, retainer, fee or a named rail) to
    Lorenzo or to Upwork and does not keep payment on Upwork. Upwork, the
    platform or the project moving the money ("Upwork will send the payment
    to you", "the bot can send you the invoice") is not a tie. Round 10: a
    question about where or how to send the money ties it to Lorenzo too."""
    if not (_CM_TIED_LORENZO_RE.search(body) or _CM_TIED_UPWORK_RE.search(body)
            or _CM_WHERE_HOW_PAY_RE.search(body)):
        return False  # most messages: no tie at all, so no sentence walk
    for sentence in _sentence_texts(body):
        if not (_CM_TIED_LORENZO_RE.search(sentence) or _CM_TIED_UPWORK_RE.search(sentence)
                or _CM_WHERE_HOW_PAY_RE.search(sentence)):
            continue
        if _cm_pay_kept(sentence):
            continue  # "I'll pay you through Upwork milestones"
        if not (_CM_MONEY_WORD_RE.search(sentence) or _CM_WHERE_HOW_PAY_RE.search(sentence)
                or any(m.cat == "pay" for m in channel_mentions(sentence))):
            continue
        for _, clause in _clause_spans(sentence):
            if _CM_PLATFORM_PAYS_RE.search(clause):
                continue
            c = None  # type: Optional[_CmClause]
            for rx, to_lorenzo in ((_CM_TIED_LORENZO_RE, True), (_CM_TIED_UPWORK_RE, False),
                                   (_CM_WHERE_HOW_PAY_RE, True)):
                for tie in rx.finditer(clause):
                    c = c or _CmClause(clause)
                    if not c.blocked(tie.start(), to_lorenzo):
                        return True
    return False


def _cm_pay_kept(text: str) -> bool:
    """Upwork's payment named and kept ("through Upwork", "milestones",
    "escrow"), not named only to leave it ("I'd rather not pay through
    Upwork", "instead of milestones")."""
    return any(not _CM_KEEP_REFUSED_RE.search(_tail(text, m.start(), 80)) for m in _CM_KEEP_PAY_RE.finditer(text))


def _cm_habitual(text: str, sentence: str) -> bool:
    """``text`` (a clause up to a payment cue) is how the client pays people
    today ("we pay by wire every Friday"), with no "you" and no "is that ok"."""
    return bool(_CM_HABITUAL_RE.search(text) and not _CM_YOU_WORD_RE.search(text)
                and not _CM_ASKS_YOU_RE.search(sentence))


def _cm_send_offered(hit: Any, clause: str, sentence: str) -> bool:
    """The client's send (the ask form of _CM_SEND_PAYMENT_RE) is offered or
    asked ("I'll send a wire", "can I send", "easier if I send", "to you"), not
    how they pay people today ("we send a wire every Friday")."""
    send = hit.start("ask_send")
    span = clause[hit.start():send]
    who = None
    for who in _CM_SENDER_ME_RE.finditer(span):
        pass  # the sender nearest "send"
    if who is None:
        return True
    gap = span[who.end():]
    at = sentence.find(clause)
    lead = (sentence[:at] if at > 0 else "") + clause[:hit.start()] + span[:who.start()]
    lead = _tail(lead, len(lead), 80)
    progressive = (hit.group("ask_send").lower() in ("sending", "mailing")
                   and not _RECURRING_RE.search(clause[hit.end():]))
    return bool(_CM_OFFER_WHO_RE.match(who.group(0)) or _CM_OFFER_WORD_RE.search(gap)
                or _CM_OFFER_LEAD_RE.search(lead) or _CM_TO_YOU_RE.match(clause[hit.end():])
                or _CM_ASKS_YOU_RE.search(sentence) or progressive)


def _cm_payment(c: _CmClause, pay_project: bool = False, your_fee: bool = False, sentence: str = "") -> bool:
    clause = c.text
    sentence = sentence or clause
    for rx in (_CM_FEES_RE, _CM_DIRECT_DEAL_RE, _DIRECTLY_RE, _CM_OTHER_WAY_RE, _CM_CHECK_YOU_RE, _CM_CHECK_OK_RE):
        hit = rx.search(clause)
        if hit and c.live(hit.start()) and not _cm_habitual(clause[:hit.end()], sentence):
            return True  # not "I pay by check every month, can the sync log it?"
    if not _cm_pay_kept(sentence):  # "a payment for the next milestone" is Upwork's
        for hit in _CM_SEND_PAYMENT_RE.finditer(clause):
            if hit.group("ask"):
                send = hit.start("ask_send")
                if (not c.live(send) or _CM_PROJECT_SENDS_RE.search(clause[hit.start():send])
                        or _CM_SEND_ELSEWHERE_RE.match(clause[hit.end():])
                        or not _cm_send_offered(hit, clause, sentence)):
                    continue  # "I'd like the bot to send a wire", "we send a wire every Friday": not to Lorenzo
            elif not c.live(hit.start()) or _CM_PLATFORM_SENDS_RE.search(clause[:hit.start()]):
                continue  # "Upwork will send you the payment", "the workflow sends the money to your account"
            return True
    hit = _CM_REFUSED_UPWORK_PAY_RE.search(clause)  # refusing Upwork is negative by nature
    if hit and not c.blocked(hit.start()):
        return True
    hit = _CM_AVOID_FEES_RE.search(clause)  # negative by nature, so not checked for negation
    if hit and not (c.on_upwork(hit.start()) or c.blocked(hit.start())):
        return True
    if _CM_PAID_PASSIVE_RE.search(clause) or _CM_THIRD_PAYEE_RE.search(clause):
        return False  # "we get paid by bank transfer", "we pay vendors through Wise", "accept payments"
    for m in c.mentions:
        if m.cat != "pay":
            continue
        left, right = _tail(clause, m.start, 60), _head(clause, m.end, 60)
        if _project_right(right) or not c.live(m.start):
            continue
        if (_CM_PAY_YOU_BEFORE_RE.search(left) or _CM_PAY_YOU_AFTER_RE.match(right)
                or _CM_YOU_TAKE_BEFORE_RE.search(left) or _CM_YOUR_BEFORE_RE.search(left) or your_fee):
            return True
        if pay_project:
            continue  # "is Stripe ok?", "can we accept payments via PayPal?" in a payments job
        if _cm_habitual(clause[:m.end], sentence):
            continue  # "we pay by wire every Friday": how the client pays people today
        if (_CM_PAY_VERB_BEFORE_RE.search(left) or _CM_REQUEST_USE_BEFORE_RE.search(left)
                or _CM_TARGET_AFTER_RE.match(right)
                or (_CM_RAIL_OK_AFTER_RE.match(right) and not _CM_PROJECT_NOUN_RE.search(clause))):
            return True
    return False


def _cm_group(c: _CmClause) -> bool:
    for hit in _CM_GROUP_SETUP_RE.finditer(c.text):
        if not c.live(hit.start()):
            continue
        rest = hit.group("rest")
        if _CM_GROUP_PARTY_RE.search(rest) or not _CM_GROUP_QUALIFIED_RE.match(rest):
            return True  # "with my team for updates"; a bare "can we set up a WhatsApp group?"
    for rx in (_CM_GROUP_INVITE_RE, _CM_GROUP_JOIN_RE):
        hit = rx.search(c.text)
        if hit and c.live(hit.start(), to_lorenzo=True):
            return True
    return False


# "Would WhatsApp be easier?": a named platform offered as easier, when the
# job post does not name it (then it may be the project's channel)
_CM_EASIER_AFTER_RE = re.compile(
    r"^\s*(?:would\s+be|'d\s+be|be|is|'s|might\s+be|seems)?\s*(?:(?:much|a\s+lot|way|so\s+much)\s+)?"
    r"(?:easier|better|quicker|faster|simpler|smoother|more\s+convenient)\b", re.I)
# Talk between the client and Lorenzo: "a call would be quicker", "easier to
# just talk", "call me", "give me a ring". A bare "Zoom?" or "WhatsApp?"
# counts only in a message that names Upwork or says this, and a phone
# number with it is a call request.
_CM_TALK_WORD_RE = re.compile(
    r"\b(?:talk|talking|speak|speaking|ring)\b|\b(?:a|one|quick|short|brief)\s+(?:quick\s+|short\s+|brief\s+|phone\s+|"
    r"video\s+|voice\s+)?(?:call|meeting|chat)\b|"
    r"\b(?:call|calls|calling|phone|ring)\s+(?:me|you|us|anytime|any\s+time)\b|"
    r"\b(?:give|gave)\s+(?:me|you|us)\s+a\s+(?:quick\s+)?(?:call|ring|buzz)\b|\b(?:hop|jump)\s+on\b|\bmeet\b", re.I)
# "Zoom?", "WhatsApp instead?": a named platform on its own as a question
_CM_BARE_CHANNEL_Q_RE = re.compile(
    r"^(?:(?:or|maybe|how\s+about|what\s+about)\s+)?(?:(?:a|on|over|via)\s+)?[\w.'-]+(?:\s+[\w.'-]+)?"
    r"(?:\s+(?:instead|then|maybe|call|chat|meeting))?\s*\?$", re.I)


def _cm_channel(c: _CmClause, event: bool, post_platforms: FrozenSet[str] = frozenset()) -> Optional[str]:
    """'call' or 'contact' when the clause moves a conversation between the
    client and Lorenzo onto a channel, else None. With ``event`` (the sentence
    is the project's event or schedule: "text me when a lead comes in") only a
    channel of Lorenzo's counts ("your email", "do you have WhatsApp")."""
    clause = c.text
    for hit in _CM_CALL_TARGET_RE.finditer(clause):
        to_you = hit.group(0).lower().rstrip().endswith("you")
        if (to_you or not event) and c.live(hit.start(), to_lorenzo=to_you):
            return "call"
    # the project, its users or a third party in the clause: "we talk to them
    # by phone", "SMS is easier for our patients"
    project = bool(_CM_PROJECT_NOUN_RE.search(clause) or _THEY_RE.search(clause))
    party = bool(_CM_PARTY_RE.search(clause))
    my_party = bool(_CM_MY_PARTY_RE.search(clause) or _IMPERATIVE_RE.match(clause))
    for m in c.mentions:
        if m.cat == "pay":
            continue
        left, right = _tail(clause, m.start, 60), _head(clause, m.end, 60)
        if _project_right(right):
            continue
        as_verb = bool(_CM_TARGET_AFTER_RE.match(right)) and not _CM_DETERMINER_BEFORE_RE.search(left)
        to_you = bool(_CM_YOUR_BEFORE_RE.search(left)
                      or (re.search(r"\byou\b[^.?!\n\x00]{0,20}$", left, re.I) and _CM_HAVE_BEFORE_RE.search(left))
                      or (as_verb and re.match(r"^\s+you\b", right, re.I)))
        if (event and not to_you) or not c.live(m.start, to_lorenzo=to_you):
            continue
        move = _CM_MOVE_VERB_RE.search(left)
        mid = move.group("mid") if move and move.group("mid") else ""
        fires = (
            to_you or as_verb
            or bool(_CM_HAVE_BEFORE_RE.search(left) or _CM_REACH_BEFORE_RE.search(left)
                    or _CM_SENT_BEFORE_RE.search(left))
            or bool(move and not (_CM_PROJECT_NOUN_RE.search(mid) or _THEY_RE.search(mid)))
            or bool(m.cat in ("meet", "phone", "chat") and _CM_SHAPE_BEFORE_RE.search(left)
                    and (m.cat == "meet" or _CM_CALL_AFTER_RE.match(right)))
            or bool(not project and m.cat in ("meet", "chat", "phone", "email", "text", "dm")
                    and (_CM_LETS_BEFORE_RE.search(left) or (party and _CM_PREP_BEFORE_RE.search(left))))
            or bool(not project and ((_CM_MY_BEFORE_RE.search(left) and my_party)
                                     or _CM_PREFER_BEFORE_RE.search(left) or _CM_REQUEST_USE_BEFORE_RE.search(left)
                                     or _CM_PREFER_AFTER_RE.match(right)
                                     or (m.cat == "meet" and _CM_RAIL_OK_AFTER_RE.match(right))
                                     or (m.key in NAMED_PLATFORMS and m.key not in post_platforms
                                         and _CM_EASIER_AFTER_RE.match(right))))
        )
        if not fires:
            continue
        near = left[-40:] + " " + right[:20]
        if m.cat in ("meet", "book") or (m.cat in ("phone", "chat") and (_CM_CALL_CUE_RE.search(near)
                                                                          or _CM_CALL_AFTER_RE.match(right))):
            return "call"
        return "contact"
    return None


def _cm_files(c: _CmClause) -> bool:
    host = _CM_FILE_HOST_RE.search(c.text)
    if not host:
        return False
    share = _CM_FILE_SHARE_RE.search(c.text)
    return bool(share and c.live(min(share.start(), host.start()), to_lorenzo=True))


def _cm_details(sentence: str) -> Optional[str]:
    """'details' when the sentence gives an address, number or handle to use,
    'call' or 'contact' for a meeting, booking or chat link; None when it is
    the project's routing ("send the alerts to quotes@...", "our main line")."""
    link = None  # type: Optional[str]
    for url in find_urls(sentence):
        host = _host(url)
        if _blocked_host(host) and not host.endswith("upwork.com"):
            link = "contact" if any(host == h or host.endswith("." + h) for h in _CM_CHAT_HOSTS) else "call"
            break
    data = bool(_EMAIL_RE.search(sentence) or _EMAIL_NO_TLD_RE.search(sentence)
                or _OBFUSCATED_EMAIL_RE.search(sentence) or _phone_numbers(sentence)
                or _SPELLED_PHONE_RE.search(sentence))
    if not data:
        for hm in _HANDLE_RE.finditer(sentence):
            window = sentence[max(0, hm.start() - 30):hm.end() + 25]
            if _HANDLE_CONTEXT_RE.search(window.replace(hm.group(0), " ")):
                data = True
                break
    if not (link or data):
        return None
    if _CM_ROUTE_RE.search(sentence) and not _CM_PERSONAL_RE.search(sentence):
        return None
    return link or "details"


def _cm_talk_word(body: str) -> bool:
    """The message talks about a call or talking between the client and
    Lorenzo: not negated, not the project's ("customers call us")."""
    for sentence in _sentence_texts(body):
        for _, clause in _clause_spans(sentence):
            hit = _CM_TALK_WORD_RE.search(clause)
            if hit:
                c = _CmClause(clause)
                if not (c.negated(hit.start()) or c.blocked(hit.start(), to_lorenzo=True)):
                    return True
    return False


def _cm_message_categories(body: str, pay_project: bool = False,
                           post_platforms: FrozenSet[str] = frozenset()) -> Set[str]:
    """The move-request categories in one client message (normalised)."""
    found = set()  # type: Set[str]
    fee_reason = bool(_CM_FEE_REASON_RE.search(body))
    upwork_named = "upwork" in body.lower()
    talk = []  # type: List[bool]  # _cm_talk_word(body), read once when needed
    for sentence in _sentence_texts(body):
        details = _cm_details(sentence)
        if details == "details" and (_phone_numbers(sentence) or _SPELLED_PHONE_RE.search(sentence)):
            talk = talk or [_cm_talk_word(body)]
            if talk[0]:
                details = "call"  # "A call would be quicker. My cell is ...", "Easier to just talk. 512 ..."
        if details:
            found.add(details)
        if _CM_BARE_CHANNEL_Q_RE.match(sentence.strip()):
            named = [m for m in channel_mentions(sentence) if m.key in NAMED_PLATFORMS]
            talk = talk or [_cm_talk_word(body)]
            if (len(named) == 1 and named[0].key not in post_platforms
                    and named[0].cat in ("meet", "chat", "social", "dm") and (upwork_named or talk[0])):
                # "I can't do calls on Upwork. Zoom?", "Upwork messages are so slow. WhatsApp?"
                found.add("call" if named[0].cat == "meet" else "contact")
        files_words = bool(_CM_FILE_WORD_RE.search(sentence))
        pay_words = bool(_CM_PAY_WORD_RE.search(sentence) or _CM_MONEY_WORD_RE.search(sentence))
        your_fee = bool(_CM_YOUR_FEE_RE.search(sentence))
        event = bool(_CM_STREAM_EVENT_RE.search(sentence) or _CM_EVERY_ONE_RE.search(sentence)
                     or (_RECURRING_RE.search(sentence) and _CM_PROJECT_NOUN_RE.search(sentence)))
        for _, clause in _clause_spans(sentence):
            c = _CmClause(clause)
            if _cm_payment(c, pay_project, your_fee, sentence):
                found.add("payment")
            if fee_reason:
                ask = _CM_PAY_ASK_RE.search(clause)
                if ask and c.live(ask.start()) and not _cm_pay_kept(clause):
                    found.add("payment")  # "Upwork takes a big cut, how should I pay you?"
            for rx in _CM_LEAVE_RES:
                hit = rx.search(clause)
                if hit and not c.negated(hit.start()) and not c.blocked(hit.start()):
                    found.add("payment" if pay_words else "call" if re.match(r"(?:call|ring)\b", hit.group(0), re.I)
                              else "contact")
                    break
            if _cm_group(c):
                found.add("group")
            if _cm_files(c):
                found.add("files")
            channel = _cm_channel(c, event, post_platforms)
            if channel:
                found.add("files" if channel == "contact" and files_words else channel)
    return found


def client_move_request(room: Optional[Dict[str, Any]]) -> Optional[str]:
    """The category of a request, in the client's unanswered messages, to move
    contact, a call, files, a group or workspace, or payment off Upwork
    ('contact', 'call', 'files', 'group', 'payment'), or 'details' when they
    give a number, address or handle to use; None when there is none. The
    newest message with a request decides; its categories rank payment, call,
    group, files, contact, details."""
    messages = unanswered_client_messages(room)[-MOVE_REQUEST_MESSAGES:]
    facts = None  # type: Optional[Tuple[bool, FrozenSet[str]]]
    budget = MOVE_REQUEST_CHARS
    for msg in reversed(messages):
        if budget <= 0:
            break
        text = msg.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        body = normalise(decode_escapes(text))[:min(ANALYSIS_MAX_CHARS, budget)]
        budget -= len(body)
        if facts is None:
            facts = _cm_job_facts(room)
        found = _cm_message_categories(body, facts[0], facts[1])
        if not found and not facts[0] and _cm_money_tied(body):
            found = {"payment"}  # round 9: money tied to Lorenzo or Upwork, outside a payments job
        for category in _MOVE_ORDER:
            if category in found:
                return category
    return None


def _cm_job_facts(room: Optional[Dict[str, Any]]) -> Tuple[bool, FrozenSet[str]]:
    """(the job is about payments, the named platforms the job names). A
    payments job's title or post names a payment rail or a payments
    workflow."""
    room = room or {}
    job = room.get("job")
    post = decode_escapes(job.get("post") or "") if isinstance(job, dict) else ""
    text = "%s\n%s" % (decode_escapes(room.get("job_title") or ""), post[:2 * ANALYSIS_MAX_CHARS])
    mentions = channel_mentions(text)
    pay_project = bool(_CM_PAY_PROJECT_RE.search(text) or any(m.cat == "pay" for m in mentions))
    return pay_project, frozenset(m.key for m in mentions if m.key in NAMED_PLATFORMS)


# The draft keeps the requested thing on Upwork in so many words
# (keeps_on_upwork), category by category:
#   payment   Upwork tied to the payment, milestones, escrow, "pay here",
#             "keep payment here"
#   call      an Upwork call, "a call here", "on here", "here on Upwork",
#             "let's do it on Upwork"
#   contact, files, details and group: "here" or "this chat" as where the talk
#             or the files go ("keep / stay / attach / send / reply ... here"),
#             Upwork messages, or an Upwork call
# and, for any of them, a keep of everything ("keep things here", "let's stay
# on Upwork"). A filler "here" ("one thing I'd flag here", "happy to help
# here"), an extra copy ("a short summary here too"), milestones that list the
# work's phases ("two milestones: intake first, then the Slack ping"),
# "here's", "Upwork's fees", and those words after "off", "outside", "instead
# of", "rather than", "skip", "not on" and the like never count.
_KEEP_NOT_BEFORE_RE = re.compile(
    r"\b(?:off|outside|out\s+of|instead\s+of|rather\s+than|skip(?:ping)?|avoid(?:ing)?|bypass(?:ing)?|without|"
    r"around|leave|leaving|away\s+from|from|not\s+(?:on|through|via|in)|no)\s+(?:of\s+)?(?:the\s+)?(?:upwork\s+)?$",
    re.I)
_HERE_NOT_PLACE_RE = re.compile(r"^(?:'s\b|\s+(?:is|are|was|were|you\s+go|goes|comes|we\s+go)\b)", re.I)
_UPWORK_FEES_AFTER_RE = re.compile(r"^(?:'s)?\s+(?:fees?|cut|commission|charges?)\b", re.I)
_KEEP_NEG_BEFORE_RE = re.compile(
    r"\b(?:can't|cannot|can\s+not|won't|will\s+not|don't|do\s+not|doesn't|does\s+not|not|never|no\s+longer|"
    r"stop)\s+(?:[\w']+\s+){0,2}$", re.I)
_KEEP_EXTRA_AFTER_RE = re.compile(r"^\s*(?:too|as\s+well)\b", re.I)
_KEEP_EXTRA_OBJ_RE = re.compile(r"\b(?:a\s+copy|copies|also)\b", re.I)
_KEEP_PLACE = (r"(?:(?:right\s+)?here(?:\s+on\s+upwork)?|on\s+here|in\s+this\s+(?:chat|thread|room|conversation)|"
               r"(?:on|through|via|in|within|inside)\s+upwork)")
_KEEP_SPLIT_RE = re.compile(r"[,;:]|\s(?:and|but|so|then|while|though|although|or)\s", re.I)
# a keep of everything
_KEEP_ALL_RE = re.compile(
    r"\b(?:keep|keeps|keeping|kept|stay|stays|staying|remain|remains)\s+(?:(?:it|this|that|things|everything|"
    r"it\s+all|all\s+of\s+(?:it|this)|us|the\s+(?:conversation|chat|work|project|contract)|our\s+(?:conversation|"
    r"chat|communication|messages|work))\s+)?(?:all\s+)?(?P<place>%s)" % _KEEP_PLACE, re.I)
# payment: Upwork tied to the payment ("paying through Upwork", "Upwork
# milestones", "keeping it on Upwork protects us both"), not any Upwork ("the
# scope is here on Upwork")
_KEEP_PAY_WORDS = (r"(?:pay|pays|paying|paid|payment|payments|fund|funds|funding|funded|invoice|invoices|invoicing|"
                   r"deposit|deposits|money|billing|billed)")
_KEEP_PAY_RE = re.compile(
    r"\bmilestones?\b|\bescrow\b|"
    r"\b(?:pay|pays|paying|paid|payment|payments)\b(?:\s+[\w'-]+){0,5}?\s+(?:right\s+)?here\b|"
    r"\b%s\b(?:\s+[\w'-]+){0,5}?\s+(?:on|through|via|in|within|inside|over)\s+upwork\b|"
    r"\bupwork(?:'s)?\s+(?:milestones?|escrow|contract|payments?|payment\s+protection|protection|terms|billing)\b|"
    r"\bupwork\b[^.?!\n\x00]{0,40}?\b(?:%s|milestones?|escrow|protects?|protected|protection|covered)\b"
    % (_KEEP_PAY_WORDS, _KEEP_PAY_WORDS), re.I)
_MILESTONE_PHASES_RE = re.compile(
    r"^(?:\s+(?:plan|breakdown|split|structure|list|schedule|outline))?\s*(?::|-\s|\(|,\s*(?:one|the\s+first|first)\b|"
    r"\s+(?:would\s+be|are|being|covering|for)\b[^.?!\n\x00]{0,40}?\b(?:first|then)\b)", re.I)
# a call
_KEEP_CALL_RE = re.compile(
    r"\bupwork(?:'s)?\s+(?:(?:video|voice)\s+)?(?:calls?|calling|meetings?|video)\b|"
    r"\bupwork\s+(?:has|offers|supports)\s+(?:(?:built-in|built\s+in|video|voice)\s+)*calls?\b|"
    r"\bcalls?\s+(?:(?:right|over)\s+)?(?P<place>here)\b|\bon\s+here\b|\bhere\s+on\s+upwork\b|"
    r"\b(?:calls?|meet|meetings?|talk|speak|chat|video)\s+(?:[\w'-]+\s+){0,3}?(?:on|through|via|in|over|inside|"
    r"within)\s+upwork\b|"
    r"\b(?:do|have|hold|take|run|keep|make)\s+(?:it|this|that|the\s+(?:call|meeting|chat))\s+(?:(?:right|here)\s+)?"
    r"(?:on|through|via|in|over)\s+upwork\b",
    re.I)
# where the talk or the files go
_KEEP_TALK_VERBS = (
    r"keep|keeps|keeping|kept|stay|stays|staying|attach|attaching|attached|send|sending|reply|replies|replying|"
    r"respond|responding|answer|answering|message|messaging|chat|chatting|talk|talking|continue|continuing|write|"
    r"writing|drop|dropping|share|sharing|upload|uploading|post|posting|put|putting|check(?:ing)?\s+(?:back\s+)?in|"
    r"follow(?:ing)?\s+up|circle\s+back|pick(?:ing)?\s+(?:it|this|things)\s+(?:back\s+)?up|"
    r"get(?:ting)?\s+back\s+to\s+you|update\s+you|touch\s+base|catch\s+up")
_KEEP_TALK_RE = re.compile(
    r"\b(?:%s)\b(?P<obj>(?:\s+[\w'-]+){0,10}?)\s+(?P<place>%s)|"
    r"\bupwork\s+(?:messages?|messaging|chat|inbox|thread)\b" % (_KEEP_TALK_VERBS, _KEEP_PLACE), re.I)
_KEEP_KINDS = (("all", _KEEP_ALL_RE), ("payment", _KEEP_PAY_RE), ("call", _KEEP_CALL_RE), ("talk", _KEEP_TALK_RE))
# the cue kinds that keep each category's requested thing on Upwork
_KEEP_FOR = {
    "payment": ("all", "payment"),
    "call": ("all", "call"),
    "contact": ("all", "talk", "call"),
    "files": ("all", "talk", "call"),
    "details": ("all", "talk", "call"),
    "group": ("all", "talk", "call"),
}


def _keep_hit_counts(part: str, hit: "re.Match[str]") -> bool:
    """A keep cue ``hit`` in the clause ``part`` really keeps something on
    Upwork: not after "off", "instead of" and the like, not "here's" or
    "Upwork's fees", not negated, not an extra copy, not a list of phases."""
    text = hit.group(0).lower()
    for m in re.finditer(r"\b(?:upwork|here)\b", text):
        pos = hit.start() + m.start()
        if _KEEP_NOT_BEFORE_RE.search(_tail(part, pos, 40)):
            return False
        right = part[hit.start() + m.end():hit.start() + m.end() + 30]
        if m.group(0) == "here" and _HERE_NOT_PLACE_RE.match(right):
            return False
        if m.group(0) == "upwork" and _UPWORK_FEES_AFTER_RE.match(right):
            return False
    if re.match(r"milestones?$", text):
        return not (_KEEP_NOT_BEFORE_RE.search(_tail(part, hit.start(), 40))
                    or _MILESTONE_PHASES_RE.match(part[hit.end():]))
    if _KEEP_NEG_BEFORE_RE.search(_tail(part, hit.start(), 30)):
        return False  # "I can't keep payment here"
    if _KEEP_EXTRA_AFTER_RE.match(part[hit.end():]) or _KEEP_EXTRA_OBJ_RE.search(text):
        return False  # "a short summary here too", "a copy here"
    return not re.search(r"\balso\s+$", _tail(part, hit.start(), 12), re.I)


def _keep_kinds(body: str) -> Set[str]:
    kinds = set()  # type: Set[str]
    for sentence in _sentence_texts(body):
        cuts = [0] + [m.end() for m in _KEEP_SPLIT_RE.finditer(sentence)] + [len(sentence)]
        # a phase list after "milestones:" is read with its sentence, the rest clause by clause
        for kind, rx in _KEEP_KINDS:
            if kind in kinds:
                continue
            for i in range(len(cuts) - 1):
                part = sentence if kind == "payment" else sentence[cuts[i]:cuts[i + 1]]
                if any(_keep_hit_counts(part, hit) for hit in rx.finditer(part)):
                    kinds.add(kind)
                    break
                if kind == "payment":
                    break
    return kinds


def keeps_on_upwork(body: str, category: Optional[str] = None) -> bool:
    """The draft keeps things on Upwork in so many words: with ``category``,
    the cues that keep that category's requested thing on Upwork; without, any
    real keep cue."""
    kinds = _keep_kinds(body)
    if category is None:
        return bool(kinds)
    return any(kind in kinds for kind in _KEEP_FOR.get(category, ("all",)))


# An opening yes ("Sure", "Works for me", "That works", "Sounds good", "No
# problem", "Happy to") only labels the reason: a draft without the
# category's keep cue is refused whatever it opens with.
_OPENING_YES_RE = re.compile(
    r"^\s*(?:(?:hi|hey|hello|thanks|thank\s+you)\b[^.,!?\n\x00]{0,30}[,.!]\s*)?"
    r"(?P<yes>sure(?:\s+thing)?|works\s+(?:for\s+me|great|fine)|that\s+(?:works|would\s+work|'ll\s+work|will\s+work|"
    r"sounds\s+(?:good|great|fine)|is\s+fine)|that's\s+(?:fine|no\s+problem)|sounds\s+(?:good|great|perfect|fine)|"
    r"no\s+problem|no\s+worries|not\s+a\s+problem|(?:happy|glad)\s+to(?!\s+(?:hear|see|know|report|read)\b)|"
    r"will\s+do|can\s+do|of\s+course|absolutely|definitely|yes|yep|yeah|yup|fine\s+by\s+me|for\s+sure|"
    r"count\s+me\s+in)\b", re.I)


def _opening_yes(body: str) -> Optional[str]:
    for sentence in _sentence_texts(body):
        hit = _OPENING_YES_RE.match(sentence)
        if hit:
            return hit.group("yes")
    return None


# Words that point back at the client's own detail or ask override the keep
# cue: "I'll call that number Thursday and post the agenda here first", "I'll
# send the scope over to that address, and a copy here", "I'll join at noon,
# and put the notes in this chat after".
_GO_ALONG_RES = (
    # the client's detail
    re.compile(r"\b(?:that|this)\s+(?:(?:phone|cell|mobile)\s+)?number\b|\b(?:that|this)\s+(?:e-?mail|address)\b|"
               r"\bthat\s+(?:(?:zoom|meet|google\s+meet|teams|calendly|booking|meeting|calendar|whats\s?app|slack|"
               r"telegram|discord)\s+)?(?:link|invite|group|workspace)\b", re.I),
    # a direct send to the client
    re.compile(r"\bi(?:'ll|\s+will)\s+(?:call\s+you|ring|text)\b|\bi(?:'ll|\s+will)\s+e-?mail\s+you\b|"
               r"\bi(?:'ll|\s+will)\s+(?:e-?mail|send)\s+(?:it|this|that|them|these|those|everything|a\s+copy|"
               r"the\s+[\w-]+(?:\s+[\w-]+)?)\s+(?:over\s+)?to\s+you\b", re.I),
    # the client's call
    re.compile(r"\bi(?:'ll|\s+will)\s+join\b|\bjoin\s+the\s+call\b", re.I),
    # the client's group
    re.compile(r"\bi(?:'ll|\s+will)\s+(?:add|set\s+up)\s+(?:[\w-]+\s+){0,3}?group\b", re.I),
)
# The same, when the clause does not put it here: "I'll send it over tonight",
# "send the invite over", "happy to switch" ("I'll send it over here" and
# "an invite for a call here on Upwork" keep it on Upwork).
_GO_ALONG_UNPLACED_RES = (
    re.compile(r"\bi(?:'ll|\s+will|'m\s+going\s+to|\s+can)\s+(?:send|e-?mail|forward|shoot)\s+(?:it|them|this|that|"
               r"these|those|everything|the\s+[\w-]+(?:\s+[\w-]+)?)\s+(?:over|across|along)\b", re.I),
    re.compile(r"\bsend\s+(?:me\s+)?(?:over\s+)?(?:the|an?|your)\s+(?:[\w-]+\s+)?(?:invite|invitation)\b", re.I),
    re.compile(r"\b(?:happy|glad|fine|ok|okay|keen)\s+to\s+(?:switch(?:\s+over)?|(?:move|hop|jump|head|go)\s+"
               r"(?:it\s+|this\s+|things\s+|the\s+conversation\s+)?(?:over|across|there))\b"
               r"(?!\s+(?:the|it|them|this|that)\b)", re.I),
)
_GO_ALONG_PLACE_RE = re.compile(r"\b(?:here|upwork|milestones?|offer|contract|proposal)\b|\bthis\s+(?:chat|thread)\b",
                                re.I)


def _goes_along(body: str) -> Optional[str]:
    for rx in _GO_ALONG_RES:
        hit = rx.search(body)
        if hit:
            return hit.group(0)
    for sentence in _sentence_texts(body):
        cuts = [0] + [m.end() for m in _KEEP_SPLIT_RE.finditer(sentence)] + [len(sentence)]
        for i in range(len(cuts) - 1):
            part = sentence[cuts[i]:cuts[i + 1]]
            for rx in _GO_ALONG_UNPLACED_RES:
                hit = rx.search(part)
                if hit and not _GO_ALONG_PLACE_RE.search(part):
                    return hit.group(0)
    return None


# How each category stays on Upwork, for the reason
_MOVE_KEEP_WAYS = {
    "payment": "payment through Upwork milestones or escrow",
    "call": "a call here on Upwork",
    "group": "Upwork messages here",
    "files": "the files attached here in this chat",
    "contact": "Upwork messages here",
    "details": "Upwork messages or a call here on Upwork",
}


def move_request_reason(body: str, room: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why ``body`` goes along with the client's unanswered request to move off
    Upwork, or None. While a request is unanswered every draft needs a keep
    cue for its category, whatever it opens with; an opening yes only labels
    the reason. The reason names the request's category only, never the
    client's words."""
    along = _goes_along(body)
    kinds = _keep_kinds(body)
    if not along and "all" in kinds:
        return None  # "let's keep things here on Upwork" keeps any category
    category = client_move_request(room)
    if not category:
        return None
    ways = _MOVE_KEEP_WAYS[category]
    if not along:
        if any(kind in kinds for kind in _KEEP_FOR[category]):
            return None
        along = _opening_yes(body)
    if along:
        return MOVE_REASONS[category] + (", and the draft goes along with it (%r); keep it on Upwork instead (%s)"
                                         % (along, ways))
    return MOVE_REASONS[category] + ", and the draft does not keep it on Upwork (say it stays here: %s)" % ways


def off_platform_reason(body: str, room: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why ``body`` moves contact or payment off Upwork, or None."""
    if _EMAIL_RE.search(body) or _EMAIL_NO_TLD_RE.search(body) or _OBFUSCATED_EMAIL_RE.search(body):
        return "contains an email address"
    if _phone_numbers(body) or _SPELLED_PHONE_RE.search(body):
        return "contains a phone number"
    for hm in _HANDLE_RE.finditer(body):
        window = body[max(0, hm.start() - 30):hm.end() + 25]
        if _LORENZO_ID_RE.search(hm.group(0)) or _HANDLE_CONTEXT_RE.search(window.replace(hm.group(0), " ")):
            return "contains a handle tied to contact: %r" % hm.group(0)
    source = client_source_text(room)
    source_low = source.lower()
    client_channel = bool(_THERE_WORD_RE.search(body) and channel_mentions(_client_messages_text(room)))
    # round 10: outside a payments job a rail is Lorenzo's own payment (_rail_reason)
    rails = bool(_RAIL_QUICK_RE.search(body)) and not _cm_job_facts(room)[0]
    last = ""
    for sentence in _sentence_texts(body):
        reach = _REACH_OUT_VIA_RE.search(sentence)
        if (reach and not (_END_USER_RE.search(sentence) or _THEY_RE.search(sentence) or _SOMEONE_RE.search(sentence))
                and _actor_before(_actors(sentence), reach.start())[0] != "project"):  # "reps can reach out by phone"
            return "off-platform contact (a way to reach Lorenzo): %r" % reach.group(0)
        there = client_channel and not (_UPWORK_RE.search(sentence) or _UPWORK_RE.search(last))
        prev = ""
        for _, clause in _clause_spans(sentence):
            ctx = _Clause(clause, sentence, prev, source_low, room)
            reason = (_clause_reason(ctx) or (_there_reason(ctx) if there else None)
                      or (_rail_reason(ctx) if rails else None))
            if reason:
                return reason
            prev = clause
        last = sentence
    allowed = platforms_named(source)
    booking_topic = bool(_BOOKING_TOPIC_RE.search(source))
    for m in channel_mentions(body):
        if m.key in NAMED_PLATFORMS and m.key not in allowed:
            return "names %r, which the job post and the client's messages do not" % m.text
        if m.key == "bookinglink" and not booking_topic:
            return "names a %r, but the job is not about booking" % m.text
    return move_request_reason(body, room)


# ------------------------------------------------------------ links
# Bare domains ("make.com", "calendly.com") are links too. The list is kept to
# common TLDs so a missing space after a period ("done.It") is not a domain.
_TLDS = "com|io|ai|co|net|org|app|dev|xyz|ly|me|us|biz|info|uk|ca|au|online|store|tech|cloud|agency"
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"')\]]+|"
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,10}(?:%s)\b(?:/[^\s<>\"')\]]*)?" % _TLDS,
    re.I)
_OBFUSCATED_URL_RE = re.compile(r"\b[a-z0-9-]{1,63}\s*(?:\(dot\)|\[dot\]|\sdot\s)\s*(?:com|io|co|net|org|me|us)\b",
                                re.I)

# Hosts refused even when the job post contains them.
BLOCKED_HOSTS = ("upwork.com", "calendly.com", "cal.com", "zcal.co", "tidycal.com", "savvycal.com",
                 "meetings.hubspot.com", "calendar.google.com", "calendar.app.google", "meet.google.com",
                 "zoom.us", "teams.microsoft.com", "wa.me", "api.whatsapp.com", "chat.whatsapp.com", "t.me",
                 "telegram.me", "m.me", "join.skype.com", "calendar.app")


def _url_key(url: str) -> str:
    key = url.strip().lower()
    key = re.sub(r"^https?://", "", key)
    key = re.sub(r"^www\.", "", key)
    return key.rstrip(".,;:!?/")


def _host(url: str) -> str:
    return _url_key(url).split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]


def find_urls(text: str) -> List[str]:
    return [m.group(0) for m in _URL_RE.finditer(text or "")]


def _blocked_host(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS)


def _link_allowed(url: str, post_keys: Set[str]) -> bool:
    host = _host(url)
    if _blocked_host(host):
        return False
    if host == "loom.com" or host.endswith(".loom.com"):
        return True
    return _url_key(url) in post_keys


# ------------------------------------------------------------ placeholders, greetings, voice
# TODO / TBD only in capitals ("a todo list" is a feature); brackets and
# braces always.
_PLACEHOLDER_RE = re.compile(r"[\[\]]|\{\{|\}\}|\bTODO\b|\bTBD\b|<[A-Za-z_][A-Za-z_ ]{0,30}>")
_XX_RE = re.compile(r"\bX{2,}\b")  # case-sensitive: "xx" in lowercase casual text is not a slot

_GREETING = (r"(?:hey|hi|hiya|hello|dear|yo|morning|evening|greetings|good\s+(?:morning|afternoon|evening|day)|"
             r"thanks|thank\s+you|thx|cheers)")
_TITLE = r"(?:mr|mrs|ms|miss|mx|dr|prof)\.?"
# A greeting, an optional comma, up to three words, then punctuation or a line end.
_GREETING_NAME_RE = re.compile(
    r"^\s*%s\s*,?\s+@?((?:%s\s+)?[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,2}?)\s*(?:[,.;:?\n]|\s-\s|\s-$|$)" % (
        _GREETING, _TITLE), re.I)
# A greeting followed straight by a word, no comma: "Hey Dana one idea".
_GREETING_NEXT_RE = re.compile(r"^\s*%s\s+@?(?:%s\s+)?([A-Za-z][\w'-]*)" % (_GREETING, _TITLE), re.I)
# "Hello there, Dana." / "Hi again, Dana,": a filler word, a comma, then a name
# and punctuation.
_GREETING_THEN_NAME_RE = re.compile(
    r"^\s*%s(?:\s+(?:there|again|all|both|folks|team|everyone))?\s*,\s*@?(?:%s\s+)?([A-Za-z][\w'-]*)\s*"
    r"(?:[,.;:?\n]|\s-\s|\s-$|$)" % (_GREETING, _TITLE), re.I)
# A name first: "Dana, one idea", "Dana Whitfield, ...".
_NAME_FIRST_RE = re.compile(r"^\s*@?([A-Za-z][\w'-]*)(?:\s+[A-Z][a-z'-]+)?\s*,")
# A name first with a dash or colon: "Dana - one idea", "Dana: one idea".
# Label-shaped openers ("Timing: ...", "Scope - ...") are common, so this form
# counts only for a known client name or a common first name.
_NAME_FIRST_MARK_RE = re.compile(r"^\s*@?([A-Za-z][\w'-]*)(?:\s+[A-Z][a-z'-]+)?\s*(?:\s-\s|:\s|\s-$|:$|-\s)")
_CAPITALISED_RE = re.compile(r"[A-Z][a-z][a-z'-]*")
_GREETING_FILLER = ("there", "again")
_ADDRESSEE_OK = {"there", "all", "team", "folks", "everyone", "everybody", "again", "guys", "friend", "friends",
                 "crew", "yall", "y'all", "both", "you", "so", "quick", "just", "one", "ok", "okay", "yes", "yeah",
                 "sure", "great", "good", "well", "also", "btw", "update", "question", "idea", "note", "man", "hey",
                 "hi", "hello", "hope", "for", "much", "a", "an", "the", "i"}
# Sentence openers that are not names (a name check on them costs a retry).
_OPENERS = frozenset("""
quick noted agreed understood perfect right yes no ok okay so well also sure great good however plus anyway anyways
anyhow first second third one two update question idea thanks honest fair true funny interesting separately
yesterday meanwhile earlier otherwise instead tonight gotcha today tomorrow besides regardless likewise overall
alright awesome cool sweet fantastic wonderful excellent brilliant indeed sorry apologies congrats congratulations
welcome yep yup nope hmm ah oh ahh haha heads aside fyi ps tldr recap summary still though although afterwards later
next then now again lastly finally absolutely totally definitely exactly naturally similarly additionally currently
recently initially originally previously basically honestly frankly luckily sadly unfortunately fortunately
hopefully ideally personally technically generally typically usually normally obviously clearly apparently actually
really simply mostly weekends weekdays mornings evenings january february march july september october november
december leads customers patients clients reps staff guests members users buyers vendors homeowners owners tenants
nobody someone anyone everyone either neither both whichever whatever sounds makes happy glad nice love
""".split())
# Tools and products: never a first name ("Airtable, not Sheets, ..."). The
# job post and config/upwork_offers.md add their own (see _product_words).
KNOWN_PRODUCTS = frozenset("""
airtable zapier make n8n hubspot salesforce pipedrive gohighlevel ghl highlevel slack notion monday clickup asana
trello jira shopify woocommerce stripe twilio calendly gmail outlook sheets excel docs drive dropbox typeform
jotform webflow wordpress wix squarespace bubble softr glide retool supabase firebase postgres mysql openai chatgpt
claude gemini vapi retell bland voiceflow manychat intercom zendesk freshdesk helpscout mailchimp klaviyo
activecampaign convertkit instantly lemlist apollo clay phantombuster apify quickbooks xero freshbooks gusto
docusign pandadoc jobber servicetitan housecall podium keap kajabi teachable thinkific skool loom figma canva zoho
freshsales attio brevo sendgrid mailgun postmark aircall ringcentral dialpad justcall openphone textline vonage
plivo telnyx integromat pabbly workato coda smartsheet baserow nocodb tally fillout formstack acuity mindbody
vagaro boulevard zenoti simplepractice cliniko dentrix weave nexhealth zocdoc yelp google facebook meta instagram
tiktok linkedin youtube twitter whatsapp telegram zoom teams discord signal skype paypal venmo zelle wise upwork
fiverr github gitlab vercel netlify aws azure heroku replit cursor lovable perplexity midjourney elevenlabs
deepgram pinecone langchain flowise botpress tidio drift hotjar semrush ahrefs gorgias recharge shipstation
calcom tidycal savvycal sheet crm api sms
""".split())
_TEAM_WORDS = {"team", "folks", "crew", "all", "gang", "people"}
_COMPANY_WORDS = {"llc", "inc", "ltd", "co", "corp", "company", "the", "and", "group", "services", "solutions",
                  "studio", "agency", "labs", "llp", "gmbh", "pty", "limited"}
# Common first names that are not also everyday words (no Will, Mark, May,
# Grace, Hope ...). Used where a lowercase or label-shaped opening gives no
# other signal: "hey dana one idea", "Dana: ...", "Dana - ...".
COMMON_FIRST_NAMES = frozenset("""
aaron abby abigail adam adrian ahmed aidan aisha alan albert alejandro alex alexa alexander alexandra alexis ali
alice alicia alison allison alyssa amanda amelia amir amit amy ana andre andrea andres andrew andy angela angelica
anita ann anna anne annie anthony antonio anya ari arjun arthur ashley austin ava avery barbara becky ben benjamin
beth bethany betty beverly bianca blake bobby brad bradley brandon brenda brendan brett brian brianna bridget
brittany brooke bruce bryan caitlin caleb cameron camila carl carla carlos carmen carol caroline carolyn casey
catherine cathy chad charles charlie charlotte chelsea cheryl chloe chris christian christina christine
christopher cindy claire clara claudia cody colin connor courtney craig cristina cynthia dan dana daniel daniela
danielle david dean debbie deborah debra denise dennis derek diana diane diego dmitri dominic donald donna doris
doug douglas dylan eduardo edward elena eli elijah elizabeth ellen emily emma eric erica erik erin ethan eugene
evan evelyn fatima felix fernando fiona francesca francisco frances gabriel gabriela gabrielle gary gavin george
gerald gina giovanni gloria gordon greg gregory hailey haley hannah harold harper harry hassan heidi helen henry
hiroshi holly howard hugo ian irene isaac isabel isabella ivan jacob jacqueline jake james jamie jan jane janet
janice jared jasmine jason javier jeff jeffrey jen jenna jennifer jenny jeremy jerry jesse jessica jill jim jimmy
joan joanna joe joel john johnny jon jonathan jordan jorge jose joseph josh joshua juan judith judy julia julian
julie justin kara karen kate katelyn katherine kathleen kathryn kathy katie kayla keith kelly ken kenji kenneth
kevin kim kimberly kristen kristin kristy kyle lana lars laura lauren leah leo leon leslie liam linda lindsay
lindsey lisa liz logan lori lorraine louis lucas lucia luis luke luna lydia madison maria mariana marie marissa
marco marcus margaret mario marisa marta martin mary mason matt matthew megan meghan melanie melissa michael
michelle miguel mike mila mohammed monica morgan muhammad nadia naomi natalie nate nathan nicholas nick nicole
nina noah noor olga oliver olivia omar owen pablo pam pamela patricia patrick paul paula peggy peter phil philip
phillip priya rachel rafael rahul raj ralph randy raquel ravi rebecca renee ricardo richard rick ricky riley
rita robert roberto rodrigo roger ron ronald rosa ryan sally sam samantha samuel sandra sanjay santiago sara sarah
scott sean sebastian sergei sergio shannon sharon shawn sheila shelby shirley simon sofia sonia sophia sophie
stacy stefan stephanie stephen steve steven susan suzanne sydney tanya tara taylor ted teresa terry theresa thomas
tiffany tim timothy tina todd tom tommy tony tracy travis trevor tyler valentina vanessa veronica vicky victor
victoria vikram vincent walter wayne wei wendy whitney william xavier yasmin yuki yvonne zach zachary zara zoe
""".split())
_SIGNOFF_RE = re.compile(
    r"(?:^|\n|[.!?]\s)\s*(?i:thanks|thank you|thx|cheers|best|regards|best regards|kind regards|sincerely|"
    r"talk soon|-+|~)\s*,?\s*([A-Z][a-z]+)(?:\s+[A-Z][a-z]+)?\s*\.?\s*$")
# A sign-off line with the name on the next line and maybe a company line
# after it: "Thanks,\nDana Whitfield\nBrightline Tile".
_SIGNOFF_BLOCK_RE = re.compile(
    r"(?:^|\n)\s*(?i:thanks|thank you|thx|cheers|best|regards|best regards|kind regards|sincerely|talk soon)\s*,?"
    r"\s*\n\s*([A-Z][a-z]+)\b")
_SELF_NAME_RE = re.compile(r"\b(?i:i'?m|i am|this is|it's|it is|my name is)\s+([A-Z][a-z]+)\b|"
                           r"(?:^|[.!?]\s+)([A-Z][a-z]+)\s+here\b")


def _not_a_name(low: str) -> bool:
    return (low in _ADDRESSEE_OK or low in STOP_WORDS or low in _OPENERS or low in KNOWN_PRODUCTS
            or low in _COMPANY_WORDS)


def _signed_names(text: str) -> Set[str]:
    """Names a piece of client text is signed with or introduces."""
    out = set()  # type: Set[str]
    body = decode_escapes(text or "").strip()
    m = _SIGNOFF_RE.search(body)
    if m and not _not_a_name(m.group(1).lower()):
        out.add(m.group(1).lower())
    for bm in _SIGNOFF_BLOCK_RE.finditer(body[-300:]):
        if not _not_a_name(bm.group(1).lower()):
            out.add(bm.group(1).lower())
    for sm in _SELF_NAME_RE.finditer(body):
        name = sm.group(1) or sm.group(2)
        if name and not _not_a_name(name.lower()):
            out.add(name.lower())
    return out


def client_names(room: Optional[Dict[str, Any]]) -> Set[str]:
    """Lower-case name words: room["client"] (minus company words) and any
    name the client signed the job post or a message with, or introduced
    themself by. The model sees the post, so a signed post leaks a name too."""
    room = room or {}
    out = set()  # type: Set[str]
    for w in re.findall(r"[A-Za-z][A-Za-z'-]+", str(room.get("client") or "")):
        if len(w) >= 3 and w.lower() not in _COMPANY_WORDS:
            out.add(w.lower())
    job = room.get("job") or {}
    if isinstance(job, dict) and job.get("post"):
        out |= _signed_names(job.get("post"))
    for msg in room.get("messages") or []:
        if isinstance(msg, dict) and msg.get("side") == "client":
            out |= _signed_names(msg.get("text") or "")
    return out


def _product_words(room: Optional[Dict[str, Any]], offers_text: str = "") -> Set[str]:
    """Words that are not first names in this room: tool and product tokens
    in the post and config/upwork_offers.md (CamelCase, digits, capitals) and
    every word the client or the post writes in lowercase."""
    source = client_source_text(room) + "\n" + decode_escapes(offers_text or "")
    out = set()  # type: Set[str]
    for w in re.findall(r"\b[A-Za-z][A-Za-z0-9]*(?:[A-Z][a-z0-9]*|\d)[A-Za-z0-9]*\b", source):
        out.add(w.lower())
    for w in re.findall(r"(?<![A-Za-z'])[a-z][a-z'-]{2,}\b", source):
        out.add(w)
    return out - COMMON_FIRST_NAMES


def _name_like(word: str, common: Iterable[str] = ()) -> bool:
    low = word.lower()
    return (bool(_CAPITALISED_RE.fullmatch(word)) and not _not_a_name(low) and not low.endswith("ly")
            and low not in set(common))


def first_name_problem(body: str, room: Optional[Dict[str, Any]], offers_text: str = "") -> Optional[str]:
    """With client_first_name null: the opening addresses a person by name.

    Refused: a greeting then one word and punctuation ("Hi Dana.", "hey dana,",
    "Thanks Dana,", "Good morning, Dana."), a filler word first ("Hey there
    Dana,", "Hi again Dana,", "Hello there, Dana."), a title ("Hello Mr.
    Whitfield,"), two or three capitalised words ("Hey Dana Whitfield,"), a
    capitalised word right after the greeting ("Hey Dana one idea"), a name
    first ("Dana, ...", "Dana: ...", "Dana - ..."), and any word of
    room["client"] or a name the client signed with in those positions ("hey
    dana one idea" when she signed "Dana"). Allowed: "hey there", "hey, quick
    idea", "Hey Brightline team,", sentence openers ("Yesterday,") and tool
    names ("Airtable, not Sheets, ...")."""
    room = room or {}
    if (room.get("client_first_name") or "").strip():
        return None
    names = client_names(room)
    common = _product_words(room, offers_text) - names
    text = body.lstrip()

    def problem(word: str) -> str:
        return "addresses %r but the client's first name is unknown" % word

    def is_name(word: str) -> bool:
        low = word.lower()
        return low in names or (low not in common and (_name_like(word, common) or low in COMMON_FIRST_NAMES))

    g = _GREETING_NAME_RE.match(text)
    if g:
        raw = [w.strip(".'-@") for w in g.group(1).split()]
        while len(raw) > 1 and raw[0].lower() in _GREETING_FILLER:
            raw = raw[1:]
        titled = bool(raw) and bool(re.fullmatch(_TITLE, raw[0], re.I))
        words = [w for w in raw if w and not re.fullmatch(_TITLE, w, re.I)]
        low = [w.lower() for w in words]
        if low and low[-1] not in _TEAM_WORDS:
            if titled or any(w in names for w in low):
                return problem(g.group(1))
            if len(low) == 1 and not _not_a_name(low[0]) and low[0] not in common:
                return problem(g.group(1))
            if len(words) > 1 and all(_CAPITALISED_RE.fullmatch(w) for w in words) and \
                    not any(w.lower() in common or _not_a_name(w.lower()) for w in words):
                return problem(g.group(1))
    gt = _GREETING_THEN_NAME_RE.match(text)
    if gt and is_name(gt.group(1)):
        return problem(gt.group(1))
    nxt = _GREETING_NEXT_RE.match(text)
    if nxt:
        word = nxt.group(1)
        after = text[nxt.end():nxt.end() + 12].strip().lower()
        if word.lower() in _GREETING_FILLER:
            later = re.match(r"\s+([A-Za-z][\w'-]*)", text[nxt.end():])
            if later and (later.group(1).lower() in names or (_name_like(later.group(1), common)
                                                              and not later.group(1).lower() in _TEAM_WORDS)):
                after2 = text[nxt.end() + later.end():nxt.end() + later.end() + 12].strip().lower()
                if not any(after2.startswith(t) for t in _TEAM_WORDS):
                    return problem(later.group(1))
        elif not any(after.startswith(t) for t in _TEAM_WORDS) and is_name(word):
            return problem(word)
    nf = _NAME_FIRST_RE.match(text)
    if nf:
        word = nf.group(1)
        if word.lower() in names or _name_like(word, common) or \
                (word.lower() in COMMON_FIRST_NAMES and word.lower() not in common):
            return problem(word)
    nm = _NAME_FIRST_MARK_RE.match(text)
    if nm:
        word = nm.group(1).lower()
        if word in names or (word in COMMON_FIRST_NAMES and word not in common):
            return problem(nm.group(1))
    return None


# Client quotes: double quotes anywhere, single quotes only when they open
# after a space or punctuation and close before one (apostrophes stay words).
_QUOTED_RE = re.compile(r'"[^"\n]{1,400}"|(?:(?<=[\s(:,])|^)\'[^\'\n]{2,300}?\'(?=[\s.,;:!?)]|$)')
_PLURAL_RE = re.compile(r"\b(?:we|we're|we've|we'll|we'd|our|ours|ourselves)\b", re.I)
_US_RE = re.compile(r"\b(?:us|Us)\b")  # "US" (the country) is left alone
_THIRD_PERSON_RE = re.compile(r"\bLorenzo\s+(?:will|can|is|has|would|could|builds|built)\b", re.I)

# Filler and stock lines (DESIGN "Tone and voice"). They are Lorenzo's voice
# unless ANOTHER SUBJECT comes right before the phrase in the same clause (the
# bot, the system, the sequence, the workflow, leads, reps, your team, your
# front desk, they, it, you), or the phrase is aimed at a third party ("touch
# base with the lead"). No subject means Lorenzo: his casual voice drops "I"
# after "hey,", so "hey, circling back on ..." and "Wanted to follow up on ..."
# are refused.
_OTHER_SUBJECT = (
    r"(?:(?:%s)\s+(?:[\w'-]+\s+){0,2}?(?:%s)|(?:%s)|you|you'll|you'd|they|they'll|they'd|it|it'll|he|she|"
    r"who|that|which)" % (
        _DETERMINER, _PROJECT_HEADS, _PROJECT_HEADS))
_AUX = (r"(?:can|could|will|would|should|may|might|must|'ll|'d|then|also|just|still|never|always|often|rarely|"
        r"usually|automatically|immediately|instantly|wanted\s+to|want\s+to|wants\s+to|needs?\s+to|needed\s+to|"
        r"has\s+to|have\s+to|had\s+to|tries\s+to|try\s+to|tried\s+to|forgets?\s+to|forgot\s+to|remembers?\s+to|"
        r"is|are|was|were|keeps?|kept|stops?|stopped|starts?|started|don't|doesn't|didn't|won't|can't|to|"
        r"is\s+supposed\s+to|are\s+supposed\s+to|gets\s+to|get\s+to)")
_SUBJECT_BEFORE_RE = re.compile(r"\b%s(?:\s+%s)*\s*$" % (_OTHER_SUBJECT, _AUX), re.I)
_THIRD_OBJECT_RE = re.compile(
    r"^\s+(?:with|on|to)\s+(?:the\s+|each\s+|every\s+|new\s+|any\s+|a\s+|those\s+|these\s+|their\s+|your\s+|"
    r"that\s+|this\s+)?(?:%s|them|reps?|techs?|the\s+team|front\s+desk)\b" % _END_USERS, re.I)
_FILLER_RE = re.compile(
    r"\b(?:just\s+)?(?:checking\s+in|check\s+in|circling\s+back|circle\s+back|touching\s+base|touch\s+base|"
    r"bumping\s+(?:this|it)|bump\s+this|following\s+up|follow\s+up)\b", re.I)
_FOLLOW_TAIL_RE = re.compile(
    r"^(?:\s+\w+ly)?(?:\s+(?:on|about|re|regarding|here|again|once\s+more|one\s+more\s+time|in\s+case)\b|"
    r"\s+with\s+you\b|\s*[.,?;!:]|\s*$)", re.I)
_BUMP_PROJECT_RE = re.compile(r"^\s+(?:lead|leads|record|contact|deal|ticket|task|card|row|up\s+the)\b", re.I)
_NOUN_DET_RE = re.compile(r"\b(?:a|an|the|this|that|each|every|any|one|first|second|third|next|last|quick|short|"
                          r"automatic|automated|same-day|written|proper|your|my|their)\s+$", re.I)
_CLAUSE_EDGE_RE = re.compile(r"[.?!;:,\n]|\s-\s")


def _clause_before(text: str, pos: int) -> str:
    """The text from the start of the clause holding ``pos`` up to ``pos``."""
    edges = [m.end() for m in _CLAUSE_EDGE_RE.finditer(text, 0, pos)]
    return text[(edges[-1] if edges else 0):pos]


def _is_lorenzos(text: str, start: int, end: int) -> bool:
    """A filler or stock phrase at text[start:end] is in Lorenzo's own voice:
    no other subject right before it in the same clause and no third-party
    object after it."""
    before = _clause_before(text, start)
    if _SUBJECT_BEFORE_RE.search(before):
        return False
    return not _THIRD_OBJECT_RE.match(text[end:])


def filler_match(text: str) -> Optional[str]:
    """The first filler phrase in Lorenzo's own voice, or None."""
    for m in _FILLER_RE.finditer(text or ""):
        phrase = m.group(0).lower()
        tail = text[m.end():]
        before = _clause_before(text, m.start())
        if "follow" in phrase or "check" in phrase:
            if _NOUN_DET_RE.search(before) or not _FOLLOW_TAIL_RE.match(tail):
                continue  # "a follow up", "follow up with a written scope"
        if "bump" in phrase and _BUMP_PROJECT_RE.match(tail):
            continue
        if _is_lorenzos(text, m.start(), m.end()):
            return m.group(0).strip()
    return None


# Stock follow-up lines. (pattern, subject-exempt): a subject-exempt line
# passes when another subject says it ("your front desk wanted to follow up").
_STOCK_RES = (
    (re.compile(r"\bhope\s+(?:you're|you\s+are|you've|you\s+have|you\s+had|you\s+were|all(?:'s|\s+is|\s+has|\s+was|"
                r"\s+good|\s+well)|everything(?:'s|\s+is|\s+has|\s+was)|things\s+(?:are|have|went)|"
                r"the\s+week(?:'s|\s+is|\s+has|\s+went)|your\s+week|the\s+weekend|your\s+weekend|your\s+day|"
                r"the\s+day|this\s+(?:finds|message|note|email)|business\s+is|work\s+is|life\s+is)\b", re.I), False),
    (re.compile(r"\b(?:wanted|want|wanting|thought\s+i'?d)\s+to\s+(?:follow\s+up|reach\s+out|check\s+in|"
                r"touch\s+base|circle\s+back|ping\s+you|nudge\s+you|bump\s+this)\b", re.I), True),
    (re.compile(r"\btouch(?:ing)?\s+base\b", re.I), True),
    (re.compile(r"\bany\s+(?:updates?|news|word|progress)\b(?:\s*\?|\s+(?:on|about|regarding|yet|so\s+far|since|"
                r"from\s+your\s+end|on\s+your\s+end)\b)|\bany\s+news\b", re.I), False),
    (re.compile(r"\bany\s+(?:thoughts|feedback)\s*\?|\bany\s+(?:thoughts|feedback)\s+(?:on|about)\s+(?:this|that|it|"
                r"my\s+\w+|the\s+(?:[\w'-]+\s+){0,2}?(?:idea|proposal|message|note|loom|video|plan|draft|approach|"
                r"suggestion|above|mockup|flow\s*chart|last\s+one))\b", re.I), False),
    (re.compile(r"\bdid\s+you\s+(?:get|have)\s+a\s+chance\b|\bhad\s+a\s+chance\s+to\s+(?:review|look)\b", re.I), False),
    (re.compile(r"\blet\s+me\s+know\s+if\s+you\s+have\s+any\s+questions\b|\bfeel\s+free\s+to\s+reach\s+out\b|"
                r"\bat\s+your\s+earliest\s+convenience\b", re.I), False),
    (re.compile(r"\bi'?d\s+love\s+to\s+help\b|\bi\s+would\s+love\s+to\s+help\b|"
                r"\b(?:i'?m|i\s+am)\s+the\s+perfect\s+fit\b|\blooking\s+forward\s+to\s+hearing\s+from\s+you\b",
                re.I), False),
)


def stock_match(text: str) -> Optional[str]:
    """The first stock follow-up line in Lorenzo's own voice, or None."""
    for rx, subject_exempt in _STOCK_RES:
        for m in rx.finditer(text or ""):
            if subject_exempt and not _is_lorenzos(text, m.start(), m.end()):
                continue
            return m.group(0).strip()
    return None


# ------------------------------------------------------------ distinctive terms
# Words that say nothing about THIS client: English function words, follow-up
# vocabulary, and the generic Upwork automation words every post shares.
STOP_WORDS = frozenset("""
about above after again against also always another anyone anything anyway around away back been before
being below best better between both bring came come comes coming could didn does doing done down during
each easy either else even ever every everything fine first from further gets getting give given goes going
gone good great half have having hear heard hello help here hers herself high himself hope hoping into
itself just keep kind know knew last late later least less like likely little long look looked looking
lots made make makes making many maybe mean might mine more most much must myself need needed needs never
next nice none nothing okay once only other others ours ourselves over own part pick please plus pretty
quick quite rather ready real really right said same says seem seems seen send sent should show side since
some something soon sort still such sure take takes taking talk tell than thank thanks that thats their
theirs them themselves then there these they thing things think this those though thought thoughts through
till time times today together tomorrow took toward tried tries truly under until upon very want wanted
wants well went were what whatever when where whether which while whole whom whose will wish with within
without wonder work worked working works would year years your yours yourself you're you've you'll you'd
i'm i've i'll i'd it's that's there's what's don't didn't doesn't won't can't isn't aren't wasn't let's
hey there team folks everyone upwork proposal proposals message messages reply replied chat call calls
minute minutes hour hours week weeks month months monday tuesday wednesday thursday friday saturday sunday
noon morning afternoon evening happy glad idea ideas question questions update updates follow following
checking circle back touch base interested interest project projects client clients business businesses
company companies system systems build building built automation automate automated automating workflow
workflows process processes solution solutions tool tools setup integration integrate integrations
experience expert experts looking loom video demo lorenzo freelancer hire hiring post posted posting
job jobs quote price pricing budget cost costs rate milestone milestones scope timeline start started
fit fits option options step steps easy simple able free open door worries worry either way
quot nbsp amp
""".split())


def _stem(word: str) -> str:
    w = word
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 6 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 5 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 5 and w.endswith("es") and w[-3] in "sxz":
        return w[:-2]
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'+-]*[a-z0-9+]|[a-z0-9]")


def distinctive_terms(text: str, exclude: Iterable[str] = ()) -> Set[str]:
    """Stemmed words of 4+ characters that are not stop-words, not pure numbers
    and not in ``exclude`` (the client's own name, so a greeting alone never
    counts as bespoke)."""
    skip = set()  # type: Set[str]
    for item in exclude:
        for w in _WORD_RE.findall((item or "").lower()):
            skip.add(_stem(w))
    out = set()  # type: Set[str]
    for raw in _WORD_RE.findall(normalise(decode_escapes(text)).lower()):
        w = raw[:-2] if raw.endswith("'s") else raw
        w = w.strip("'-")
        if len(w) < 4 or w in STOP_WORDS or w.replace(",", "").replace(".", "").isdigit():
            continue
        s = _stem(w)
        if s in STOP_WORDS or s in skip or len(s) < 4:
            continue
        out.add(s)
    return out


def client_source_text(room: Optional[Dict[str, Any]]) -> str:
    """The job post, the job title and every client-side message, decoded."""
    room = room or {}
    parts = []  # type: List[str]
    job = room.get("job") or {}
    if isinstance(job, dict) and job.get("post"):
        parts.append(decode_escapes(job.get("post")))
    if room.get("job_title"):
        parts.append(decode_escapes(room.get("job_title")))
    for msg in room.get("messages") or []:
        if isinstance(msg, dict) and msg.get("side") == "client" and msg.get("text"):
            parts.append(decode_escapes(msg.get("text")))
    return "\n".join(parts)


def _client_messages_text(room: Optional[Dict[str, Any]]) -> str:
    """Every client-side message, decoded (not the job post)."""
    return "\n".join(decode_escapes(msg.get("text")) for msg in (room or {}).get("messages") or []
                     if isinstance(msg, dict) and msg.get("side") == "client" and msg.get("text"))


def shared_terms(text: str, room: Optional[Dict[str, Any]]) -> Set[str]:
    room = room or {}
    names = [str(room.get("client") or ""), str(room.get("client_first_name") or "")]
    return distinctive_terms(text, names) & distinctive_terms(client_source_text(room), names)


# ------------------------------------------------------------ the framework band
# Lorenzo, 2026-10-06: a framework reply (draft.is_framework_reply) states
# the price as a range computed from the assessment (draft.price_band). The
# gate is handed that band and lets exactly its two figures through, together,
# in a range form: "between $1,500 and $2,000", "$1,500 to $2,000",
# "$1,500-$2,000" (the second "$" optional, commas optional), stated once in
# its sentence. Everything else keeps its rule: a single price, one end
# alone, an off-band figure and agreeing to the client's number are still
# refused.
BAND_MASK = "the band"
_BAND_RE = re.compile(
    r"(\bbetween\s+)?\$\s?(\d[\d,]*(?:\.\d+)?)(\s?k)?\s*(-|to|and)\s*\$?\s?(\d[\d,]*(?:\.\d+)?)(\s?k)?(?![\d,]*\d)",
    re.I)


# A band next to a rate or a per-unit word is a rate, not the project's
# price, so it is not masked and the figure check refuses it (Lorenzo,
# 2026-10-06: anywhere in the same sentence, before or after the range).
# Right after the range: "/" and a word, per / each / every, a/an plus a
# period or a unit ("a month", "an hour", "a lead"), monthly / hourly / ....
_BAND_RATE_TAIL_RE = re.compile(
    r"^\s*(?:/\s?\w|(?:per|each|every)\b|(?:a|an)\s+(?:month|mo|hour|hr|week|wk|year|yr|day|workflow|seat|user|"
    r"location|lead|client|clinic|site|call|message|unit|piece|account|inbox|domain|sequence|campaign|page)s?\b|"
    r"(?:monthly|hourly|annually|yearly|weekly|daily)\b)", re.I)
# Anywhere in the sentence that states the range: per, each, every, apiece,
# "a pop", a rate adverb (monthly, quarterly, weekly, hourly, daily, yearly,
# annually, ...), retainer, subscription, billed, "/", "x 2", times, "on a
# monthly basis", "the first month", and a/an plus a unit ("a seat", "a
# location") or a period ("a month", "a quarter"). A period after "about /
# within / in / under / ..." is a duration, not a rate ("I aim to finish in
# about a week").
_BAND_CUE_RE = re.compile(
    r"\b(?:per|each|every|apiece|retainers?|subscriptions?|billed|invoiced|times|multiplied|monthly|quarterly|weekly|"
    r"hourly|daily|yearly|annually|annual|biweekly|bi-weekly|fortnightly|installments?|instalments?|basis)\b|"
    r"\ba\s+pop\b|\bx\s*\d|\d\s*x\b|/|"
    r"\b(?:first|second|third)\s+(?:month|quarter|year)s?\b|"
    r"\b(?:a|an)\s+(?:workflow|seat|user|location|lead|client|clinic|site|unit|piece|account|inbox|mailbox|domain|"
    r"license|licence|store|branch|office|agent|campaign|sequence|form|page|integration|automation|bot|head|member|"
    r"contact)s?\b", re.I)
_BAND_PERIOD_RE = re.compile(r"\b(?:a|an)\s+(?:hour|hr|day|week|wk|month|mo|quarter|year|yr)s?\b", re.I)
_BAND_DURATION_BEFORE = frozenset(
    "about around roughly approximately approx within in inside under over than after before by half just only "
    "almost nearly".split())
_BAND_URL_RE = re.compile(r"(?:https?://|www\.)\S+|<[^>\s]*://[^>]*>", re.I)
BAND_TOKEN = " _range_ "


def _band_cue(sentence: str) -> Optional[str]:
    """The first rate, per-unit or period cue in ``sentence`` (the range
    itself already replaced by BAND_TOKEN), or None."""
    text = _BAND_URL_RE.sub(" ", sentence)
    m = _BAND_CUE_RE.search(text)
    if m:
        return m.group(0)
    for m in _BAND_PERIOD_RE.finditer(text):
        before = re.findall(r"[\w']+", text[:m.start()])
        if not before or before[-1].lower() not in _BAND_DURATION_BEFORE:
            return m.group(0)
    return None


def _band_statements(body: str, band: Optional[Sequence[Any]]) -> List[Tuple[int, int, Optional[str]]]:
    """(start, end, cue) of every place ``body`` states exactly ``band``
    (low, high) in a range form ("and" only after "between"). ``cue`` is None
    for a statement that counts, else what keeps it from counting: a rate or
    per-unit word right after it, a cue anywhere in its sentence (see
    _BAND_CUE_RE), or the range stated twice in one sentence ("$750 to
    $3,500 for the build plus $750 to $3,500 for phase two")."""
    if not band or len(band) != 2 or not body:
        return []
    want = (_canon(str(band[0])), _canon(str(band[1])))
    found = []  # type: List[Tuple[int, int]]
    for m in _BAND_RE.finditer(body):
        if m.group(4).lower() == "and" and not m.group(1):
            continue
        low = _canon(m.group(2), (m.group(3) or "").strip())
        high = _canon(m.group(5), (m.group(6) or "").strip())
        if (low, high) == want:
            found.append((m.start(), m.end()))
    if not found:
        return []
    sentences = _fw_sentences(body)
    out = []  # type: List[Tuple[int, int, Optional[str]]]
    for start, end in found:
        s_start, s_end = next(((s, e) for s, e in sentences if s <= start < e), (0, len(body)))
        tail = _BAND_RATE_TAIL_RE.match(body[end:end + 40])
        cue = tail.group(0).strip() if tail else None
        if cue is None:
            others = [(s, e) for s, e in found if s_start <= s < s_end and (s, e) != (start, end)]
            if others:
                cue = "the range twice in one sentence"
        if cue is None:
            cue = _band_cue(body[s_start:start] + BAND_TOKEN + body[end:s_end])
        out.append((start, end, cue))
    return out


def band_spans(body: str, band: Optional[Sequence[Any]]) -> List[Tuple[int, int]]:
    """(start, end) of every place ``body`` states exactly ``band`` (low,
    high) in a range form that counts: "and" only after "between", and no
    rate, per-unit or period cue in its sentence (see _band_statements)."""
    return [(s, e) for s, e, cue in _band_statements(body, band) if cue is None]


def band_rate_cues(body: str, band: Optional[Sequence[Any]]) -> List[str]:
    """The cues that kept a stated band from counting, in order."""
    return [cue for _, _, cue in _band_statements(body, band) if cue]


def mask_band(body: str, band: Optional[Sequence[Any]]) -> str:
    """``body`` with every stated band replaced by BAND_MASK, for the figure,
    price-agreement and private-fact checks only."""
    spans = band_spans(body, band)
    if not spans:
        return body
    out, last = [], 0
    for s, e in spans:
        out.append(body[last:s])
        out.append(BAND_MASK)
        last = e
    out.append(body[last:])
    return "".join(out)


# ------------------------------------------------------------ the gate
def _strip_quotes(text: str) -> str:
    return _QUOTED_RE.sub(" ", text)


def check_detailed(text: Any, kind: str, room: Optional[Dict[str, Any]], offers_text: str,
                   private_texts: Sequence[str] = (), band: Optional[Sequence[Any]] = None,
                   framework: bool = False) -> List[Tuple[str, str]]:
    """[(code, reason), ...] in CODES order, one entry per code. ``band`` is
    the (low, high) price range of a framework reply (draft.price_band), or
    None for every other draft: see "the framework band" above.
    ``framework`` is True for every framework reply, with or without a band
    (a band implies it): a deferral to the call never frees an agreement to
    the client's figure, every sentence is read for one ("agreeing in a
    framework reply"), and any other price point is refused ("other price
    points in a framework reply")."""
    framework = bool(framework or band)
    room = room or {}
    body = normalise(decode_escapes(text))
    found = {}  # type: Dict[str, str]

    def flag(code: str, detail: str = "") -> None:
        if code not in found:
            found[code] = detail or DESCRIPTIONS[code]

    if not body.strip():
        flag("empty")
        return [(c, found[c]) for c in CODES if c in found]

    # Characters and length
    if _DASH_RE.search(body) or _DOUBLE_HYPHEN_RE.search(body):
        flag("em_dash")
    if "!" in body:
        flag("exclamation")
    others = sorted({ch for ch in _DASH_RE.sub("", body) if ord(ch) > 127})
    if others:
        flag("non_ascii", "non-ASCII characters: %s" % " ".join("U+%04X" % ord(c) for c in others[:5]))
    limit = REPLY_MAX_CHARS if (kind or "").lower() == "reply" else TOUCH_MAX_CHARS
    if len(body) > limit:
        flag("too_long", "%d characters, the limit for a %s is %d" % (len(body), kind or "touch", limit))
    # Everything below reads the first ANALYSIS_MAX_CHARS only. A longer draft
    # is already too_long, and the cap keeps a runaway draft from costing
    # seconds (the off-platform check is per clause and per channel word).
    body = body[:ANALYSIS_MAX_CHARS]

    # Off-platform contact and links
    reason = off_platform_reason(body, room)
    if reason:
        flag("off_platform_contact", reason)
    job = room.get("job") or {}
    post = decode_escapes(job.get("post") or "") if isinstance(job, dict) else ""
    post_keys = {_url_key(u) for u in find_urls(post)}
    scan = _EMAIL_RE.sub(" ", body)
    bad_links = [u for u in find_urls(scan) if not _link_allowed(u, post_keys)]
    bad_links += [m.group(0) for m in _OBFUSCATED_URL_RE.finditer(scan)]
    if bad_links:
        flag("external_link", "link not allowed: %s" % ", ".join(bad_links[:3]))
        if any(_blocked_host(_host(u)) and not _host(u).endswith("upwork.com") for u in bad_links):
            flag("off_platform_contact", "links to a booking or chat host: %s" % bad_links[0])

    # Figures. A framework reply's band is masked first, so its two figures
    # pass only together, in a range form, in a sentence with no rate or
    # per-unit word (Lorenzo, 2026-10-06), and no other price point passes.
    priced = mask_band(body, band) if band else body
    stray = figure_problems(priced, offers_text)
    if framework:
        stray += [p for p in framework_figure_problems(priced)
                  if not any(s.split(" ", 1)[0] == p.split(" ", 1)[0] for s in stray)]
    if stray:
        detail = "figures not allowed: %s" % ", ".join(stray[:5])
        cues = band_rate_cues(body, band) if band else []
        if cues:
            detail += ("; the range sits in a sentence with %s, which makes it a rate or a per-unit price: state "
                       "the range once, in a sentence of its own, as the price of this one build"
                       % ", ".join(repr(c) for c in cues[:3]))
        flag("figure_not_in_offers", detail)

    # Agreeing to the client's price (round 13): Lorenzo's call, notes or not.
    agreed = client_price_agreements(priced, room)
    if not agreed:
        if framework:
            # 2026-10-06: every sentence of a framework reply, and no deferral
            # frees it (that reply always defers the exact figure to the call)
            figureless = framework_price_agreement(priced, room)
        else:
            figureless = (figureless_price_agreement(priced, room)  # round 14: "Sure, that works."
                          or price_subject_agreement(priced, room))  # round 16
        if figureless:
            agreed = ['"%s" with no figure' % figureless[:60]]
    if agreed:
        flag("agrees_to_client_price", "agrees to the client's price (%s): do not agree to or accept a price; "
             "leave pricing to Lorenzo" % ", ".join(agreed[:3]))

    # Private facts. Round 12: a private price, rate or hours figure is refused
    # however the room states it; a private pricing number passes only as a
    # count with its noun that the post or the room states ("25k emails").
    private = "\n".join(normalise(decode_escapes(p)) for p in (private_texts or ()) if p)
    if private.strip():
        leaks = []  # type: List[str]
        figs = private_figures(private_texts, public_texts(room))
        money = money_spans(priced)
        leaks += ["$" + f for f in {v for _, _, v in money} & figs["money"]]
        leaks += [f + "%" for f in set(percent_figures(priced)) & figs["percent"]]
        leaks += [f + " hours" for f in _hours(priced) & figs["hours"]]
        leaks += [f + " (review)" for f in _reviews(priced) & figs["reviews"]]
        leaks += [v + " (private pricing)" for _, _, v in _private_pricing_uses(priced, figs["priced"],
                                                                                figs["stated"], money)]
        leaks += [f + " (private rate)" for f in rate_values(priced) & figs["rated"]]
        if _ODDS_RE.search(body) and _LIKELIHOOD_RE.search(private):
            leaks.append("likelihood")
        for m in _REVIEW_WORDS_RE.finditer(body):
            if re.search(re.escape(m.group(0)), private, re.I):
                leaks.append(m.group(0))
        if leaks:
            flag("private_fact", "private facts in the draft: %s" % ", ".join(sorted(set(leaks))[:5]))

    # Placeholders
    if _WITHHELD_RE.search(body):
        flag("placeholder", "it repeats the %s marker: leave that figure out" % WITHHELD_FIGURE)
    if _XX_RE.search(body) or _PLACEHOLDER_RE.search(body):
        flag("placeholder")

    # First-name greeting with no known first name
    problem = first_name_problem(body, room, offers_text)
    if problem:
        flag("first_name_unknown", problem)

    # Voice
    unquoted = _strip_quotes(body)
    plural = _PLURAL_RE.search(unquoted) or _US_RE.search(unquoted)
    if plural:
        flag("not_first_person", "first person plural outside a quote: %r" % plural.group(0))
    elif _THIRD_PERSON_RE.search(unquoted):
        flag("not_first_person", "writes about Lorenzo in the third person")
    filler = filler_match(unquoted)
    if filler:
        flag("filler_phrase", "filler phrase: %r" % filler)

    # Bespoke, never template-sounding
    stock = stock_match(unquoted)
    if stock:
        flag("generic_phrasing", "stock follow-up line: %r" % stock)
    elif client_source_text(room).strip() and not shared_terms(body, room):
        flag("generic_phrasing", "shares no distinctive term with the job post or the client's messages")

    return [(c, found[c]) for c in CODES if c in found]


def check(text: Any, kind: str, room: Optional[Dict[str, Any]], offers_text: str,
          private_texts: Sequence[str] = (), band: Optional[Sequence[Any]] = None,
          framework: bool = False) -> List[str]:
    """Problem codes for ``text`` (empty list == ready to copy).

    ``kind`` is "touch", "checkin" or "reply" (only the length limit differs).
    ``room`` is a RoomContext; the gate reads ``job.post`` (allowed links, the
    client's terms, named platforms, a signed name), ``messages`` (the client's
    terms and signed name), ``client`` and ``client_first_name``.
    ``offers_text`` is config/upwork_offers.md. ``private_texts`` are the
    assessment notes and client intel. ``band`` and ``framework``: see
    ``check_detailed``.
    """
    return [code for code, _ in check_detailed(text, kind, room, offers_text, private_texts, band=band,
                                               framework=framework)]


def describe(codes: Iterable[str]) -> List[str]:
    return ["%s: %s" % (c, DESCRIPTIONS.get(c, c)) for c in codes]
