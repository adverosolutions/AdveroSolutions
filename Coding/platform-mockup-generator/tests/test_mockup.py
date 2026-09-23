"""What must not regress.

The failure mode this tool has is not a crash — it is a page that renders and
looks slightly wrong on camera. So most of these tests assert properties of the
*output* rather than of the code path that produced it.
"""

import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mockup.render import KICKER, render
from mockup.spec import PLATFORMS, STEP_TYPES, MockupSpec, SpecError
from mockup.theme import THEMES, initials, tile_color

BASE = {
    "title": "Test Automation",
    "platform": "ghl",
    "trigger": {"app": "Typeform", "label": "Form Submitted"},
    "steps": [
        {"type": "action", "app": "Slack", "label": "Notify Team"},
        {"type": "ai", "app": "Claude", "label": "Summarize"},
    ],
    "input_sample": {"name": "Dana Reyes"},
    "output_sample": {"status": "done"},
}


def spec(**overrides):
    data = dict(BASE)
    data.update(overrides)
    return MockupSpec.from_dict(data)


class SpecValidation(unittest.TestCase):
    def test_unknown_step_type_is_rejected(self):
        with self.assertRaises(SpecError) as caught:
            spec(steps=[{"type": "teleport", "app": "X", "label": "Y"}])
        # The message must name the legal values — it is read mid-application.
        self.assertIn("action", str(caught.exception))

    def test_step_without_a_label_is_rejected(self):
        with self.assertRaises(SpecError):
            spec(steps=[{"type": "action", "app": "Slack"}])

    def test_action_without_an_app_is_rejected(self):
        """The app tile is what makes a card read as a real product card."""
        with self.assertRaises(SpecError):
            spec(steps=[{"type": "action", "label": "Do Something"}])

    def test_native_steps_need_no_app(self):
        result = spec(steps=[{"type": "wait", "label": "Wait 2 Hours"}])
        self.assertEqual(result.card_count, 2)

    def test_branch_with_two_empty_arms_is_rejected(self):
        with self.assertRaises(SpecError):
            spec(steps=[{"type": "branch", "label": "Qualified", "yes": [], "no": []}])

    def test_branches_cannot_nest_forever(self):
        inner = {"type": "branch", "label": "B",
                 "yes": [{"type": "wait", "label": "W"}], "no": []}
        middle = {"type": "branch", "label": "A", "yes": [inner], "no": []}
        outer = {"type": "branch", "label": "Top", "yes": [middle], "no": []}
        with self.assertRaises(SpecError):
            spec(steps=[outer])

    def test_a_trigger_with_no_steps_is_not_an_automation(self):
        with self.assertRaises(SpecError):
            spec(steps=[])

    def test_gohighlevel_aliases_resolve(self):
        for name in ("gohighlevel", "GoHighLevel", "HighLevel", "ghl"):
            self.assertEqual(spec(platform=name).platform, "ghl")

    def test_missing_samples_warn_rather_than_fail(self):
        result = spec(input_sample={}, output_sample={})
        warnings = " ".join(result.validate())
        self.assertIn("input_sample", warnings)
        self.assertIn("output_sample", warnings)


class Rendering(unittest.TestCase):
    def test_every_platform_renders(self):
        for platform in PLATFORMS:
            html = render(spec(platform=platform))
            self.assertIn("<!doctype html>", html)
            self.assertIn("Test Automation", html)

    def test_every_step_type_renders_and_is_labelled(self):
        """A type in the vocabulary with no kicker would render a blank label."""
        for step_type in STEP_TYPES:
            self.assertIn(step_type, KICKER,
                          "{} has no card label".format(step_type))
            if step_type == "branch":
                step = {"type": "branch", "label": "Split",
                        "yes": [{"type": "wait", "label": "Hold"}], "no": []}
            else:
                step = {"type": step_type, "app": "Slack", "label": "Step"}
            html = render(spec(steps=[step]))
            self.assertIn(KICKER[step_type].upper(), html.upper())

    def test_page_is_completely_self_contained(self):
        """No external request may exist — one that fails repaints on camera."""
        for platform in PLATFORMS:
            html = render(spec(platform=platform))
            for pattern in (r'src\s*=', r'<link', r'@import', r'https?://'):
                self.assertIsNone(
                    re.search(pattern, html, re.I),
                    "{} output references something external ({})".format(
                        platform, pattern),
                )

    def test_spec_content_is_html_escaped(self):
        """Job posts contain angle brackets and ampersands verbatim."""
        html = render(spec(title='Acme <script>alert(1)</script> & Co'))
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_zapier_numbers_its_steps_and_ghl_does_not(self):
        self.assertIn('class="num"', render(spec(platform="zapier")))
        self.assertNotIn('class="num"', render(spec(platform="ghl")))

    def test_zapier_ticks_steps_and_ghl_shows_a_row_menu(self):
        # Both rules live in the shared stylesheet, so assert on the markup.
        tick, menu = '<div class="cmark">', '<div class="cmenu">'
        zapier, ghl = render(spec(platform="zapier")), render(spec(platform="ghl"))
        self.assertIn(tick, zapier)
        self.assertNotIn(menu, zapier)
        self.assertIn(menu, ghl)
        self.assertNotIn(tick, ghl)

    def test_both_samples_are_rendered_exactly_once(self):
        html = render(spec())
        self.assertEqual(html.count("Dana Reyes"), 1)
        self.assertEqual(html.count("done"), 1)

    def test_output_sample_lands_on_the_deepest_branch_arm(self):
        """The last card is visually the bottom of the longer arm, not the
        last one in the JSON — the sample must follow the eye."""
        html = render(spec(steps=[{
            "type": "branch", "label": "Qualified",
            "yes": [{"type": "action", "app": "Slack", "label": "Alpha"},
                    {"type": "action", "app": "Slack", "label": "Bravo"}],
            "no": [{"type": "action", "app": "Slack", "label": "Charlie"}],
        }]))
        after_bravo = html.split("Bravo", 1)[1]
        after_charlie = html.split("Charlie", 1)[1]
        self.assertIn("done", after_bravo.split("Charlie")[0])
        self.assertNotIn("done", after_charlie)

    def test_a_branch_widens_the_canvas(self):
        """Two columns squeezed into one card's width is unreadable at zoom."""
        narrow = render(spec())
        wide = render(spec(steps=[{
            "type": "branch", "label": "Split",
            "yes": [{"type": "wait", "label": "Hold"}], "no": []}]))
        self.assertIn("760px", wide)
        self.assertNotIn("760px", narrow)

    def test_long_sample_values_are_truncated(self):
        html = render(spec(input_sample={"blob": "x" * 200}))
        self.assertIn("…", html)
        self.assertNotIn("x" * 100, html)


class Theming(unittest.TestCase):
    def test_tile_colours_are_stable_across_processes(self):
        """`hash()` is randomised per interpreter; the same app must be the
        same colour in every Loom, so the palette cannot depend on it."""
        code = ("import sys; sys.path.insert(0, {!r});"
                "from mockup.theme import tile_color;"
                "print(tile_color('Some Unlisted App'))").format(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        seen = set()
        for _ in range(3):
            out = subprocess.check_output(
                [sys.executable, "-c", code],
                env=dict(os.environ, PYTHONHASHSEED="random"))
            seen.add(out.decode().strip())
        self.assertEqual(len(seen), 1, "tile colour is not deterministic")
        self.assertEqual(seen.pop(), tile_color("Some Unlisted App"))

    def test_initials_never_come_back_empty(self):
        for app in ("Slack", "Google Sheets", "x", "", "  ", "Go-High.Level"):
            self.assertTrue(initials(app).strip())

    def test_each_theme_defines_every_key(self):
        keys = set(THEMES["ghl"]) | set(THEMES["zapier"])
        for platform, theme in THEMES.items():
            missing = keys - set(theme)
            self.assertFalse(missing, "{} is missing {}".format(platform, missing))


if __name__ == "__main__":
    unittest.main()
