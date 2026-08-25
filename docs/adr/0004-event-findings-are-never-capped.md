# Event findings are never capped; the literature cap remains

The digest renders every event finding — an outbreak, recall, or investigation
update — as actionable, provided each is a unique event. Only literature
findings (criterion "novel characteristic") count against the 5-slot actionable
cap; those past it are demoted to "Reviewed but not included" and, per
[ADR 0003](0003-the-cap-defers-a-finding-rather-than-consuming-it.md), compete
again next run.

The cap exists to keep a digest reviewable in one sitting. For literature that
trade works: a paper defers without loss, because its result is as true next
month. An event does not — it is time-sensitive, and deferring it costs the
reviewer freshness on precisely the findings the wiki exists to distribute.
The change that forced the issue was lowering the outbreak criterion to the
epidemiological definition (≥2 linked cases) and moving the inclusion call to
the reviewing expert: a run then produced 13 unique outbreaks, of which the cap
would have shown 5 and queued 8 across four future record cycles.

Uniqueness is not a new mechanism. It is the existing dedup: one finding per
(source id, serovar), and state retires reported pairs.

## Considered options

**Raising the cap** (to 8 or 10) keeps one number but re-creates the same
deferral on the next busy window, and slows literature findings for no reason.

**Uncapping everything** loses the one place the cap genuinely helps: a long
backfill can carry dozens of literature findings, which queue harmlessly.

## Consequences

A busy window can render a long digest; "reviewable in one sitting" is no
longer guaranteed for events. That is the accepted cost of the expert-judgment
model — the expert sees every qualifying event and decides.

Criterion strings are free text from the classifier. Matching is exact on
"novel characteristic" (case-insensitive); an unrecognised criterion renders
uncapped, because over-showing is the safe failure.
