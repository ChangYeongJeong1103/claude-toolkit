#!/usr/bin/env python3
"""PreToolUse hook: confirm before any Gmail send (send_message, reply, forward).

Sending is external and can't be undone, so this hook always asks and shows what is about to go out.
A send by draftId is denied: the hook can't see that draft's recipient or body, so it can't show a preview.
Any error still asks; an outbound action never fails open.
"""
import html
import json
import re
import sys

PREVIEW_CHARS = 300
TAG = "[campaign-analysis]"


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def plain(markup):
    """HTML → one line of plain text, for the preview."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())


def decide(event):
    tool = event.get("tool_name", "")
    tin = event.get("tool_input") or {}
    action = tool.rsplit("__", 1)[-1]  # send_message | reply | forward
    if action == "send_message" and tin.get("draftId"):
        return "deny", (f"{TAG} Sending by draftId hides the draft's recipient and body, so they can't be "
                        "confirmed. Send with explicit to, subject and htmlBody (or body) instead.")

    lines = [f"{TAG} About to send an email ({action}). Sending is immediate and can't be undone."]
    if tin.get("messageId"):
        lines.append(f"Message: {tin['messageId']}")
    if action == "reply" and not tin.get("to"):
        lines.append("To: the original sender" + (" and all recipients (reply all)" if tin.get("replyAll") else ""))
    for label in ("to", "cc", "bcc"):
        if tin.get(label):
            value = tin[label]
            lines.append(f"{label.capitalize()}: {', '.join(value) if isinstance(value, list) else value}")
    if tin.get("subject"):
        lines.append(f"Subject: {tin['subject']}")
    text = tin.get("body") or tin.get("forwardText") or plain(tin.get("htmlBody"))
    preview = text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "…"
    lines.append(f"Preview: {preview or '(no body)'}")
    lines.append("Approve only if the recipient and content are right.")
    return "ask", "\n".join(lines)


def main():
    try:
        decision, reason = decide(json.load(sys.stdin))
    except Exception as exc:  # unreadable request: still ask, never let the send through silently
        decision, reason = "ask", (f"{TAG} Could not read this send request ({type(exc).__name__}: {exc}). "
                                   "Check the recipient and content yourself before approving.")
    emit(decision, reason)


if __name__ == "__main__":
    main()
