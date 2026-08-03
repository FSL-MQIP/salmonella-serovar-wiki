"""State-file behaviour.

State is keyed on (source's own stable identifier, serovar) and records what the
digest *reported*, so nothing is reported twice.  See ADR 0001 and ADR 0003.
"""

from __future__ import annotations

AGONA = "docs/serovars/group-b/agona.md"
DUBLIN = "docs/serovars/group-d/dublin.md"


def reported_pairs(state):
    return {(entry["source_id"], entry["serovar"]) for entry in state["reported"]}


def test_a_first_run_creates_state_from_nothing(wiki_repo, build, make_finding):
    result = build(wiki_repo, findings=[make_finding()], state=None)

    assert reported_pairs(result.state) == {("F-1234-2026", "Agona")}
    assert result.state["last_successful_run"] == "2026-08-02T06:00:00Z"


def test_the_run_timestamp_becomes_the_new_last_successful_run(wiki_repo, build, make_finding):
    prior = {"last_successful_run": "2026-07-26T06:00:00Z", "reported": []}

    result = build(wiki_repo, findings=[make_finding()], state=prior)

    assert result.state["last_successful_run"] == "2026-08-02T06:00:00Z"


def test_prior_entries_are_kept_alongside_the_new_ones(wiki_repo, build, make_finding):
    prior = {
        "last_successful_run": "2026-07-26T06:00:00Z",
        "reported": [
            {"source_id": "F-0001-2026", "serovar": "Dublin", "data_source": "openfda"}
        ],
    }

    result = build(wiki_repo, findings=[make_finding()], state=prior)

    assert reported_pairs(result.state) == {
        ("F-0001-2026", "Dublin"),
        ("F-1234-2026", "Agona"),
    }


def test_an_already_reported_finding_is_not_reported_again(wiki_repo, build, make_finding):
    prior = {
        "last_successful_run": "2026-07-26T06:00:00Z",
        "reported": [
            {"source_id": "F-1234-2026", "serovar": "Agona", "data_source": "openfda"}
        ],
    }

    result = build(wiki_repo, findings=[make_finding()], state=prior)

    assert "F-1234-2026" not in result.html
    assert "No actionable findings" in result.html


def test_the_same_source_item_is_reportable_for_a_second_serovar(wiki_repo, build, make_finding):
    """A recall naming two covered serovars fans out; the key is per serovar."""
    prior = {
        "last_successful_run": "2026-07-26T06:00:00Z",
        "reported": [
            {"source_id": "F-1234-2026", "serovar": "Agona", "data_source": "openfda"}
        ],
    }
    dublin_finding = make_finding(serovar="Dublin", target_page=DUBLIN)

    result = build(wiki_repo, findings=[dublin_finding], state=prior)

    assert "Dublin" in result.html
    assert reported_pairs(result.state) == {
        ("F-1234-2026", "Agona"),
        ("F-1234-2026", "Dublin"),
    }


def test_one_source_item_naming_two_serovars_records_two_entries(wiki_repo, build, make_finding):
    findings = [
        make_finding(serovar="Agona", target_page=AGONA),
        make_finding(serovar="Dublin", target_page=DUBLIN),
    ]

    result = build(wiki_repo, findings=findings)

    assert reported_pairs(result.state) == {
        ("F-1234-2026", "Agona"),
        ("F-1234-2026", "Dublin"),
    }


def test_items_shown_in_the_reviewed_list_are_recorded_too(wiki_repo, build, make_excluded):
    result = build(wiki_repo, excluded=[make_excluded(source_id="fsn-42")])

    assert ("fsn-42", "Agona") in reported_pairs(result.state)


def test_a_finding_the_cap_pushed_down_is_not_recorded(wiki_repo, build, make_finding):
    """It was listed by title, not reported with its entry — it gets another run."""
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 7)]

    result = build(wiki_repo, findings=findings)
    recorded = {source_id for source_id, _ in reported_pairs(result.state)}

    assert recorded == {"F-1-2026", "F-2-2026", "F-3-2026", "F-4-2026", "F-5-2026"}
    assert "F-6-2026" in result.html, "it is still shown in the reviewed list"


def test_a_demoted_finding_can_win_an_actionable_slot_on_a_later_run(
    wiki_repo, build, make_finding, digest_section
):
    """The whole point of not recording it: next week it competes again."""
    crowded = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 7)]
    first = build(wiki_repo, findings=crowded)

    # Next run, only the previously-demoted finding is still in the source window.
    second = build(
        wiki_repo,
        findings=[make_finding(source_id="F-6-2026")],
        state=first.state,
    )
    actionable = digest_section(second.html, "Actionable findings")

    assert "F-6-2026" in actionable
    assert "5-finding cap" not in actionable


def test_a_classifier_excluded_item_is_recorded_even_though_it_was_never_actionable(
    wiki_repo, build, make_finding, make_excluded
):
    """Reported-as-excluded still counts as reported, so it is not re-judged."""
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 7)]
    excluded = [make_excluded(source_id="fsn-7")]

    result = build(wiki_repo, findings=findings, excluded=excluded)
    recorded = {source_id for source_id, _ in reported_pairs(result.state)}

    assert "fsn-7" in recorded
    assert "F-6-2026" not in recorded


def test_items_dropped_by_the_plus_n_more_note_are_not_recorded(wiki_repo, build, make_excluded):
    """They were never shown, so they must compete again next run."""
    excluded = [
        make_excluded(source_id=f"item-{n}", title=f"Candidate {n}")
        for n in range(1, 21)
    ]

    result = build(wiki_repo, excluded=excluded)
    recorded = {source_id for source_id, _ in reported_pairs(result.state)}

    assert "item-15" in recorded
    assert "item-16" not in recorded
    assert len(recorded) == 15


def test_coverage_gaps_are_not_recorded_so_they_keep_being_suggested(wiki_repo, build):
    from wiki_monitor.digest import CoverageGap

    gap = CoverageGap(
        serovar="Kentucky",
        data_source="pubmed",
        source_id="40123456",
        title="MDR Kentucky in poultry",
        url="https://pubmed.ncbi.nlm.nih.gov/40123456/",
    )

    result = build(wiki_repo, coverage_gaps=[gap])

    assert reported_pairs(result.state) == set()


def test_an_already_reported_finding_frees_its_slot_for_the_next_one(wiki_repo, build, make_finding):
    """Dedup happens before the 5-finding cap, not after."""
    prior = {
        "last_successful_run": "2026-07-26T06:00:00Z",
        "reported": [
            {"source_id": "F-1-2026", "serovar": "Agona", "data_source": "openfda"}
        ],
    }
    findings = [make_finding(source_id=f"F-{n}-2026") for n in range(1, 8)]

    result = build(wiki_repo, findings=findings, state=prior)

    # F-1 is already reported, so F-2..F-6 fill the five actionable slots.
    assert "F-6-2026" in result.html
    assert "5-finding cap" in result.html
