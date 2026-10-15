#!/usr/bin/env python3
"""PreToolUse guard: ask the user before Edit/Write/MultiEdit/NotebookEdit touches a file under a `drafts/` folder.

`ask`, not deny: the QA plugin never changes drafts, but the analyst may still choose to.
Fails open: on any error it prints nothing and exits 0.
"""
import json
import sys
from pathlib import PurePath


def decision(event):
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not path or "drafts" not in (p.lower() for p in PurePath(path).parts[:-1]):
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": (
            f"deliverable-qa: {path} is a client draft. The QA check never changes drafts; "
            "approve only if the analyst asked for this edit."),
    }}


def main():
    try:
        out = decision(json.load(sys.stdin))
    except Exception:
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
