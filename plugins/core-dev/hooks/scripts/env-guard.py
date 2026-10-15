#!/usr/bin/env python3
"""PreToolUse(Write|Edit|Bash|Monitor): block creating or modifying .env files."""
import importlib
import json
import os
import re
import sys

ENV_NAME_RE = re.compile(r"\.env(?:\..+)?")
ALLOWED = {".env.example", ".env.sample", ".env.template"}
IN_PLACE_RE = re.compile(r"^(?:-\w*i|--in-place)")
LAST_ARG_CMDS = {"cp", "ln", "install", "rsync"}    # destination = last argument
ALL_ARGS_CMDS = {"mv", "touch", "tee", "truncate"}  # every argument is written
IN_PLACE_CMDS = {"sed", "perl"}                     # only with -i
REASON = ("[core-dev env-guard] Creating or editing .env files is blocked. "
          "Ask the user to add the variables themselves, and put example values in .env.example.")
shell_words = None  # imported in run(), so a failed import also ends in `ask`


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def is_env_file(path):
    name = os.path.basename(path.strip("'\"").rstrip("/")).lower()  # macOS APFS is case-insensitive
    return bool(ENV_NAME_RE.fullmatch(name)) and name not in ALLOWED


def bash_writes_env(cmd):
    for argv, redirect_targets in shell_words.segments(cmd):
        if any(is_env_file(t) for t in redirect_targets):
            return True
        if not argv:
            continue
        prog = os.path.basename(argv[0])
        flags = [w for w in argv[1:] if w.startswith("-")]
        args = [w for w in argv[1:] if not w.startswith("-")]
        if prog in LAST_ARG_CMDS:
            targets = args[-1:]
        elif prog in ALL_ARGS_CMDS or (prog in IN_PLACE_CMDS and any(IN_PLACE_RE.match(f) for f in flags)):
            targets = args
        else:
            targets = []
        if any(is_env_file(t) for t in targets):
            return True
    return False


def main():
    data = json.load(sys.stdin)
    tool, tin = data.get("tool_name", ""), data.get("tool_input", {})
    if tool in ("Bash", "Monitor"):
        blocked = bash_writes_env(tin.get("command", ""))
    else:
        blocked = is_env_file(tin.get("file_path", ""))
    if blocked:
        emit("deny", REASON)


def run():
    """Entry point: any error, including a failed shell_words import, asks instead of failing open."""
    global shell_words
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        shell_words = importlib.import_module("shell_words")
        main()
    except Exception as exc:
        emit("ask", f"[core-dev env-guard] The guard hit an error and could not decide "
                    f"({type(exc).__name__}: {exc}). Check whether this command modifies a .env file.")


if __name__ == "__main__":
    run()
