"""Tests for policy_context.py. Run from the plugin root: python3 -B -m unittest discover -s tests

The fixture is a copy of the sample policy folder. Expected statuses and sections come from reading those
documents (front matter, inline metadata, and what each section says), not from the script's output.
"""
import atexit
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True  # the plugin loads in place; keep __pycache__ out of it

PLUGIN = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN / "skills" / "policy-answers" / "scripts" / "policy_context.py"
DOCS = str(PLUGIN / "tests" / "fixtures" / "policy-docs")
TODAY = date(2026, 10, 12)

spec = importlib.util.spec_from_file_location("policy_context", SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def context(question, as_of=TODAY, folder=DOCS):
    return pc.build_context(folder, question, as_of)


def citations(ctx):
    return [s["citation"] for s in ctx["sections"]]


def temp_folder(files):
    d = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    for name, text in files.items():
        Path(d, name).write_text(text)
    return d


class MetadataTest(unittest.TestCase):
    def test_every_metadata_format_in_the_sample(self):
        docs = {d["name"]: d for d in pc.load_docs(DOCS)}
        cases = [
            ("ai-acceptable-use-policy-v1.md", "status_word", "superseded"),       # front matter
            ("ai-data-handling-standard.md", "status_word", "active"),             # inline "Status: Active ·"
            ("ai-data-handling-standard.md", "effective", date(2026, 4, 1)),       # "April 1, 2026"
            ("approved-ai-tools.md", "last_updated", date(2026, 8, 15)),           # inline "Last updated: 2026-08-15"
            ("ai-tools-faq.md", "last_updated", date(2025, 9, 1)),                 # "*Last updated: September 2025*"
            ("data-classification.md", "effective", date(2025, 11, 1)),            # front matter date
            ("ai-tool-access-policy-v3.md", "replaces", "Section 4 of approved-ai-tools.md"),
        ]
        for name, field, expected in cases:
            with self.subTest(name=name, field=field):
                self.assertEqual(docs[name][field], expected)


class StatusTest(unittest.TestCase):
    def test_status_as_of_today(self):
        self.assertEqual(context("anything")["status"], {
            "ai-acceptable-use-policy-v1.md": "superseded",
            "ai-acceptable-use-policy-v2.md": "in effect",
            "ai-data-handling-standard.md": "in effect",
            "ai-tool-access-policy-v3.md": "upcoming",
            "ai-tools-faq.md": "dated (no status)",
            "approved-ai-tools.md": "dated (no status)",
            "data-classification.md": "in effect",
        })

    def test_future_policy_takes_effect_on_its_date(self):
        ctx = context("How do I get access to Claude?", as_of=date(2026, 11, 2))
        self.assertEqual(ctx["status"]["ai-tool-access-policy-v3.md"], "in effect")
        old = next(s for s in ctx["sections"] if s["citation"] == "approved-ai-tools.md § 4. Requesting access")
        self.assertTrue(old.get("replaced"))
        self.assertIn("replaced by ai-tool-access-policy-v3.md", old["note"])

    def test_superseded_by_another_document_and_reference_only(self):
        folder = temp_folder({
            "old.md": "# Old guide\n\n## Rule\nCursor is fine.\n",
            "new.md": "---\nstatus: Active\neffective: 2026-01-01\nsupersedes: old.md\n---\n# New\n\n## Rule\nNo.\n",
            "notes.md": "# Team notes\n\n## Tips\nBe careful.\n",
        })
        status = context("rule", folder=folder)["status"]
        self.assertEqual(status, {"new.md": "in effect", "old.md": "superseded", "notes.md": "reference only"})

    def test_supersession_waits_until_the_new_document_is_in_effect(self):
        folder = temp_folder({
            "old.md": "---\nstatus: Active\neffective: 2026-01-01\n---\n# Old\n\n## Rule\nYes.\n",
            "new.md": "---\nstatus: Approved\neffective: 2027-01-01\nsupersedes: old.md\n---\n# New\n\n## Rule\nNo.\n",
        })
        self.assertEqual(context("rule", folder=folder)["status"], {"new.md": "upcoming", "old.md": "in effect"})


class RetrievalTest(unittest.TestCase):
    def test_cursor_with_client_data(self):
        cites = citations(context("Can I use Cursor with client data?"))
        for expected in ("approved-ai-tools.md § 1. Approved tools", "ai-tools-faq.md § AI Tools FAQ",
                         "ai-data-handling-standard.md § 3. Client data",
                         "data-classification.md § Data Classification Policy",
                         "ai-acceptable-use-policy-v2.md § 2. Precedence"):
            with self.subTest(expected=expected):
                self.assertIn(expected, cites)

    def test_claude_access_mentions_the_upcoming_change(self):
        ctx = context("How do I get access to Claude?")
        current = next(s for s in ctx["sections"] if s["citation"] == "approved-ai-tools.md § 4. Requesting access")
        self.assertIn("changes on 2026-11-01", current["note"])
        self.assertFalse(current.get("replaced"))
        self.assertEqual([d["name"] for d in ctx["upcoming"]], ["ai-tool-access-policy-v3.md"])

    def test_household_viewing_data(self):
        cites = citations(context("Can I put household-level viewing data into an AI tool?"))
        self.assertIn("ai-data-handling-standard.md § 2. Restricted data", cites)
        self.assertIn("data-classification.md § Data Classification Policy", cites)

    def test_uncovered_question(self):
        self.assertFalse(context("Can I use an AI note-taker to record meetings?")["covered"])
        self.assertTrue(context("Can I use Cursor with client data?")["covered"])

    def test_precedence_section_is_always_included(self):
        self.assertIn("ai-acceptable-use-policy-v2.md § 2. Precedence", citations(context("Gemini email drafts")))


class ExtractedFactsTest(unittest.TestCase):
    def setUp(self):
        self.ctx = context("Who do I contact?")

    def test_contacts_come_only_from_the_documents_with_their_source_status(self):
        contacts = self.ctx["contacts"]
        self.assertEqual({st for _, st in contacts["jamie.lee@company.example"]}, {"superseded"})
        self.assertIn("in effect", {st for _, st in contacts["ai-taskforce@company.example"]})
        self.assertEqual({st for _, st in contacts["#ai-help"]}, {"dated (no status)"})
        raw = "\n".join(Path(DOCS, n).read_text() for n in os.listdir(DOCS))
        for value in contacts:
            with self.subTest(contact=value):
                self.assertIn(value, raw)

    def test_missing_references_are_flagged(self):
        missing = "\n".join(f"{c}: {w}" for c, w in self.ctx["missing"])
        self.assertIn('ai-data-handling-standard.md § 2. Restricted data: "[link TBD]"', missing)
        self.assertIn('ai-acceptable-use-policy-v2.md § 5. Exceptions: "Appendix B" is referenced but not in the folder',
                      missing)

    def test_links_include_the_portal(self):
        self.assertIn("https://it.company.example/portal/ai-access", self.ctx["links"])


class ReviewFixesTest(unittest.TestCase):
    """Bugs found in code and skill review of the script."""

    def status(self, files, as_of=TODAY):
        return context("rule", as_of=as_of, folder=temp_folder(files))["status"]

    def test_unknown_status_words_and_unreadable_dates_are_not_in_effect(self):
        status = self.status({
            "draft.md": "---\nstatus: Draft\neffective: 2026-01-01\n---\n# D\n\n## Rule\nx\n",
            "quoted.md": "---\nstatus: Approved\neffective: \"2027-01-01\"\n---\n# Q\n\n## Rule\nx\n",
            "odd.md": "---\nstatus: Active\neffective: early next year\n---\n# O\n\n## Rule\nx\n",
        })
        self.assertEqual(status["draft.md"], "not in effect (status: draft)")
        self.assertEqual(status["quoted.md"], "upcoming")
        self.assertEqual(status["odd.md"], "unreadable date (early next year)")

    def test_only_an_in_effect_document_can_supersede(self):
        status = self.status({
            "v2.md": "---\nstatus: Active\neffective: 2026-01-01\n---\n# V2\n\n## Rule\nx\n",
            "v3-draft.md": "---\nstatus: Draft\nsupersedes: v2.md\n---\n# V3\n\n## Rule\ny\n",
        })
        self.assertEqual(status["v2.md"], "in effect")

    def test_contractions_do_not_make_a_question_covered(self):
        self.assertFalse(context("What's the Zoom note-taker rule?")["covered"])

    def test_in_effect_contact_sections_are_always_included(self):
        cites = citations(context("Can I use Cursor with client data?"))
        self.assertIn("ai-acceptable-use-policy-v2.md § 6. Contacts", cites)
        self.assertIn("data-classification.md § Contact", cites)

    def test_only_related_upcoming_changes_are_listed(self):
        folder = temp_folder({
            "tools.md": "---\nstatus: Active\neffective: 2026-01-01\n---\n# Tools\n\n## 4. Requesting access\nAsk IT.\n",
            "access-v2.md": "---\nstatus: Approved\neffective: 2027-01-01\nreplaces: Section 4 of tools.md\n---\n"
                            "# Access v2\n\n## Self-service\nUse Okta.\n",
            "retention.md": "---\nstatus: Approved\neffective: 2027-02-01\n---\n# Retention\n\n## Logs\nKeep 30 days.\n",
        })
        ctx = context("How do I request access?", folder=folder)
        self.assertEqual([d["name"] for d in ctx["upcoming"]], ["access-v2.md"])


class ReleaseFixesTest(unittest.TestCase):
    """Bugs found in review after the first public release."""

    def test_superseded_document_applied_before_its_replacement(self):
        v1, v2 = "ai-acceptable-use-policy-v1.md", "ai-acceptable-use-policy-v2.md"
        cases = [
            (date(2025, 5, 1), "upcoming", "upcoming"),        # before v1 took effect
            (date(2025, 12, 1), "in effect", "upcoming"),      # v1 in effect, v2 not yet
            (date(2026, 3, 1), "superseded", "in effect"),     # v2 takes effect on its date
        ]
        for as_of, v1_status, v2_status in cases:
            with self.subTest(as_of=as_of):
                status = context("anything", as_of=as_of)["status"]
                self.assertEqual((status[v1], status[v2]), (v1_status, v2_status))

    def test_past_status_notes_when_the_replacement_starts(self):
        out = io.StringIO()
        with redirect_stdout(out):
            pc.main(["--docs", DOCS, "--question", "AI tools", "--as-of", "2025-12-01"])
        self.assertIn("superseded by ai-acceptable-use-policy-v2.md from 2026-03-01", out.getvalue())

    def test_superseded_without_a_dated_replacement_stays_superseded(self):
        status = context("rule", as_of=date(2025, 12, 1), folder=temp_folder({
            "old.md": "---\nstatus: Superseded\neffective: 2025-06-01\nsuperseded_by: new.md\n---\n# O\n\n## Rule\nx\n",
            "new.md": "---\nstatus: Active\nsupersedes: old.md\n---\n# N\n\n## Rule\ny\n",
            "orphan.md": "---\nstatus: Superseded\neffective: 2025-06-01\n---\n# P\n\n## Rule\nz\n",
        }))["status"]
        self.assertEqual(status["old.md"], "superseded")
        self.assertEqual(status["orphan.md"], "superseded")


class CliTest(unittest.TestCase):
    def test_runs_on_the_sample(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = pc.main(["--docs", DOCS, "--question", "How do I get access to Claude?", "--as-of", "2026-10-12"])
        self.assertEqual(code, 0)
        for expected in ("As of: 2026-10-12 (set with --as-of)", "### Upcoming changes", "### Missing references"):
            with self.subTest(expected=expected):
                self.assertIn(expected, out.getvalue())

    def test_bad_folder_is_a_clear_error(self):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--docs", "/nonexistent", "--question", "x"],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.startswith("ERROR: not a folder"))


if __name__ == "__main__":
    unittest.main()
