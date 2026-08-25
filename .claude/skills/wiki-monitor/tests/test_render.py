"""Rendering behaviour of the digest module."""

from __future__ import annotations

from wiki_monitor.digest import CoverageGap, ExcludedItem


def test_digest_has_the_three_sections(wiki_repo, build, make_finding):
    result = build(wiki_repo, findings=[make_finding()])

    assert "Actionable findings" in result.html
    assert "Coverage gaps" in result.html
    assert "Reviewed but not included" in result.html


def test_actionable_finding_shows_what_the_reviewer_needs_to_judge_it(
    wiki_repo, build, make_finding
):
    result = build(wiki_repo, findings=[make_finding()])
    html = result.html

    # Which serovar, which page, which section the entry belongs in.
    assert "Agona" in html
    assert "docs/serovars/group-b/agona.md" in html
    assert "Recalls" in html
    # Which criterion it satisfies, and why.
    assert "novel commodity" in html
    assert "Tahini is not yet documented on the Agona page." in html
    # The paste-ready entry itself.
    assert "| 2026 | US: multistate | [Tahini](https://example.org/tahini)" in html


def test_coverage_gap_names_the_uncovered_serovar_and_where_it_appeared(
    wiki_repo, build
):
    gap = CoverageGap(
        serovar="Kentucky",
        data_source="pubmed",
        source_id="40123456",
        title="Emergence of MDR Salmonella Kentucky ST198 in poultry",
        url="https://pubmed.ncbi.nlm.nih.gov/40123456/",
    )

    html = build(wiki_repo, coverage_gaps=[gap]).html

    assert "Kentucky" in html
    assert "Emergence of MDR Salmonella Kentucky ST198 in poultry" in html
    assert "https://pubmed.ncbi.nlm.nih.gov/40123456/" in html


def test_reviewed_item_states_why_it_was_excluded(wiki_repo, build):
    item = ExcludedItem(
        data_source="food-safety-news",
        source_id="https://foodsafetynews.example/item/99",
        serovar="Agona",
        title="Routine sampling finds Salmonella in pet treats",
        url="https://foodsafetynews.example/item/99",
        exclusion_reason="No serovar-specific novelty; commodity already documented.",
    )

    html = build(wiki_repo, excluded=[item]).html

    assert "Routine sampling finds Salmonella in pet treats" in html
    assert "No serovar-specific novelty; commodity already documented." in html


def test_a_bounded_scan_says_so_before_reporting_what_it_found(
    wiki_repo, build, make_finding
):
    """Otherwise a truncated candidate pool reads as a complete scan."""
    note = "PubMed: took the 200 most recent of 431 matching papers in this window."

    html = build(wiki_repo, findings=[make_finding()], notes=[note]).html

    assert note in html
    assert html.index(note) < html.index("Actionable findings"), (
        "the caveat must precede the findings it qualifies"
    )


def test_an_unbounded_scan_adds_no_caveat(wiki_repo, build, make_finding):
    html = build(wiki_repo, findings=[make_finding()]).html

    assert "Scan coverage" not in html


def test_the_digest_is_a_complete_styled_html_document(wiki_repo, build, make_finding):
    """The digest is opened in a browser, so it must carry its own document
    skeleton and stylesheet rather than render as bare default-styled fragments."""
    html = build(wiki_repo, findings=[make_finding()]).html

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "<style>" in html
    assert '<meta charset="utf-8"' in html


def test_a_run_with_nothing_to_report_still_renders_all_three_sections(
    wiki_repo, build
):
    html = build(wiki_repo).html

    assert "Actionable findings" in html
    assert "Coverage gaps" in html
    assert "Reviewed but not included" in html
    # A quiet week says so, rather than showing three bare headings.
    assert "No actionable findings" in html
