"""Tests for the grounding Stop hook. Run from the plugin root: python3 -B -m unittest discover -s tests

Each case writes a small transcript, runs the hook the way Claude Code does (stdin JSON -> stdout JSON), and fails
on a crash or stderr output, so a broken hook can't pass as "no objection".
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
HOOK = PLUGIN / "hooks" / "verify_answer.py"
CONFIG = PLUGIN / "hooks" / "hooks.json"
FIXTURES = PLUGIN / "tests" / "fixtures"
DOCS = FIXTURES / "policy-docs"
CALL = f'python3 /p/skills/policy-answers/scripts/policy_context.py --docs "{DOCS}" --question "Cursor?"'

GOOD = ("No. Cursor's max class is Internal (`approved-ai-tools.md § 1. Approved tools`), and client data is "
        "Confidential (data-classification.md § Data Classification Policy). Use Claude or Claude Code, which allow "
        "Confidential (approved-ai-tools.md §1). The FAQ says yes, but ai-acceptable-use-policy-v2.md § Precedence "
        "makes the policy win. Contact ai-taskforce@company.example or #ai-taskforce.")


def entries_for(command=CALL, cwd=None, after=()):
    return [
        {"type": "user", "message": {"role": "user", "content": "Can I use Cursor with client data?"}},
        {"type": "assistant", "cwd": cwd, "message": {"content": [
            {"type": "text", "text": "Checking the policy."},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "## Policy context"}]}},
        *after,
    ]


def run_hook(answer, entries=None, stop_hook_active=False, stdin=None, command=None, env=None):
    with tempfile.TemporaryDirectory() as d:
        transcript = Path(d, "t.jsonl")
        transcript.write_text("\n".join(json.dumps(e) for e in (entries if entries is not None else entries_for())))
        payload = stdin if stdin is not None else json.dumps({
            "session_id": "s", "transcript_path": str(transcript), "cwd": d, "hook_event_name": "Stop",
            "stop_hook_active": stop_hook_active, "last_assistant_message": answer})
        proc = subprocess.run(command or [sys.executable, "-B", str(HOOK)], input=payload, capture_output=True,
                              text=True, timeout=10, shell=bool(command), env=env)
    assert (proc.returncode, proc.stderr) == (0, ""), f"hook crashed: {proc.returncode} {proc.stderr}"
    return json.loads(proc.stdout) if proc.stdout.strip() else None


class GroundingHookTest(unittest.TestCase):
    def assert_blocked(self, out, *fragments):
        self.assertIsNotNone(out)
        self.assertEqual(out["decision"], "block")
        for fragment in fragments:
            self.assertIn(fragment, out["reason"])

    def test_grounded_answer_passes(self):
        self.assertIsNone(run_hook(GOOD))

    def test_section_that_does_not_exist_blocks(self):
        self.assert_blocked(run_hook(GOOD + " See ai-tools-faq.md § 3. Cursor rules."),
                            "ai-tools-faq.md has no such section")

    def test_document_that_does_not_exist_blocks(self):
        self.assert_blocked(run_hook(GOOD + " See security-policy.md § 1."), "security-policy.md, which is not in")

    def test_invented_contact_or_link_blocks(self):
        self.assert_blocked(run_hook(GOOD + " Or ask help@company.example."), "help@company.example")
        self.assert_blocked(run_hook(GOOD + " Form: https://intranet.company.example/ai."), "https://intranet")

    def test_answer_without_any_citation_blocks(self):
        self.assert_blocked(run_hook("No, Cursor isn't allowed with client data."), "no citation")

    def test_not_covered_with_a_contact_passes(self):
        entries = entries_for(command=f'python3 /p/policy_context.py --docs "{DOCS}" '
                                      "--question 'Can I use an AI note-taker to record meetings?'")
        self.assertIsNone(run_hook("The policy documents don't cover AI note-takers. "
                                   "Ask the AI Task Force: ai-taskforce@company.example.", entries=entries))

    def test_turn_without_policy_context_is_not_checked(self):
        entries = entries_for(command="ls -la")
        self.assertIsNone(run_hook("No citation and help@nowhere.example", entries=entries))

    def test_relative_docs_path_uses_the_session_cwd(self):
        entries = entries_for(command="python3 /p/policy_context.py --docs policy-docs --question x", cwd=str(FIXTURES))
        self.assertIsNone(run_hook(GOOD, entries=entries))
        self.assert_blocked(run_hook(GOOD + " Ask help@company.example.", entries=entries), "help@company.example")

    def test_revision_is_checked_but_blocked_only_once(self):
        feedback = {"type": "user", "message": {"role": "user", "content": "Stop hook feedback: Grounding check failed"}}
        entries = entries_for(after=[feedback])
        self.assert_blocked(run_hook("No citation.", entries=entries), "no citation")
        out = run_hook("Still no citation.", entries=entries, stop_hook_active=True)
        self.assertNotIn("decision", out)
        self.assertIn("still fails after one revision", out["systemMessage"])

    def test_bad_folder_is_left_to_the_script_error(self):
        entries = entries_for(command="python3 /p/policy_context.py --docs /nonexistent --question x")
        self.assertIsNone(run_hook("ERROR: not a folder: /nonexistent", entries=entries))

    def test_hook_error_warns_without_blocking(self):
        for stdin in ("not json", "[]", json.dumps({"transcript_path": "/nonexistent.jsonl"})):
            with self.subTest(stdin=stdin):
                out = run_hook("", stdin=stdin)
                self.assertNotIn("decision", out)
                self.assertIn("could not run", out["systemMessage"])

    def test_declared_command_runs_as_written(self):
        entry = json.loads(CONFIG.read_text())["hooks"]["Stop"][0]["hooks"][0]
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN))
        self.assertIsNone(run_hook(GOOD, command=entry["command"], env=env))
        self.assert_blocked(run_hook("No citation here.", command=entry["command"], env=env), "no citation")
        self.assertFalse(list(PLUGIN.rglob("__pycache__")))


class ReviewFixesTest(GroundingHookTest.__base__):
    """Regressions for the /code-review findings on the hook."""

    def assert_blocked(self, out, *fragments):
        GroundingHookTest.assert_blocked(self, out, *fragments)

    def test_real_section_number_with_an_invented_title_blocks(self):
        self.assert_blocked(run_hook(GOOD + " See approved-ai-tools.md § 3. Cursor is fine with client data."),
                            "has no such section")

    def test_links_wrapped_in_markdown_or_punctuation_pass(self):
        self.assertIsNone(run_hook(GOOD + " Portal: **https://it.company.example/portal/ai-access**; `go/ai-access`."))

    def test_truncated_contact_blocks(self):
        self.assert_blocked(run_hook(GOOD + " Or lee@company.example."), "lee@company.example")

    def test_uncited_yes_with_a_contact_blocks_on_a_covered_question(self):
        self.assert_blocked(run_hook("Yes; no policy restricts it. Questions: ai-taskforce@company.example."),
                            "no citation")

    def test_a_failed_folder_does_not_skip_the_good_one(self):
        entries = entries_for(after=[{"type": "assistant", "message": {"content": [{
            "type": "tool_use", "id": "t2", "name": "Bash",
            "input": {"command": "python3 /p/policy_context.py --docs /nonexistent --question x"}}]}}])
        self.assert_blocked(run_hook(GOOD + " Ask fake@evil.example.", entries=entries), "fake@evil.example")

    def test_folders_are_checked_as_a_union(self):
        with tempfile.TemporaryDirectory() as other:
            Path(other, "README.md").write_text("# Readme\n\n## About\nNotes.\n")
            entries = entries_for(after=[{"type": "assistant", "message": {"content": [{
                "type": "tool_use", "id": "t2", "name": "Bash",
                "input": {"command": f'python3 /p/policy_context.py --docs "{other}" --question x'}}]}}])
            self.assertIsNone(run_hook(GOOD, entries=entries))

    def test_an_earlier_policy_turn_is_not_checked_later(self):
        later = [{"type": "user", "message": {"role": "user", "content": "Write a Python function."}},
                 {"type": "assistant", "message": {"content": [{"type": "text", "text": "def f(): ..."}]}}]
        self.assertIsNone(run_hook("def f(): ...", entries=entries_for(after=later), stop_hook_active=True))


class EndToEndFixesTest(GroundingHookTest.__base__):
    """Regressions for issues found in the end-to-end check (step 5)."""

    def test_korean_particles_after_contacts_and_links_pass(self):
        korean = (" FAQ는 go/ai-access를 안내하지만, https://it.company.example/portal/ai-access에서 신청하고 "
                  "ai-taskforce@company.example로 문의하세요.")
        self.assertIsNone(run_hook(GOOD + korean))
        out = run_hook(GOOD + " go/ai-free를 쓰세요.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("go/ai-free is not", out["reason"])

    def test_korean_particles_after_a_section_number_pass(self):
        korean = (" 현재 절차는 `approved-ai-tools.md § 4`가 정하고, approved-ai-tools.md § 4의 절차는 "
                  "2026-11-01에 바뀝니다.")
        self.assertIsNone(run_hook(GOOD + korean))
        out = run_hook(GOOD + " `approved-ai-tools.md § 9`가 허용합니다.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("has no such section", out["reason"])


if __name__ == "__main__":
    unittest.main()
