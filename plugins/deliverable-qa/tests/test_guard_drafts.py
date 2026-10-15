import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "guard_drafts.py"
HOOKS_JSON = Path(__file__).parent.parent / "hooks" / "hooks.json"


def run(stdin):
    p = subprocess.run([sys.executable, "-B", str(HOOK)], input=stdin, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def event(tool, **tool_input):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input})


class GuardDraftsTest(unittest.TestCase):
    def assert_ask(self, stdin):
        code, out = run(stdin)
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "ask"))

    def test_edit_and_write_under_drafts_ask(self):
        self.assert_ask(event("Edit", file_path="/w/team-workflow/drafts/kestrel-q3-recap.md",
                              old_string="$11.50", new_string="$12.50"))
        self.assert_ask(event("Write", file_path="drafts/new.md", content="x"))
        self.assert_ask(event("MultiEdit", file_path="/w/Drafts/a.md", edits=[]))
        self.assert_ask(event("NotebookEdit", notebook_path="/w/drafts/a.ipynb", new_source="x"))

    def test_other_paths_pass_silently(self):
        for path in ("/w/plugin/README.md", "/w/mydrafts/a.md", "/w/rulebook/drafts.md"):
            self.assertEqual(run(event("Edit", file_path=path)), (0, ""), path)

    def test_fails_open(self):
        self.assertEqual(run("not json"), (0, ""))
        self.assertEqual(run(json.dumps({"tool_name": "Edit"})), (0, ""))

    def test_hooks_json_wires_the_guard(self):
        entry = json.loads(HOOKS_JSON.read_text())["hooks"]["PreToolUse"][0]
        self.assertEqual(set(entry["matcher"].split("|")), {"Edit", "Write", "MultiEdit", "NotebookEdit"})
        self.assertIn("guard_drafts.py", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
