# The actionable cap defers a finding rather than consuming it

State records what a digest *reported*: an actionable finding carrying its wiki-ready
entry, or a candidate the classification step itself ruled out. A finding that was
merely listed in "Reviewed but not included" because the 5-finding cap pushed it down
is **not** recorded, so it competes for an actionable slot again on the next run.

This qualifies [ADR 0001](0001-digest-reports-findings-once.md), which says a reported
finding is never reported again. A demoted finding was never reported in the sense
that matters — the reviewer got a one-line title and an exclusion reason, not the
paste-ready row, footnote number, and reference line they would act on.

## Considered options

**Recording everything the digest displayed** is the simpler rule and was how this was
first built. We rejected it because it silently destroys work: the monitor judges a
finding actionable, ranks it sixth, shows it as a title, and then never offers it
again. The first live run is the worst case — it backfills roughly 90 days across four
Update Criteria, so the PRD expects the cap to be well exceeded on precisely the run
whose findings matter most.

It also left an arbitrary seam. The "Reviewed but not included" list is itself capped
at roughly 15, and items collapsed into its "+N more" note were already unrecorded and
free to compete again. Under the old rule, ranking 16th got a finding another chance
while ranking 6th did not.

**Reminding the reviewer about unactioned findings** is what ADR 0001 rejected, and
this decision does not revive it. Nothing here re-reports a finding that was fully
reported.

## Consequences

A deferred finding does not nag indefinitely, because the scan window bounds it. Every
run after the first scans since the last successful run, so an unrecorded PubMed or
Food Safety News item is simply never fetched again. Only the openFDA adapter re-offers
it, because it queries a rolling 60-day window regardless of the since-date to absorb
openFDA's publication lag. A crowded-out recall therefore gets roughly eight further
chances and then ages out of the window on its own.

The cost is re-work: for up to 60 days, openFDA candidates already seen and demoted are
re-classified each run. That is a small, bounded amount of model work traded against
permanently losing an actionable finding.

Because deferral is invisible in the digest — a demoted finding looks the same whether
it will return or not — the reviewed list is the only record that it existed. If the
monitor ever gains a rejection channel, both this decision and ADR 0001 are worth
revisiting together.
