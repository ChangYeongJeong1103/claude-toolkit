"""Expected values were derived manually from the fixtures, not from the script's output."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE.parent / "skills" / "qa-check" / "scripts" / "qa.py"
sys.path.insert(0, str(SCRIPT.parent))
import qa  # noqa: E402

FIX = HERE / "fixtures"
OTHER = FIX / "other-team"


def scan(name, root=FIX, **kw):
    return qa.scan(root / "drafts" / name, qa.load_rulebook(root / "rulebook"), **kw)


def at(items, line):
    return [i for i in items if i["line"] == line]


class RulebookTest(unittest.TestCase):
    def test_rules_metrics_clients(self):
        rb = qa.load_rulebook(FIX / "rulebook")
        severity = {r["id"]: r["severity"] for r in rb["rules"]}
        self.assertEqual(len(severity), 10)
        self.assertEqual({k for k, v in severity.items() if v == "Blocker"}, {"R1", "R2", "R4", "R5", "R6", "R10"})
        self.assertEqual({k for k, v in severity.items() if v == "Warning"}, {"R3", "R7", "R8", "R9"})
        self.assertEqual(len(rb["metrics"]), 6)
        self.assertEqual(len(rb["clients"]), 5)
        self.assertEqual(rb["threshold_households"], 50)
        r8 = next(r for r in rb["rules"] if r["id"] == "R8")
        self.assertEqual(r8["quoted_terms"], ["guarantee", "guaranteed", "will increase"])

    def test_missing_file_is_an_error(self):
        with self.assertRaises(qa.QAError):
            qa.load_rulebook(FIX / "drafts")

    def test_clients_csv_with_excel_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(FIX / "rulebook", tmp, dirs_exist_ok=True)
            path = Path(tmp) / "clients.csv"
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
            self.assertEqual(len(qa.load_rulebook(tmp)["clients"]), 5)

    def test_unparsable_formula_is_a_qa_error(self):
        metric = qa.parse_metric("CPM", "Spend / Impressions * 1,000", "currency, 2 decimals")
        with self.assertRaises(qa.QAError):
            qa.compute(metric, {"spend": qa.Decimal(1), "impressions": qa.Decimal(1)}, 2)


class KestrelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = scan("kestrel-q3-recap.md")

    def test_client_from_title(self):
        self.assertEqual(self.d["client"], {"display_name": "Kestrel Studios", "found_by": "title"})

    def test_only_live_tv_cpt_is_wrong(self):
        # 3 rows: Streaming and Live TV check 4 metrics each; Total has no reach, so only CPT and CPM.
        self.assertEqual(len(self.d["table_checks"]), 10)
        wrong = [c for c in self.d["table_checks"] if not c["match"]]
        self.assertEqual(len(wrong), 1)
        self.assertEqual((wrong[0]["line"], wrong[0]["shown"], wrong[0]["computed"]), (13, "$11.50", "12.50"))

    def test_crestfall_benchmark(self):
        crest = at(self.d["client_mentions"], 20)
        self.assertEqual([(m["client"], m["own_client"], m["status"], m["benchmark_consent"]) for m in crest],
                         [("Crestfall Pictures", False, "former", "no")])

    def test_conversion_rate_term(self):
        self.assertIn(("R3", "conversion rate"), [(t["rule"], t["text"]) for t in at(self.d["rule_terms"], 6)])

    def test_reach_note_available(self):
        self.assertTrue(any("cannot be added together" in n for n in self.d["metric_notes"]))


class BluepeakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = scan("bluepeak-campaign-review.md")

    def test_lumen_has_consent_and_bpk_is_own(self):
        self.assertEqual([(m["client"], m["benchmark_consent"]) for m in at(self.d["client_mentions"], 16)],
                         [("Lumen Sports Network", "yes")])
        self.assertEqual([(m["text"], m["own_client"]) for m in at(self.d["client_mentions"], 6)], [("BPK", True)])

    def test_small_row(self):
        self.assertEqual([(r["line"], r["value"]) for r in self.d["small_rows"]], [(14, "38")])

    def test_draft_markers_and_guarantees(self):
        hits = {(t["rule"], t["text"]) for t in at(self.d["rule_terms"], 22)}
        self.assertEqual(hits, {("R10", "TBD"), ("R8", "guarantees")})

    def test_tune_in_rate_column_needs_calc(self):
        # The table has "Households", not "Reach", so the script can't recompute it; the skill uses calc.
        self.assertEqual(self.d["table_checks"], [])
        self.assertEqual([(u["metric"], u["missing_columns"]) for u in self.d["table_unchecked"]],
                         [("Tune-in rate", ["reach"])])

    def test_prose_metric_lines(self):
        self.assertEqual([p["line"] for p in self.d["prose_metric_lines"]], [6, 19])


class HarborlineTest(unittest.TestCase):
    def test_client_from_file_name_and_title_mismatch(self):
        d = scan("harborline-brand-study.md")
        self.assertEqual(d["client"], {"display_name": "Harborline Auto", "found_by": "file name"})
        self.assertFalse(d["title"]["has_display_name"])
        self.assertEqual([(f["text"], f["decimals"]) for f in at(d["number_formats"], 9)],
                         [("1.20%", 2), ("0.96%", 2), ("25.0%", 1)])

    def test_client_flag_overrides(self):
        d = scan("harborline-brand-study.md", client="Harborline")
        self.assertEqual(d["client"]["found_by"], "--client")


class CalcTest(unittest.TestCase):
    rb = qa.load_rulebook(FIX / "rulebook")

    def calc(self, name, claim):
        return qa.calc(FIX / "drafts" / name, self.rb, [claim])["claims"][0]

    def test_lift(self):
        r = self.calc("bluepeak-campaign-review.md", {"line": 19, "metric": "Incremental lift",
                      "inputs": {"Exposed rate": 0.82, "Control rate": 0.60}, "shown": "36.7%"})
        self.assertEqual((r["computed"], r["match"], r["errors"]), ("36.7", True, []))

    def test_cpt_by_abbreviation(self):
        r = self.calc("kestrel-q3-recap.md", {"line": 13, "metric": "CPT",
                      "inputs": {"Spend": "$150,000.00", "Tune-ins": "12,000"}, "shown": "$11.50"})
        self.assertEqual((r["computed"], r["match"]), ("12.50", False))

    def test_invented_input_and_wrong_line_are_reported(self):
        r = self.calc("bluepeak-campaign-review.md", {"line": 3, "metric": "CPM",
                      "inputs": {"Spend": 99999, "Impressions": 2460000}, "shown": "$25.00"})
        self.assertEqual(len(r["errors"]), 2)

    def test_sum_of_shown_numbers(self):
        # Bluepeak L6 CPT: total tune-ins are not shown, only the segment rows (3,708 + 1,960 + 1).
        r = self.calc("bluepeak-campaign-review.md", {"line": 6, "metric": "Cost per tune-in",
                      "inputs": {"Spend": "$61,500.00", "Tune-ins": [3708, 1960, 1]}, "shown": "$10.85"})
        self.assertEqual((r["computed"], r["match"], r["errors"]), ("10.85", True, []))

    def test_sum_with_an_invented_part_is_reported(self):
        r = self.calc("bluepeak-campaign-review.md", {"line": 6, "metric": "CPT",
                      "inputs": {"Spend": 61500, "Tune-ins": [3708, 1234]}, "shown": "$10.85"})
        self.assertEqual(len(r["errors"]), 1)

    def test_unknown_metric(self):
        r = self.calc("bluepeak-campaign-review.md", {"line": 6, "metric": "ROAS", "inputs": {}, "shown": "1"})
        self.assertEqual(r["errors"], ["not a derived metric in metric-definitions.md"])


class OtherTeamTest(unittest.TestCase):
    """A different rulebook (rule IDs, metrics, clients, threshold) works with no code change."""

    def test_other_team_rulebook(self):
        d = scan("northwind-q3-report.md", root=OTHER)
        self.assertEqual([r["id"] for r in d["rules"]], ["PA-1", "PA-2", "PA-3", "PA-4"])
        self.assertEqual(d["client"]["display_name"], "Northwind Foods")
        wrong = [(c["line"], c["computed"]) for c in d["table_checks"] if not c["match"]]
        self.assertEqual(wrong, [(8, "5.00")])
        self.assertEqual(len(d["table_checks"]), 4)
        self.assertEqual([(r["line"], r["threshold"]) for r in d["small_rows"]], [(8, 100)])
        mentions = {m["client"]: m["benchmark_consent"] for m in at(d["client_mentions"], 10)}
        self.assertEqual(mentions, {"Granite Bank": "no", "Orchid Travel": "yes"})
        self.assertIn(("PA-3", "risk-free"), [(t["rule"], t["text"]) for t in d["rule_terms"]])


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        p = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    def test_scan_finds_rulebook_next_to_drafts(self):
        code, out = self.run_cli("scan", str(FIX / "drafts" / "kestrel-q3-recap.md"))
        self.assertEqual(code, 0)
        self.assertEqual(Path(out["rulebook"]).name, "rulebook")

    def test_pdf_is_out_of_scope(self):
        code, out = self.run_cli("scan", "deck.pdf")
        self.assertEqual(code, 2)
        self.assertIn("Markdown", out["error"])

    def test_findings_must_be_objects(self):
        code, out = self.run_cli("report", str(FIX / "drafts" / "kestrel-q3-recap.md"), "--findings", '["R2"]')
        self.assertEqual(code, 2)
        self.assertIn("list of objects", out["error"])

    def test_report_errors_exit_1_and_draft_is_unchanged(self):
        draft = FIX / "drafts" / "kestrel-q3-recap.md"
        before = draft.read_bytes()
        code, out = self.run_cli("report", str(draft), "--findings", json.dumps([F_KESTREL[0]]))
        self.assertEqual(code, 1)
        self.assertTrue(out["errors"])
        self.assertEqual(draft.read_bytes(), before)


def finding(rule, line, quote):
    return {"rule": rule, "line": line, "quote": quote, "issue": "x", "fix": "y"}


F_KESTREL = [finding("R1", 20, "Crestfall's Q2 thriller launch"), finding("R2", 13, "$11.50"),
             finding("R2", 6, "3.05 million households"), finding("R3", 6, "conversion rate")]


class ReportTest(unittest.TestCase):
    def report(self, name, findings, root=FIX, notes=()):
        return qa.report(root / "drafts" / name, qa.load_rulebook(root / "rulebook"), findings, notes)

    def test_kestrel_not_ready(self):
        md, errors = self.report("kestrel-q3-recap.md", F_KESTREL)
        self.assertEqual(errors, [])
        self.assertIn("**Verdict: NOT READY TO SEND** — 3 blockers, 1 warning.", md)
        self.assertIn("`kestrel-q3-recap.md:13`", md)

    def test_severity_comes_from_the_rulebook(self):
        findings = [{**F_KESTREL[0], "severity": "Warning"}, *F_KESTREL[1:]]
        md, _ = self.report("kestrel-q3-recap.md", findings)
        self.assertLess(md.index("R1 · Client confidentiality"), md.index("## Warnings"))

    def test_harborline_ready_with_warnings_and_note(self):
        md, errors = self.report("harborline-brand-study.md",
                                 [finding("R9", 1, "Harbor Line Auto"), finding("R7", 9, "1.20%")],
                                 notes=["R7 vs metric-definitions precision"])
        self.assertEqual(errors, [])
        self.assertIn("**Verdict: READY TO SEND** — 0 blockers, 2 warnings.", md)
        self.assertIn("## Rulebook notes", md)

    def test_unknown_rule_and_wrong_quote_are_rejected(self):
        md, errors = self.report("harborline-brand-study.md",
                                 [finding("R11", 9, "recieve"), finding("R9", 1, "Harborline Auto")])
        self.assertIsNone(md)
        self.assertEqual(len(errors), 2)
        self.assertIn("'R11' is not in the rulebook", errors[0])
        self.assertIn("is not on line 1", errors[1])

    def test_missed_metric_and_client_are_rejected(self):
        md, errors = self.report("kestrel-q3-recap.md", F_KESTREL[2:])
        self.assertIsNone(md)
        self.assertEqual([e.split(":")[0] for e in errors], ["line 13", "line 20"])

    def test_missed_small_row_is_rejected(self):
        _, errors = self.report("bluepeak-campaign-review.md",
                                [finding("R10", 22, "TBD"), finding("R8", 22, "guarantees")])
        self.assertEqual([e.split(":")[0] for e in errors], ["line 14"])

    def test_a_finding_on_the_line_must_quote_the_evidence(self):
        # A warning that quotes something else on the line does not hide the blocker there.
        _, errors = self.report("bluepeak-campaign-review.md",
                                [finding("R7", 14, "2.63%"), finding("R10", 22, "TBD"), finding("R8", 22, "guarantees")])
        self.assertEqual([e.split(":")[0] for e in errors], ["line 14"])
        _, errors = self.report("kestrel-q3-recap.md", [finding("R7", 13, "0.60%"), *F_KESTREL[0:1], *F_KESTREL[2:]])
        self.assertEqual([e.split(":")[0] for e in errors], ["line 13"])

    def test_no_forced_finding_for_lowercase_alias_or_non_count_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / "northwind-q4.md"
            draft.write_text("# Northwind Foods — Q4 Partner Report\n\n"
                             "| Segment | Reach | Cost per household | Reach % |\n|---|---|---|---|\n"
                             "| Shoppers | 40,000 | $0.12 | 35.0% |\n\n"
                             "A granite countertop creative ran in October.\n")
            rb = qa.load_rulebook(OTHER / "rulebook")
            d = qa.scan(draft, rb)
            self.assertEqual(d["small_rows"], [])
            self.assertEqual([(m["client"], m["exact_case"]) for m in d["client_mentions"] if not m["own_client"]],
                             [("Granite Bank", False)])
            md, errors = qa.report(draft, rb, [])
            self.assertEqual(errors, [])
            self.assertIn("READY TO SEND", md)

    def test_duplicates_collapse(self):
        md, _ = self.report("kestrel-q3-recap.md", F_KESTREL + [F_KESTREL[1]])
        self.assertIn("3 blockers, 1 warning", md)

    def test_other_team(self):
        md, errors = self.report("northwind-q3-report.md",
                                 [finding("PA-2", 8, "$4.00"), finding("PA-4", 8, "90"),
                                  finding("PA-1", 10, "Granite's spring campaign"), finding("PA-3", 10, "risk-free")],
                                 root=OTHER)
        self.assertEqual(errors, [])
        self.assertIn("**Verdict: NOT READY TO SEND** — 3 blockers, 1 warning.", md)


if __name__ == "__main__":
    unittest.main()
