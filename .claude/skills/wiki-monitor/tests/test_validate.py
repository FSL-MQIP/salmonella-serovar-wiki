"""Validation of a finding's target page, target section, and footnote.

A finding whose target does not exist is *flagged*, never silently dropped —
the reviewer needs to see that the monitor produced something unpasteable.
"""

from __future__ import annotations

AGONA = "docs/serovars/group-b/agona.md"
DUBLIN = "docs/serovars/group-d/dublin.md"


def test_a_valid_finding_raises_no_validation_issues(wiki_repo, build, make_finding):
    result = build(wiki_repo, findings=[make_finding(target_page=AGONA)])

    assert result.validation == []


def test_a_missing_target_page_is_reported(wiki_repo, build, make_finding):
    finding = make_finding(target_page="docs/serovars/group-b/nosuchserovar.md")

    result = build(wiki_repo, findings=[finding])

    assert len(result.validation) == 1
    issue = result.validation[0]
    assert issue.kind == "missing-page"
    assert issue.source_id == "F-1234-2026"
    assert issue.serovar == "Agona"
    assert "nosuchserovar.md" in issue.message


def test_a_missing_target_section_is_reported(wiki_repo, build, make_finding):
    finding = make_finding(target_page=AGONA, target_section="Vaccine Development")

    result = build(wiki_repo, findings=[finding])

    assert len(result.validation) == 1
    issue = result.validation[0]
    assert issue.kind == "missing-section"
    assert "Vaccine Development" in issue.message


def test_an_entry_expecting_a_number_it_cannot_get_is_reported(
    wiki_repo, build, make_finding
):
    """A placeholder with nothing to cite would ship literal {footnote} text."""
    finding = make_finding(target_page=AGONA, citation_url="")

    result = build(wiki_repo, findings=[finding])

    assert [issue.kind for issue in result.validation] == ["unresolved-footnote"]
    assert "{footnote}" in result.html, "the unresolvable entry is shown, not dropped"


def test_a_flagged_finding_still_appears_in_the_digest(wiki_repo, build, make_finding):
    finding = make_finding(target_page="docs/serovars/group-b/nosuchserovar.md")

    result = build(wiki_repo, findings=[finding])

    assert "F-1234-2026" in result.html
    assert "nosuchserovar.md" in result.html


def test_the_digest_warns_the_reader_about_flagged_findings(
    wiki_repo, build, make_finding
):
    findings = [
        make_finding(source_id="F-1-2026", target_page=AGONA),
        make_finding(
            source_id="F-2-2026",
            target_page=AGONA,
            target_section="Vaccine Development",
        ),
    ]

    html = build(wiki_repo, findings=findings).html

    # The reviewer must not paste a flagged entry believing it is verified.
    assert "Needs attention" in html
    assert "Vaccine Development" in html


def test_a_flagged_finding_explains_what_is_wrong(wiki_repo, build, make_finding):
    finding = make_finding(target_page=AGONA, target_section="Vaccine Development")

    html = build(wiki_repo, findings=[finding]).html

    assert "has no ## Vaccine Development section" in html


def test_each_bad_finding_is_reported_separately(wiki_repo, build, make_finding):
    findings = [
        make_finding(source_id="F-1-2026", target_page="docs/serovars/nope.md"),
        make_finding(
            source_id="F-2-2026", target_page=AGONA, target_section="Nonexistent"
        ),
        make_finding(source_id="F-3-2026", target_page=AGONA),
    ]

    result = build(wiki_repo, findings=findings)

    assert [issue.source_id for issue in result.validation] == ["F-1-2026", "F-2-2026"]


def test_a_warning_stays_on_the_serovar_it_belongs_to(wiki_repo, build, make_finding):
    """One source item fanned out across two serovars shares a source id.

    Keying warnings on the source id alone would print the Dublin problem on the
    healthy Agona block and mark both as needing attention.
    """
    findings = [
        make_finding(serovar="Agona", target_page=AGONA),
        make_finding(
            serovar="Dublin", target_page=DUBLIN, target_section="Vaccine Development"
        ),
    ]

    html = build(wiki_repo, findings=findings).html

    assert html.count("Needs attention") == 1
    agona_block, dublin_block = html.split("Dublin", 1)
    assert "Vaccine Development" not in agona_block
    assert "Needs attention" not in agona_block


def test_findings_past_the_actionable_cap_are_validated_too(
    wiki_repo, build, make_finding
):
    """A demoted finding is displayed and recorded, so it must still be checked."""
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 6)]
    findings.append(
        make_finding(source_id="F-6-2026", target_page="docs/serovars/nope.md")
    )

    result = build(wiki_repo, findings=findings)

    assert [issue.source_id for issue in result.validation] == ["F-6-2026"]
