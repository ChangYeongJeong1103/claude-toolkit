"""Tests for core-dev hook scripts. Run from plugins/core-dev: python3 -B -m unittest discover -s tests

- Unit tests import shell_words and each guard and call their functions directly.
- Hook tests run each guard the way Claude Code does (stdin JSON -> stdout JSON) and fail on
  any crash: non-zero exit, output on stderr, or stdout that is not a valid PreToolUse decision.
  Without this, a crashed hook prints nothing and looks the same as "no objection" (fail-open).
- Fail-safe tests break a guard on purpose (exception in an internal function, missing or broken
  shell_words module, unparseable stdin) and expect an `ask` decision.
- Config test runs every command exactly as hooks.json declares it.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # the plugin loads in place, so keep __pycache__ out of hooks/scripts

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "hooks" / "scripts"
CONDA_GUARD = SCRIPTS / "conda-guard.py"
ENV_GUARD = SCRIPTS / "env-guard.py"
GUARDS = [CONDA_GUARD, ENV_GUARD]


def load(path):
    """Import a script file (hyphenated names allowed) as a module."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shell_words = load(SCRIPTS / "shell_words.py")
conda_guard = load(CONDA_GUARD)
env_guard = load(ENV_GUARD)
conda_guard.shell_words = env_guard.shell_words = shell_words  # normally imported in run()


def run_hook(script, payload, conda_env="base"):
    """Run a hook script like Claude Code does; return its hookSpecificOutput, or None if it printed nothing.

    Raises AssertionError if the script crashed or printed a malformed decision.
    """
    env = {k: v for k, v in os.environ.items() if k != "CONDA_DEFAULT_ENV"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if conda_env is not None:
        env["CONDA_DEFAULT_ENV"] = conda_env
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    proc = subprocess.run([sys.executable, str(script)], input=stdin,
                          capture_output=True, text=True, env=env, timeout=10)
    if proc.returncode != 0 or proc.stderr:
        raise AssertionError(f"{script.name} crashed (exit {proc.returncode}):\n{proc.stderr}")
    if not proc.stdout.strip():
        return None
    try:
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        ok = (out["hookEventName"] == "PreToolUse"
              and out["permissionDecision"] in {"allow", "deny", "ask"}
              and out["permissionDecisionReason"])
    except (ValueError, KeyError, TypeError):
        ok = False
    if not ok:
        raise AssertionError(f"{script.name} printed a malformed decision:\n{proc.stdout}")
    return out


def run_with_injected_error(script, func, payload):
    """Run a guard in a subprocess with one internal function replaced by one that raises."""
    with tempfile.TemporaryDirectory() as d:
        driver = Path(d) / "driver.py"
        driver.write_text(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('guard', {str(script)!r})\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "def boom(*args, **kwargs):\n"
            "    raise RuntimeError('injected failure')\n"
            f"setattr(mod, {func!r}, boom)\n"
            "mod.run()\n"
        )
        return run_hook(driver, payload)


def run_with_shell_words(script, module_source, payload):
    """Run a copy of a guard next to `module_source` as shell_words.py (None = module missing)."""
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / script.name
        shutil.copy(script, copy)
        if module_source is not None:
            (Path(d) / "shell_words.py").write_text(module_source)
        return run_hook(copy, payload)


def decision(out):
    return out["permissionDecision"] if out else None


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def monitor(cmd):
    return {"tool_name": "Monitor", "tool_input": {"command": cmd, "description": "test"}}


def edit(tool, path):
    return {"tool_name": tool, "tool_input": {"file_path": path}}


HEREDOC_COMMIT = "git commit -m \"$(cat <<'EOF'\nUse `python -m pytest` for tests\nEOF\n)\""
HEREDOC_PR = "gh pr create --title t --body \"$(cat <<'EOF'\nSetup: run `cp .env.example .env`\nEOF\n)\""
HEREDOC_SCRIPT = "cat <<'EOF' > setup.sh\ncp .env.example .env\nEOF"


# ---------- unit tests: functions ----------

class ShellWordsUnitTest(unittest.TestCase):
    def seg(self, cmd):
        return [argv for argv, _ in shell_words.segments(cmd)]

    def test_splits_on_operators(self):
        self.assertEqual(self.seg("(cd sub && cp a .env)"), [["cd", "sub"], ["cp", "a", ".env"]])
        self.assertEqual(self.seg("{ touch .env; }"), [["touch", ".env"]])
        self.assertEqual(self.seg("$(touch .env)"), [["touch", ".env"]])
        self.assertEqual(self.seg("if true; then touch .env; fi"), [["true"], ["touch", ".env"], ["fi"]])
        self.assertEqual(self.seg("ls\npython x.py"), [["ls"], ["python", "x.py"]])

    def test_quotes_and_heredocs_are_data(self):
        self.assertEqual(self.seg('git commit -m "a (python) | b; c"'), [["git", "commit", "-m", "a (python) | b; c"]])
        self.assertEqual(self.seg(HEREDOC_SCRIPT), [["cat"]])
        self.assertEqual(shell_words.strip_heredocs("cat <<'EOF' > f\nbody\nEOF\nls"), "cat <<'EOF' > f\nls")

    def test_line_continuation_and_fallback(self):
        self.assertEqual(self.seg("conda run -n project-env \\\n  python x.py"), [["conda", "run", "-n", "project-env", "python", "x.py"]])
        self.assertEqual(self.seg('python x.py "unclosed'), [["python", "x.py", '"unclosed']])

    def test_redirect_targets(self):
        self.assertEqual(shell_words.split_redirects(["python", "x.py", ">", "out", "2", ">&", "1"]),
                         (["python", "x.py", "2"], ["out", "1"]))
        self.assertEqual(list(shell_words.segments("echo A=1 >> .env")), [(["echo", "A=1"], [".env"])])
        self.assertEqual(list(shell_words.segments("sed -i '' s/a/b/ .env")), [(["sed", "-i", "", "s/a/b/", ".env"], [])])

    def test_strip_prefix(self):
        strip = shell_words.strip_prefix
        self.assertEqual(strip(["sudo", "-u", "root", "FOO=1", "env", "-i", "python", "x.py"]), ["python", "x.py"])
        self.assertEqual(strip(["nice", "-n", "10", "time", "-p", "pip", "-V"]), ["pip", "-V"])
        self.assertEqual(strip(["timeout", "-s", "KILL", "300", "python", "x.py"]), ["python", "x.py"])
        self.assertEqual(strip(["caffeinate", "-i", "python", "x.py"]), ["python", "x.py"])
        self.assertEqual(strip(["git", "status"]), ["git", "status"])


class CondaGuardUnitTest(unittest.TestCase):
    def test_env_from_prefix(self):
        self.assertEqual(conda_guard.env_from_prefix("/x/miniforge3/envs/project-env"), "project-env")
        self.assertEqual(conda_guard.env_from_prefix("/x/miniforge3"), "base")
        self.assertEqual(conda_guard.env_from_prefix(".venv"), ".venv")

    def test_env_from_interp(self):
        self.assertIsNone(conda_guard.env_from_interp("python"))
        self.assertEqual(conda_guard.env_from_interp("~/miniforge3/envs/project-env/bin/python"), "project-env")
        self.assertEqual(conda_guard.env_from_interp("~/miniforge3/bin/pip"), "base")
        self.assertEqual(conda_guard.env_from_interp(".venv/bin/python"), ".venv")

    def test_conda_run(self):
        self.assertEqual(conda_guard.conda_run(["-n", "project-env", "python", "x.py"]), ("project-env", ["python", "x.py"]))
        self.assertEqual(conda_guard.conda_run(["--name=project-env", "python"]), ("project-env", ["python"]))
        self.assertEqual(conda_guard.conda_run(["--no-capture-output", "-p", "/x/miniforge3", "pip"]),
                         ("base", ["pip"]))

    def test_invocations(self):
        inv = lambda cmd: list(conda_guard.invocations(cmd, "base"))
        self.assertEqual(inv("cd x && FOO=1 python a.py | tee log; pip -V"), [("python", "base"), ("pip", "base")])
        self.assertEqual(inv("conda run -n project-env python x.py"), [("python", "project-env")])
        self.assertEqual(inv("conda activate project-env && python x.py"), [("python", "project-env")])
        self.assertEqual(inv("conda activate ~/miniforge3 && python x.py"), [("python", "base")])
        self.assertEqual(inv("conda activate project-env; conda deactivate; python x.py"), [("python", "base")])
        self.assertEqual(inv("python x.py; conda activate project-env"), [("python", "base")])
        self.assertEqual(inv("source .venv/bin/activate && pip -V"), [("pip", ".venv")])
        self.assertEqual(inv("source ~/miniforge3/bin/activate project-env && python x.py"), [("python", "project-env")])
        self.assertEqual(inv("grep python README.md"), [])


class EnvGuardUnitTest(unittest.TestCase):
    def test_is_env_file(self):
        for path in [".env", "/a/.env.local", '".env"', "/a/.env.production", "/a/.ENV", "/a/.Env.Local"]:
            with self.subTest(path=path):
                self.assertTrue(env_guard.is_env_file(path))
        for path in ["", ".env.example", "/a/.ENV.EXAMPLE", ".envrc", "prod.env", "/a/config.py"]:
            with self.subTest(path=path):
                self.assertFalse(env_guard.is_env_file(path))

    def test_bash_writes_env(self):
        self.assertTrue(env_guard.bash_writes_env("cp .env.example .env"))
        self.assertTrue(env_guard.bash_writes_env("(echo A=1 > .env)"))
        self.assertFalse(env_guard.bash_writes_env("cp .env /tmp/backup"))
        self.assertFalse(env_guard.bash_writes_env(HEREDOC_SCRIPT))


# ---------- hook tests: real subprocess, stdin JSON -> stdout JSON ----------

class HarnessTest(unittest.TestCase):
    def test_crashing_script_fails_instead_of_passing_as_no_decision(self):
        with tempfile.TemporaryDirectory() as d:
            broken = Path(d) / "broken.py"
            broken.write_text("import json, sys\njson.load(sys.stdin)\nUNDEFINED_RE.match('x')\n")
            with self.assertRaises(AssertionError):
                run_hook(broken, bash("python x.py"))


class CondaGuardHookTest(unittest.TestCase):
    def decision(self, cmd, conda_env="base"):
        return decision(run_hook(CONDA_GUARD, bash(cmd), conda_env))

    def test_asks_in_base_or_unknown_env(self):
        for cmd, env in [
            ("python train.py", "base"),
            ("pip install numpy", "base"),
            ("python x.py", None),
            ("cd src && python3.11 -m pytest", "base"),
            ("conda run -n base python x.py", "project-env"),
            ("~/miniforge3/bin/python x.py", "project-env"),
            ("{ python x.py; }", "base"),
            ("sudo -E python x.py", "base"),
            ("env -i python x.py", "base"),
            ("if true; then python x.py; fi", "base"),
            ("conda activate project-env; conda deactivate; python x.py", "base"),
            ("python x.py; conda activate project-env", "base"),
            ("timeout 300 python train.py", "base"),
            ("caffeinate -i python train.py", "base"),
            ("conda activate ~/miniforge3 && python x.py", "base"),
            ("python - <<'EOF'\nprint(1)\nEOF", "base"),
            ('python x.py "unclosed', "base"),
        ]:
            with self.subTest(cmd=cmd, env=env):
                self.assertEqual(self.decision(cmd, env), "ask")

    def test_allows_explicit_non_base_env(self):
        for cmd, env in [
            ("conda run -n project-env python train.py", "base"),
            ("conda run -n project-env \\\n  python train.py", "base"),
            ("conda activate project-env && python train.py", "base"),
            ("~/miniforge3/envs/project-env/bin/python x.py", "base"),
            ("source .venv/bin/activate && pip install -e .", "base"),
            ("python train.py", "project-env"),
        ]:
            with self.subTest(cmd=cmd, env=env):
                self.assertIsNone(self.decision(cmd, env))

    def test_ignores_python_mentioned_as_text(self):
        for cmd in ["ls -la; git status", "grep python README.md", 'git commit -m "fix python path"',
                    "which python", 'git commit -m "feat: add x (python 3.11 support)"', HEREDOC_COMMIT,
                    'grep -rn "conda install\\|pip install" README.md']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decision(cmd))

    def test_checks_monitor_commands(self):
        self.assertEqual(decision(run_hook(CONDA_GUARD, monitor("python train.py 2>&1 | grep --line-buffered loss"))),
                         "ask")
        self.assertIsNone(decision(run_hook(CONDA_GUARD, monitor("conda run -n project-env python train.py"))))


class EnvGuardHookTest(unittest.TestCase):
    def decision(self, payload):
        return decision(run_hook(ENV_GUARD, payload))

    def test_denies_env_file_edits(self):
        for tool, path in [("Write", "/p/.env"), ("Edit", "/p/.env.local"), ("Write", "/p/sub/.env.production"),
                           ("Write", "/p/.ENV"), ("Edit", "/p/.Env.Local")]:
            with self.subTest(tool=tool, path=path):
                self.assertEqual(self.decision(edit(tool, path)), "deny")

    def test_allows_templates_and_other_files(self):
        for path in ["/p/.env.example", "/p/.ENV.EXAMPLE", "/p/.env.template", "/p/config.py",
                     "/p/.envrc", "/p/prod.env"]:
            with self.subTest(path=path):
                self.assertIsNone(self.decision(edit("Write", path)))

    def test_denies_bash_writes(self):
        for cmd in ["echo A=1 >> .env", "cp .env.example .env", "sed -i '' 's/a/b/' .env",
                    "cat <<EOF > config/.env.local", "touch .env", "mv .env .env.bak", "tee -a .env",
                    "(cd sub && cp a .env)", "{ touch .env; }", "sudo cp x .env", "FOO=1 touch .env",
                    "$(touch .env)", "if true; then touch .env; fi", "(echo A=1 > .env)",
                    "cp .env.example \\\n  .env", 'echo "A=1 > .env']:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decision(bash(cmd)), "deny")

    def test_allows_bash_reads_and_other_writes(self):
        for cmd in ["cat .env", "grep KEY .env", "cp .env /tmp/backup", "cp .env.example .env.sample",
                    "echo hi > out.txt", "python run.py 2>&1 | tee log.txt", "(cd sub && cat .env)",
                    "sudo cp .env /tmp/backup"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decision(bash(cmd)))

    def test_ignores_env_writes_mentioned_as_text(self):
        for cmd in [HEREDOC_PR, HEREDOC_SCRIPT, 'git commit -m "chore: stop writing > .env"']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decision(bash(cmd)))

    def test_checks_monitor_commands(self):
        self.assertEqual(self.decision(monitor("echo A=1 >> .env")), "deny")
        self.assertIsNone(self.decision(monitor("tail -f app.log")))


class FailSafeTest(unittest.TestCase):
    """A broken guard must produce an `ask` decision, not a crash or silence.

    Payloads normally produce no decision, so `ask` can only come from the fail-safe path.
    """

    def test_internal_exception_asks(self):
        for script, func, payload in [
            (CONDA_GUARD, "invocations", bash("ls -la")),
            (CONDA_GUARD, "env_from_interp", bash("conda activate project-env && python x.py")),
            (ENV_GUARD, "bash_writes_env", bash("cat README.md")),
            (ENV_GUARD, "is_env_file", edit("Write", "/p/config.py")),
        ]:
            with self.subTest(script=script.name, func=func):
                self.assertIsNone(decision(run_hook(script, payload)))  # baseline: no decision
                out = run_with_injected_error(script, func, payload)
                self.assertEqual(decision(out), "ask")
                self.assertIn("RuntimeError: injected failure", out["permissionDecisionReason"])

    def test_shell_words_import_failure_asks(self):
        working = (SCRIPTS / "shell_words.py").read_text()
        for script in GUARDS:
            with self.subTest(script=script.name, case="baseline: working copy"):
                self.assertIsNone(run_with_shell_words(script, working, bash("ls -la")))
            for case, source, expected in [
                ("missing", None, "ModuleNotFoundError: No module named 'shell_words'"),
                ("raises on import", "raise RuntimeError('broken shell_words')\n", "RuntimeError: broken shell_words"),
            ]:
                with self.subTest(script=script.name, case=case):
                    out = run_with_shell_words(script, source, bash("ls -la"))
                    self.assertEqual(decision(out), "ask")
                    self.assertIn(expected, out["permissionDecisionReason"])

    def test_unparseable_stdin_asks(self):
        for script in GUARDS:
            for stdin in ["not json", "[]"]:
                with self.subTest(script=script.name, stdin=stdin):
                    self.assertEqual(decision(run_hook(script, stdin)), "ask")

    def test_payload_without_target_is_ignored(self):
        for script in GUARDS:
            for stdin in ["{}", json.dumps({"tool_name": "Bash"})]:
                with self.subTest(script=script.name, stdin=stdin):
                    self.assertIsNone(run_hook(script, stdin))


class HooksConfigTest(unittest.TestCase):
    """Run each command exactly as hooks.json declares it: through a shell, with ${CLAUDE_PLUGIN_ROOT}."""

    def test_declared_commands_run_cleanly_without_writing_bytecode(self):
        shutil.rmtree(SCRIPTS / "__pycache__", ignore_errors=True)
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT), CONDA_DEFAULT_ENV="base")
        config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
        for entry in config["hooks"]["PreToolUse"]:
            for hook in entry["hooks"]:
                with self.subTest(matcher=entry["matcher"], command=hook["command"]):
                    proc = subprocess.run(hook["command"], shell=True, input=json.dumps(bash("ls -la")),
                                          capture_output=True, text=True, env=env, timeout=10)
                    self.assertEqual((proc.returncode, proc.stderr, proc.stdout), (0, "", ""))
        self.assertFalse((SCRIPTS / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
