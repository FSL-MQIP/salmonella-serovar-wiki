"""Delivery behaviour: who gets what, and what happens when config is missing.

No network: every test injects a fake ``post``.  The point of these tests is the
recipient routing — a failed run must never reach the digest recipients.
"""

from __future__ import annotations

import pytest

from wiki_monitor import delivery


def recorder(calls):
    def _post(url, payload, api_key):
        calls.append({"url": url, "payload": payload, "api_key": api_key})
        return {"id": "msg_123"}

    return _post


def test_digest_goes_to_the_configured_recipients_and_cc():
    calls = []
    env = {
        "RESEND_API_KEY": "re_test",
        "DIGEST_TO": "lead@example.org, contributor@example.org",
        "DIGEST_CC": "tech@example.org",
    }

    delivery.send_digest("<p>Digest</p>", "Weekly digest", env, post=recorder(calls))

    payload = calls[0]["payload"]
    assert payload["to"] == ["lead@example.org", "contributor@example.org"]
    assert payload["cc"] == ["tech@example.org"]
    assert payload["subject"] == "Weekly digest"
    assert calls[0]["api_key"] == "re_test"


def test_a_single_recipient_and_no_cc_is_fine():
    """The trial-run configuration: one address, nobody copied."""
    calls = []
    env = {"RESEND_API_KEY": "re_test", "DIGEST_TO": "only@example.org"}

    delivery.send_digest("<p>Digest</p>", "Subject", env, post=recorder(calls))

    payload = calls[0]["payload"]
    assert payload["to"] == ["only@example.org"]
    assert "cc" not in payload, "an empty cc is omitted rather than sent empty"


def test_the_monitor_refuses_to_guess_digest_recipients():
    with pytest.raises(delivery.ConfigError, match="DIGEST_TO"):
        delivery.send_digest("<p>x</p>", "s", {"RESEND_API_KEY": "re_test"})


def test_a_missing_api_key_is_reported_clearly():
    with pytest.raises(delivery.ConfigError, match="RESEND_API_KEY"):
        delivery.send_digest("<p>x</p>", "s", {"DIGEST_TO": "a@example.org"})


def test_the_failure_notice_never_reaches_the_digest_recipients():
    """"No news" and "broken" must not be confusable — see the PRD failure path."""
    calls = []
    env = {
        "RESEND_API_KEY": "re_test",
        "DIGEST_TO": "lead@example.org,contributor@example.org",
        "DIGEST_CC": "tech@example.org",
        "FAILURE_TO": "tech@example.org",
    }

    delivery.send_failure("openFDA fetch failed", "https://run/1", env, post=recorder(calls))

    payload = calls[0]["payload"]
    assert payload["to"] == ["tech@example.org"]
    assert "cc" not in payload
    assert "lead@example.org" not in str(payload)
    assert "contributor@example.org" not in str(payload)


def test_the_failure_notice_is_visibly_different_and_carries_no_digest():
    calls = []
    env = {"RESEND_API_KEY": "re_test", "FAILURE_TO": "tech@example.org"}

    delivery.send_failure("openFDA returned 500", "https://run/1", env, post=recorder(calls))

    payload = calls[0]["payload"]
    assert "FAILED" in payload["subject"]
    assert "openFDA returned 500" in payload["html"]
    assert "https://run/1" in payload["html"]
    assert "Actionable findings" not in payload["html"]


def test_a_failure_after_sending_does_not_claim_nothing_was_sent():
    """A state-push or upload failure happens after delivery.

    Claiming "no digest was sent" there invites a re-run that delivers the same
    findings to the Project Lead twice.
    """
    calls = []
    env = {"RESEND_API_KEY": "re_test", "FAILURE_TO": "tech@example.org"}

    delivery.send_failure(
        "state push rejected", "https://run/1", env,
        post=recorder(calls), digest_sent=True,
    )

    payload = calls[0]["payload"]
    assert "No digest was sent" not in payload["html"]
    assert "already been sent" in payload["html"]
    assert "Do not simply re-run" in payload["html"]
    assert "after sending" in payload["subject"]


def test_a_failure_before_sending_still_says_nothing_went_out():
    calls = []
    env = {"RESEND_API_KEY": "re_test", "FAILURE_TO": "tech@example.org"}

    delivery.send_failure("openFDA unreachable", "", env, post=recorder(calls))

    payload = calls[0]["payload"]
    assert "No digest was sent" in payload["html"]
    assert "after sending" not in payload["subject"]


def test_the_failure_path_does_not_fall_back_to_the_digest_list():
    """FAILURE_TO is deliberately separate; unset means refuse, not broadcast."""
    with pytest.raises(delivery.ConfigError, match="FAILURE_TO"):
        delivery.send_failure(
            "boom", "", {"RESEND_API_KEY": "re_test", "DIGEST_TO": "lead@example.org"}
        )


def test_the_sender_falls_back_to_resends_test_address():
    """It needs no domain verification, but only delivers to the account owner."""
    calls = []
    env = {"RESEND_API_KEY": "re_test", "DIGEST_TO": "me@example.org"}

    delivery.send_digest("<p>x</p>", "s", env, post=recorder(calls))

    assert "onboarding@resend.dev" in calls[0]["payload"]["from"]


def test_a_configured_sender_wins():
    calls = []
    env = {
        "RESEND_API_KEY": "re_test",
        "DIGEST_TO": "me@example.org",
        "DIGEST_FROM": "Monitor <monitor@wiki.example.org>",
    }

    delivery.send_digest("<p>x</p>", "s", env, post=recorder(calls))

    assert calls[0]["payload"]["from"] == "Monitor <monitor@wiki.example.org>"
