"""Sending the digest, and the separate failure notification.

Transport is Resend's HTTP API.  Recipients and the sender come from the
environment, never from this file — the repository is public, so no address is
committed here, and changing who receives the digest needs no code change.

A failed run must never reach the digest recipients (see the PRD's failure-path
requirement), so the two send paths take their addresses from different
variables and share no default.
"""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.request

RESEND_ENDPOINT = "https://api.resend.com/emails"

#: Resend's test sender.  It needs no domain verification but will only deliver
#: to the address the Resend account was registered with, which is why it is a
#: safe default for a trial run rather than for production.
FALLBACK_SENDER = "Salmonella Wiki Monitor <onboarding@resend.dev>"


class ConfigError(Exception):
    """A required environment variable is missing."""


class SendError(Exception):
    """Resend rejected the message."""


def _addresses(env, name: str) -> list[str]:
    """Parse a comma-separated recipient list from *env*."""
    return [item.strip() for item in env.get(name, "").split(",") if item.strip()]


def _require(env, name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. The monitor will not guess who to email."
        )
    return value


def send_digest(html: str, subject: str, env, post=None) -> str:
    """Email the digest to the configured recipients, cc'ing the configured cc list."""
    to = _addresses(env, "DIGEST_TO")
    if not to:
        raise ConfigError(
            "DIGEST_TO is not set. Set it to a comma-separated recipient list; "
            "the monitor will not guess who to email."
        )
    return _send(
        {
            "from": env.get("DIGEST_FROM", "").strip() or FALLBACK_SENDER,
            "to": to,
            "cc": _addresses(env, "DIGEST_CC"),
            "subject": subject,
            "html": html,
        },
        env,
        post,
    )


def send_failure(
    summary: str, run_url: str, env, post=None, digest_sent: bool = False
) -> str:
    """Tell the Technical Lead alone that a run failed.

    Deliberately carries no digest content and reads nothing from ``DIGEST_TO``,
    so a broken run can never be mistaken for a quiet week by the Project Lead.

    *digest_sent* changes what the notice claims. A run can fail *after* the
    email is away — on the state push, or on uploading the artifact — and saying
    "no digest was sent" there is both false and dangerous: it invites a re-run
    that delivers the same findings twice.
    """
    to = _addresses(env, "FAILURE_TO")
    if not to:
        raise ConfigError(
            "FAILURE_TO is not set. It must name the Technical Lead only, and is "
            "deliberately separate from DIGEST_TO."
        )
    if digest_sent:
        subject = "[FAILED after sending] Salmonella Wiki Monitor run"
        opening = (
            "<p>The Salmonella Wiki Monitor run <strong>failed after the digest "
            "had already been sent</strong>. Recipients have it.</p>"
            "<p><strong>Do not simply re-run.</strong> Check whether the state "
            "file was committed — if it was not, the next run will report the "
            "same findings again.</p>"
        )
    else:
        subject = "[FAILED] Salmonella Wiki Monitor run"
        opening = (
            "<p>The Salmonella Wiki Monitor run <strong>failed</strong>. "
            "No digest was sent.</p>"
        )
    body = f"{opening}<p>{_escape(summary)}</p>"
    if run_url:
        body += f'<p>Run log: <a href="{_escape(run_url)}">{_escape(run_url)}</a></p>'

    return _send(
        {
            "from": env.get("DIGEST_FROM", "").strip() or FALLBACK_SENDER,
            "to": to,
            "subject": subject,
            "html": body,
        },
        env,
        post,
    )


def _send(message: dict, env, post) -> str:
    api_key = _require(env, "RESEND_API_KEY")
    payload = {key: value for key, value in message.items() if value}
    sender = post or _post
    response = sender(RESEND_ENDPOINT, payload, api_key)
    return response.get("id", "")


def _post(url: str, payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        raise SendError(f"Resend returned HTTP {error.code}: {detail}") from error


def _escape(text: str) -> str:
    return html.escape(text)
