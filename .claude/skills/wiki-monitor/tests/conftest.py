"""Test fixtures for the wiki-monitor digest module.

``wiki_monitor`` is importable because ``pytest.ini`` puts the skill directory on
``pythonpath``.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
def git(repo: Path, *args: str, when: str = "2026-05-04T12:00:00+00:00") -> None:
    """Run one git command in *repo*, with author and committer dates pinned."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.org",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.org",
            "PATH": os.environ.get("PATH", ""),
        },
    )


@pytest.fixture
def commit_all():
    """Stage and commit everything in a repo, at a given date."""

    def _commit(repo: Path, message: str, when: str) -> None:
        git(repo, "add", "-A", when=when)
        git(repo, "commit", "-q", "-m", message, when=when)

    return _commit


# ---------------------------------------------------------------------------
# A throwaway repo standing in for the wiki, with real serovar-page structure.
# ---------------------------------------------------------------------------
def _serovar_page(name: str, reference_count: int) -> str:
    """A minimal serovar page carrying the nine standard sections.

    The references list is appended *after* dedenting — interpolating a
    multi-line string into the template first would leave its second and later
    lines unindented and defeat ``textwrap.dedent`` entirely.
    """
    body = textwrap.dedent(
        f"""\
        # *S.* {name}

        ## Background Information

        Placeholder background for serovar {name}.

        ## Genetic Characteristics

        Placeholder genetics for serovar {name}.

        ## Animal Reservoir

        Placeholder reservoir.

        ## Geographical Distribution

        Placeholder distribution.

        ## Human Outbreaks

        | Year | Location | Associated source | Number of cases |
        | --- | --- | --- | --- |
        | 2020 | US: multistate | [Peanut butter](https://example.org/pb) | 42 |

        ## Animal Outbreaks

        There have been no recent animal outbreaks linked to this serovar.

        ## Border Rejections

        | Year | Exporting country | Importing country | Associated source | Product category |
        | --- | --- | --- | --- | --- |
        | 2021 | Brazil | Netherlands | [Sesame seeds](https://example.org/ss) | Nuts and seeds |

        ## Recalls

        | Year | Location | Recalled food | Type |
        | --- | --- | --- | --- |
        | 2019 | US: multistate | [Flour](https://example.org/flour) | Ready-to-Eat food |

        ## References

        """
    )
    references = "\n".join(
        f"{n}. [https://example.org/ref-{n}](https://example.org/ref-{n})"
        for n in range(1, reference_count + 1)
    )
    return body + references + "\n"


@pytest.fixture
def wiki_repo(tmp_path: Path) -> Path:
    """A git repo laid out like the wiki, with three serovar pages.

    Reference counts differ per page so footnote-allocation tests can tell the
    pages apart: agona ends at 21, dublin at 20, typhimurium at 50.
    """
    repo = tmp_path / "wiki"
    (repo / "docs" / "serovars" / "group-b").mkdir(parents=True)
    (repo / "docs" / "serovars" / "group-d").mkdir(parents=True)

    (repo / "docs" / "serovars" / "group-b" / "agona.md").write_text(
        _serovar_page("Agona", reference_count=21), encoding="utf-8"
    )
    (repo / "docs" / "serovars" / "group-b" / "typhimurium.md").write_text(
        _serovar_page("Typhimurium", reference_count=50), encoding="utf-8"
    )
    (repo / "docs" / "serovars" / "group-d" / "dublin.md").write_text(
        _serovar_page("Dublin", reference_count=20), encoding="utf-8"
    )

    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "Add serovar pages")
    return repo


@pytest.fixture
def real_repo() -> Path:
    """This repository itself, for checking the parser against real pages."""
    return SKILL_DIR.parents[2]


# ---------------------------------------------------------------------------
# Calling the module
# ---------------------------------------------------------------------------
@pytest.fixture
def build():
    """Call ``build_digest`` for *repo*, defaulting every input to an empty run."""
    from wiki_monitor.digest import build_digest

    def _build(repo, **overrides):
        kwargs = dict(
            findings=[],
            excluded=[],
            coverage_gaps=[],
            state=None,
            repo_root=repo,
            run_timestamp="2026-08-02T06:00:00Z",
        )
        kwargs.update(overrides)
        return build_digest(**kwargs)

    return _build


@pytest.fixture
def digest_section():
    """Slice one ``<h2>`` section out of a rendered digest.

    Lets a test assert *where* in the digest something landed, rather than only
    that it appears somewhere.
    """

    def _section(digest_html: str, heading: str) -> str:
        opening = f"<h2>{heading}</h2>"
        start = digest_html.index(opening)
        rest = digest_html[start:]
        next_heading = rest.find("<h2>", len(opening))
        return rest if next_heading == -1 else rest[:next_heading]

    return _section


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------
@pytest.fixture
def make_literature(make_finding):
    """A novel-characteristic (literature) finding — the one capped kind."""

    def _make(source_id="P-1", **overrides):
        fields = dict(
            source_id=source_id,
            target_section="Genetic Characteristics",
            criterion="novel characteristic",
            criterion_reason="A plasmid the page does not describe.",
            entry=(
                "Serovar Agona isolates carried a "
                "[novel plasmid](https://example.org/p)."
            ),
            citation_url="https://example.org/p",
        )
        fields.update(overrides)
        return make_finding(**fields)

    return _make


@pytest.fixture
def make_finding():
    """Build an actionable Finding, overriding only the fields a test cares about."""
    from wiki_monitor.digest import Finding

    defaults = dict(
        data_source="openfda",
        source_id="F-1234-2026",
        serovar="Agona",
        target_page="docs/serovars/group-b/agona.md",
        target_section="Recalls",
        criterion="novel commodity",
        criterion_reason="Tahini is not yet documented on the Agona page.",
        entry=(
            "| 2026 | US: multistate | [Tahini](https://example.org/tahini)"
            "<sup>{footnote}</sup> | Ready-to-Eat food |"
        ),
        citation_url="https://example.org/tahini",
    )

    def _make(**overrides):
        return Finding(**{**defaults, **overrides})

    return _make


@pytest.fixture
def make_excluded():
    """Build an ExcludedItem, overriding only the fields a test cares about."""
    from wiki_monitor.digest import ExcludedItem

    defaults = dict(
        data_source="food-safety-news",
        source_id="https://foodsafetynews.example/item/1",
        serovar="Agona",
        title="Routine sampling finds Salmonella in pet treats",
        url="https://foodsafetynews.example/item/1",
        exclusion_reason="No serovar-specific novelty.",
    )

    def _make(**overrides):
        return ExcludedItem(**{**defaults, **overrides})

    return _make
