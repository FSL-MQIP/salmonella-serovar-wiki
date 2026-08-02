"""Command-line behaviour, especially what happens when nothing is sent.

These exercise the paths the workflow depends on, without network or email.
"""

from __future__ import annotations

import json

import pytest

from wiki_monitor import cli

FINDINGS = {
    "findings": [
        {
            "source": "openfda",
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


def test_no_send_writes_the_digest_but_leaves_state_alone(
    wiki_repo, findings_file, tmp_path, capsys
):
    """The workflow's default: publish the digest without touching anyone's inbox."""
    out = tmp_path / "digest.html"

    exit_code = cli.main(
        [
            "--repo-root", str(wiki_repo),
            "deliver", "--findings", str(findings_file),
            "--out", str(out), "--no-send",
        ]
    )

    assert exit_code == 0
    assert "&lt;sup&gt;22&lt;/sup&gt;" in out.read_text(encoding="utf-8")
    assert not (wiki_repo / cli.STATE_PATH).exists(), (
        "nothing was reported, so recording it would lose these findings"
    )
    assert "Nothing sent" in capsys.readouterr().out


def test_no_send_still_reports_validation_problems(
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
            "deliver", "--findings", str(findings_file),
            "--out", str(tmp_path / "d.html"), "--no-send",
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


def test_fetch_notes_reach_the_delivered_digest(
    wiki_repo, findings_file, tmp_path
):
    """The note recorded at fetch has to survive into what recipients read."""
    payload = dict(FINDINGS)
    payload["notes"] = ["openFDA: took 100 of 137 matching recalls in the window."]
    findings_file.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "digest.html"

    cli.main(
        [
            "--repo-root", str(wiki_repo),
            "deliver", "--findings", str(findings_file),
            "--out", str(out), "--no-send",
        ]
    )

    assert "took 100 of 137 matching recalls" in out.read_text(encoding="utf-8")


def test_no_send_leaves_no_sent_marker(wiki_repo, findings_file, tmp_path, monkeypatch):
    """Otherwise a later failure would wrongly report that a digest went out."""
    monkeypatch.chdir(tmp_path)

    cli.main(
        [
            "--repo-root", str(wiki_repo),
            "deliver", "--findings", str(findings_file),
            "--out", str(tmp_path / "d.html"), "--no-send",
        ]
    )

    assert not (tmp_path / cli.SENT_MARKER).exists()


def test_the_failure_command_reports_a_digest_that_did_go_out(
    tmp_path, monkeypatch, capsys
):
    from wiki_monitor import delivery

    calls = []
    monkeypatch.chdir(tmp_path)
    (tmp_path / cli.SENT_MARKER).write_text("msg_1", encoding="utf-8")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("FAILURE_TO", "tech@example.org")
    monkeypatch.setattr(
        delivery,
        "_post",
        lambda url, payload, key: calls.append(payload) or {"id": "m"},
    )

    cli.main(["fail", "--summary", "state push rejected"])

    assert "already been sent" in calls[0]["html"]


def test_the_failure_command_exits_cleanly_with_no_transport_configured(
    capsys, monkeypatch, tmp_path
):
    """A red run is the signal; failing here too would bury the real error."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("FAILURE_TO", raising=False)

    exit_code = cli.main(["fail", "--summary", "boom"])

    assert exit_code == 0
    assert "No failure notification sent" in capsys.readouterr().out
