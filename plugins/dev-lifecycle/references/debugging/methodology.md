<!--
library: debugging
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Debugging methodology & techniques

The universal techniques, applicable to any layer. Read for the *how* of the workflow steps.

## Contents
- Reading stack traces
- Reading logs
- Instrumentation
- Bisection (narrowing the search)
- Differential debugging
- Minimal reproduction
- Flaky / intermittent bugs
- Anti-patterns

## Reading stack traces
- Find the actual exception type and message first — it often names the problem outright (`KeyError`, `NoneType has no attribute`, `IntegrityError`).
- Read to the deepest frame in *your* code (not library internals) — that's usually where to look, even if the throw happens deeper in a dependency.
- Trace the call path that led there; the bug may be an invalid value passed several frames up, not at the throw site.
- For async code, the trace may be shallow or detached — note that the failing operation was scheduled elsewhere and follow the logical flow, not just the literal frames.

## Reading logs
- Establish a timeline: what happened right before the failure. Correlate by timestamp and, if present, request/trace ID across services.
- Look for the first anomaly, not just the loudest error — a downstream error is often a symptom of an earlier one.
- Raise log verbosity around the suspect area if the default level hides the detail; structured logs let you filter to the relevant request.

## Instrumentation
- When you can't see the state, add temporary, targeted logging at decision points and around the failure — print the *actual* values of the variables your hypothesis depends on.
- A debugger (breakpoints, stepping, inspecting frames) is often faster than print-debugging for complex state; use it where the project supports it.
- Instrument to *test a specific hypothesis*, not to scatter prints randomly. Remove temporary instrumentation before shipping.

## Bisection (narrowing the search)
The core move: halve the search space repeatedly until the cause is cornered.
- **History:** `git bisect` to find the commit that introduced a regression — mark good/bad and let it binary-search.
- **Code/data flow:** check the value at the midpoint of the suspect path. Correct there? The bug is downstream. Wrong? Upstream. Repeat.
- **Input:** shrink the failing input by half repeatedly — the smallest input that still fails is highly diagnostic.
- **Config/environment:** disable half the variables (middleware, flags, services) to isolate which one matters.

## Differential debugging
- Compare a working case against the failing one and find the difference. What's different about this input, this user, this environment, this time?
- "Works on my machine" is a differential clue, not an excuse — enumerate the differences (versions, env vars, data, OS, timezone) and test each.

## Minimal reproduction
- Strip the repro to the least code/data/steps that still triggers the bug. Each thing you remove that *doesn't* stop the failure is eliminated as the cause.
- A minimal repro is also the seed of the regression test you'll add after the fix.

## Flaky / intermittent bugs
- Usual suspects: race conditions / ordering, shared mutable state, reliance on timing or wall-clock, test pollution (one test leaking state into another), network/external flakiness, unseeded randomness.
- Make the conditions deterministic to reproduce: control concurrency, freeze time, seed randomness, run the suspected order explicitly.
- A test that fails 1-in-N is still a real bug — increase iterations or add logging to catch it in the act rather than dismissing it.

## Anti-patterns
- **Shotgun debugging:** changing many things hoping one works. You won't know what fixed it and may add bugs.
- **Symptom patching:** swallowing the exception, adding a null-guard at the crash site, or retrying — without understanding *why* the value was bad.
- **Assuming instead of checking:** "it must be X" without observing X. Verify.
- **Cargo-culting a fix** from a search result without understanding why it applies to your case.
