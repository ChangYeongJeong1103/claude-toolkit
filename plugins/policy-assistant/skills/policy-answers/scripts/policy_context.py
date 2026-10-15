#!/usr/bin/env python3
"""Find the policy sections that answer a question, with each document's status as of a date.

The script owns everything deterministic: metadata, status (in effect / superseded / upcoming / ...),
section citations, retrieval, contacts, links, and missing references. The skill only presents and
cites this output; it never reads the documents itself. Standard library only (Python 3.8+).

Usage:
  policy_context.py --docs DIR --question "Can I use Cursor with client data?" [--as-of YYYY-MM-DD]
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y")
IN_EFFECT_WORDS = {"active", "approved", "in effect", "current"}
STOPWORDS = set("""
a an the and or but if then else of to in on at by for with from into about as is are was were be been being
do does did can could should would may might must will shall i me my we our you your it its this that these
those there here what which who whom whose when where why how use using used get got any some all no not yes
ok okay please company work ai
""".split())
TOP_SECTIONS = 6
# Contacts and links are ASCII. Python's \w also matches Hangul, so a Korean particle written right after a
# link was read as part of the link, and the grounding hook blocked a correct answer.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.ASCII)
CHANNEL_RE = re.compile(r"(?<![\w/#])#[a-z0-9][a-z0-9_-]+")
LINK_RE = re.compile(r"https?://[^\s)>\]\x80-\U0010ffff]+|\bgo/[\w-]+", re.ASCII)
MISSING_RE = re.compile(r"\[link TBD\]|\bTBD\b", re.I)
APPENDIX_RE = re.compile(r"\bAppendix\s+([A-Z])\b")
REPLACES_RE = re.compile(r"Section\s+(\d+)\s+of\s+(\S+\.md)", re.I)


class DocsError(Exception):
    """The folder can't be used at all (missing, or no Markdown files)."""


# ---------- parsing ----------

def parse_date(text):
    text = (text or "").strip().strip("*_ \"'").rstrip(".")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def split_front_matter(text):
    """Return (front matter dict, body). Front matter is `---` / key: value lines / `---` at the top."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    return meta, text[end + 4:].lstrip("\n")


def inline_meta(body):
    """`Status:`, `Effective:`, `Last updated:` written in the text before the first `##` heading."""
    head = body.split("\n## ", 1)[0].replace("*", "").replace("_", " ")
    found = {}
    for key, value in re.findall(r"(?i)\b(status|effective|last updated)\s*:\s*([^·|\n]+)", head):
        found.setdefault(key.lower(), value.strip())
    return found


def tokens(text):
    out = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 2 or word in STOPWORDS:  # drops the "s" of "what's" / "tool's"
            continue
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.append(word)
    return out


def sections_of(name, body):
    """Split a document on Markdown headings; each section is cited as `name § heading`."""
    sections, heading, lines = [], None, []

    def close():
        text = "\n".join(lines).strip()
        if heading is not None and text:
            sections.append({"doc": name, "heading": heading, "citation": f"{name} § {heading}", "text": text,
                             "tokens": tokens(text), "heading_tokens": set(tokens(heading))})

    for line in body.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if match:
            close()
            heading, lines = match.group(2), []
        else:
            lines.append(line)
    close()
    return sections


def load_docs(folder):
    if not os.path.isdir(folder):
        raise DocsError(f"not a folder: {folder}")
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".md"))
    if not names:
        raise DocsError(f"no Markdown (.md) files in {folder}")
    docs = []
    for name in names:
        with open(os.path.join(folder, name), encoding="utf-8-sig") as f:
            meta, body = split_front_matter(f.read())
        inline = inline_meta(body)
        title = meta.get("title") or next((m.group(1) for m in re.finditer(r"^#\s+(.*\S)", body, re.M)), name)
        effective_raw = (meta.get("effective") or inline.get("effective") or "").strip()
        docs.append({
            "name": name, "title": title, "body": body,
            "status_word": (meta.get("status") or inline.get("status") or "").strip().strip("\"'").lower() or None,
            "effective_raw": effective_raw or None,
            "effective": parse_date(effective_raw),
            "last_updated": parse_date(meta.get("last_updated") or meta.get("last updated") or inline.get("last updated")),
            "supersedes": meta.get("supersedes"), "superseded_by": meta.get("superseded_by"),
            "replaces": meta.get("replaces"),
            "sections": sections_of(name, body),
        })
    return docs


# ---------- status as of a date ----------

def base_status(d, as_of):
    word = d["status_word"]
    if word == "superseded":
        return "superseded"
    if d["effective_raw"] and d["effective"] is None:  # never guess: an unreadable date is not "in effect"
        return f"unreadable date ({d['effective_raw']})"
    if word and word not in IN_EFFECT_WORDS:  # Draft, Retired, Under review, ...
        return f"not in effect (status: {word})"
    if d["effective"] and d["effective"] > as_of:
        return "upcoming"
    if word in IN_EFFECT_WORDS or d["effective"]:
        return "in effect"
    return "dated (no status)" if d["last_updated"] else "reference only"


def successors(d, docs):
    """Documents that replace `d`, named by its `superseded_by` or by their own `supersedes`."""
    names = {os.path.basename(d["superseded_by"])} if d["superseded_by"] else set()
    names |= {o["name"] for o in docs if o["supersedes"] and os.path.basename(o["supersedes"]) == d["name"]}
    return [o for o in docs if o["name"] in names]


def assign_status(docs, as_of):
    """Set doc["status"]: superseded, upcoming, in effect, not in effect, unreadable date, dated, or reference only."""
    by_name = {d["name"]: d for d in docs}
    for d in docs:
        d["status"] = base_status(d, as_of)
    # A document marked Superseded still applied before its replacement took effect. If any replacement date
    # is unknown, it stays superseded rather than guessing.
    for d in docs:
        if d["status"] != "superseded" or not d["effective"]:
            continue
        later = [o["effective"] for o in successors(d, docs)]
        if later and all(later) and as_of < min(later):
            d["status"] = "upcoming" if d["effective"] > as_of else "in effect"
            d["replaced_on"] = min(later)
    # Only a document that is itself in effect can supersede another (an undated draft can't).
    live = {d["name"] for d in docs if d["status"] == "in effect"}
    superseded = set()
    for d in docs:
        if d["name"] in live and d["supersedes"]:
            superseded.add(os.path.basename(d["supersedes"]))
        if d["superseded_by"] and os.path.basename(d["superseded_by"]) in live:
            superseded.add(d["name"])
    for name in superseded & set(by_name):
        by_name[name]["status"] = "superseded"

    # Section-level replacement, e.g. "replaces: Section 4 of approved-ai-tools.md".
    for d in docs:
        match = REPLACES_RE.search(d["replaces"] or "")
        target = by_name.get(os.path.basename(match.group(2))) if match else None
        if not target or d["status"] not in ("in effect", "upcoming"):
            continue
        for s in target["sections"]:
            if not re.match(rf"{match.group(1)}[.\s]", s["heading"]) or s.get("replaced"):
                continue  # an in-effect replacement is never overwritten by a later, upcoming one
            if d["status"] == "upcoming":
                s["note"] = f"changes on {d['effective']}: replaced by {d['name']}"
            else:
                s["note"] = f"replaced by {d['name']} (effective {d['effective']}); do not use as the answer"
                s["replaced"] = True


def doc_dates(d):
    if d["effective"]:
        return f"effective {d['effective']}"
    if d["last_updated"]:
        return f"last updated {d['last_updated']}"
    return "no date"


# ---------- retrieval and extracted facts ----------

def rank(question, docs):
    """Score every section by question-term overlap; heading matches count double."""
    qterms = list(dict.fromkeys(tokens(question)))
    scored = []
    for d in docs:
        for s in d["sections"]:
            body = Counter(s["tokens"])
            matched = {t for t in qterms if body[t] or t in s["heading_tokens"]}
            if matched:
                score = sum(min(body[t], 3) for t in qterms) + 2 * sum(t in s["heading_tokens"] for t in qterms)
                scored.append((len(matched), score, s))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]["citation"]))
    best = scored[0][0] if scored else 0
    covered = bool(qterms) and best >= min(2, len(qterms))
    return qterms, covered, scored[:TOP_SECTIONS]


def extract(docs):
    contacts, links, missing = defaultdict(list), defaultdict(list), []
    headings = {s["heading"] for d in docs for s in d["sections"]}
    for d in docs:
        for s in d["sections"]:
            for value in EMAIL_RE.findall(s["text"]) + CHANNEL_RE.findall(s["text"]):
                contacts[value].append((s["citation"], d["status"]))
            for value in LINK_RE.findall(s["text"]):
                links[value.rstrip(".,")].append((s["citation"], d["status"]))
            for value in MISSING_RE.findall(s["text"]):
                missing.append((s["citation"], f'"{value}" (no link in the document)'))
            for letter in APPENDIX_RE.findall(s["text"]):
                if not any(h.lower().startswith(f"appendix {letter.lower()}") for h in headings):
                    missing.append((s["citation"], f'"Appendix {letter}" is referenced but not in the folder'))
    return contacts, links, missing


def build_context(folder, question, as_of):
    docs = load_docs(folder)
    assign_status(docs, as_of)
    qterms, covered, top = rank(question, docs)
    chosen = [s for _, _, s in top]
    for d in docs:  # precedence rules and contact sections of in-effect documents always travel with the answer
        if d["status"] == "in effect":
            chosen += [s for s in d["sections"] if s["heading_tokens"] & {"precedence", "contact"} and s not in chosen]
    status = {d["name"]: d["status"] for d in docs}
    upcoming = [d for d in docs if d["status"] == "upcoming"
                and any(s["doc"] == d["name"] or d["name"] in s.get("note", "") for s in chosen)]
    contacts, links, missing = extract(docs)
    return {"question": question, "as_of": as_of, "folder": folder, "docs": docs, "status": status,
            "terms": qterms, "covered": covered, "sections": chosen, "upcoming": upcoming,
            "contacts": contacts, "links": links, "missing": missing}


# ---------- rendering ----------

def render(ctx, as_of_given):
    out = ["## Policy context", f"Question: {ctx['question']}",
           f"As of: {ctx['as_of']} ({'set with --as-of' if as_of_given else 'today'})",
           f"Folder: `{ctx['folder']}` ({len(ctx['docs'])} documents)", "",
           "### Documents", "| Document | Status | Date | Notes |", "|---|---|---|---|"]
    for d in ctx["docs"]:
        notes = "; ".join(x for x in (
            d["supersedes"] and f"supersedes {d['supersedes']}",
            d["superseded_by"] and f"superseded by {d['superseded_by']}"
            + (f" from {d['replaced_on']}" if d.get("replaced_on") else ""),
            d["replaces"] and f"replaces {d['replaces']}") if x)
        out.append(f"| {d['name']} | {d['status']} | {doc_dates(d)} | {notes} |")

    out += ["", "### Coverage"]
    if ctx["covered"]:
        out.append(f"Covered: the sections below match the question terms ({', '.join(ctx['terms'])}).")
    else:
        out.append("NOT COVERED: no section matches the question well enough. Say so and give a contact below.")

    out += ["", "### Relevant sections"]
    for s in ctx["sections"]:
        label = ctx["status"][s["doc"]] + (f"; {s['note']}" if s.get("note") else "")
        out += [f"#### {s['citation']} [{label}]", *("> " + line for line in s["text"].splitlines()), ""]

    if ctx["upcoming"]:
        out.append("### Upcoming changes (not in effect yet; mention, don't apply)")
        out += [f"- {d['name']}: effective {d['effective']}" + (f"; replaces {d['replaces']}" if d["replaces"] else "")
                for d in ctx["upcoming"]]
        out.append("")

    out += ["### Contacts found in the documents", "| Contact | Where | Source status |", "|---|---|---|"]
    for value, where in sorted(ctx["contacts"].items()):
        out.append(f"| {value} | {'; '.join(c for c, _ in where)} | {', '.join(sorted({st for _, st in where}))} |")
    if ctx["links"]:
        out += ["", "### Links found in the documents"]
        out += [f"- {v} ({'; '.join(c for c, _ in where)}; {', '.join(sorted({st for _, st in where}))})"
                for v, where in sorted(ctx["links"].items())]
    if ctx["missing"]:
        out += ["", "### Missing references (say they are missing; never fill them in)"]
        out += [f"- {citation}: {what}" for citation, what in ctx["missing"]]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Policy sections and facts for one question.")
    parser.add_argument("--docs", required=True, help="folder of Markdown policy documents")
    parser.add_argument("--question", required=True)
    parser.add_argument("--as-of", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                        help="judge 'in effect' as of this date (YYYY-MM-DD); default today")
    args = parser.parse_args(argv)
    try:
        ctx = build_context(os.path.expanduser(args.docs), args.question, args.as_of or date.today())
    except (DocsError, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(render(ctx, args.as_of is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
