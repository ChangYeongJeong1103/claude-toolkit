# Partner Report Rules

Owner: Partner Analytics · Last updated: 2026-08-01

- **Blocker**: the report must not be sent until it is fixed.
- **Warning**: should be fixed; the analyst may send with a note.
- A report is **ready to send** only when it has no blockers.

## PA-1. Partner confidentiality (Blocker)
A report may name only the partner it is addressed to. Other partners in `clients.csv` must not appear unless `benchmark_consent = yes`.

## PA-2. Metric accuracy (Blocker)
Every derived metric must equal the value computed from the base numbers in the report, using `metric-definitions.md`, after rounding.

## PA-3. Banned claims (Warning)
Avoid "best-in-class" and "risk-free".

## PA-4. Minimum audience (Blocker)
No row may be reported if it is based on fewer than 100 households.
