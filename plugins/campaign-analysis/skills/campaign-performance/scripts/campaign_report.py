#!/usr/bin/env python3
"""Answer account-manager questions about a campaign_performance CSV export.

Every number in an answer is computed here; the skill only presents this output.
Standard library only (Python 3.8+).

Usage:
  campaign_report.py campaign        --csv FILE --campaign "<id or name>"
  campaign_report.py platforms       --csv FILE [--period last-week|all]
  campaign_report.py underperformers --csv FILE [--period last-week|all]
  campaign_report.py exclusions      --csv FILE
Every command also takes --format md|html (html is the same output as an email body) and,
with html, --question TEXT (shown at the top of the email).
"""
import argparse
import csv
import html
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

REQUIRED = ("campaign_id", "campaign_name", "date", "impressions", "tune_ins",
            "spend", "platform", "content_type")
PLATFORMS = {"streaming": "Streaming", "live_tv": "Live TV"}
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")
METRICS = ("impressions", "tune_ins", "spend", "tune_in_rate", "cpt", "cpm")
FLAG_MULTIPLIER = 1.5
THOUSANDS_RE = re.compile(r"-?\d{1,3}(,\d{3})+(\.\d+)?")  # "1,234.50" yes; "200,50" and "1,2,3" no


class DataError(Exception):
    """The file can't be analysed at all (unreadable, a required column missing, or no usable rows)."""


# ---------- load, normalize, validate ----------

def load(path):
    """Return [(line_number, raw_row)] with stripped, lower-cased column names."""
    path = os.path.expanduser(path)  # the skill quotes the path, so the shell never expands "~"
    try:
        f = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise DataError(f"cannot open {path}: {exc.strerror}") from None
    with f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames or []]
        missing = [c for c in REQUIRED if c not in reader.fieldnames]
        if missing:
            raise DataError("missing required column(s): " + ", ".join(missing))
        return [(reader.line_num, row) for row in reader]


def parse_date(text):
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_number(text, field):
    """Return (value, problem). Spend may carry `$`; commas count only as thousands separators."""
    s = (text or "").strip()
    if field == "spend":
        s = s.replace("$", "")
    if not s:
        return None, ("missing value", f"missing {field}")
    invalid = ("invalid value", f"invalid {field} {text!r}")
    if "," in s:
        if not THOUSANDS_RE.fullmatch(s):  # e.g. a decimal comma: "200,50" must not become 20050
            return None, invalid
        s = s.replace(",", "")
    try:
        value = float(s)
    except ValueError:
        return None, invalid
    if not math.isfinite(value) or (field != "spend" and value != int(value)):  # nan/inf would poison totals
        return None, invalid
    return (value if field == "spend" else int(value)), None


def normalize_platform(text):
    key = "_".join((text or "").strip().lower().replace("-", " ").split())
    return key if key in PLATFORMS else None


def parse_row(line, raw):
    """Return (row, problems); problems is a list of (reason, detail)."""
    problems = []
    row = {
        "line": line,
        "campaign_id": (raw.get("campaign_id") or "").strip(),
        "campaign_name": " ".join((raw.get("campaign_name") or "").split()),
        "content_type": (raw.get("content_type") or "").strip().lower(),
        "date": parse_date(raw.get("date")),
        "platform": normalize_platform(raw.get("platform")),
    }
    for field in ("campaign_id", "campaign_name", "content_type"):
        if not row[field]:
            problems.append(("missing value", f"missing {field}"))
    for field, label in (("date", "unreadable date"), ("platform", "unknown platform")):
        text = (raw.get(field) or "").strip()
        if row[field] is None:
            problems.append(("missing value", f"missing {field}") if not text else (label, f"{label} {text!r}"))
    for field in ("impressions", "tune_ins", "spend"):
        row[field], problem = parse_number(raw.get(field), field)
        if problem:
            problems.append(problem)
    if not problems:
        negative = [f for f in ("impressions", "tune_ins", "spend") if row[f] < 0]
        if negative:
            problems.append(("negative value", "negative " + ", ".join(negative)))
        elif row["impressions"] == 0:
            problems.append(("zero impressions", "zero impressions"))
        elif row["tune_ins"] > row["impressions"]:
            problems.append(("tune-ins exceed impressions",
                             f"tune_ins {row['tune_ins']:,} > impressions {row['impressions']:,}"))
    return row, problems


def exclusion(row, raw, reason, detail):
    return {
        "line": row["line"],
        "campaign_id": row["campaign_id"] or "?",
        "campaign_name": row["campaign_name"],
        "day": row["date"],
        "date": row["date"].isoformat() if row["date"] else (raw.get("date") or "").strip(),
        "platform": PLATFORMS.get(row["platform"]) or (raw.get("platform") or "").strip(),
        "reason": reason,
        "detail": detail,
    }


def clean(raw_rows):
    """Return (valid rows, exclusions, lines of exact duplicates removed)."""
    parsed, exclusions = [], []
    for line, raw in raw_rows:
        row, problems = parse_row(line, raw)
        if problems:
            exclusions.append(exclusion(row, raw, problems[0][0], "; ".join(d for _, d in problems)))
        else:
            parsed.append((row, raw))

    groups = defaultdict(list)
    for row, raw in parsed:
        groups[(row["campaign_id"], row["date"], row["platform"])].append((row, raw))
    valid, duplicates = [], []
    for (cid, day, platform), group in groups.items():
        values = {(r["impressions"], r["tune_ins"], round(r["spend"], 2), r["content_type"]) for r, _ in group}
        if len(values) == 1:  # exact duplicates: keep the first copy
            valid.append(group[0][0])
            duplicates.extend(r["line"] for r, _ in group[1:])
        else:  # same key, different values: we can't tell which copy is right
            detail = f"{len(group)} rows for {cid} {day} {PLATFORMS[platform]} with different values"
            exclusions.extend(exclusion(r, raw, "conflicting duplicate", detail) for r, raw in group)
    valid.sort(key=lambda r: r["line"])
    exclusions.sort(key=lambda e: e["line"])
    return valid, exclusions, sorted(duplicates)


class Dataset:
    def __init__(self, path):
        raw_rows = load(path)
        self.path = path
        self.total_rows = len(raw_rows)
        self.rows, self.exclusions, self.duplicates = clean(raw_rows)
        # An all-excluded file still loads, so the `exclusions` command can explain it; reports check self.rows.
        dates = [r["date"] for r in self.rows]
        self.start, self.end = (min(dates), max(dates)) if dates else (None, None)
        names = defaultdict(Counter)
        for r in self.rows:
            names[r["campaign_id"]][r["campaign_name"]] += 1
        self.names = {cid: c.most_common(1)[0][0] for cid, c in sorted(names.items())}
        self.excluded_names = {e["campaign_id"]: e["campaign_name"] for e in self.exclusions
                               if e["campaign_id"] != "?" and e["campaign_id"] not in self.names}


# ---------- periods and metrics ----------

def last_complete_week(end):
    """Mon–Sun week ending on the latest Sunday on or before `end`."""
    sunday = end - timedelta(days=(end.weekday() + 1) % 7)
    return sunday - timedelta(days=6), sunday


def period_range(ds, period):
    return last_complete_week(ds.end) if period == "last-week" else (ds.start, ds.end)


def in_range(rows, start, end):
    return [r for r in rows if start <= r["date"] <= end]


def ratio(numerator, denominator, scale=1.0):
    return numerator * scale / denominator if denominator else None


def pct_change(new, old):
    return None if new is None or not old else (new - old) / old * 100


def diff(a, b):
    return None if a is None or b is None else a - b


def totals(rows):
    """Sums and metrics for a set of rows, or None when there are no rows ("no data", never zeros)."""
    if not rows:
        return None
    imp = sum(r["impressions"] for r in rows)
    ti = sum(r["tune_ins"] for r in rows)
    sp = sum(r["spend"] for r in rows)
    return {"days": len({r["date"] for r in rows}), "impressions": imp, "tune_ins": ti, "spend": sp,
            "tune_in_rate": ratio(ti, imp, 100), "cpt": ratio(sp, ti), "cpm": ratio(sp, imp, 1000)}


def exclusion_summary(ds, start, end, campaign_id=None):
    in_scope = [e for e in ds.exclusions
                if (campaign_id is None or e["campaign_id"] == campaign_id)
                and (e["day"] is None or start <= e["day"] <= end)]
    return {"total_rows": ds.total_rows, "excluded": len(ds.exclusions),
            "by_reason": Counter(e["reason"] for e in ds.exclusions).most_common(),
            "duplicates_removed": len(ds.duplicates), "in_scope": in_scope}


# ---------- the three questions ----------

def words_match(query, text):
    """Every query word starts a word in text: "fall thrill" matches "Fall Thriller"; "a" does not match "Beta"."""
    q_words = re.findall(r"[a-z0-9]+", query.lower())
    t_words = re.findall(r"[a-z0-9]+", text.lower())
    return bool(q_words) and all(any(t.startswith(q) for t in t_words) for q in q_words)


def resolve_campaign(ds, query):
    """Return (campaign_id or None, candidates [(id, name)], partial). Fully excluded campaigns still resolve."""
    q = " ".join(query.split()).lower()
    known = dict(ds.excluded_names, **ds.names)
    exact = [cid for cid, name in known.items() if q in (cid.lower(), name.lower())]
    matches = exact or [cid for cid, name in known.items() if words_match(q, name) or words_match(q, cid)]
    if len(matches) == 1:
        return matches[0], [], not exact
    return None, [(cid, known[cid]) for cid in sorted(matches or ds.names)], False


def campaign_report(ds, query):
    """Q1: one campaign, last complete week vs the week before, per platform and combined."""
    cid, candidates, partial = resolve_campaign(ds, query)
    if cid is None:
        return {"query": query, "campaign_id": None, "candidates": candidates}
    if cid not in ds.names:  # the campaign exists in the file, but every row of it was excluded
        return {"query": query, "campaign_id": cid, "campaign_name": ds.excluded_names[cid],
                "all_rows_excluded": [e for e in ds.exclusions if e["campaign_id"] == cid]}
    last = last_complete_week(ds.end)
    prev = (last[0] - timedelta(days=7), last[1] - timedelta(days=7))
    rows = [r for r in ds.rows if r["campaign_id"] == cid]

    def compare(subset):
        before, after = totals(in_range(subset, *prev)), totals(in_range(subset, *last))
        return {"previous": before, "last": after,
                "change": {m: pct_change(after and after[m], before and before[m]) for m in METRICS}}

    return {
        "query": query, "partial_match": partial,
        "campaign_id": cid, "campaign_name": ds.names[cid], "last_week": last, "previous_week": prev,
        "platforms": {p: compare([r for r in rows if r["platform"] == p])
                      for p in PLATFORMS if any(r["platform"] == p for r in rows)},
        "combined": compare(rows),
        "zero_tune_in_days": [r for r in in_range(rows, prev[0], last[1]) if r["tune_ins"] == 0 and r["spend"] > 0],
        "exclusions": exclusion_summary(ds, prev[0], last[1], cid),
    }


def platform_report(ds, period):
    """Q2: streaming vs live TV over the period."""
    start, end = period_range(ds, period)
    rows = in_range(ds.rows, start, end)
    per = {}
    for p in PLATFORMS:
        subset = [r for r in rows if r["platform"] == p]
        per[p] = totals(subset)
        if per[p]:
            per[p]["campaigns"] = len({r["campaign_id"] for r in subset})
    s, l = per["streaming"], per["live_tv"]
    difference = None
    if s and l:
        difference = {"tune_in_rate_pp": diff(s["tune_in_rate"], l["tune_in_rate"]),
                      "cpt": diff(s["cpt"], l["cpt"]), "cpt_pct": pct_change(s["cpt"], l["cpt"]),
                      "cpm": diff(s["cpm"], l["cpm"]), "cpm_pct": pct_change(s["cpm"], l["cpm"])}
    return {"period": period, "start": start, "end": end, "platforms": per, "difference": difference,
            "exclusions": exclusion_summary(ds, start, end)}


def underperformer_report(ds, period):
    """Q3: campaigns whose cost per tune-in is >= 1.5x their platform median, and the spend at risk."""
    start, end = period_range(ds, period)
    rows = in_range(ds.rows, start, end)
    segments = defaultdict(list)
    for r in rows:
        segments[(r["campaign_id"], r["platform"])].append(r)
    seg_totals = {key: totals(group) for key, group in segments.items()}

    platforms, flagged = {}, []
    for p in PLATFORMS:
        segs = {key: t for key, t in sorted(seg_totals.items()) if key[1] == p}
        if not segs:
            continue
        cpts = [t["cpt"] for t in segs.values() if t["cpt"] is not None]  # zero-tune-in campaigns stay out
        median = statistics.median(cpts) if cpts else None
        threshold = median * FLAG_MULTIPLIER if median is not None else None
        platforms[p] = {"campaigns": len(segs), "median_cpt": median, "threshold": threshold}
        for (cid, _), t in segs.items():
            if t["cpt"] is None and t["spend"] > 0:
                why = "spend with no tune-ins"
            elif threshold is not None and t["cpt"] is not None and (
                    t["cpt"] > threshold or math.isclose(t["cpt"], threshold, rel_tol=1e-9)):  # float-safe ">="
                why = f"cost per tune-in at or above {FLAG_MULTIPLIER}x median"
            else:
                continue
            flagged.append(dict(t, campaign_id=cid, campaign_name=ds.names[cid], platform=p, why=why))

    flagged_keys = {(f["campaign_id"], f["platform"]) for f in flagged}
    zero_days = [r for r in rows if r["tune_ins"] == 0 and r["spend"] > 0
                 and (r["campaign_id"], r["platform"]) not in flagged_keys]
    flagged_spend = sum(f["spend"] for f in flagged)
    zero_day_spend = sum(r["spend"] for r in zero_days)
    period_spend = sum(r["spend"] for r in rows)
    waste = flagged_spend + zero_day_spend
    return {"period": period, "start": start, "end": end, "platforms": platforms, "flagged": flagged,
            "waste": {"flagged": flagged_spend, "zero_tune_in_days": zero_day_spend, "zero_tune_in_rows": zero_days,
                      "total": waste, "period_spend": period_spend, "pct_of_spend": ratio(waste, period_spend, 100)},
            "exclusions": exclusion_summary(ds, start, end)}


# ---------- rendering (markdown) ----------

def money(x):
    return "N/A" if x is None else f"${x:,.2f}"


def signed_money(x):
    return "N/A" if x is None else f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"


def rate(x):
    return "N/A" if x is None else f"{x:.2f}%"


def change(x):
    return "N/A" if x is None else f"{x:+.1f}%"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def header(ds):
    span = f"covering {ds.start} to {ds.end}" if ds.rows else "no usable rows"
    return f"Data: `{os.path.basename(ds.path)}`: {ds.total_rows} rows, {len(ds.rows)} used, {span}."


def period_line(report):
    if report["period"] == "last-week":
        return f"Period: last week, {report['start']} to {report['end']} (latest complete Mon–Sun week in the data)."
    return f"Period: all data, {report['start']} to {report['end']}."


def metric_cells(t):
    if t is None:
        return ["no data", "", "", "", "", "", ""]
    return [t["days"], f"{t['impressions']:,}", f"{t['tune_ins']:,}", money(t["spend"]),
            rate(t["tune_in_rate"]), money(t["cpt"]), money(t["cpm"])]


def exclusion_line(summary):
    reasons = ", ".join(f"{reason}: {n}" for reason, n in summary["by_reason"]) or "none"
    line = (f"Excluded rows: {summary['excluded']} of {summary['total_rows']} ({reasons}); "
            f"{summary['duplicates_removed']} exact duplicates removed.")
    if summary["in_scope"]:
        hits = "; ".join(f"{e['campaign_id']} {e['platform']} {e['date']} ({e['reason']})" for e in summary["in_scope"])
        return line + f" Affecting this answer: {hits}. Ask for the exclusions list for row-level detail."
    return line + " None of them fall in this answer's scope."


def render_campaign(ds, report):
    if report["campaign_id"] is None:
        return (f"No single campaign matches \"{report['query']}\". Pick one of these:\n\n"
                + table(["Campaign ID", "Name"], [list(c) for c in report["candidates"]]))
    if "all_rows_excluded" in report:
        n = len(report["all_rows_excluded"])
        return "\n".join([f"## {report['campaign_id']}: {report['campaign_name']}", header(ds),
                          f"This campaign has no usable rows: all {n} of its rows were excluded. "
                          "Ask for the exclusions list for row-level detail."])
    last, prev = report["last_week"], report["previous_week"]
    body = []
    labelled = [(PLATFORMS[p], c) for p, c in report["platforms"].items()] + [("All platforms", report["combined"])]
    for label, c in labelled:
        body.append([label, "Previous week"] + metric_cells(c["previous"]))
        body.append([label, "Last week"] + metric_cells(c["last"]))
        ch = c["change"]
        body.append([label, "Change", ""] + [change(ch[m]) for m in METRICS])
    out = [f"## {report['campaign_id']}: {report['campaign_name']}", header(ds)]
    if report["partial_match"]:
        out.append(f"Matched \"{report['query']}\" to {report['campaign_id']} ({report['campaign_name']}) by name.")
    out += [f"Last week = {last[0]} to {last[1]} (latest complete Mon–Sun week in the data), "
           f"compared with {prev[0]} to {prev[1]}.", "",
           table(["Platform", "Week", "Days", "Impressions", "Tune-ins", "Spend", "Tune-in rate",
                  "Cost per tune-in", "CPM"], body), ""]
    if report["zero_tune_in_days"]:
        days = "; ".join(f"{r['date']} {PLATFORMS[r['platform']]} ({money(r['spend'])} spend)"
                         for r in report["zero_tune_in_days"])
        out.append(f"No tune-ins (spend counted as waste): {days}.")
    out.append(exclusion_line(report["exclusions"]))
    return "\n".join(out)


def render_platforms(ds, report):
    body = []
    for p, label in PLATFORMS.items():
        t = report["platforms"][p]
        body.append([label, t["campaigns"] if t else "no data"] + (metric_cells(t)[1:] if t else [""] * 6))
    out = ["## Streaming vs Live TV", header(ds), period_line(report), "",
           table(["Platform", "Campaigns", "Impressions", "Tune-ins", "Spend", "Tune-in rate",
                  "Cost per tune-in", "CPM"], body), ""]
    d = report["difference"]
    if d:
        pp = "N/A" if d["tune_in_rate_pp"] is None else f"{d['tune_in_rate_pp']:+.2f} pp"
        out.append(f"Difference (Streaming minus Live TV): tune-in rate {pp}; cost per tune-in "
                   f"{signed_money(d['cpt'])} ({change(d['cpt_pct'])}); CPM {signed_money(d['cpm'])} "
                   f"({change(d['cpm_pct'])}).")
    out.append(exclusion_line(report["exclusions"]))
    return "\n".join(out)


def render_underperformers(ds, report):
    out = ["## Underperforming campaigns", header(ds), period_line(report),
           f"Rule: a campaign is underperforming when its cost per tune-in (total spend ÷ total tune-ins for "
           f"the period) is at least {FLAG_MULTIPLIER}x the median of campaigns on the same platform. Campaigns "
           f"with spend but no tune-ins are always flagged. Potential waste = spend of flagged campaigns + "
           f"spend on zero-tune-in days in other campaigns.", ""]
    out.append(table(["Platform", "Campaigns", "Median cost per tune-in", f"Flag threshold ({FLAG_MULTIPLIER}x)"],
                     [[PLATFORMS[p], v["campaigns"], money(v["median_cpt"]), money(v["threshold"])]
                      for p, v in report["platforms"].items()]))
    out.append("")
    if report["flagged"]:
        out.append(table(["Campaign", "Platform", "Spend", "Tune-ins", "Cost per tune-in", "Why"],
                         [[f"{f['campaign_id']} {f['campaign_name']}", PLATFORMS[f["platform"]], money(f["spend"]),
                           f"{f['tune_ins']:,}", money(f["cpt"]), f["why"]] for f in report["flagged"]]))
    else:
        out.append("No campaign meets the rule in this period.")
    w = report["waste"]
    out += ["", f"Potential waste: {money(w['total'])} of {money(w['period_spend'])} total spend "
                f"({rate(w['pct_of_spend'])}).",
            f"- Flagged campaigns: {money(w['flagged'])}",
            f"- Zero-tune-in days in other campaigns: {money(w['zero_tune_in_days'])}", "",
            exclusion_line(report["exclusions"])]
    return "\n".join(out)


def render_exclusions(ds):
    rows = [[e["line"], e["campaign_id"], e["date"], e["platform"], e["reason"], e["detail"]] for e in ds.exclusions]
    dupes = ", ".join(str(n) for n in ds.duplicates) or "none"
    return "\n".join([f"## Excluded rows: {len(ds.exclusions)} of {ds.total_rows}", header(ds), "",
                      table(["Line", "Campaign", "Date", "Platform", "Reason", "Detail"], rows), "",
                      f"Exact duplicates removed (first copy kept), lines: {dupes}."])


# ---------- email format (HTML) ----------

def inline_html(text):
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text, quote=False))


def md_to_html(text, question=None):
    """Convert this script's own Markdown output to HTML for an email body.

    Line by line: `## ` headings, pipe tables, `- ` list items, paragraphs. Text is only escaped,
    never changed, so every number is identical to the Markdown answer.
    """
    out, block, kind = [], [], None

    def flush():
        if kind == "table":
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in block
                    if set(r.replace("|", "").strip()) - {"-"}]  # drop the |---|---| separator row
            out.append('<table border="1" cellpadding="4" cellspacing="0">')
            out.append("<tr>" + "".join(f"<th>{inline_html(c)}</th>" for c in rows[0]) + "</tr>")
            out.extend("<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append("</table>")
        elif kind == "list":
            out.append("<ul>" + "".join(f"<li>{inline_html(item)}</li>" for item in block) + "</ul>")
        block.clear()

    if question:
        out.append(f"<p><strong>Question:</strong> {inline_html(question)}</p>")
    for line in text.splitlines():
        line_kind = "table" if line.startswith("|") else "list" if line.startswith("- ") else None
        if line_kind != kind:
            flush()
            kind = line_kind
        if kind == "table":
            block.append(line)
        elif kind == "list":
            block.append(line[2:])
        elif line.startswith("## "):
            out.append(f"<h3>{inline_html(line[3:])}</h3>")
        elif line.strip():
            out.append(f"<p>{inline_html(line)}</p>")
    flush()
    return "\n".join(out)


# ---------- CLI ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Campaign performance answers from a CSV export.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_parser(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--csv", required=True)
        p.add_argument("--format", choices=("md", "html"), default="md",
                       help="html renders the same output as an email body")
        p.add_argument("--question", help="with --format html: the question, shown at the top of the email")
        return p

    add_parser("campaign", "one campaign, last week vs the week before").add_argument(
        "--campaign", required=True, help="campaign id or (part of) its name")
    for name, help_text in (("platforms", "streaming vs live TV"),
                            ("underperformers", "campaigns at or above 1.5x platform median cost per tune-in")):
        add_parser(name, help_text).add_argument("--period", choices=("last-week", "all"), default="last-week")
    add_parser("exclusions", "row-level list of excluded rows")
    args = parser.parse_args(argv)

    try:
        ds = Dataset(args.csv)
    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.command != "exclusions" and not ds.rows:
        print("ERROR: no usable rows after cleaning; run the `exclusions` command to see why", file=sys.stderr)
        return 2
    if args.command == "campaign":
        text = render_campaign(ds, campaign_report(ds, args.campaign))
    elif args.command == "platforms":
        text = render_platforms(ds, platform_report(ds, args.period))
    elif args.command == "underperformers":
        text = render_underperformers(ds, underperformer_report(ds, args.period))
    else:
        text = render_exclusions(ds)
    print(md_to_html(text, args.question) if args.format == "html" else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
