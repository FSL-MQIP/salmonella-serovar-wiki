# Active FDA investigations are displayed, never recorded

FDA CORE edits an investigation's row in place: the case count and both status
columns change under the same reference number for the investigation's whole
life. The monitor therefore treats the two phases differently:

- An **Active** row is information, not a finding. It renders in the digest's
  "Active FDA investigations" section every run with current data, is never
  classified, and never touches state — the same displayed-but-unrecorded
  pattern coverage gaps already use.
- A **Closed** row is final, and final data is wiki-shaped. Closures become
  ordinary candidates, bounded by a rolling posted-date lookback (a closure has
  no date of its own, so the scan window cannot bound it without dropping late
  closures).

This resolves the discrepancy `--record` could otherwise create. Recording a
finding built from an Active row retired its `(reference, serovar)` pair while
the underlying facts kept moving: a reviewer who declined the ongoing version
had silently declined the closure too, and a pasted version went stale with no
resurfacing. With phases separated, `--record` only ever retires final data,
and the reviewer sees every active investigation fresh each run until it
closes and arrives as a new finding.

## Considered options

**Phase-suffixed identity** (`1387#active` / `1387#closed`) kept Active rows as
findings and split the dedup key. Rejected: it encodes event semantics into an
ID string, captures only two phases (a case-count jump within "active" still
never resurfaces), and still lets a recorded snapshot go stale.

**Verifying `--record` against the wiki pages** (record only findings whose
citation URL appears on the target page) solves a broader deferral problem but
adds reconciliation machinery. Not adopted for now; worth revisiting if
deferral of immutable findings becomes a real pain. The saved dated digest
remains the reviewer's record for those.

## Consequences

Ongoing-outbreak *news* coverage leans on Food Safety News, which reports each
development as a new immutable item — the structure that suits reporting-once.
The rare active investigation FSN has not covered still appears in the digest's
active section, where a reviewer can act early by hand.

The lookback re-offers a closed row until it is reported once or ages out;
state dedup makes the re-offer cheap. Active rows appear every run by design —
that is the feature, not re-reporting, because nothing about them is recorded.
