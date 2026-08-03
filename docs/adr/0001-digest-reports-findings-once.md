# Digest reports each finding once, never repeats it

The weekly digest reports each actionable finding exactly once. Once reported, a finding
is recorded in the monitor's state and never appears again, whether or not anyone acted
on it.

## Considered options

We considered keeping unactioned findings in the digest — either in full, or as a compact
"outstanding" list — until the corresponding row appeared on the target serovar page. That
would stop findings being lost when a reviewer is busy, and the monitor already reads
target pages, so detecting resolution would have been nearly free.

We rejected it because the monitor has no channel through which a reviewer can decline a
finding. Absence of a row means either "not edited yet" or "we considered this and decided
against it", and the monitor cannot tell those apart. Reminders would therefore nag
indefinitely about findings the team had already rejected — and the ones most likely to be
rejected are the ones that would nag longest.

## Consequences

A finding that is never actioned exists only in the recipient's inbox. The monitor's state
records that it was *reported*, not what was *decided*, so the repo holds no record of
rejected findings.

If a rejection channel is ever added — a reply-parsed mailbox, or a declined-findings file
in the repo — reminders become viable and this decision is worth revisiting.
