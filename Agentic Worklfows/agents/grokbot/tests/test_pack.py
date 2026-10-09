"""Checks on the onboarding pack files. Offline, reads local files only."""

import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ONBOARDING = os.path.join(ROOT, "onboarding")
UPDATE = os.path.join(ROOT, "updates", "2026-10-06_cold-reply-autosend.md")

_spec = importlib.util.spec_from_file_location("build_pack", os.path.join(ROOT, "build_pack.py"))
build_pack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_pack)

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bpit-[0-9a-f]{8}-"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{24,}"),
    re.compile(r"(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]", re.I),
]


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def pack_files():
    for base, _dirs, files in os.walk(ONBOARDING):
        for name in files:
            yield os.path.join(base, name)


class Pack(unittest.TestCase):
    def test_every_file_exists(self):
        for name in build_pack.DOCS + ["ask_opus.py", "GROK_ONBOARDING_PACK.md"]:
            self.assertTrue(os.path.isfile(os.path.join(ONBOARDING, name)), name)
        for name in build_pack.SKILLS:
            self.assertTrue(os.path.isfile(os.path.join(ONBOARDING, "skills", name + ".md")), name)
        for name in build_pack.LINKEDIN_FILES:
            self.assertTrue(os.path.isfile(os.path.join(ONBOARDING, "linkedin", name)), name)

    def test_script_inline_in_04_matches_the_file(self):
        doc = read(os.path.join(ONBOARDING, "04_ask_opus.md"))
        script = read(os.path.join(ONBOARDING, "ask_opus.py"))
        self.assertEqual(doc, build_pack.inline_script(doc, script))
        self.assertIn(script.rstrip(), doc)

    def test_combined_pack_is_current(self):
        self.assertEqual(read(os.path.join(ONBOARDING, "GROK_ONBOARDING_PACK.md")),
                         build_pack.combine())

    def test_skills_have_no_maintainer_sources(self):
        for name in build_pack.SKILLS:
            text = read(os.path.join(ONBOARDING, "skills", name + ".md"))
            self.assertNotIn("Sources (for maintainers)", text, name)
            self.assertTrue(text.startswith("---\nname: " + name + "\n"), name)

    def test_skill_copies_match_their_sources(self):
        skills_dir = os.path.expanduser("~/.claude/skills")
        checked = 0
        for name in build_pack.SKILLS:
            source = os.path.join(skills_dir, name, "SKILL.md")
            if not os.path.isfile(source):
                continue
            with self.subTest(skill=name):
                self.assertEqual(read(os.path.join(ONBOARDING, "skills", name + ".md")),
                                 build_pack.strip_sources(build_pack.read(source)),
                                 "%s drifted from its skill; run build_pack.py" % name)
            checked += 1
        if not checked:
            self.skipTest("no skill sources on this machine")

    def test_linkedin_copies_match_their_sources(self):
        for name in build_pack.LINKEDIN_FILES:
            with self.subTest(file=name):
                self.assertEqual(read(os.path.join(ONBOARDING, "linkedin", name)),
                                 read(os.path.join(build_pack.LINKEDIN_SRC, name)),
                                 "linkedin/%s drifted from its source; run build_pack.py" % name)

    def test_strip_sources_keeps_later_sections(self):
        text = "# A\n\n## Keep\nx\n\n## Sources (for maintainers)\n- `a/b.py`\n\n## After\ny\n"
        self.assertEqual(build_pack.strip_sources(text), "# A\n\n## Keep\nx\n\n## After\ny\n")

    def test_no_secrets_anywhere_in_the_pack(self):
        for path in pack_files():
            text = read(path)
            for pattern in SECRET_PATTERNS:
                self.assertIsNone(pattern.search(text), "%s matches %s" % (path, pattern.pattern))

    def test_our_docs_have_no_dashes_or_exclamation_style(self):
        for name in build_pack.DOCS:
            text = read(os.path.join(ONBOARDING, name))
            self.assertNotIn("—", text, name)
            self.assertNotIn("–", text, name)

    def test_pack_names_the_copy_doc_and_model(self):
        pack = read(os.path.join(ONBOARDING, "GROK_ONBOARDING_PACK.md"))
        self.assertIn("e95a04557f8a8faa", pack)
        self.assertIn("claude-opus-5-5", pack)
        # the doc build Lorenzo says "done" on, in the approval example and the copy doc section
        self.assertIn('"doc_build": "e95a04557f8a8faa"',
                      read(os.path.join(ONBOARDING, "02_operating_model.md")))
        self.assertIn("Current build `e95a04557f8a8faa`",
                      read(os.path.join(ONBOARDING, "06_systems_and_access.md")))

    def test_file_02_names_the_allow_list_in_code(self):
        spec = importlib.util.spec_from_file_location(
            "ask_opus_for_pack", os.path.join(ONBOARDING, "ask_opus.py"))
        ask_opus = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ask_opus)
        doc = read(os.path.join(ONBOARDING, "02_operating_model.md"))
        rule = [line for line in doc.splitlines()
                if line.startswith("14. **The auto-send allow list**")]
        self.assertEqual(len(rule), 1)
        for branch in ask_opus.AUTO_SEND_FIRST_REPLIES:
            self.assertIn("." + branch + ".full", rule[0], branch)
        self.assertIn("`cadence.e1` to `cadence.e10`", rule[0])
        self.assertEqual(ask_opus.AUTO_SEND_LADDER, tuple("cadence.e%d" % n for n in range(1, 11)))
        for template_id in ask_opus.AUTO_SEND_CONFIRMATIONS:
            self.assertIn("`" + template_id + "`", rule[0], template_id)

    def test_file_01_offer_keys_are_the_scripts_seven(self):
        spec = importlib.util.spec_from_file_location(
            "ask_opus_for_keys", os.path.join(ONBOARDING, "ask_opus.py"))
        ask_opus = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ask_opus)
        doc = read(os.path.join(ONBOARDING, "01_business_context.md"))
        keys = set(re.findall(r"^\| ([a-z_]+) \| 2026 ", doc, re.M))
        self.assertEqual(keys, set(ask_opus.KNOWN_OFFERS))
        self.assertIn("no call is booked for it", doc)
        lead_row = [line for line in read(os.path.join(ONBOARDING, "04_ask_opus.md")).splitlines()
                    if line.startswith("| `lead` |")]
        self.assertEqual(len(lead_row), 1)
        self.assertIn("not one of the seven in file 01, every email for this lead is a hold card "
                      "and no call is booked", lead_row[0])

    def test_ai_agents_campaigns_map_to_their_key(self):
        ids = ["e8867dbb-4f94-40ee-81c0-c11d7a256e2d", "d81f1d53-23d6-48a6-aea3-80c21192e17e",
               "9b82c9ce-b772-440a-b4a0-b984fe6a7a3f", "8a50b4e8-48e7-4db2-aa8f-b2e75187a8be",
               "891bf2b5-9351-4cde-a5c4-13dd1d8ffce8", "59b20790-12bb-446d-bcd6-e3b6f9a61953",
               "4eedb228-53c7-42ff-baf5-5b40c8646bd8", "21f5568a-d82e-4280-8437-04b0f8d6df37"]
        doc = read(os.path.join(ONBOARDING, "01_business_context.md"))
        for campaign_id in ids:
            row = [line for line in doc.splitlines() if campaign_id in line]
            self.assertEqual(len(row), 1, campaign_id)
            self.assertTrue(row[0].startswith("| ai_agents |"), campaign_id)
        self.assertIn("has no key", doc)

    def test_no_stale_rule_contradicts_files_00_to_07(self):
        stale = {
            "00_START_HERE.md": ["1bK3bkYfxYkhY0vFtHhB4RG6lMkKQrHvp6Qyasp8Pbt4",
                                 "The common first replies send on their own"],
            "01_business_context.md": ["No booking link in any email", "Zoom is not connected",
                                       "Booking Thu 3:00pm CT and sending the Locked in "
                                       "confirmation. Approve?"],
            "02_operating_model.md": ["(Ask first). If that time is not clear",
                                      "it is a hold card or a `booked_call` case",
                                      "Only default, pricing, mechanism, send_info and booking_link",
                                      "(gmail, googlemail, yahoo, outlook, hotmail, live, msn, "
                                      "icloud, me, aol, proton, protonmail, gmx)"],
            "03_team.md": ["Zoom is not connected", "does not run until Zoom is connected",
                           "Create a GHL appointment on the Discovery Call calendar (Ask first)"],
            "04_ask_opus.md": ["in the chosen template or one of its variants",
                               "approval_ok` is also false for a first reply"],
            "05_lead_state_ghl.md": ["Zoom not connected", "create appointments only with Ask first"],
            "06_systems_and_access.md": ["Zoom is not connected",
                                         "appointments on the Discovery Call calendar (Ask first)",
                                         "Current build `170b09dd897430a9`"],
            "09_company_and_process_overview.md": ["Zoom is not connected",
                                                   "Grok creates the appointment (Ask first)",
                                                   "against the no-booking-link rule"],
            "skills/cold-campaigns.md": ["We never talk\nnumbers over email", "Mention AI"],
            "skills/booked-calls.md": ["never appear in any email", "Never a booking link"],
            "skills/client-fulfillment.md": ["tooling, AI or automation",
                                             'says never a booking link, "Everywhere"'],
            "skills/cold-email-replies.md": ["We never talk numbers over email**",
                                              "A model may improve the wording",
                                              "new first-reply copy is being written",
                                              "it goes to Lorenzo or the booked-call flow",
                                              "Do Not Disturb, or Sequence `stopped` or `booked`",
                                              "## Step 4: the first reply (first contact)"],
            "skills/grok-operator.md": ['except the Zoom link in the "Locked in" confirmation and',
                                        "Advero emails: edit here (build 170b09dd897430a9)"],
            "skills/quiet-lead-followup.md": ["Veto button", "no AI or automation",
                                              "No booking link anywhere"],
            "skills/lorenzo-voice.md": ['"AI", "automation", "automated", "bot"'],
        }
        for name, phrases in stale.items():
            text = read(os.path.join(ONBOARDING, name))
            for phrase in phrases:
                self.assertNotIn(phrase, text, "%s still says %r" % (name, phrase))

    def test_a_lead_who_had_a_call_is_lorenzos_in_the_docs(self):
        doc02 = read(os.path.join(ONBOARDING, "02_operating_model.md"))
        appointment = [line for line in doc02.splitlines() if line.startswith("- `appointment`")]
        self.assertEqual(len(appointment), 1)
        self.assertIn("A lead who has or had a call (any appointment, past or future) gets no "
                      "first reply, no booking and no follow-up E1 to E10 on its own",
                      appointment[0])
        self.assertIn("for a first reply, a booking and E1 to E10 a missing `appointment` is a "
                      "hold card", appointment[0])
        rule14 = [line for line in doc02.splitlines()
                  if line.startswith("14. **The auto-send allow list**")][0]
        self.assertIn("only for a lead whose offer is `ai_agents` and who never had a call", rule14)
        self.assertIn("They are not only for first contact (Lorenzo, 2026-10-08)", rule14)
        self.assertIn("every first reply and every booking for a lead who has or had a call",
                      rule14)
        row = [line for line in read(os.path.join(ONBOARDING, "04_ask_opus.md")).splitlines()
               if line.startswith("| `appointment` |")]
        self.assertEqual(len(row), 1)
        self.assertIn("A first reply, a booking (`book_call`) and E1 to E10 hold for a lead with "
                      "any appointment, past or future", row[0])
        skill = read(os.path.join(ONBOARDING, "skills", "cold-email-replies.md"))
        self.assertIn("The first replies are not only for first contact (Lorenzo, 2026-10-08)",
                      skill)
        self.assertIn("a first reply or a booking never goes to a lead who has or had a call",
                      skill)
        self.assertIn("at most one per lead per day", skill)

    def test_the_booked_time_is_one_the_lead_named(self):
        rule15 = [line for line in read(os.path.join(ONBOARDING, "02_operating_model.md"))
                  .splitlines() if line.startswith("15. **Book first")][0]
        self.assertIn("The time must be one offered to this lead (`offered_times`), or the lead's "
                      "newest email must name it", rule15)
        self.assertIn("When a lead who never had a call", rule15)

    def test_bookings_are_central_and_both_calendars_are_read(self):
        doc02 = read(os.path.join(ONBOARDING, "02_operating_model.md")).splitlines()
        rule15 = [line for line in doc02 if line.startswith("15. **Book first")][0]
        for phrase in ("no Instantly interest status 2, 3 or 4, no GHL stage Call Booked, "
                       "Proposal Sent or Won",
                       "The time must also be Central: nothing is booked on its own, not even a "
                       "time we offered this lead, when the thread names any other time zone",
                       "or when `lead.timezone` is known and not Central and the lead did not "
                       "write the time with CT, CST, CDT or Central",
                       'Offered Thursday 4:30pm CT, the lead wrote "Thursday 4:30pm Eastern '
                       'works": a hold card for Lorenzo.'):
            self.assertIn(phrase, rule15)
        item9 = [line for line in doc02 if line.startswith("9. Does the lead have a future")][0]
        self.assertIn("or on Lorenzo's Google Calendar (`lorenzovillarreal@adverosolutions.com`)? "
                      "Read both calendars", item9)
        thread = [line for line in doc02 if line.startswith("- the thread:")][0]
        self.assertIn("a `subject` key (`null` when it has no subject)", thread)
        doc04 = read(os.path.join(ONBOARDING, "04_ask_opus.md")).splitlines()
        row = [line for line in doc04 if line.startswith("| `thread` |")][0]
        self.assertIn("a missing key is a hold card", row)
        self.assertIn("every `subject` and `body` in the thread for a time zone other than Central",
                      row)
        row = [line for line in doc04 if line.startswith("| `instantly` |")][0]
        self.assertIn("A first reply and a booking hold when it is 2, 3 or 4", row)
        skill = read(os.path.join(ONBOARDING, "skills", "cold-email-replies.md"))
        self.assertIn("The time must be Central: no booking goes on its own, not even for a time "
                      "we offered", skill)
        self.assertIn("an Instantly interest status of 2, 3 or 4, or a GHL stage of Call Booked, "
                      "Proposal Sent or Won", skill)
        for name in ("cold-email-replies", "quiet-lead-followup"):
            self.assertIn("a `dnd`, `do-not-disturb` or `do not disturb` tag",
                          read(os.path.join(ONBOARDING, "skills", name + ".md")), name)
        self.assertIn("**Bookings are Central only.**", read(UPDATE))

    def test_day_0_starts_the_ladder(self):
        team = [line for line in read(os.path.join(ONBOARDING, "03_team.md")).splitlines()
                if '"Day 0 watch"' in line and line.lstrip().startswith("- ")][0]
        for text in (team, read(os.path.join(ONBOARDING, "05_lead_state_ghl.md")),
                     read(os.path.join(ONBOARDING, "skills", "quiet-lead-followup.md"))):
            self.assertIn("Sequence `followup`, Next Email `cadence.e1` and Next Due Date the "
                          "next business day at 10:00 CT", text)
            self.assertIn("reply_waiting", text)
        self.assertIn("After the send's own records (file 05, section 6)", team)
        self.assertIn("Sequence `followup`, Next Email `cadence.e1` and Next Due Date "
                      "`2026-09-29T10:00:00-05:00`",
                      read(os.path.join(ONBOARDING, "04_ask_opus.md")))
        self.assertIn("**Day 0 starts the ladder.**", read(UPDATE))

    def test_free_mail_examples_in_file_02_are_the_scripts(self):
        spec = importlib.util.spec_from_file_location(
            "ask_opus_for_mail", os.path.join(ONBOARDING, "ask_opus.py"))
        ask_opus = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ask_opus)
        doc = read(os.path.join(ONBOARDING, "02_operating_model.md"))
        self.assertIn("The full list is `FREE_MAIL_NAMES` in `ask_opus.py`", doc)
        for name in ("gmail", "yahoo", "outlook", "hotmail", "icloud", "aol", "proton", "gmx",
                     "hey", "duck", "mailbox", "posteo", "comcast", "att", "verizon"):
            self.assertIn(name, ask_opus.FREE_MAIL_NAMES, name)

    def test_the_rollback_brings_back_ask_first(self):
        update = read(UPDATE)
        rollback = [line for line in update.splitlines() if line.startswith("**Rollback.**")]
        self.assertEqual(len(rollback), 1)
        for phrase in ("With either one, the new `ask_opus.py` in part 3 never answers `send`",
                       "Copying the `.bak` back brings back the script from before this update "
                       "(c12bc35)", "it does not read the kill switch",
                       "built to run behind Ask first on every email send",
                       "`KILL_SWITCH` created", '`"go_live": false`',
                       '`"ask_first_on_sends": true`',
                       "Ask first back on for every email send",
                       '`go_live` stays false until Lorenzo says "go live" again'):
            self.assertIn(phrase, rollback[0], phrase)
        self.assertNotIn("copying it back undoes the script change", update)
        self.assertIn("put the `.bak` back, do every rollback step at the top", update)
        approval = update.split("### `~/advero/state/approval.json`", 1)[1].split("\n### ", 1)[0]
        self.assertIn('If `"go_live"` is true, set it to false and `"go_live_at"` to null',
                      approval)
        self.assertIn('only when Lorenzo says "go live" on this version', approval)


if __name__ == "__main__":
    unittest.main()
