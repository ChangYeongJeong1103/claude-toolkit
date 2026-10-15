#!/usr/bin/env python3
"""Deterministic parts of the segment planner: the targeting policy and the delivery math.

  check  Which catalog segments pass the policy, and the rules that exclude the rest.
  plan   Impressions and reach for the chosen segments (policy D1-D4); refuses unknown or excluded IDs.

The policy comes from a JSON config (rule kinds below), so another team can plug in its own
catalog and policy without code changes. Output is Markdown for the skill to copy verbatim.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date
from fractions import Fraction

REQUIRED_COLUMNS = [
    "segment_id", "name", "type", "description", "households", "cpm_usd",
    "status", "expires_on", "sensitive_category", "age_floor", "exclusive_group",
]
RULE_KINDS = {
    "banned_sensitive_category",
    "min_households",
    "active_through_flight_end",
    "banned_type_for_advertiser",
    "min_age_floor_for_advertiser",
}
NO_RESTRICTION = "other"


class PlanError(Exception):
    """Input the planner must refuse: a bad catalog or policy, an unknown category, or a bad segment ID."""


def load_catalog(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise PlanError(f"catalog {path} is missing columns: {', '.join(missing)}")
        catalog = []
        for row_number, row in enumerate(reader, start=2):
            try:
                households = int(row["households"])
                cpm_usd = Fraction(row["cpm_usd"])
                expires_on = date.fromisoformat(row["expires_on"])
                age_floor = int(row["age_floor"])
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                raise PlanError(
                    f"catalog row {row_number} has an invalid number or date: {exc}"
                ) from exc
            if households <= 0:
                raise PlanError(f"catalog row {row_number} households must be positive")
            if cpm_usd <= 0:
                raise PlanError(f"catalog row {row_number} cpm_usd must be positive")
            if age_floor < 0:
                raise PlanError(f"catalog row {row_number} age_floor cannot be negative")
            catalog.append({
                **row,
                "households": households,
                "cpm_usd": cpm_usd,  # exact, so floors at output are exact
                "expires_on": expires_on,
                "age_floor": age_floor,
            })
    return catalog


def load_policy(path):
    with open(path, encoding="utf-8") as f:
        policy = json.load(f)
    if not isinstance(policy, dict) or not isinstance(policy.get("rules"), list):
        raise PlanError("policy must be an object with a rules list")
    default_cap = policy.get("default_frequency_cap")
    if not isinstance(default_cap, int) or isinstance(default_cap, bool) or default_cap <= 0:
        raise PlanError("policy default_frequency_cap must be a positive integer")
    for index, rule in enumerate(policy["rules"], start=1):
        if not isinstance(rule, dict) or not rule.get("id") or not rule.get("kind"):
            raise PlanError(f"policy rule {index} must have id and kind")
        rule_id = rule["id"]
        kind = rule["kind"]
        if kind not in RULE_KINDS:
            raise PlanError(f"policy rule {rule_id} has unknown kind {kind!r}")
        if kind == "min_households":
            value = rule.get("value")
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise PlanError(f"policy rule {rule_id} value must be a positive integer")
        if kind == "min_age_floor_for_advertiser":
            value = rule.get("value")
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise PlanError(f"policy rule {rule_id} value must be a non-negative integer")
    return policy


def advertiser_categories(policy):
    """The advertiser categories the policy restricts, plus `other` for none."""
    cats = {a for rule in policy["rules"] for a in rule.get("advertisers", [])}
    return sorted(cats) + [NO_RESTRICTION]


def rule_failure(rule, seg, advertiser, flight_end):
    """The reason `seg` breaks `rule`, or None if it passes."""
    kind = rule["kind"]
    applies = advertiser in rule.get("advertisers", [])
    if kind == "banned_sensitive_category":
        if seg["sensitive_category"] in rule["values"]:
            return f"sensitive_category is {seg['sensitive_category']}"
    elif kind == "min_households":
        if seg["households"] < rule["value"]:
            return f"{seg['households']:,} households, below {rule['value']:,}"
    elif kind == "active_through_flight_end":
        if seg["status"] != "active":
            return f"status is {seg['status']}"
        if seg["expires_on"] < flight_end:
            return f"expires {seg['expires_on']}, before the flight ends {flight_end}"
    elif kind == "banned_type_for_advertiser":
        if applies and seg["type"] in rule["values"]:
            return f"type {seg['type']} is not allowed for {advertiser} advertisers"
    elif kind == "min_age_floor_for_advertiser":
        if applies and seg["age_floor"] < rule["value"]:
            return f"age_floor {seg['age_floor']}, below {rule['value']} for {advertiser} advertisers"
    return None


def check(catalog, policy, advertiser, flight_end):
    """Split the catalog into eligible segments and excluded (segment, [(rule_id, reason)])."""
    allowed = advertiser_categories(policy)
    if advertiser not in allowed:
        raise PlanError(f"unknown advertiser category {advertiser!r}; use one of: {', '.join(allowed)}")
    eligible, excluded = [], []
    for seg in catalog:
        failures = []
        for rule in policy["rules"]:
            reason = rule_failure(rule, seg, advertiser, flight_end)
            if reason:
                failures.append((rule["id"], reason))
        if failures:
            excluded.append((seg, failures))
        else:
            eligible.append(seg)
    return eligible, excluded


def plan(catalog, policy, advertiser, flight_end, budget, segment_ids, frequency_cap=None):
    """Delivery per segment (D1-D3) and combined reach (D4). Refuses unknown or excluded IDs."""
    budget = Fraction(budget)
    if budget <= 0:
        raise PlanError("budget must be positive")
    cap = policy["default_frequency_cap"] if frequency_cap is None else frequency_cap
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        raise PlanError("frequency cap must be a positive integer")

    ids = list(dict.fromkeys(segment_ids))
    if not ids:
        raise PlanError("no segments given")
    by_id = {s["segment_id"]: s for s in catalog}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise PlanError(f"not in the catalog: {', '.join(unknown)}")
    _, excluded = check(catalog, policy, advertiser, flight_end)
    blocked = {s["segment_id"]: failures for s, failures in excluded}
    refused = [f"{i} ({', '.join(rid for rid, _ in blocked[i])})" for i in ids if i in blocked]
    if refused:
        raise PlanError(f"excluded by policy: {'; '.join(refused)}")

    share = Fraction(budget) / len(ids)                                  # D3: even split
    rows = []
    for i in ids:
        seg = by_id[i]
        impressions = share / seg["cpm_usd"] * 1000                      # D1: catalog CPM
        reach = min(Fraction(seg["households"]), impressions / cap)      # D2
        rows.append({"segment": seg, "budget": share,
                     "impressions": math.floor(impressions), "reach": math.floor(reach)})

    # D4: reach adds only within an exclusive group; across those units it is a range.
    units = {}
    for r in rows:
        group = r["segment"]["exclusive_group"]
        key = ("group", group) if group else ("segment", r["segment"]["segment_id"])
        units.setdefault(key, []).append(r)
    unit_reach = {key: sum(r["reach"] for r in members) for key, members in units.items()}
    return {"rows": rows, "frequency_cap": cap, "units": units, "unit_reach": unit_reach,
            "low": max(unit_reach.values()), "high": sum(unit_reach.values())}


def unit_label(key, members):
    kind, name = key
    if kind == "segment":
        return name
    return f"exclusive group {name} ({' + '.join(r['segment']['segment_id'] for r in members)})"


def header(policy, advertiser, flight_end):
    return (f"Policy: {policy['policy']} ({policy['owner']}, effective {policy['effective']}) · "
            f"advertiser category: {advertiser} · flight end: {flight_end}")


def render_check(policy, advertiser, flight_end, eligible, excluded):
    lines = ["## Policy check", header(policy, advertiser, flight_end), "",
             f"### Eligible segments ({len(eligible)})",
             "| ID | Name | Type | Description | Households | CPM | Expires | Exclusive group |",
             "|---|---|---|---|---:|---:|---|---|"]
    for s in eligible:
        lines.append(f"| {s['segment_id']} | {s['name']} | {s['type']} | {s['description']} | "
                     f"{s['households']:,} | ${float(s['cpm_usd']):,.2f} | {s['expires_on']} | "
                     f"{s['exclusive_group'] or '—'} |")
    lines += ["", f"### Excluded by policy ({len(excluded)})",
              "| ID | Name | Rules | Reason |", "|---|---|---|---|"]
    for s, failures in excluded:
        rules = ", ".join(rid for rid, _ in failures)
        reasons = "; ".join(f"{rid}: {why}" for rid, why in failures)
        lines.append(f"| {s['segment_id']} | {s['name']} | {rules} | {reasons} |")
    return "\n".join(lines)


def render_plan(policy, advertiser, flight_end, budget, cap_from_brief, result):
    rows = result["rows"]
    cap_source = "from the brief" if cap_from_brief else "policy default"
    lines = ["## Delivery plan", header(policy, advertiser, flight_end),
             f"Budget: ${float(budget):,.2f}, split evenly across {len(rows)} segment(s) (D3) · "
             f"frequency cap: {result['frequency_cap']} ({cap_source}, D2) · CPM from the catalog (D1)", "",
             "| ID | Name | Households | CPM | Budget | Impressions | Est. reach |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        s = r["segment"]
        lines.append(f"| {s['segment_id']} | {s['name']} | {s['households']:,} | ${float(s['cpm_usd']):,.2f} | "
                     f"${float(r['budget']):,.2f} | {r['impressions']:,} | {r['reach']:,} |")
    total_impressions = sum(r["impressions"] for r in rows)
    lines += [f"| **Total** | | | | ${float(budget):,.2f} | {total_impressions:,} | see combined reach |", ""]

    units, unit_reach = result["units"], result["unit_reach"]
    if len(units) == 1:
        (key, members), = units.items()
        why = "one segment" if key[0] == "segment" else f"{unit_label(key, members)} is mutually exclusive, so its reach adds (D4)"
        lines.append(f"**Combined reach: {result['low']:,}** ({why}).")
    else:
        top = max(unit_reach, key=unit_reach.get)
        lines.append(f"**Combined reach: {result['low']:,} to {result['high']:,}.** These segments can overlap, "
                     f"so reach is not added across them (D4). Lower bound: the largest reach, "
                     f"{unit_label(top, units[top])}. Upper bound: the sum of all segment reaches.")
        grouped = [unit_label(k, m) for k, m in units.items() if k[0] == "group" and len(m) > 1]
        if grouped:
            lines.append(f"Reach is added within {', '.join(grouped)}: the group is mutually exclusive by construction.")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--catalog", required=True, help="segment catalog CSV")
    common.add_argument("--policy", required=True, help="policy config JSON")
    common.add_argument("--advertiser", required=True, help="advertiser category from the policy config, or 'other'")
    common.add_argument("--flight-end", required=True, type=date.fromisoformat, help="last flight day, YYYY-MM-DD")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", parents=[common], help="policy check over the whole catalog")
    pl = sub.add_parser("plan", parents=[common], help="delivery math for the chosen segments")
    pl.add_argument("--budget", required=True, type=Fraction, help="total budget in USD, e.g. 180000")
    pl.add_argument("--segments", required=True, help="comma-separated segment IDs")
    pl.add_argument("--frequency-cap", type=int, help="from the brief; omit to use the policy default")
    args = p.parse_args(argv)

    try:
        catalog, policy = load_catalog(args.catalog), load_policy(args.policy)
        if args.command == "check":
            eligible, excluded = check(catalog, policy, args.advertiser, args.flight_end)
            print(render_check(policy, args.advertiser, args.flight_end, eligible, excluded))
        else:
            ids = [i.strip() for i in args.segments.split(",") if i.strip()]
            result = plan(catalog, policy, args.advertiser, args.flight_end, args.budget, ids, args.frequency_cap)
            print(render_plan(policy, args.advertiser, args.flight_end, args.budget,
                              args.frequency_cap is not None, result))
    except PlanError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
