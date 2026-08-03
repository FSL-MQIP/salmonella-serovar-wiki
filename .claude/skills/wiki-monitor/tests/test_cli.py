"""Command-line behaviour.

The digest is generated and read locally; there is no transport. Rendering is
therefore repeatable, and recording state is the one irreversible step.
"""

from __future__ import annotations

import json

import pytest

from wiki_monitor import cli

FINDINGS = {
    "findings": [
        {
            "data_source": "openfda",
            "source_id": "F-1234-2026",
            "serovar": "Agona",
            "target_page": "docs/serovars/group-b/agona.md",
            "target_section": "Recalls",
            "criterion": "novel commodity",
            "criterion_reason": "Tahini is not yet documented.",
            "entry": "| 2026 | US | [Tahini](https://x/1)<sup>{footnote}</sup> | RTE |",
            "citation_url": "https://x/1",
        }
    ],
    "excluded": [],
    "coverage_gaps": [],
}


@pytest.fixture
def findings_file(tmp_path):
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(FINDINGS), encoding="utf-8")
    return path


def test_rendering_writes_the_digest_and_leaves_state_alone(
    wiki_repo, findings_file, tmp_path, capsys
):
    """The default is consequence-free: read it first, record it deliberately."""
    out = tmp_path / "digest.html"

    exit_code = cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(out),
        ]
    )

    assert exit_code == 0
    assert "&lt;sup&gt;22&lt;/sup&gt;" in out.read_text(encoding="utf-8")
    assert not (wiki_repo / cli.STATE_PATH).exists(), (
        "nothing was reported, so recording it would lose these findings"
    )
    assert "State unchanged" in capsys.readouterr().out


def test_record_marks_the_findings_reported(wiki_repo, findings_file, tmp_path, capsys):
    """The one irreversible act in a local run, so it is opt-in."""
    exit_code = cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(tmp_path / "digest.html"), "--record",
        ]
    )

    assert exit_code == 0
    state = json.loads((wiki_repo / cli.STATE_PATH).read_text(encoding="utf-8"))
    assert [(e["source_id"], e["serovar"]) for e in state["reported"]] == [
        ("F-1234-2026", "Agona")
    ]
    assert "Recorded" in capsys.readouterr().out


def test_a_recorded_finding_does_not_come_back(wiki_repo, findings_file, tmp_path):
    """Rendering twice with --record between must not re-report the same finding."""
    args = [
        "--repo-root", str(wiki_repo),
        "render", "--findings", str(findings_file),
        "--out", str(tmp_path / "digest.html"),
    ]
    cli.main(args + ["--record"])

    cli.main(args)

    second = (tmp_path / "digest.html").read_text(encoding="utf-8")
    assert "F-1234-2026" not in second
    assert "No actionable findings" in second


def test_rendering_reports_validation_problems(
    wiki_repo, findings_file, tmp_path, capsys
):
    bad = dict(FINDINGS)
    bad["findings"] = [
        {**FINDINGS["findings"][0], "target_section": "Vaccine Development"}
    ]
    findings_file.write_text(json.dumps(bad), encoding="utf-8")

    cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(tmp_path / "d.html"),
        ]
    )

    assert "missing-section" in capsys.readouterr().out


def test_fetch_records_what_the_classifier_needs(wiki_repo, tmp_path, monkeypatch):
    """No network: the source layer is stubbed, the plumbing is what's under test."""
    monkeypatch.setattr(cli.sources, "fetch_all", lambda *a, **k: [])
    out = tmp_path / "candidates.json"

    cli.main(["--repo-root", str(wiki_repo), "fetch", "--out", str(out)])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["first_run"] is True
    assert payload["scan_window"]["since"].startswith("2026-05-04")
    assert "Agona" in payload["covered_serovars"]
    assert payload["already_reported"] == []


def test_fetch_notes_reach_the_rendered_digest(
    wiki_repo, findings_file, tmp_path
):
    """The note recorded at fetch has to survive into what the reader sees."""
    payload = dict(FINDINGS)
    payload["notes"] = ["openFDA: took 100 of 137 matching recalls in the window."]
    findings_file.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "digest.html"

    cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(out),
        ]
    )

    assert "took 100 of 137 matching recalls" in out.read_text(encoding="utf-8")


def test_the_schema_command_is_generated_from_the_dataclasses(capsys):
    """So the documented contract cannot drift from the code.

    A field rename reached the code and the JSON example but not the sentence
    describing candidates, and a session can be served a SKILL.md older than the
    repository. This command is the authority precisely because nobody types it.
    """
    from dataclasses import fields as dc_fields

    from wiki_monitor import digest

    cli.main(["schema"])
    out = capsys.readouterr().out

    for record_type in (digest.Finding, digest.ExcludedItem, digest.CoverageGap):
        for field in dc_fields(record_type):
            assert field.name in out, f"{record_type.__name__}.{field.name} undocumented"
    assert "source_id" in out
    # The pre-rename name must not appear as a field of its own.
    assert "\n    source\n" not in out


def test_writing_into_a_missing_directory_creates_it(wiki_repo, tmp_path, monkeypatch):
    """A bare FileNotFoundError traceback says nothing about what to do."""
    monkeypatch.setattr(cli.sources, "fetch_all", lambda *a, **k: [])
    out = tmp_path / "does" / "not" / "exist" / "candidates.json"

    assert cli.main(["--repo-root", str(wiki_repo), "fetch", "--out", str(out)]) == 0
    assert out.is_file()


def test_a_misspelled_top_level_key_fails_instead_of_rendering_a_quiet_week(
    wiki_repo, findings_file, tmp_path, capsys
):
    """The worst possible outcome is a broken run that looks like a quiet week.

    Without this check, {"finding": [...]} left the renderer nothing to show and
    produced a digest reading "No actionable findings this run" — exit 0, no
    warning, indistinguishable from a genuinely empty week.
    """
    findings_file.write_text(
        json.dumps({"finding": FINDINGS["findings"]}), encoding="utf-8"
    )
    out = tmp_path / "digest.html"

    exit_code = cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(out),
        ]
    )

    assert exit_code == 1
    assert "unrecognised top-level ['finding']" in capsys.readouterr().err
    assert not out.exists(), "no digest is written from an unreadable input"


def test_a_non_text_field_value_is_reported_before_it_reaches_the_renderer(
    wiki_repo, findings_file, tmp_path, capsys
):
    findings_file.write_text(
        json.dumps({"findings": [{**FINDINGS["findings"][0], "entry": 42}]}),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(tmp_path / "d.html"),
        ]
    )

    assert exit_code == 1
    assert "non-text values for ['entry']" in capsys.readouterr().err


def test_an_unwritable_output_path_names_the_path_that_was_asked_for(
    wiki_repo, tmp_path, monkeypatch, capsys
):
    """A parent that is a file must not produce an error blaming the parent."""
    monkeypatch.setattr(cli.sources, "fetch_all", lambda *a, **k: [])
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    target = blocker / "candidates.json"

    exit_code = cli.main(["--repo-root", str(wiki_repo), "fetch", "--out", str(target)])

    assert exit_code == 1
    assert f"Cannot write {target}" in capsys.readouterr().err


def test_findings_json_needs_none_of_its_top_level_keys(
    wiki_repo, findings_file, tmp_path
):
    """An empty object is a legitimate nothing-to-report run, not an error."""
    findings_file.write_text("{}", encoding="utf-8")
    out = tmp_path / "digest.html"

    assert (
        cli.main(
            [
                "--repo-root", str(wiki_repo),
                "render", "--findings", str(findings_file),
                "--out", str(out),
            ]
        )
        == 0
    )
    assert "No actionable findings" in out.read_text(encoding="utf-8")


def test_the_old_source_key_is_rejected_by_name(
    wiki_repo, findings_file, tmp_path, capsys
):
    """findings.json is written by a model, so a stale field name is likely.

    It should say which entry and which field rather than raising a bare TypeError
    from inside a comprehension.
    """
    stale = {**FINDINGS["findings"][0]}
    stale["source"] = stale.pop("data_source")
    findings_file.write_text(json.dumps({"findings": [stale]}), encoding="utf-8")

    exit_code = cli.main(
        [
            "--repo-root", str(wiki_repo),
            "render", "--findings", str(findings_file),
            "--out", str(tmp_path / "d.html"),
        ]
    )

    assert exit_code == 1
    message = capsys.readouterr().err
    assert "findings[0]" in message
    assert "unexpected ['source']" in message
    assert "missing ['data_source']" in message