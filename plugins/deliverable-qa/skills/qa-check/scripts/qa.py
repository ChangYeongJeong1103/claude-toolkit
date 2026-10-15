#!/usr/bin/env python3
"""Deterministic checks for a client deliverable draft against a rulebook folder.

  qa.py scan <draft> [--rulebook DIR] [--client NAME]     evidence as JSON
  qa.py calc <draft> --claims JSON [--rulebook DIR]       recompute metric claims from prose
  qa.py report <draft> --findings JSON [--notes JSON] [--rulebook DIR] [--client NAME]
                                                          validate findings, then print the Markdown report

The rulebook folder holds deliverable-rules.md, metric-definitions.md and clients.csv
(contract in the plugin README). Rule IDs and client names come only from that folder.
Nothing here writes to the draft.
"""
import argparse
import ast
import csv
import json
import operator
import re
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

RULEBOOK_FILES = ("deliverable-rules.md", "metric-definitions.md", "clients.csv")
RULE_RE = re.compile(r"^##\s+(\S+?)\.\s+(.+?)\s+\((Blocker|Warning)\)\s*$")
QUOTED_RE = re.compile(r'"([^"]+)"|“([^”]+)”')
THRESHOLD_RE = re.compile(r"fewer than ([\d,]+) households", re.I)
NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[÷×−+*/()]|[A-Za-z][A-Za-z\- ]*[A-Za-z]|[A-Za-z]")
OPS = {"÷": "/", "×": "*", "−": "-", "+": "+", "*": "*", "/": "/", "(": "(", ")": ")"}
BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
HOUSEHOLD_HEADER_RE = re.compile(r"household|reach|\bhh\b", re.I)


class QAError(Exception):
    pass


# ---------- small helpers ----------

def norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def to_decimal(text):
    """'$61,500.00' -> Decimal('61500.00'); '0.90%' -> Decimal('0.90'); '' or text -> None."""
    t = str(text).strip().replace("$", "").replace(",", "").rstrip("%").strip()
    try:
        return Decimal(t) if t else None
    except InvalidOperation:
        return None


def decimals_of(text):
    m = re.search(r"\.(\d+)", str(text).replace(",", ""))
    return len(m.group(1)) if m else 0


def word_re(term, suffix=False):
    return re.compile(r"(?<!\w)" + re.escape(term) + (r"\w*" if suffix else r"(?!\w)"), re.I)


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_tables(lines):
    """Pipe tables as {header_line, header, rows: [(line_no, cells)]}; line numbers are 1-based."""
    tables, i = [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            table = {"header_line": i + 1, "header": split_row(lines[i]), "rows": []}
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                table["rows"].append((i + 1, split_row(lines[i])))
                i += 1
            tables.append(table)
        else:
            i += 1
    return tables


def header_keys(cell):
    """'Reach (HH)' -> {'reach', 'hh'}; 'Cost per tune-in (CPT)' -> {'cost per tune-in', 'cpt'}."""
    keys = {norm(re.sub(r"\(.*?\)", "", cell))}
    keys.update(norm(x) for x in re.findall(r"\((.*?)\)", cell))
    return keys - {""}


# ---------- rulebook ----------

def parse_rules(text):
    rules, current = [], None
    for line in text.splitlines():
        m = RULE_RE.match(line)
        if m:
            current = {"id": m.group(1), "title": m.group(2), "severity": m.group(3), "text": ""}
            rules.append(current)
        elif line.startswith("#"):
            current = None
        elif current is not None and line.strip():
            current["text"] = (current["text"] + " " + line.strip()).strip()
    if not rules:
        raise QAError("no rules found in deliverable-rules.md; expected headings like '## R1. Title (Blocker)'")
    for rule in rules:
        rule["quoted_terms"] = [a or b for a, b in QUOTED_RE.findall(rule["text"])]
    return rules


def parse_metric(name, formula, shown):
    tokens = TOKEN_RE.findall(formula)
    derived = any(t in OPS for t in tokens)
    variables = []
    for t in tokens:
        if derived and t[0].isalpha() and norm(t) not in variables:
            variables.append(norm(t))
    m = re.search(r"(\d+)\s+decimal", shown)
    kind = "percent" if "percent" in shown.lower() else "currency" if "currency" in shown.lower() else "number"
    return {"name": name, "aliases": sorted(header_keys(name) | {norm(name)}),
            "formula": formula if derived else None, "variables": variables,
            "decimals": int(m.group(1)) if m else 0, "kind": kind}


def parse_metrics(text):
    lines = text.splitlines()
    for table in markdown_tables(lines):
        cols = [norm(h) for h in table["header"]]
        if {"metric", "formula", "shown as"} <= set(cols):
            i, f, s = cols.index("metric"), cols.index("formula"), cols.index("shown as")
            metrics = [parse_metric(c[i], c[f], c[s]) for _, c in table["rows"] if len(c) > max(i, f, s)]
            table_lines = {table["header_line"], table["header_line"] + 1, *(n for n, _ in table["rows"])}
            notes = [l.strip()[2:] for n, l in enumerate(lines, 1)
                     if n not in table_lines and l.strip().startswith("- ")]
            return metrics, notes
    raise QAError("metric-definitions.md has no table with the columns Metric | Formula | Shown as")


def parse_clients(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"display_name", "aliases", "status", "benchmark_consent"} - set(reader.fieldnames or [])
        if missing:
            raise QAError(f"clients.csv is missing columns: {', '.join(sorted(missing))}")
        rows = [{k: (r.get(k) or "").strip() for k in ("display_name", "aliases", "status", "benchmark_consent")}
                for r in reader]
        return [{"display_name": r["display_name"],
                 "aliases": [a.strip() for a in r["aliases"].split(";") if a.strip()],
                 "status": r["status"], "benchmark_consent": r["benchmark_consent"].lower()}
                for r in rows if r["display_name"]]


def load_rulebook(folder):
    folder = Path(folder)
    missing = [n for n in RULEBOOK_FILES if not (folder / n).is_file()]
    if missing:
        raise QAError(f"rulebook folder {folder} is missing: {', '.join(missing)}")
    rules_text = (folder / "deliverable-rules.md").read_text(encoding="utf-8-sig")
    metrics, notes = parse_metrics((folder / "metric-definitions.md").read_text(encoding="utf-8-sig"))
    m = THRESHOLD_RE.search(rules_text)
    return {"folder": str(folder), "rules": parse_rules(rules_text), "metrics": metrics, "metric_notes": notes,
            "clients": parse_clients(folder / "clients.csv"),
            "threshold_households": int(m.group(1).replace(",", "")) if m else None}


def resolve_rulebook(draft, given):
    if given:
        return Path(given)
    for candidate in (draft.parent.parent / "rulebook", draft.parent / "rulebook", Path.cwd() / "rulebook"):
        if candidate.is_dir():
            return candidate
    raise QAError("no rulebook folder found next to the drafts folder or in the current folder; pass --rulebook DIR")


def find_metric(metrics, name):
    key = norm(str(name))
    return next((m for m in metrics if key in m["aliases"]), None)


def compute(metric, values, decimals):
    """Evaluate the metric's formula with Decimal values, then round half-up to `decimals`."""
    env, expr = {}, []
    for tok in TOKEN_RE.findall(metric["formula"]):
        if tok in OPS:
            expr.append(OPS[tok])
        elif tok[0].isdigit():
            expr.append(tok)
        else:
            name = f"v{metric['variables'].index(norm(tok))}"
            env[name] = values[norm(tok)]
            expr.append(name)

    def ev(node):
        if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
            return BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            return env[node.id]
        raise QAError(f"unsupported formula: {metric['formula']}")

    try:
        value = ev(ast.parse(" ".join(expr), mode="eval").body)
    except SyntaxError:
        raise QAError(f"cannot parse the formula for {metric['name']}: {metric['formula']}")
    except (ZeroDivisionError, InvalidOperation):
        return None
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


# ---------- draft checks ----------

def addressed_client(clients, title, draft, wanted):
    def names(c):
        return [c["display_name"], *c["aliases"]]

    if wanted:
        hits = [c for c in clients if norm(wanted) in map(norm, names(c))]
        return (hits[0], "--client") if len(hits) == 1 else (None, f"--client {wanted!r} is not in clients.csv")
    hits = [c for c in clients if title and any(word_re(n).search(title) for n in names(c))]
    if len(hits) == 1:
        return hits[0], "title"
    slug = re.sub(r"[^a-z0-9]", "", draft.stem.lower())
    hits = [c for c in clients if any(re.sub(r"[^a-z0-9]", "", n.lower()) in slug for n in names(c))]
    if len(hits) == 1:
        return hits[0], "file name"
    return None, "could not tell which client this draft is for; ask the analyst and pass --client"


def client_mentions(lines, clients, own):
    out = []
    for c in clients:
        names = sorted({c["display_name"], *c["aliases"]}, key=len, reverse=True)
        for no, line in enumerate(lines, 1):
            taken = []
            for n in names:
                for m in word_re(n).finditer(line):
                    if any(m.start() < e and s < m.end() for s, e in taken):
                        continue
                    taken.append((m.start(), m.end()))
                    out.append({"line": no, "text": m.group(0), "client": c["display_name"],
                                "exact_case": m.group(0) == n, "own_client": c is own, "status": c["status"],
                                "benchmark_consent": c["benchmark_consent"]})
    return sorted(out, key=lambda x: x["line"])


def rule_term_hits(lines, rules):
    out = []
    for rule in rules:
        for term in rule["quoted_terms"]:
            pattern = word_re(term, suffix=True)
            for no, line in enumerate(lines, 1):
                out += [{"line": no, "rule": rule["id"], "term": term, "text": m.group(0)}
                        for m in pattern.finditer(line)]
    return sorted(out, key=lambda x: x["line"])


def table_checks(tables, metrics):
    checks, unchecked = [], []
    for table in tables:
        cols = [header_keys(h) for h in table["header"]]

        def col_for(keys):
            return next((i for i, k in enumerate(cols) if k & keys), None)

        for metric in metrics:
            mi = col_for(set(metric["aliases"])) if metric["formula"] else None
            if mi is None:
                continue
            var_cols = {v: col_for({v}) for v in metric["variables"]}
            missing = [v for v, c in var_cols.items() if c is None]
            if missing:
                unchecked.append({"line": table["header_line"], "metric": metric["name"], "missing_columns": missing})
                continue
            for line_no, cells in table["rows"]:
                if len(cells) <= max(mi, *var_cols.values()):
                    continue
                shown, values = cells[mi], {v: to_decimal(cells[c]) for v, c in var_cols.items()}
                if to_decimal(shown) is None or None in values.values():
                    continue
                computed = compute(metric, values, decimals_of(shown))
                checks.append({"line": line_no, "row": cells[0], "metric": metric["name"], "shown": shown,
                               "computed": None if computed is None else str(computed),
                               "match": None if computed is None else computed == to_decimal(shown),
                               "inputs": {v: cells[c] for v, c in var_cols.items()},
                               "shown_decimals": decimals_of(shown), "defined_decimals": metric["decimals"]})
    return checks, unchecked


def small_rows(tables, threshold):
    out = []
    for table in tables if threshold is not None else []:
        for i, header in enumerate(table["header"]):
            if not HOUSEHOLD_HEADER_RE.search(header):
                continue
            for line_no, cells in table["rows"]:
                # Household counts only: plain integers, not rates ("35.0%") or costs ("$0.12").
                is_count = i < len(cells) and re.fullmatch(r"\d[\d,]*", cells[i])
                if is_count and to_decimal(cells[i]) < threshold:
                    out.append({"line": line_no, "row": cells[0], "column": header, "value": cells[i],
                                "threshold": threshold})
    return out


def prose_metric_lines(lines, table_lines, derived):
    """Lines outside tables that name a derived metric and contain a number: claims to recompute with calc."""
    out = []
    for no, line in enumerate(lines, 1):
        if no in table_lines or not re.search(r"\d", line):
            continue
        found = [m["name"] for m in derived if any(word_re(a).search(line) for a in m["aliases"])]
        if found:
            out.append({"line": no, "metrics": found, "text": line.strip()})
    return out


def draft_title(lines):
    no = next((n for n, l in enumerate(lines, 1) if l.startswith("# ")), None)
    return no, (lines[no - 1][2:].strip() if no else None)


def scan(draft, rulebook, client=None):
    lines = draft.read_text(encoding="utf-8-sig").splitlines()
    title_no, title = draft_title(lines)
    own, found_by = addressed_client(rulebook["clients"], title, draft, client)
    tables = markdown_tables(lines)
    table_lines = {n for t in tables for n in (t["header_line"], t["header_line"] + 1, *(r for r, _ in t["rows"]))}
    checks, unchecked = table_checks(tables, rulebook["metrics"])
    derived = [m for m in rulebook["metrics"] if m["formula"]]
    return {
        "draft": str(draft),
        "rulebook": rulebook["folder"],
        "rules": rulebook["rules"],
        "metrics": rulebook["metrics"],
        "metric_notes": rulebook["metric_notes"],
        "threshold_households": rulebook["threshold_households"],
        "client": own and {"display_name": own["display_name"], "found_by": found_by},
        "client_error": None if own else found_by,
        "title": title_no and {"line": title_no, "text": title,
                               "has_display_name": bool(own) and own["display_name"] in title},
        "headings": [{"line": n, "level": len(l) - len(l.lstrip("#")), "text": l.lstrip("#").strip()}
                     for n, l in enumerate(lines, 1) if l.startswith("#")],
        "client_mentions": client_mentions(lines, rulebook["clients"], own),
        "rule_terms": rule_term_hits(lines, rulebook["rules"]),
        "table_checks": checks,
        "table_unchecked": unchecked,
        "prose_metric_lines": prose_metric_lines(lines, table_lines, derived),
        "small_rows": small_rows(tables, rulebook["threshold_households"]),
        "number_formats": [
            {"line": n, "text": tok, "kind": "percent" if tok.endswith("%") else "currency", "decimals": decimals_of(tok)}
            for n, l in enumerate(lines, 1) for tok in NUMBER_RE.findall(l) if tok.endswith("%") or tok.startswith("$")],
    }


def input_value(raw, shown_numbers):
    """A number shown in the draft, or a list of them that is summed. Returns (Decimal or None, error or None)."""
    parts = raw if isinstance(raw, list) else [raw]
    decimals = [to_decimal(p) for p in parts]
    bad = [p for p, d in zip(parts, decimals) if d is None or d not in shown_numbers]
    if not parts or bad:
        return None, f"{bad or raw} is not a number shown in the draft"
    return sum(decimals, Decimal(0)), None


def calc(draft, rulebook, claims):
    """Recompute prose claims: [{line, metric, inputs: {variable: number or [numbers to sum]}, shown}]."""
    lines = draft.read_text(encoding="utf-8-sig").splitlines()
    shown_numbers = {d for d in (to_decimal(t) for t in NUMBER_RE.findall("\n".join(lines))) if d is not None}
    results = []
    for claim in claims:
        r = {"line": claim.get("line"), "metric": claim.get("metric"), "shown": claim.get("shown"),
             "computed": None, "match": None, "errors": []}
        results.append(r)
        metric = find_metric(rulebook["metrics"], claim.get("metric", ""))
        if not metric or not metric["formula"]:
            r["errors"].append("not a derived metric in metric-definitions.md")
            continue
        r.update(metric=metric["name"], formula=metric["formula"], defined_decimals=metric["decimals"])
        inputs = {norm(k): v for k, v in (claim.get("inputs") or {}).items()}
        missing = [v for v in metric["variables"] if v not in inputs]
        if missing:
            r["errors"].append(f"missing inputs: {', '.join(missing)}")
            continue
        values = {}
        for v in metric["variables"]:
            values[v], error = input_value(inputs[v], shown_numbers)
            if error:
                r["errors"].append(f"input {v}: {error}")
        line_no, shown = claim.get("line"), str(claim.get("shown", ""))
        if not (isinstance(line_no, int) and 1 <= line_no <= len(lines)):
            r["errors"].append(f"line {line_no} is not in the draft")
        elif not shown or shown not in lines[line_no - 1]:
            r["errors"].append(f"shown value {shown!r} is not on line {line_no}")
        if None in values.values() or to_decimal(shown) is None:
            continue
        computed = compute(metric, values, decimals_of(shown))
        r["shown_decimals"] = decimals_of(shown)
        if computed is not None:
            r.update(computed=str(computed), match=computed == to_decimal(shown))
    return {"draft": str(draft), "claims": results}


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def missed_evidence(evidence, quotes_by_line):
    """Unambiguous violations from scan that no finding on the same line quotes."""
    def quoted(line, token):
        return any(token in q for q in quotes_by_line.get(line, []))

    missed = []
    for c in evidence["table_checks"]:
        if c["match"] is False and not quoted(c["line"], c["shown"].strip("$%")):
            missed.append(f"line {c['line']}: {c['metric']} is {c['shown']} but computes to {c['computed']}")
    for m in evidence["client_mentions"]:
        if (m["exact_case"] and not m["own_client"] and m["benchmark_consent"] != "yes"
                and not quoted(m["line"], m["text"])):
            missed.append(f"line {m['line']}: names another client, {m['text']!r}, without benchmark consent")
    for r in evidence["small_rows"]:
        if not quoted(r["line"], r["value"]):
            missed.append(f"line {r['line']}: {r['column']} {r['value']} is below the {r['threshold']}-household threshold")
    return [f"{m}; no finding on this line quotes it" for m in missed]


def report(draft, rulebook, findings, notes=(), client=None):
    """Validate the findings and render the report. Returns (markdown, []) or (None, errors)."""
    lines = draft.read_text(encoding="utf-8-sig").splitlines()
    rules = {r["id"]: r for r in rulebook["rules"]}
    errors, seen, valid = [], set(), []
    for i, f in enumerate(findings, 1):
        rule, line_no, quote = f.get("rule"), f.get("line"), str(f.get("quote") or "")
        problems = []
        if rule not in rules:
            problems.append(f"rule {rule!r} is not in the rulebook")
        if not (isinstance(line_no, int) and 1 <= line_no <= len(lines)):
            problems.append(f"line {line_no!r} is not in the draft")
        elif not quote.strip() or quote not in lines[line_no - 1]:
            problems.append(f"quote {quote!r} is not on line {line_no}")
        problems += [f"{k} is empty" for k in ("issue", "fix") if not str(f.get(k) or "").strip()]
        if problems:
            errors.append(f"finding {i}: " + "; ".join(problems))
        elif (rule, line_no, quote) not in seen:
            seen.add((rule, line_no, quote))
            valid.append({**f, "severity": rules[rule]["severity"], "title": rules[rule]["title"]})

    evidence = scan(draft, rulebook, client)
    if evidence["client"] is None:
        errors.append(evidence["client_error"])
    quotes_by_line = {}
    for f in valid:
        quotes_by_line.setdefault(f["line"], []).append(f["quote"])
    errors += missed_evidence(evidence, quotes_by_line)
    if errors:
        return None, errors

    by_line = lambda f: f["line"]  # noqa: E731
    blockers = sorted((f for f in valid if f["severity"] == "Blocker"), key=by_line)
    warnings = sorted((f for f in valid if f["severity"] == "Warning"), key=by_line)
    verdict = "READY TO SEND" if not blockers else "NOT READY TO SEND"
    who = evidence["client"]
    out = [f"# QA report — {draft.name}", "",
           f"**Verdict: {verdict}** — {plural(len(blockers), 'blocker')}, {plural(len(warnings), 'warning')}.",
           "",
           f"Client: {who['display_name']} (from the {who['found_by']}) · Rulebook: `{rulebook['folder']}`",
           ""]
    for heading, items in (("Blockers", blockers), ("Warnings", warnings)):
        out.append(f"## {heading} ({len(items)})")
        out += ["None."] if not items else []
        for n, f in enumerate(items, 1):
            out += [f"{n}. **{f['rule']} · {f['title']}** — `{draft.name}:{f['line']}`",
                    f"   > {f['quote']}",
                    f"   - Issue: {f['issue']}",
                    f"   - Suggested fix: {f['fix']}"]
        out.append("")
    if notes:
        out += ["## Rulebook notes", *(f"- {n}" for n in notes), ""]
    out.append("_The draft was not changed. Fixes are suggestions; the analyst decides._")
    return "\n".join(out), []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "calc", "report"):
        p = sub.add_parser(name)
        p.add_argument("draft")
        p.add_argument("--rulebook")
        if name in ("scan", "report"):
            p.add_argument("--client")
        if name == "calc":
            p.add_argument("--claims", required=True, help="JSON list of {line, metric, inputs, shown}")
        if name == "report":
            p.add_argument("--findings", required=True, help="JSON list of {rule, line, quote, issue, fix}")
            p.add_argument("--notes", default="[]", help="JSON list of rulebook notes (strings)")
    args = parser.parse_args(argv)
    try:
        draft = Path(args.draft)
        if draft.suffix.lower() != ".md":
            raise QAError("only Markdown drafts (.md) are supported; PowerPoint and PDF are out of scope")
        if not draft.is_file():
            raise QAError(f"draft not found: {draft}")
        rulebook = load_rulebook(resolve_rulebook(draft, args.rulebook))
        if args.cmd == "scan":
            result = scan(draft, rulebook, args.client)
        elif args.cmd == "calc":
            result = calc(draft, rulebook, json_list(args.claims, "--claims", dict))
        else:
            markdown, errors = report(draft, rulebook, json_list(args.findings, "--findings", dict),
                                      json_list(args.notes, "--notes", str), args.client)
            if errors:
                print(json.dumps({"errors": errors}, indent=1, ensure_ascii=False))
                return 1
            print(markdown)
            return 0
    except (QAError, json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        return 2
    except Exception as e:  # keep the JSON contract: the skill never sees a traceback
        print(json.dumps({"error": f"unexpected {type(e).__name__}: {e}"}))
        return 2
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0


def json_list(text, flag, item_type):
    value = json.loads(text)
    if not isinstance(value, list) or not all(isinstance(v, item_type) for v in value):
        kind = "objects" if item_type is dict else "strings"
        raise QAError(f"{flag} must be a JSON list of {kind}")
    return value


if __name__ == "__main__":
    sys.exit(main())
