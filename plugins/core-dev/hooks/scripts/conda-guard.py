#!/usr/bin/env python3
"""PreToolUse(Bash|Monitor): ask before pip/python runs in the conda base env (or an unknown env)."""
import importlib
import json
import os
import re
import sys

INTERP_RE = re.compile(r"^(?:python|pip)(?:3(?:\.\d+)?)?$")
CONDA_CMDS = {"conda", "mamba", "micromamba"}
CONDA_ROOTS = {"miniforge3", "miniconda3", "anaconda3", "mambaforge"}
VALUE_OPTS = {"-n", "--name", "-p", "--prefix", "--cwd"}
shell_words = None  # imported in run(), so a failed import also ends in `ask`


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def env_from_prefix(path):
    """Map an env prefix path to an env name ('base' for the conda root)."""
    m = re.search(r"/envs/([^/]+)/?$", path)
    if m:
        return m.group(1)
    return "base" if os.path.basename(path.rstrip("/")) in CONDA_ROOTS else path


def env_from_interp(prog):
    """Env implied by an explicit interpreter path; None for a bare `python`."""
    if "/" not in prog:
        return None
    return env_from_prefix(prog.rsplit("/bin/", 1)[0]) if "/bin/" in prog else prog


def conda_run(args):
    """Parse `conda run` options; return (env, remaining words)."""
    env, i = None, 0
    while i < len(args) and args[i].startswith("-"):
        opt, _, val = args[i].partition("=")
        if opt in VALUE_OPTS and not val:
            val = args[i + 1] if i + 1 < len(args) else ""
            i += 1
        if opt in ("-n", "--name"):
            env = val
        elif opt in ("-p", "--prefix"):
            env = env_from_prefix(val)
        i += 1
    return env, args[i:]


def invocations(cmd, session_env):
    """Yield (interpreter, env) for each pip/python command, applying earlier activate/deactivate."""
    active = None
    for argv, _ in shell_words.segments(cmd):
        if not argv:
            continue
        prog, sub = os.path.basename(argv[0]), argv[1:2]
        args = [w for w in argv[2:] if not w.startswith("-")]
        if prog in CONDA_CMDS and sub == ["activate"]:
            active = env_from_prefix(args[0]) if args else "base"
        elif (prog in CONDA_CMDS and sub == ["deactivate"]) or prog == "deactivate":
            active = None
        elif prog in ("source", ".") and sub == ["activate"]:  # legacy `source activate X`
            active = env_from_prefix(args[0]) if args else "base"
        elif prog in ("source", ".") and sub and sub[0].endswith("/bin/activate"):  # venv or conda root
            active = env_from_prefix(args[0] if args else sub[0][: -len("/bin/activate")])
        else:
            run_env = None
            if prog in CONDA_CMDS and sub == ["run"]:
                run_env, argv = conda_run(argv[2:])
            if argv and INTERP_RE.match(os.path.basename(argv[0])):
                yield argv[0], env_from_interp(argv[0]) or run_env or active or session_env


def main():
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    for prog, env in invocations(cmd, os.environ.get("CONDA_DEFAULT_ENV")):
        if env in (None, "", "base"):
            emit("ask", f"[core-dev conda-guard] `{prog}`이(가) conda env '{env or 'unknown'}'에서 "
                        "실행됩니다. 의도한 env가 맞는지 확인하세요 (다른 env: `conda run -n <env> ...`).")
            return


def run():
    """Entry point: any error, including a failed shell_words import, asks instead of failing open."""
    global shell_words
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        shell_words = importlib.import_module("shell_words")
        main()
    except Exception as exc:
        emit("ask", f"[core-dev conda-guard] guard 오류로 판정하지 못했습니다 "
                    f"({type(exc).__name__}: {exc}). 실행할 env를 직접 확인하세요.")


if __name__ == "__main__":
    run()
