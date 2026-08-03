"""The digest's ranking and capping behaviour.

Findings arrive already ranked by the classification step; the module treats
input order as rank order.
"""

from __future__ import annotations


def test_only_five_findings_are_actionable_and_the_rest_are_listed_as_reviewed(
    wiki_repo, build, make_finding, digest_section
):
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 8)]

    html = build(wiki_repo, findings=findings).html
    actionable = digest_section(html, "Actionable findings")
    reviewed = digest_section(html, "Reviewed but not included")

    for kept in ("F-1-2026", "F-2-2026", "F-3-2026", "F-4-2026", "F-5-2026"):
        assert kept in actionable, f"{kept} should be actionable"
        assert kept not in reviewed

    for overflow in ("F-6-2026", "F-7-2026"):
        assert overflow not in actionable, f"{overflow} is past the 5-finding cap"
        assert overflow in reviewed


def test_findings_past_the_cap_say_that_the_cap_is_why_they_were_left_out(
    wiki_repo, build, make_finding, digest_section
):
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 7)]

    html = build(wiki_repo, findings=findings).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert "5-finding cap" in reviewed


def test_findings_past_the_cap_rank_above_items_judged_not_actionable(
    wiki_repo, build, make_finding, make_excluded, digest_section
):
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 7)]
    excluded = [make_excluded(title="Judged not actionable")]

    html = build(wiki_repo, findings=findings, excluded=excluded).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert reviewed.index("F-6-2026") < reviewed.index("Judged not actionable")


def test_reviewed_list_truncates_at_fifteen_and_says_how_many_it_dropped(
    wiki_repo, build, make_excluded, digest_section
):
    excluded = [
        make_excluded(source_id=f"item-{n}", title=f"Candidate {n}")
        for n in range(1, 21)
    ]

    html = build(wiki_repo, excluded=excluded).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert "Candidate 15" in reviewed
    assert "Candidate 16" not in reviewed
    assert "+5 more" in reviewed


def test_a_reviewed_item_with_no_url_is_not_rendered_as_an_empty_link(
    wiki_repo, build, make_finding, digest_section
):
    """A prose finding cites nothing; demoting it must not emit href="".

    Genetic Characteristics entries carry no citation URL, so an over-cap one
    would otherwise render an unclickable empty anchor.
    """
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 6)]
    findings.append(
        make_finding(
            source_id="F-6-2026",
            target_section="Genetic Characteristics",
            entry="Serovar Agona isolates carried a novel plasmid.",
            citation_url="",
        )
    )

    html = build(wiki_repo, findings=findings).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert 'href=""' not in reviewed
    assert "F-6-2026" in reviewed


def test_a_reviewed_list_within_the_cap_has_no_plus_n_more_note(
    wiki_repo, build, make_excluded, digest_section
):
    excluded = [
        make_excluded(source_id=f"item-{n}", title=f"Candidate {n}")
        for n in range(1, 16)
    ]

    html = build(wiki_repo, excluded=excluded).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert "Candidate 15" in reviewed
    # The literal rendered phrase, so an exclusion reason containing the word
    # "more" cannot make this pass or fail by accident.
    assert "more not listed" not in reviewed
