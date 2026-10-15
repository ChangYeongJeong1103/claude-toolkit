#!/usr/bin/env python3
"""Stop hook: before a policy answer ends the turn, check that it is grounded in the policy documents.

It runs its checks only when the current turn ran policy_context.py, and blocks (so Claude revises in the same turn)
when the answer
- cites a `file.md § heading` that doesn't exist in the policy folder,
- contains an email, Slack channel, or link that is not exactly one found in the documents, or
- doesn't match the script's coverage verdict: a covered question needs at least one valid citation; an uncovered
  one must say the documents don't cover it and give a contact.
It checks facts that can be checked deterministically; it doesn't judge meaning.
It blocks at most once per turn: if the revision still fails, it warns instead of looping.
On its own errors it doesn't block, it warns: a broken quality gate shouldn't stop every turn.
"""
import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # the plugin loads in place; keep __pycache__ out of it

TAG = "[policy-assistant]"
SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "policy-answers" / "scripts" / "policy_context.py"
# The text after "§" is captured in a lookahead, so it isn't consumed and a later citation on the same line
# is still found (a consuming capture swallowed the next citations, and they went unchecked).
# It stops at a backtick, so a backticked "approved-ai-tools.md § 4" followed by a Korean particle cites § 4,
# not "§ 4" plus the particle.
CITATION_RE = re.compile(r"(?i)([\w.-]+\.md)\s*§\s*(?=([^\n`]{0,200}))")
NOT_COVERED_RE = re.compile(r"(?i)(?:\bnot|n't|n’t)\s+(?:\w+\s+)?(?:cover|address|mention)\w*")
LINK_PUNCT = "*_`'\"<>()[]{};:.,!?"


def load_policy_context():
    spec = importlib.util.spec_from_file_location("policy_context", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_entries(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except ValueError:
                pass
    return entries


def content_of(entry):
    return (entry.get("message") or {}).get("content")


def is_prompt(entry):
    """A real user prompt: not a tool result, not meta, not stop-hook feedback."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = content_of(entry)
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return False
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return isinstance(content, str) and not content.lstrip().lower().startswith("stop hook feedback")


def option(words, name):
    for i, word in enumerate(words):
        if word.startswith(name + "="):
            return word.split("=", 1)[1]
        if word == name and i + 1 < len(words):
            return words[i + 1]
    return None


def policy_calls(event, entries):
    """(docs folder, question) for each policy_context.py call in the current turn only."""
    starts = [i for i, e in enumerate(entries) if is_prompt(e)]
    calls = []
    for entry in entries[starts[-1] + 1:] if starts else entries:
        if entry.get("type") != "assistant" or not isinstance(content_of(entry), list):
            continue
        for block in content_of(entry):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            command = str((block.get("input") or {}).get("command", ""))
            if "policy_context.py" not in command:
                continue
            try:
                words = shlex.split(command)
            except ValueError:
                words = command.split()
            folder = option(words, "--docs")
            if folder:
                folder = os.path.expanduser(os.path.expandvars(folder))
                calls.append((os.path.join(entry.get("cwd") or event.get("cwd") or "", folder),
                              option(words, "--question") or ""))
    return calls


def last_answer(event, entries):
    if event.get("last_assistant_message"):
        return event["last_assistant_message"]
    for entry in reversed(entries):  # older versions: fall back to the transcript
        if entry.get("type") == "assistant" and isinstance(content_of(entry), list):
            text = " ".join(b.get("text", "") for b in content_of(entry) if isinstance(b, dict) and b.get("type") == "text")
            if text.strip():
                return text
    return ""


def norm(text):
    return " ".join(re.sub(r"[`*_\"“”'’]", "", text).lower().split())


def heading_matches(heading, cited):
    """Accept `§ 1. Approved tools`, `§1`, `§ 1)`, and `§ Approved tools` for the heading "1. Approved tools",
    but not a real number with an invented title (`§ 1. Anything goes`)."""
    text, full = norm(cited), norm(heading)
    bare = re.sub(r"^\d+[.)]?\s*", "", full)
    if text.startswith(full) or (bare and text.startswith(bare)):
        return True
    number = re.match(r"\d+", full)
    if number and re.match(rf"{number.group()}(?!\d)", text):
        rest = text[len(number.group()):]
        if rest[:1] in (".", " "):  # a title follows the number: it must be the real one
            return bool(bare and rest.lstrip(" .").startswith(bare))
        # the citation ends right after the number, including before a non-ASCII particle (Korean attaches one)
        return not rest or rest[0] in ")],;:" or not rest[0].isascii()
    return False


def found_values(pattern, text):
    return {v.strip(LINK_PUNCT) for v in pattern.findall(text)}


def problems_in(answer, calls, pc):
    """Check the answer against the union of every policy folder the turn used."""
    docs, raw = {}, []
    for folder, _ in calls:
        try:
            for d in pc.load_docs(folder):
                docs.setdefault(d["name"].lower(), d)
            raw += [Path(folder, n).read_text(encoding="utf-8-sig") for n in os.listdir(folder)
                    if n.lower().endswith(".md")]
        except pc.DocsError:
            continue  # this call failed in the script too; check against the folders that worked
    if not docs:
        return []
    raw = "\n".join(raw)
    problems = []
    for name, cited in CITATION_RE.findall(answer):
        doc = docs.get(name.lower())
        if not doc:
            problems.append(f"cites {name}, which is not in the policy folder")
        elif not any(heading_matches(s["heading"], cited) for s in doc["sections"]):
            problems.append(f"cites `{name} § {cited[:40].strip()}`, but {name} has no such section")
    contacts = found_values(pc.EMAIL_RE, answer) | found_values(pc.CHANNEL_RE, answer)
    known = found_values(pc.EMAIL_RE, raw) | found_values(pc.CHANNEL_RE, raw) | found_values(pc.LINK_RE, raw)
    for value in sorted(contacts | found_values(pc.LINK_RE, answer)):
        if value not in known:
            problems.append(f"{value} is not a contact or link found in the policy documents")
    covered = any(pc.rank(question, list(docs.values()))[1] for _, question in calls)
    if covered and not CITATION_RE.search(answer):
        problems.append("the documents cover this question, but the answer has no citation (`file.md § heading`)")
    # A real citation doesn't make an uncovered question answerable, so this check applies with or without one.
    if not covered and not (NOT_COVERED_RE.search(answer) and contacts):
        problems.append("the documents don't cover this question: say so and give a contact from the documents")
    return problems


def run(event):
    entries = read_entries(event["transcript_path"])
    calls = policy_calls(event, entries)
    if not calls:
        return None  # not a policy answer: nothing to check
    problems = list(dict.fromkeys(problems_in(last_answer(event, entries), calls, load_policy_context())))
    if not problems:
        return None
    listed = "\n- " + "\n- ".join(problems)
    if event.get("stop_hook_active"):  # already revised once: warn instead of looping
        return {"systemMessage": f"{TAG} The grounding check still fails after one revision:{listed}\n"
                                 "Treat this answer as unverified."}
    return {"decision": "block", "reason": (
        f"{TAG} Grounding check failed:{listed}\n"
        "Revise the answer using only the policy_context.py output: cite sections as `file.md § heading`, use only "
        "contacts and links that appear in the documents, or say the documents don't cover it and give a contact.")}


def main():
    try:
        result = run(json.load(sys.stdin))
    except Exception as exc:  # fail open: warn instead of blocking every turn
        result = {"systemMessage": f"{TAG} The grounding check could not run ({type(exc).__name__}: {exc}). "
                                   "This answer was not verified against the policy documents."}
    if result:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
