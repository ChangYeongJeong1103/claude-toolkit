"""Tests for the send-confirmation hook. Run from the plugin root: python3 -B -m unittest discover -s tests

Each case runs the hook the way Claude Code does (stdin JSON -> stdout JSON) and fails on a crash, stderr output,
or a malformed decision, so a broken hook can't pass as "no objection".
"""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
HOOK = PLUGIN / "hooks" / "confirm_send.py"
CONFIG = PLUGIN / "hooks" / "hooks.json"
SEND = "mcp__claude_ai_Gmail__send_message"


def run_hook(stdin, command=None, env=None):
    if not isinstance(stdin, str):
        stdin = json.dumps(stdin)
    args = dict(shell=True) if command else {}
    proc = subprocess.run(command or [sys.executable, "-B", str(HOOK)], input=stdin, capture_output=True,
                          text=True, timeout=10, env=env, **args)
    assert (proc.returncode, proc.stderr) == (0, ""), f"hook crashed: {proc.returncode} {proc.stderr}"
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] in ("ask", "deny"), proc.stdout
    return out["permissionDecision"], out["permissionDecisionReason"]


def event(tool, **tool_input):
    return {"tool_name": tool, "tool_input": tool_input}


class ConfirmSendTest(unittest.TestCase):
    def test_send_with_fields_asks_and_shows_recipient_subject_preview(self):
        decision, reason = run_hook(event(SEND, to=["am@example.com"], cc=["lead@example.com"],
                                          subject="Campaign answer: Fall Thriller",
                                          htmlBody="<h3>Fall &amp; Thriller</h3><table><tr><td>$3.31</td></tr></table>"))
        self.assertEqual(decision, "ask")
        for expected in ("To: am@example.com", "Cc: lead@example.com", "Subject: Campaign answer: Fall Thriller",
                         "Preview: Fall & Thriller $3.31", "can't be undone"):
            with self.subTest(expected=expected):
                self.assertIn(expected, reason)

    def test_long_body_is_truncated_in_the_preview(self):
        _, reason = run_hook(event(SEND, to=["am@example.com"], subject="s", body="x" * 1000))
        self.assertIn("x" * 300 + "…", reason)
        self.assertNotIn("x" * 301, reason)

    def test_send_by_draft_id_is_denied(self):
        decision, reason = run_hook(event(SEND, draftId="r123", to=["am@example.com"]))
        self.assertEqual(decision, "deny")
        self.assertIn("draftId", reason)

    def test_reply_and_forward_ask(self):
        for tool, tin, expected in [
            ("mcp__claude_ai_Gmail__reply", {"messageId": "m1", "body": "ok", "replyAll": True}, "reply all"),
            ("mcp__claude_ai_Gmail__forward", {"messageId": "m2", "to": ["x@example.com"], "forwardText": "fyi"},
             "To: x@example.com"),
        ]:
            with self.subTest(tool=tool):
                decision, reason = run_hook(event(tool, **tin))
                self.assertEqual(decision, "ask")
                self.assertIn(expected, reason)

    def test_unreadable_request_still_asks(self):
        for stdin in ("not json", "[]"):
            with self.subTest(stdin=stdin):
                decision, reason = run_hook(stdin)
                self.assertEqual(decision, "ask")
                self.assertIn("Could not read", reason)


class HooksConfigTest(unittest.TestCase):
    def test_matcher_covers_sends_only(self):
        matcher = json.loads(CONFIG.read_text())["hooks"]["PreToolUse"][0]["matcher"]
        for tool, should_match in [(SEND, True), ("mcp__claude_ai_Gmail__reply", True),
                                   ("mcp__claude_ai_Gmail__forward", True), ("mcp__gmail__send_message", True),
                                   ("mcp__claude_ai_Gmail__create_draft", False),
                                   ("mcp__claude_ai_Gmail__search_threads", False), ("Bash", False)]:
            with self.subTest(tool=tool):
                self.assertEqual(bool(re.fullmatch(matcher, tool)), should_match)

    def test_declared_command_runs_as_written(self):
        entry = json.loads(CONFIG.read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN))
        decision, _ = run_hook(event(SEND, to=["am@example.com"], subject="s", body="b"),
                               command=entry["command"], env=env)
        self.assertEqual(decision, "ask")
        self.assertFalse((PLUGIN / "hooks" / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
