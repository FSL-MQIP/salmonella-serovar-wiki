"""Reference-number allocation.

Numbering is per target page and sequential, continuing from the highest number
already under that page's ``## References`` heading.  The ``wiki_repo`` fixture
ends agona at 21 references, dublin at 20, typhimurium at 50.
"""

from __future__ import annotations

import re

AGONA = "docs/serovars/group-b/agona.md"
DUBLIN = "docs/serovars/group-d/dublin.md"
TYPHIMURIUM = "docs/serovars/group-b/typhimurium.md"


def test_entry_continues_the_target_pages_reference_numbering(
    wiki_repo, build, make_finding
):
    html = build(wiki_repo, findings=[make_finding(target_page=AGONA)]).html

    # agona.md ends at reference 21, so the new row cites 22.
    assert "&lt;sup&gt;22&lt;/sup&gt;" in html
    assert "{footnote}" not in html


def test_two_findings_on_one_page_get_different_numbers(
    wiki_repo, build, make_finding
):
    findings = [
        make_finding(source_id="F-1-2026", target_page=AGONA),
        make_finding(source_id="F-2-2026", target_page=AGONA),
    ]

    html = build(wiki_repo, findings=findings).html

    assert "&lt;sup&gt;22&lt;/sup&gt;" in html
    assert "&lt;sup&gt;23&lt;/sup&gt;" in html


def test_each_page_is_numbered_independently(wiki_repo, build, make_finding):
    findings = [
        make_finding(source_id="F-1-2026", target_page=AGONA),
        make_finding(source_id="F-2-2026", target_page=DUBLIN),
        make_finding(source_id="F-3-2026", target_page=TYPHIMURIUM),
    ]

    html = build(wiki_repo, findings=findings).html

    # agona 21 -> 22, dublin 20 -> 21, typhimurium 50 -> 51.
    assert "&lt;sup&gt;22&lt;/sup&gt;" in html
    assert "&lt;sup&gt;21&lt;/sup&gt;" in html
    assert "&lt;sup&gt;51&lt;/sup&gt;" in html


def test_a_finding_that_cites_nothing_does_not_consume_a_number(
    wiki_repo, build, make_finding
):
    findings = [
        make_finding(
            source_id="F-1-2026",
            target_page=AGONA,
            target_section="Genetic Characteristics",
            entry="Serovar Agona isolates from this study carried a novel plasmid.",
            citation_url="",
        ),
        make_finding(source_id="F-2-2026", target_page=AGONA),
    ]

    html = build(wiki_repo, findings=findings).html

    # The citing finding takes 22 — the uncited one above it burns nothing.
    assert "&lt;sup&gt;22&lt;/sup&gt;" in html
    assert "&lt;sup&gt;23&lt;/sup&gt;" not in html


def test_digest_supplies_the_reference_line_to_paste_under_references(
    wiki_repo, build, make_finding
):
    html = build(wiki_repo, findings=[make_finding(target_page=AGONA)]).html

    assert "22. [https://example.org/tahini](https://example.org/tahini)" in html


def test_numbering_reads_the_real_wikis_reference_lists(
    real_repo, build, make_finding
):
    """Guards against fixture pages being tidier than the wiki's real markdown.

    Real reference lines carry query strings, ``#:~:text=`` fragments and
    trailing periods.  The expected number is derived from the live page rather
    than hardcoded, so editing agona.md cannot break this test spuriously.
    """
    expected = _last_reference_number(real_repo / AGONA) + 1

    html = build(real_repo, findings=[make_finding(target_page=AGONA)]).html

    assert f"&lt;sup&gt;{expected}&lt;/sup&gt;" in html
    assert expected > 1, "agona.md should have a populated ## References list"


def _last_reference_number(page):
    """Independently read the last numbered item under ``## References``."""
    text = page.read_text(encoding="utf-8")
    references = text.split("## References", 1)[1]
    numbers = [int(m) for m in re.findall(r"^(\d+)\. ", references, re.MULTILINE)]
    return numbers[-1]
