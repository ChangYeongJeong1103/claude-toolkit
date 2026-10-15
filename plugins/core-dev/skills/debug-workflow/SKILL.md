---
name: debug-workflow
description: This skill should be used when the user reports a bug or asks to "debug this", "fix this bug/error", "why does this fail", investigate a traceback or failing test, or says "버그 분석", "에러 고쳐줘", "왜 안 돼". Enforces a fixed analysis order (Intent → Tiny Trace → Input/State/Control Flow/Output → Edge Cases → Minimal Fix + Guard), then reports root cause, fix, and verification results.
version: 0.1.0
---

# Debug Workflow

Follow these steps in order. Do not propose a fix before steps 1–4 are done.

## 1. Intent
- State what the code should do and the observed vs expected behavior in one or two lines.
- If the intent is ambiguous, ask before changing code.

## 2. Tiny Trace
- Build the smallest input that reproduces the bug (a few elements, tiny arrays).
- Trace it through the actual execution path and record intermediate values. Prefer running it over reasoning about it.

## 3. Input / State / Control Flow / Output
Find where the trace first diverges from the intent:
- **Input**: type, shape, dtype, None, units, encoding
- **State**: mutation vs rebinding, aliasing (shared lists, views vs copies), mutable default args, caches/globals
- **Control flow**: branch conditions, early returns, loop bounds, off-by-one, swallowed exceptions
- **Output**: return values (e.g., methods returning None such as `list.sort()`), side effects

## 4. Edge Cases
Check empty input, a single element, boundaries, NaN/inf, duplicates, and large sizes. List the ones the fix must also cover.

## 5. Minimal Fix + Guard
- Fix the root cause with the smallest change. Keep the user's existing approach and structure.
- Do not mask symptoms (broad try/except, special-casing the failing input).
- Add a guard against recurrence: a regression test, an assertion, or input validation.
- Propose larger refactors separately instead of applying them.

## After the Fix
Run the relevant tests or the reproduction case and report the real output.
If it cannot be run, say so explicitly.

## Response Format
Intent → Trace → Root cause → Edge cases → Fix (diff) → Guard → Verification (command + result)
- **Root cause**: one or two lines grounded in the actual execution flow
  (e.g., "`b = a` aliased the list, so `b.append()` also mutated `a`").
- **Edge cases**: the cases from step 4 and whether the fix covers each.
