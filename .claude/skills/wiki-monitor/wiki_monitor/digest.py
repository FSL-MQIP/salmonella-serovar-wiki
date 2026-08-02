"""Render a digest, update monitor state, and validate finding targets.

This is the monitor's one testing seam.  Input is a list of already-classified
finding records plus the current state; output is the rendered digest HTML, the
updated state, and validation results.  No network, no LLM.
"""

from __future__ import annotations

import html
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: Actionable findings shown per digest.  Anything past this is demoted to the
#: "Reviewed but not included" list rather than dropped.
ACTIONABLE_CAP = 5

#: Rough cap on the "Reviewed but not included" list; the remainder collapses
#: into a "+N more" note.
REVIEWED_CAP = 15

_OVER_CAP_REASON = "Ranked below the top 5 this run — past the 5-finding cap."

#: Placeholder a finding's ``entry`` carries where its reference number goes.
FOOTNOTE_PLACEHOLDER = "{footnote}"

_REFERENCES_HEADING = re.compile(r"^##\s+References\s*$", re.MULTILINE)
_NUMBERED_ITEM = re.compile(r"^\s*(\d+)\.\s", re.MULTILINE)
_SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

#: A serovar page's H1, e.g. ``# *S.* Agona`` — the serovar name without markup.
_H1 = re.compile(r"^#\s+(?:\*S\.\*|\*Salmonella\*)?\s*(.+?)\s*$", re.MULTILINE)

#: The tree whose last commit anchors a first run's scan window.
SEROVAR_PAGES = "docs/serovars"


@dataclass(frozen=True)
class Finding:
    """An actionable finding: one covered serovar, one target section.

    ``entry`` is the paste-ready wiki markdown.  Where it needs to cite its
    source it carries the literal placeholder ``{footnote}``, which this module
    replaces with a reference number allocated against the target page.
    """

    data_source: str
    source_id: str
    serovar: str
    target_page: str
    target_section: str
    criterion: str
    criterion_reason: str
    entry: str
    citation_url: str


@dataclass(frozen=True)
class ExcludedItem:
    """A candidate that was reviewed and judged not actionable."""

    data_source: str
    source_id: str
    serovar: str
    title: str
    url: str
    exclusion_reason: str


@dataclass(frozen=True)
class CoverageGap:
    """A serovar named by a source item but with no serovar page yet."""

    serovar: str
    data_source: str
    source_id: str
    title: str
    url: str


@dataclass(frozen=True)
class ValidationIssue:
    """A finding the monitor produced but could not verify against the repo.

    Identified by (source id, serovar) rather than source id alone: one source
    item naming several covered serovars fans out into one finding per serovar,
    so the source id on its own does not name a single finding.
    """

    kind: str  # "missing-page" | "missing-section" | "unresolved-footnote"
    source_id: str
    serovar: str
    message: str


@dataclass(frozen=True)
class DigestResult:
    html: str
    state: dict
    validation: list[ValidationIssue]
    #: Findings actually rendered as actionable — after dedup against state and
    #: after the cap. The only honest count to describe the digest by.
    actionable_count: int


def build_digest(
    *,
    findings: Sequence[Finding],
    excluded: Sequence[ExcludedItem],
    coverage_gaps: Sequence[CoverageGap],
    state: dict | None,
    repo_root: Path | str,
    run_timestamp: str,
    notes: Sequence[str] = (),
) -> DigestResult:
    already_reported = reported_pairs(state)

    # Drop what has been reported before *first*, so a stale finding does not
    # occupy one of the five actionable slots.
    fresh = [f for f in findings if (f.source_id, f.serovar) not in already_reported]
    fresh_excluded = [
        e for e in excluded if (e.source_id, e.serovar) not in already_reported
    ]

    actionable = fresh[:ACTIONABLE_CAP]

    # Findings past the cap are demoted, not dropped, and rank above the items
    # the classification step judged not actionable.
    demoted = [_demote(f) for f in fresh[ACTIONABLE_CAP:]]
    reviewed = [*demoted, *fresh_excluded]

    reviewed_shown = reviewed[:REVIEWED_CAP]
    dropped_count = max(0, len(reviewed) - REVIEWED_CAP)

    # Demoted findings lead `reviewed`, so everything after them is a candidate
    # the classifier itself ruled out.  Only those are recorded — a finding the
    # cap pushed down was listed, not reported.  See ADR 0003.
    excluded_shown = reviewed_shown[len(demoted) :]

    allocator = _ReferenceAllocator(repo_root)
    prepared = [allocator.prepare(finding) for finding in actionable]

    # Every finding is checked, not just the five shown: a demoted finding is
    # displayed and recorded in state, so an unverified target would never be
    # looked at again.
    issues = _validate(fresh, repo_root)
    warnings: dict[tuple[str, str], list[str]] = {}
    for issue in issues:
        warnings.setdefault((issue.source_id, issue.serovar), []).append(issue.message)

    return DigestResult(
        html="\n".join(
            [
                _scope_section(notes),
                _actionable_section(prepared, warnings),
                _coverage_gaps_section(coverage_gaps),
                _reviewed_section(reviewed_shown, dropped_count),
            ]
        ),
        state=_updated_state(state, actionable, excluded_shown, run_timestamp),
        validation=issues,
        actionable_count=len(actionable),
    )


# ---------------------------------------------------------------------------
# Scan window
# ---------------------------------------------------------------------------
def scan_window_start(state: dict | None, repo_root: Path | str) -> datetime:
    """The instant this run should scan from.

    Normally the last successful run recorded in *state*, so the window
    self-corrects when a scheduled run is skipped.  With no recorded run, anchor
    to the most recent commit touching the serovar pages instead of guessing a
    lookback period.
    """
    recorded = (state or {}).get("last_successful_run")
    if recorded:
        return _parse_iso8601(recorded)
    return last_serovar_commit(repo_root)


def last_serovar_commit(repo_root: Path | str) -> datetime:
    """Commit date of the most recent commit touching ``docs/serovars/``."""
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", SEROVAR_PAGES],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    stamp = completed.stdout.strip()
    if not stamp:
        raise RuntimeError(
            f"No commit in {repo_root} touches {SEROVAR_PAGES}, so a first run has "
            "nothing to anchor its scan window to."
        )
    return _parse_iso8601(stamp)


def _parse_iso8601(stamp: str) -> datetime:
    """Parse an ISO 8601 instant, accepting the ``Z`` suffix Python 3.10 rejects."""
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def covered_serovars(repo_root: Path | str) -> list[str]:
    """Every serovar with a serovar page, read from each page's H1.

    Coverage is what limits a candidate to being an actionable finding rather
    than a coverage gap, so it is derived from the pages themselves rather than
    from a list that could drift.  Filenames are not usable — several encode
    antigenic formulae rather than a serovar name.
    """
    pages = (Path(repo_root) / SEROVAR_PAGES).rglob("*.md")
    names = set()
    for page in pages:
        if page.name == "index.md":
            continue
        heading = _H1.search(page.read_text(encoding="utf-8"))
        if heading:
            names.add(heading.group(1).strip())
    return sorted(names)


def reported_pairs(state: dict | None) -> set[tuple[str, str]]:
    """The (source id, serovar) pairs already reported by an earlier run."""
    if not state:
        return set()
    return {
        (entry["source_id"], entry["serovar"]) for entry in state.get("reported", ())
    }


def _updated_state(
    state: dict | None,
    actionable: Sequence[Finding],
    excluded_shown: Sequence[ExcludedItem],
    run_timestamp: str,
) -> dict:
    """State carrying an entry for everything this digest *reported*.

    Reported means an actionable finding carrying its wiki-ready entry, or a
    candidate the classifier itself ruled out.  Three things are deliberately
    absent, so each competes again next run: findings the actionable cap pushed
    into the reviewed list, items the "+N more" note collapsed away, and
    coverage gaps — an uncovered serovar stays a candidate until someone
    creates its page.  See ADR 0003.
    """
    reported = list(state.get("reported", ())) if state else []
    seen = reported_pairs(state)

    # Finding and ExcludedItem deliberately share these three fields, so both
    # kinds of reported item record the same way.
    for item in [*actionable, *excluded_shown]:
        pair = (item.source_id, item.serovar)
        if pair in seen:
            continue
        seen.add(pair)
        reported.append(
            {
                "source_id": item.source_id,
                "serovar": item.serovar,
                "data_source": item.data_source,
            }
        )

    return {"last_successful_run": run_timestamp, "reported": reported}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate(
    findings: Sequence[Finding], repo_root: Path | str
) -> list[ValidationIssue]:
    """Check every finding's target page and section exist, and its entry resolves."""
    root = Path(repo_root)
    issues: list[ValidationIssue] = []

    for finding in findings:
        if FOOTNOTE_PLACEHOLDER in finding.entry and not finding.citation_url:
            issues.append(
                ValidationIssue(
                    kind="unresolved-footnote",
                    source_id=finding.source_id,
                    serovar=finding.serovar,
                    message=(
                        f"Entry expects a reference number but the finding cites "
                        f"no source, so {FOOTNOTE_PLACEHOLDER} cannot be resolved."
                    ),
                )
            )

        page = root / finding.target_page
        if not page.is_file():
            issues.append(
                ValidationIssue(
                    kind="missing-page",
                    source_id=finding.source_id,
                    serovar=finding.serovar,
                    message=(
                        f"Target page {finding.target_page} does not exist in the repo."
                    ),
                )
            )
            continue

        sections = _SECTION_HEADING.findall(page.read_text(encoding="utf-8"))
        if finding.target_section not in sections:
            issues.append(
                ValidationIssue(
                    kind="missing-section",
                    source_id=finding.source_id,
                    serovar=finding.serovar,
                    message=(
                        f"Target page {finding.target_page} has no "
                        f"## {finding.target_section} section."
                    ),
                )
            )

    return issues


def _demote(finding: Finding) -> ExcludedItem:
    """Recast an over-cap finding as a reviewed-but-not-included entry.

    A finding carries no title of its own — the classifier gives it a criterion
    and a reason — so those stand in as the reviewed list's description.
    """
    return ExcludedItem(
        data_source=finding.data_source,
        source_id=finding.source_id,
        serovar=finding.serovar,
        title=f"{finding.criterion}: {finding.criterion_reason}",
        url=finding.citation_url,
        exclusion_reason=_OVER_CAP_REASON,
    )


# ---------------------------------------------------------------------------
# Reference numbering
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _PreparedFinding:
    """A finding with its reference number resolved into the entry text."""

    finding: Finding
    entry: str
    reference_number: int | None

    @property
    def reference_line(self) -> str | None:
        """The line to paste under the target page's ``## References``."""
        if self.reference_number is None:
            return None
        url = self.finding.citation_url
        return f"{self.reference_number}. [{url}]({url})"


class _ReferenceAllocator:
    """Hands out reference numbers, one running sequence per target page.

    Numbers continue from the highest already on the page, so two findings
    landing on the same page in one run never claim the same number.
    """

    def __init__(self, repo_root: Path | str) -> None:
        self._repo_root = Path(repo_root)
        self._next: dict[str, int] = {}

    def prepare(self, finding: Finding) -> _PreparedFinding:
        if not finding.citation_url:
            return _PreparedFinding(
                finding=finding, entry=finding.entry, reference_number=None
            )

        number = self._allocate(finding.target_page)
        return _PreparedFinding(
            finding=finding,
            entry=finding.entry.replace(FOOTNOTE_PLACEHOLDER, str(number)),
            reference_number=number,
        )

    def _allocate(self, target_page: str) -> int:
        if target_page not in self._next:
            self._next[target_page] = self._highest_on_page(target_page) + 1
        number = self._next[target_page]
        self._next[target_page] = number + 1
        return number

    def _highest_on_page(self, target_page: str) -> int:
        page = self._repo_root / target_page
        if not page.is_file():
            # A missing page is reported by validation; numbering starts fresh
            # rather than blowing up the whole digest.
            return 0
        return _highest_reference_number(page.read_text(encoding="utf-8"))


def _highest_reference_number(page_text: str) -> int:
    """Highest number in the page's ``## References`` list, or 0 if there is none."""
    heading = _REFERENCES_HEADING.search(page_text)
    if heading is None:
        return 0
    numbers = [int(n) for n in _NUMBERED_ITEM.findall(page_text[heading.end() :])]
    return max(numbers) if numbers else 0


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _scope_section(notes: Sequence[str]) -> str:
    """Say where the scan was bounded, before anything it found.

    A truncated candidate pool must not read as a complete scan, so this leads
    the digest rather than trailing it.
    """
    if not notes:
        return ""
    parts = [
        "<h2>Scan coverage</h2>",
        "<p>This run did not see everything in its window:</p>",
        "<ul>",
    ]
    parts.extend(f"<li>{html.escape(note)}</li>" for note in notes)
    parts.append("</ul>")
    return "\n".join(parts)


def _actionable_section(
    prepared: Sequence[_PreparedFinding],
    warnings: dict[tuple[str, str], list[str]],
) -> str:
    parts = ["<h2>Actionable findings</h2>"]
    if not prepared:
        parts.append("<p>No actionable findings this run.</p>")
    for rank, item in enumerate(prepared, start=1):
        key = (item.finding.source_id, item.finding.serovar)
        parts.append(_finding_block(rank, item, warnings.get(key, [])))
    return "\n".join(parts)


def _finding_block(
    rank: int, prepared: _PreparedFinding, warnings: Sequence[str]
) -> str:
    esc = html.escape
    finding = prepared.finding
    heading = f"{rank}. <em>S.</em> {esc(finding.serovar)}"
    if warnings:
        heading += " &mdash; <strong>Needs attention</strong>"
    parts = [
        "<div>",
        f"<h3>{heading}</h3>",
        f"<p><strong>Target:</strong> {esc(finding.target_page)}"
        f" &rarr; <code>## {esc(finding.target_section)}</code></p>",
        f"<p><strong>Criterion:</strong> {esc(finding.criterion)}"
        f" &mdash; {esc(finding.criterion_reason)}</p>",
        # "Data source" in full: the entry below may carry an "Associated source"
        # column, which means the food vehicle. CONTEXT.md keeps the two apart.
        f"<p><strong>Data source:</strong> {esc(finding.data_source)}"
        f" <code>{esc(finding.source_id)}</code></p>",
    ]
    for message in warnings:
        parts.append(f"<p><strong>Check before pasting:</strong> {esc(message)}</p>")
    parts.append(f"<pre>{esc(prepared.entry)}</pre>")
    if prepared.reference_line is not None:
        parts.append("<p>Add under <code>## References</code>:</p>")
        parts.append(f"<pre>{esc(prepared.reference_line)}</pre>")
    parts.append("</div>")
    return "\n".join(parts)


def _coverage_gaps_section(coverage_gaps: Sequence[CoverageGap]) -> str:
    esc = html.escape
    parts = ["<h2>Coverage gaps</h2>"]
    if not coverage_gaps:
        parts.append("<p>No uncovered serovars appeared in this run's sources.</p>")
        return "\n".join(parts)

    parts.append(
        "<p>Serovars named by this run's sources with no serovar page yet."
        " Creating a page is an editorial decision.</p>"
    )
    parts.append("<ul>")
    for gap in coverage_gaps:
        parts.append(
            f"<li><em>S.</em> {esc(gap.serovar)} &mdash; "
            f'<a href="{esc(gap.url)}">{esc(gap.title)}</a> '
            f"({esc(gap.data_source)} <code>{esc(gap.source_id)}</code>)</li>"
        )
    parts.append("</ul>")
    return "\n".join(parts)


def _reviewed_section(items: Sequence[ExcludedItem], dropped_count: int) -> str:
    """Render the reviewed list.

    *items* holds both the classifier's non-actionable candidates and findings
    demoted past the actionable cap.
    """
    esc = html.escape
    parts = ["<h2>Reviewed but not included</h2>"]
    if not items:
        parts.append("<p>Nothing else was reviewed this run.</p>")
        return "\n".join(parts)

    parts.append("<ol>")
    for item in items:
        title = esc(item.title)
        if item.url:
            title = f'<a href="{esc(item.url)}">{title}</a>'
        parts.append(
            f"<li>{title} &mdash; "
            f"<em>S.</em> {esc(item.serovar)} &mdash; {esc(item.exclusion_reason)} "
            f"({esc(item.data_source)} <code>{esc(item.source_id)}</code>)</li>"
        )
    parts.append("</ol>")
    if dropped_count:
        parts.append(f"<p>+{dropped_count} more not listed.</p>")
    return "\n".join(parts)
