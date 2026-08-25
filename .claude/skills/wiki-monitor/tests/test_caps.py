"""The digest's ranking and capping behaviour.

Findings arrive already ranked by the classification step; the module treats
input order as rank order.
"""

from __future__ import annotations


def test_event_findings_are_never_capped(
    wiki_repo, build, make_finding, digest_section
):
    """Each outbreak or recall is a unique, time-sensitive event; deferring one
    costs freshness, so every event finding renders actionable."""
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 9)]

    html = build(wiki_repo, findings=findings).html
    actionable = digest_section(html, "Actionable findings")
    reviewed = digest_section(html, "Reviewed but not included")

    for n in range(1, 9):
        assert f"F-{n}-2026" in actionable, f"F-{n}-2026 should be actionable"
        assert f"F-{n}-2026" not in reviewed


def test_only_five_literature_findings_are_actionable(
    wiki_repo, build, make_literature, digest_section
):
    findings = [make_literature(f"P-{n}") for n in range(1, 8)]

    html = build(wiki_repo, findings=findings).html
    actionable = digest_section(html, "Actionable findings")
    reviewed = digest_section(html, "Reviewed but not included")

    for kept in ("P-1", "P-2", "P-3", "P-4", "P-5"):
        assert kept in actionable, f"{kept} should be actionable"
        assert kept not in reviewed

    for overflow in ("P-6", "P-7"):
        assert overflow not in actionable, f"{overflow} is past the literature cap"
        assert overflow in reviewed


def test_events_do_not_use_up_the_literature_caps_slots(
    wiki_repo, build, make_finding, make_literature, digest_section
):
    """The cap counts literature findings only: seven events ahead of five
    literature findings must not demote any of the literature."""
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 8)]
    findings += [make_literature(f"P-{n}") for n in range(1, 6)]

    html = build(wiki_repo, findings=findings).html
    actionable = digest_section(html, "Actionable findings")

    for n in range(1, 6):
        assert f"P-{n}" in actionable


def test_findings_past_the_cap_say_that_the_cap_is_why_they_were_left_out(
    wiki_repo, build, make_literature, digest_section
):
    findings = [make_literature(f"P-{n}") for n in range(1, 7)]

    html = build(wiki_repo, findings=findings).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert "literature cap" in reviewed


def test_findings_past_the_cap_rank_above_items_judged_not_actionable(
    wiki_repo, build, make_literature, make_excluded, digest_section
):
    findings = [make_literature(f"P-{n}") for n in range(1, 7)]
    excluded = [make_excluded(title="Judged not actionable")]

    html = build(wiki_repo, findings=findings, excluded=excluded).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert reviewed.index("P-6") < reviewed.index("Judged not actionable")


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
    wiki_repo, build, make_finding, make_literature, digest_section
):
    """A prose finding cites nothing; demoting it must not emit href="".

    Genetic Characteristics entries carry no citation URL, so an over-cap one
    would otherwise render an unclickable empty anchor.
    """
    findings = [make_literature(f"P-{n}") for n in range(1, 6)]
    findings.append(
        make_finding(
            source_id="P-6",
            target_section="Genetic Characteristics",
            criterion="novel characteristic",
            entry="Serovar Agona isolates carried a novel plasmid.",
            citation_url="",
        )
    )

    html = build(wiki_repo, findings=findings).html
    reviewed = digest_section(html, "Reviewed but not included")

    assert 'href=""' not in reviewed
    assert "P-6" in reviewed


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
