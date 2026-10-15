"""Tests for segments.py. Expected values come from reading the catalog and policy by hand."""
import copy
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "skills", "plan-segments")
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import segments  # noqa: E402

CATALOG = os.path.join(HERE, "fixtures", "segments.csv")
POLICY = os.path.join(SKILL, "config", "targeting-policy.json")


def excluded_rules(excluded):
    return {s["segment_id"]: [rid for rid, _ in failures] for s, failures in excluded}


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.catalog = segments.load_catalog(CATALOG)
        self.policy = segments.load_policy(POLICY)

    def run_check(self, advertiser, flight_end, policy=None):
        return segments.check(self.catalog, policy or self.policy, advertiser, date.fromisoformat(flight_end))

    def catalog_with_first_row_value(self, column, value):
        """Return a temporary catalog path with one controlled field changed."""
        with open(CATALOG, newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            rows = list(reader)
            fieldnames = reader.fieldnames
        rows[0][column] = value
        with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False) as tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(os.remove, tmp.name)
        return tmp.name

    def test_health_advertiser_brightwell(self):
        eligible, excluded = self.run_check("otc_medicine", "2027-01-31")
        self.assertEqual(excluded_rules(excluded), {
            "SEG-105": ["T1", "T4"], "SEG-107": ["T1", "T4"], "SEG-109": ["T1"], "SEG-113": ["T3"],
            "SEG-114": ["T2"], "SEG-117": ["T3"], "SEG-118": ["T1"],
        })
        self.assertEqual(len(eligible), 11)

    def test_no_restriction_lumen_expiry_on_last_flight_day_passes(self):
        eligible, excluded = self.run_check("other", "2026-11-15")
        self.assertEqual(excluded_rules(excluded), {
            "SEG-105": ["T1"], "SEG-107": ["T1"], "SEG-109": ["T1"], "SEG-113": ["T3"],
            "SEG-114": ["T2"], "SEG-118": ["T1"],
        })
        self.assertIn("SEG-117", [s["segment_id"] for s in eligible])

    def test_alcohol_only_age_floor_21(self):
        eligible, excluded = self.run_check("alcohol", "2027-03-31")
        self.assertEqual([s["segment_id"] for s in eligible], ["SEG-103", "SEG-115", "SEG-116"])
        self.assertEqual(excluded_rules(excluded)["SEG-104"], ["T5"])

    def test_alcohol_flight_past_expiry(self):
        eligible, excluded = self.run_check("alcohol", "2027-04-01")
        rules = excluded_rules(excluded)
        self.assertEqual(rules["SEG-103"], ["T3"])
        self.assertEqual(rules["SEG-104"], ["T3", "T5"])
        self.assertEqual([s["segment_id"] for s in eligible], ["SEG-115", "SEG-116"])

    def test_unknown_advertiser_category_refused(self):
        with self.assertRaisesRegex(segments.PlanError, "unknown advertiser category 'pharmaceutical'"):
            self.run_check("pharmaceutical", "2027-01-31")

    def test_other_team_policy_config(self):
        policy = copy.deepcopy(self.policy)
        policy["rules"][1]["value"] = 50000  # T2 minimum size
        eligible, _ = self.run_check("other", "2026-11-15", policy)
        self.assertIn("SEG-114", [s["segment_id"] for s in eligible])

    def test_missing_catalog_column_refused(self):
        with open(CATALOG, encoding="utf-8") as f:
            text = f.read().replace(",exclusive_group", "", 1)
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as tmp:
            tmp.write(text)
        self.addCleanup(os.remove, tmp.name)
        with self.assertRaisesRegex(segments.PlanError, "missing columns: exclusive_group"):
            segments.load_catalog(tmp.name)

    def test_non_positive_catalog_values_refused(self):
        for column, value, expected in [
            ("households", "0", "households must be positive"),
            ("cpm_usd", "-1", "cpm_usd must be positive"),
            ("age_floor", "-1", "age_floor cannot be negative"),
        ]:
            with self.subTest(column=column):
                with self.assertRaisesRegex(segments.PlanError, expected):
                    segments.load_catalog(self.catalog_with_first_row_value(column, value))

    def test_malformed_catalog_value_refused(self):
        with self.assertRaisesRegex(segments.PlanError, "invalid number or date"):
            segments.load_catalog(self.catalog_with_first_row_value("households", "not-a-number"))

    def test_non_positive_policy_values_refused(self):
        cases = []
        for value in (0, -1, "3"):
            policy = copy.deepcopy(self.policy)
            policy["default_frequency_cap"] = value
            cases.append(("default cap", policy, "default_frequency_cap must be a positive integer"))
        policy = copy.deepcopy(self.policy)
        policy["rules"][1]["value"] = "many"
        cases.append(("minimum households", policy, "value must be a positive integer"))
        policy = copy.deepcopy(self.policy)
        policy["rules"][4]["value"] = -1
        cases.append(("minimum age", policy, "value must be a non-negative integer"))

        for label, policy, expected in cases:
            with self.subTest(label=label):
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
                    json.dump(policy, tmp)
                self.addCleanup(os.remove, tmp.name)
                with self.assertRaisesRegex(segments.PlanError, expected):
                    segments.load_policy(tmp.name)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.catalog = segments.load_catalog(CATALOG)
        self.policy = segments.load_policy(POLICY)

    def run_plan(self, advertiser, flight_end, budget, ids, cap=None):
        return segments.plan(self.catalog, self.policy, advertiser, date.fromisoformat(flight_end),
                             budget, ids, cap)

    def test_brightwell_single_segment_cap_4(self):
        # 180,000 / 27 * 1000 = 6,666,666.67 impressions; / 4 = 1,666,666.67 < 3,300,000 households
        result = self.run_plan("otc_medicine", "2027-01-31", 180000, ["SEG-106"], cap=4)
        row = result["rows"][0]
        self.assertEqual((row["impressions"], row["reach"]), (6666666, 1666666))
        self.assertEqual((result["low"], result["high"]), (1666666, 1666666))

    def test_lumen_even_split_and_reach_range(self):
        # $50,000 each; default cap 3. 101: 1,785,714 / 595,238; 102: 1,562,500 / 520,833;
        # 112: 2,000,000 / 666,666; 115 and 116: 2,272,727 / 757,575, summed within AGE = 1,515,150.
        ids = ["SEG-101", "SEG-102", "SEG-112", "SEG-115", "SEG-116"]
        result = self.run_plan("other", "2026-11-15", 250000, ids)
        self.assertEqual(result["frequency_cap"], 3)
        self.assertEqual([r["budget"] for r in result["rows"]], [50000] * 5)
        self.assertEqual([r["impressions"] for r in result["rows"]],
                         [1785714, 1562500, 2000000, 2272727, 2272727])
        self.assertEqual([r["reach"] for r in result["rows"]], [595238, 520833, 666666, 757575, 757575])
        self.assertEqual((result["low"], result["high"]), (1515150, 3297887))

    def test_reach_capped_by_households(self):
        # SEG-110: 180,000 / 33 * 1000 = 5,454,545 impressions; / 3 = 1,818,181 > 640,000 households
        row = self.run_plan("other", "2026-12-31", 180000, ["SEG-110"])["rows"][0]
        self.assertEqual((row["impressions"], row["reach"]), (5454545, 640000))

    def test_unknown_segment_refused(self):
        with self.assertRaisesRegex(segments.PlanError, "not in the catalog: Fantasy Football Players"):
            self.run_plan("other", "2026-11-15", 250000, ["SEG-101", "Fantasy Football Players"])

    def test_excluded_segment_refused(self):
        with self.assertRaisesRegex(segments.PlanError, r"excluded by policy: SEG-107 \(T1, T4\)"):
            self.run_plan("otc_medicine", "2027-01-31", 180000, ["SEG-106", "SEG-107"])

    def test_non_positive_budget_refused(self):
        for budget in (0, -1):
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(segments.PlanError, "budget must be positive"):
                    self.run_plan("other", "2026-11-15", budget, ["SEG-101"])

    def test_non_positive_frequency_cap_refused(self):
        for cap in (0, -1):
            with self.subTest(cap=cap):
                with self.assertRaisesRegex(segments.PlanError, "frequency cap must be a positive integer"):
                    self.run_plan("other", "2026-11-15", 250000, ["SEG-101"], cap=cap)


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        script = os.path.join(SKILL, "scripts", "segments.py")
        common = ["--catalog", CATALOG, "--policy", POLICY]
        return subprocess.run([sys.executable, script, *args, *common], capture_output=True, text=True)

    def test_check_lists_exclusions_with_rules(self):
        out = self.run_cli("check", "--advertiser", "otc_medicine", "--flight-end", "2027-01-31")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("| SEG-107 | Seasonal Allergy Sufferers | T1, T4 |", out.stdout)

    def test_plan_refuses_excluded_segment(self):
        out = self.run_cli("plan", "--advertiser", "otc_medicine", "--flight-end", "2027-01-31",
                           "--budget", "180000", "--segments", "SEG-107")
        self.assertEqual(out.returncode, 2)
        self.assertIn("excluded by policy: SEG-107 (T1, T4)", out.stderr)


if __name__ == "__main__":
    unittest.main()
