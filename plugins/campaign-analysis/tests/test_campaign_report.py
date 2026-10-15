"""Tests for campaign_report.py. Run from the plugin root: python3 -B -m unittest discover -s tests

Expected values for the sample export were computed independently with sqlite3, not with the script.
"""
import csv
import html
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # the plugin loads in place; keep __pycache__ out of it

PLUGIN = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN / "skills" / "campaign-performance" / "scripts" / "campaign_report.py"
SAMPLE = PLUGIN / "tests" / "fixtures" / "sample_export.csv"

spec = importlib.util.spec_from_file_location("campaign_report", SCRIPT)
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

HEADER = ["campaign_id", "campaign_name", "date", "impressions", "tune_ins", "spend", "platform", "content_type"]


def row(**overrides):
    base = {"campaign_id": "CAMP_A", "campaign_name": "Alpha", "date": "2026-09-28", "impressions": "10000",
            "tune_ins": "100", "spend": "200", "platform": "streaming", "content_type": "movie"}
    base.update(overrides)
    return base


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)


def dataset(rows):
    """Write rows to a temp CSV and load it as a Dataset (data line N = file line N + 1)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "export.csv")
        write_csv(path, rows)
        return cr.Dataset(path)


class MessyRulesTest(unittest.TestCase):
    def test_cosmetic_issues_are_normalized(self):
        for overrides, field, expected in [
            ({"platform": "Live TV"}, "platform", "live_tv"),
            ({"platform": "LIVE_TV"}, "platform", "live_tv"),
            ({"platform": " live_tv"}, "platform", "live_tv"),
            ({"platform": "Streaming"}, "platform", "streaming"),
            ({"spend": "$3,823.53"}, "spend", 3823.53),
            ({"date": "10/01/2026"}, "date", date(2026, 10, 1)),
        ]:
            with self.subTest(overrides=overrides):
                ds = dataset([row(**overrides)])
                self.assertEqual(ds.exclusions, [])
                self.assertEqual(ds.rows[0][field], expected)

    def test_untrustworthy_rows_are_excluded_with_a_reason(self):
        for overrides, reason in [
            ({"spend": ""}, "missing value"),
            ({"tune_ins": ""}, "missing value"),
            ({"spend": "-1500"}, "negative value"),
            ({"impressions": "0", "tune_ins": "703"}, "zero impressions"),
            ({"tune_ins": "146380", "impressions": "141380"}, "tune-ins exceed impressions"),
            ({"platform": "CTV"}, "unknown platform"),
            ({"date": "2026-13-45"}, "unreadable date"),
        ]:
            with self.subTest(overrides=overrides):
                ds = dataset([row(campaign_id="CAMP_OK"), row(**overrides)])
                self.assertEqual([(e["line"], e["reason"]) for e in ds.exclusions], [(3, reason)])
                self.assertEqual([r["campaign_id"] for r in ds.rows], ["CAMP_OK"])

    def test_exact_duplicate_is_kept_once(self):
        ds = dataset([row(), row()])
        self.assertEqual(len(ds.rows), 1)
        self.assertEqual(ds.duplicates, [3])
        self.assertEqual(ds.exclusions, [])

    def test_conflicting_duplicates_are_both_excluded(self):
        ds = dataset([row(campaign_id="CAMP_OK"), row(spend="200"), row(platform="Streaming", spend="$250.00")])
        self.assertEqual([(e["line"], e["reason"]) for e in ds.exclusions],
                         [(3, "conflicting duplicate"), (4, "conflicting duplicate")])

    def test_zero_tune_ins_are_kept_with_cpt_na(self):
        ds = dataset([row(tune_ins="0", spend="50")])
        self.assertEqual(ds.exclusions, [])
        self.assertIsNone(cr.totals(ds.rows)["cpt"])

    def test_name_variant_maps_to_canonical_name(self):
        ds = dataset([row(date="2026-09-28"), row(date="2026-09-29"), row(date="2026-09-30", campaign_name="alpha ")])
        self.assertEqual(ds.names, {"CAMP_A": "Alpha"})


class LogicTest(unittest.TestCase):
    def test_last_complete_week(self):
        self.assertEqual(cr.last_complete_week(date(2026, 10, 4)), (date(2026, 9, 28), date(2026, 10, 4)))  # Sunday
        self.assertEqual(cr.last_complete_week(date(2026, 10, 7)), (date(2026, 9, 28), date(2026, 10, 4)))  # Wednesday

    def test_underperformer_rule_boundary_and_waste(self):
        # Streaming CPTs: A 2.0, B 2.0, C 3.0 -> median 2.0, threshold 3.0 -> C flagged at the boundary.
        # E has spend and no tune-ins: left out of the median, always flagged.
        # Live TV: D alone, CPT 2.5, not flagged; its zero-tune-in day (25) counts as waste on its own line.
        ds = dataset([
            row(campaign_id="A", campaign_name="A", spend="200", tune_ins="100"),
            row(campaign_id="B", campaign_name="B", spend="200", tune_ins="100"),
            row(campaign_id="C", campaign_name="C", spend="300", tune_ins="100"),
            row(campaign_id="E", campaign_name="E", spend="40", tune_ins="0"),
            row(campaign_id="D", campaign_name="D", spend="100", tune_ins="50", platform="live_tv"),
            # Sunday, so the data ends a complete week (Sep 28–Oct 4) and every row is in it.
            row(campaign_id="D", campaign_name="D", spend="25", tune_ins="0", platform="live_tv", date="2026-10-04"),
        ])
        rep = cr.underperformer_report(ds, "last-week")
        self.assertEqual(rep["platforms"]["streaming"]["median_cpt"], 2.0)
        self.assertEqual(rep["platforms"]["streaming"]["threshold"], 3.0)
        self.assertEqual([(f["campaign_id"], f["platform"]) for f in rep["flagged"]],
                         [("C", "streaming"), ("E", "streaming")])
        self.assertEqual(rep["waste"]["flagged"], 340)
        self.assertEqual(rep["waste"]["zero_tune_in_days"], 25)
        self.assertEqual(rep["waste"]["total"], 365)
        self.assertAlmostEqual(rep["waste"]["pct_of_spend"], 365 / 865 * 100)

    def test_campaign_without_rows_last_week_shows_no_data(self):
        ds = dataset([row(campaign_id="OLD", campaign_name="Old", date="2026-09-22"),
                      row(campaign_id="NEW", campaign_name="New", date="2026-10-04")])
        rep = cr.campaign_report(ds, "Old")
        self.assertIsNone(rep["combined"]["last"])
        self.assertIsNotNone(rep["combined"]["previous"])
        self.assertIsNone(rep["combined"]["change"]["spend"])


class SampleExportTest(unittest.TestCase):
    """The messy sample export, checked against values computed independently with sqlite3."""

    @classmethod
    def setUpClass(cls):
        cls.ds = cr.Dataset(str(SAMPLE))

    def test_exclusions_match_the_independent_check(self):
        self.assertEqual([(e["line"], e["reason"]) for e in self.ds.exclusions], [
            (108, "negative value"), (119, "missing value"), (166, "missing value"),
            (182, "tune-ins exceed impressions"), (185, "conflicting duplicate"), (186, "conflicting duplicate"),
            (214, "conflicting duplicate"), (215, "conflicting duplicate"), (264, "zero impressions"),
        ])
        self.assertEqual(self.ds.duplicates, [93, 229, 249])
        self.assertEqual(len(self.ds.rows), 291)
        summary = cr.exclusion_summary(self.ds, self.ds.start, self.ds.end)
        self.assertEqual(sum(n for _, n in summary["by_reason"]), len(self.ds.exclusions))

    def test_q1_campaign_last_week(self):
        rep = cr.campaign_report(self.ds, "CAMP_2026_105")
        last = rep["platforms"]["streaming"]["last"]
        self.assertEqual((last["impressions"], last["tune_ins"], last["days"]), (673625, 4576, 7))
        self.assertAlmostEqual(last["tune_in_rate"], 0.679310, places=6)
        self.assertAlmostEqual(last["cpt"], 4.509008, places=6)

    def test_q2_platforms_last_week(self):
        live = cr.platform_report(self.ds, "last-week")["platforms"]["live_tv"]
        self.assertEqual((live["impressions"], live["tune_ins"], live["campaigns"]), (9661076, 74148, 5))
        self.assertAlmostEqual(live["spend"], 281874.20, places=2)

    def test_q3_underperformers_last_week(self):
        rep = cr.underperformer_report(self.ds, "last-week")
        self.assertEqual([(f["campaign_id"], f["platform"]) for f in rep["flagged"]], [("CAMP_2026_106", "live_tv")])
        self.assertAlmostEqual(rep["flagged"][0]["cpt"], 24.629493, places=6)


class ReviewFixesTest(unittest.TestCase):
    """Bugs found in code and skill review."""

    def test_home_relative_path_is_expanded(self):
        with tempfile.TemporaryDirectory() as home:
            write_csv(os.path.join(home, "export.csv"), [row()])
            with mock.patch.dict(os.environ, {"HOME": home}):
                self.assertEqual(len(cr.Dataset("~/export.csv").rows), 1)

    def test_bad_numbers_are_excluded_not_kept_or_crashing(self):
        for overrides in ({"spend": "nan"}, {"spend": "inf"}, {"impressions": "nan"}, {"impressions": "inf"},
                          {"spend": "200,50"}, {"spend": "1,2,3"}):
            with self.subTest(overrides=overrides):
                ds = dataset([row(campaign_id="CAMP_OK"), row(**overrides)])
                self.assertEqual([(e["line"], e["reason"]) for e in ds.exclusions], [(3, "invalid value")])

    def test_boundary_is_flagged_despite_float_error(self):
        # In floating point 2.2 * 1.5 = 3.3000000000000003, so a CPT of exactly 3.3 used to be missed.
        ds = dataset([row(campaign_id=c, campaign_name=c, spend=s, tune_ins="100", date="2026-10-04")
                      for c, s in (("A", "220"), ("B", "220"), ("C", "330"))])
        self.assertEqual([f["campaign_id"] for f in cr.underperformer_report(ds, "last-week")["flagged"]], ["C"])

    def test_campaign_matching(self):
        ds = dataset([row(campaign_id="A", campaign_name="Alpha", spend="-5"),  # every row of A is excluded
                      row(campaign_id="B", campaign_name="Beta", date="2026-10-04"),
                      row(campaign_id="F", campaign_name="Fall Thriller Premiere", date="2026-10-04")])
        self.assertIn("all_rows_excluded", cr.campaign_report(ds, "A"))  # used to resolve to Beta ('a' in 'beta')
        self.assertIsNone(cr.campaign_report(ds, "et")["campaign_id"])   # mid-word substrings no longer match
        fuzzy = cr.campaign_report(ds, "fall thriller")
        self.assertEqual((fuzzy["campaign_id"], fuzzy["partial_match"]), ("F", True))

    def test_exclusions_still_work_when_every_row_is_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "allbad.csv")
            write_csv(path, [row(spend="-5")])
            run = lambda cmd: subprocess.run([sys.executable, "-B", str(SCRIPT), cmd, "--csv", path],
                                             capture_output=True, text=True, timeout=30)
            ok, bad = run("exclusions"), run("platforms")
            self.assertEqual(ok.returncode, 0)
            self.assertIn("Excluded rows: 1 of 1", ok.stdout)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("no usable rows", bad.stderr)


NUMBER_RE = re.compile(r"[-+]?\$?\d[\d,]*(?:\.\d+)?%?")


class HtmlFormatTest(unittest.TestCase):
    """--format html (email bodies) must carry exactly the same numbers as the Markdown answer."""

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cr.main(list(args)), 0)
        return out.getvalue()

    def test_same_numbers_as_markdown(self):
        for args in (["campaign", "--campaign", "Fall Thriller"], ["platforms"], ["underperformers"], ["exclusions"]):
            with self.subTest(args=args):
                base = [args[0], "--csv", str(SAMPLE), *args[1:]]
                md = self.run_cli(*base)
                page = self.run_cli(*base, "--format", "html")
                text = html.unescape(re.sub(r"<[^>]+>", " ", page))  # strip tags (and their attributes)
                self.assertEqual(sorted(NUMBER_RE.findall(text)), sorted(NUMBER_RE.findall(md)))
                self.assertIn("<table", page)
                self.assertNotIn("|", page)

    def test_question_is_shown_and_escaped(self):
        page = self.run_cli("platforms", "--csv", str(SAMPLE), "--format", "html",
                            "--question", "How is streaming doing <vs> live TV & why?")
        self.assertTrue(page.startswith(
            "<p><strong>Question:</strong> How is streaming doing &lt;vs&gt; live TV &amp; why?</p>"))

    def test_markdown_blocks_convert(self):
        page = cr.md_to_html("## A & B\n| x | y |\n|---|---|\n| <1> | `z` |\n- item\nplain")
        for expected in ("<h3>A &amp; B</h3>", "<th>x</th><th>y</th>", "<td>&lt;1&gt;</td><td><code>z</code></td>",
                         "<ul><li>item</li></ul>", "<p>plain</p>"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)
        self.assertNotIn("---", page)


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=30)

    def test_every_subcommand_runs_on_the_sample(self):
        for args in (["campaign", "--campaign", "Fall Thriller"], ["platforms"], ["platforms", "--period", "all"],
                     ["underperformers"], ["exclusions"]):
            with self.subTest(args=args):
                proc = self.run_cli(args[0], "--csv", str(SAMPLE), *args[1:])
                self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                self.assertIn("2026-10-04", proc.stdout)

    def test_missing_file_is_a_clear_error(self):
        proc = self.run_cli("platforms", "--csv", "/nonexistent/export.csv")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.startswith("ERROR: cannot open"))

    def test_unknown_campaign_lists_candidates(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cr.main(["campaign", "--csv", str(SAMPLE), "--campaign", "no such campaign"])
        self.assertEqual(code, 0)
        self.assertIn("No single campaign matches", out.getvalue())
        self.assertIn("CAMP_2026_101", out.getvalue())


if __name__ == "__main__":
    unittest.main()
