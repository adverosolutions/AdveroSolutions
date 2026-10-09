"""finalize fills job_created_utc, age_hours_at_apply, connects and boosted.

    python3 -m pytest -q tests/test_finalize_meta.py

Every write goes to a temp directory; the real proposals.csv is never touched.
"""

from __future__ import annotations

import contextlib
import csv
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen import apply_meta, finalize  # noqa: E402

UTC = datetime.timezone.utc
PROPOSAL = ("Hey there \U0001F44B I built this lead router for your team so you can see how it handles every new lead end to end, [N]-min video: "
            "https://www.loom.com/share/[LOOMURL]\n\nI can start [START].\n\nLorenzo\n")
SPEC = {"title": "Your Lead Router", "platform": "n8n",
        "nodes": [{"key": "t", "kind": "trigger.webhook", "label": "1 - Lead In"},
                  {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
                   "label": "2 - Tell Sales"}],
        "edges": [{"from": "t", "to": "s"}]}


class TestApplyMeta(unittest.TestCase):
    NOW = datetime.datetime(2026, 9, 28, 18, 30, tzinfo=UTC)

    def test_created_utc_line_gives_time_and_age(self):
        jd = "url: u\nTitle\ncreated_utc: 2026-09-28T11:04:11.561Z\nConnects to apply: 22.\n"
        created, moment = apply_meta.job_created(jd)
        self.assertEqual(created, "2026-09-28T11:04:11Z")
        self.assertEqual(apply_meta.age_hours(moment, self.NOW), "7.4")
        self.assertEqual(apply_meta.connects_cost(jd), "22")

    def test_posted_date_only_leaves_age_blank_and_about_is_skipped(self):
        created, moment = apply_meta.job_created("Posted 2026-09-21, 0 hires")
        self.assertEqual((created, moment), ("2026-09-21", None))
        self.assertEqual(apply_meta.age_hours(moment, self.NOW), "")
        self.assertEqual(apply_meta.job_created("Posted about 2026-09-25, 1 invite"), ("", None))

    def test_flags_override_jd_and_bad_values_stay_blank(self):
        jd = "Posted 2026-09-21. Connects to apply: 11."
        self.assertEqual(apply_meta.job_created(jd, "2026-09-28 06:04:11-05:00")[0],
                         "2026-09-28T11:04:11Z")
        self.assertEqual(apply_meta.connects_cost(jd, 30), "30")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(apply_meta.job_created("", "3 minutes ago"), ("", None))
            self.assertEqual(apply_meta.job_created(jd, "3 minutes ago"), ("2026-09-21", None))
        self.assertEqual(err.getvalue().count("--posted '3 minutes ago' not parsed"), 2)
        future = apply_meta.parse_utc("2026-09-29T00:00:00Z")
        self.assertEqual(apply_meta.age_hours(future, self.NOW), "")  # negative age
        self.assertEqual(apply_meta.normalize_boosted("maybe"), "")

    def test_meta_for_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(apply_meta.meta_for(os.path.join(tmp, "missing"), self.NOW),
                             {k: "" for k in apply_meta.META_FIELDS})
            with unittest.mock.patch.object(apply_meta, "job_created", side_effect=RuntimeError):
                self.assertEqual(apply_meta.meta_for(tmp, self.NOW, connects=5)["connects"], "")


class TestFinalizeLogsMeta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.job = os.path.join(self.tmp, "job")
        os.makedirs(self.job)
        with open(os.path.join(self.job, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(PROPOSAL)
        with open(os.path.join(self.job, "spec.json"), "w", encoding="utf-8") as fh:
            json.dump(SPEC, fh)
        self.csv = os.path.join(self.tmp, "proposals.csv")
        with open(self.csv, "w", encoding="utf-8") as fh:
            fh.write(",".join(finalize.CSV_HEADER) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_main(self, jd: str, *extra: str):
        with open(os.path.join(self.job, "jd.txt"), "w", encoding="utf-8") as fh:
            fh.write(jd)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = finalize.main([self.job, "--no-copy", "--csv", self.csv, "--loom",
                                  "https://www.loom.com/share/abc123", "--runtime", "2",
                                  "--start", "today"] + list(extra))
        self.assertEqual(code, 0, out.getvalue())
        with open(self.csv, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], finalize.CSV_HEADER)  # column order unchanged
        self.assertTrue(all(len(r) == len(rows[0]) for r in rows))
        return dict(zip(rows[0], rows[-1])), out.getvalue()

    def test_fills_columns_from_jd_and_flags(self):
        posted = (datetime.datetime.now(UTC) - datetime.timedelta(hours=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        row, out = self.run_main("url: https://www.upwork.com/jobs/~021\nA Job\n"
                                 "Posted about 2026-09-25. Connects to apply: 17.\n",
                                 "--posted", posted, "--boosted", "yes")
        self.assertEqual(row["job_created_utc"], posted)
        self.assertAlmostEqual(float(row["age_hours_at_apply"]), 5.0, delta=0.2)
        self.assertEqual((row["connects"], row["boosted"]), ("17", "yes"))
        self.assertIn("apply:   job_created_utc " + posted, out)

    def test_missing_data_leaves_columns_blank(self):
        row, out = self.run_main("url: https://www.upwork.com/jobs/~022\nA Job\nno metadata\n")
        self.assertEqual([row[k] for k in apply_meta.META_FIELDS], ["", "", "", ""])
        self.assertEqual(row["job_title"], "A Job")
        self.assertIn("connects blank", out)


if __name__ == "__main__":
    unittest.main()
