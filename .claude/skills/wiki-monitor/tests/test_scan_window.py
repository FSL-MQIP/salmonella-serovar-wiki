"""Where a run starts scanning from.

Every run after the first scans since the last successful run.  The first run
has no state, so it anchors to the most recent commit touching the serovar
pages — read from git history at run time, not a hardcoded day count.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from wiki_monitor.digest import scan_window_start


def test_a_later_run_scans_since_the_last_successful_run(wiki_repo):
    state = {"last_successful_run": "2026-07-26T06:00:00Z", "reported": []}

    start = scan_window_start(state, wiki_repo)

    assert start == datetime(2026, 7, 26, 6, 0, tzinfo=timezone.utc)


def test_a_first_run_anchors_to_the_last_serovar_page_commit(wiki_repo):
    start = scan_window_start(None, wiki_repo)

    assert start.date().isoformat() == "2026-05-04"


def test_state_without_a_recorded_run_also_anchors_to_git(wiki_repo):
    """A state file that exists but has never completed a run is still a first run."""
    start = scan_window_start({"reported": []}, wiki_repo)

    assert start.date().isoformat() == "2026-05-04"


def test_the_anchor_ignores_commits_that_miss_the_serovar_pages(wiki_repo, commit_all):
    """A later commit elsewhere must not move the anchor forward."""
    (wiki_repo / "README.md").write_text("Unrelated edit.\n", encoding="utf-8")
    commit_all(wiki_repo, "Edit README", when="2026-06-15T12:00:00+00:00")

    start = scan_window_start(None, wiki_repo)

    assert start.date().isoformat() == "2026-05-04"


def test_the_anchor_follows_a_later_serovar_page_commit(wiki_repo, commit_all):
    """Editing a serovar page moves the anchor to that commit."""
    page = wiki_repo / "docs" / "serovars" / "group-b" / "agona.md"
    page.write_text(page.read_text(encoding="utf-8") + "\nEdit.\n", encoding="utf-8")
    commit_all(wiki_repo, "Update agona.md", when="2026-07-01T09:00:00+00:00")

    start = scan_window_start(None, wiki_repo)

    assert start.date().isoformat() == "2026-07-01"


def test_the_anchor_follows_the_real_repositorys_history(real_repo):
    """Derived from live git history, not a hardcoded date, so commits can't break it."""
    expected = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", "docs/serovars"],
        cwd=real_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    start = scan_window_start(None, real_repo)

    assert start == datetime.fromisoformat(expected)
