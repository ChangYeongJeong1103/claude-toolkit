import csv
import unittest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
RULEBOOK_FILES = ("deliverable-rules.md", "metric-definitions.md", "clients.csv")
CLIENT_COLUMNS = {"display_name", "aliases", "status", "benchmark_consent"}


class FixtureContractTest(unittest.TestCase):
    """Both fixture rulebooks follow the 3-file contract in the README."""

    def test_rulebooks_have_the_three_files(self):
        for root in (FIXTURES, FIXTURES / "other-team"):
            for name in RULEBOOK_FILES:
                self.assertTrue((root / "rulebook" / name).is_file(), f"{root.name}/{name}")

    def test_clients_csv_has_contract_columns(self):
        for root in (FIXTURES, FIXTURES / "other-team"):
            with open(root / "rulebook" / "clients.csv", newline="") as f:
                self.assertTrue(CLIENT_COLUMNS <= set(csv.DictReader(f).fieldnames))

    def test_drafts_present(self):
        self.assertEqual(len(list((FIXTURES / "drafts").glob("*.md"))), 3)
        self.assertEqual(len(list((FIXTURES / "other-team" / "drafts").glob("*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
