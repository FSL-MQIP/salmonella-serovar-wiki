"""Command line for the monitor's deterministic halves.

The run is deliberately split so the model's judgement sits between two
mechanical steps:

    fetch    -> candidates.json   (state, scan window, raw source items)
    ...the skill classifies each candidate against the Update Criteria...
    deliver  <- findings.json     (render, validate, send, update state)
    fail                          (failure notification only)

Nothing here judges a candidate, and the classification step touches neither the
network nor the state file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from wiki_monitor import digest, sources

#: The monitor's only permitted write, besides nothing at all.
STATE_PATH = Path(".claude/skills/wiki-monitor/state.json")

#: Dropped in the workspace the moment a digest is away, so the failure path can
#: tell "never sent" from "sent, then something later broke". Never committed.
SENT_MARKER = Path("digest-sent.marker")


def _load_state(repo_root: Path):
    path = repo_root / STATE_PATH
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cmd_fetch(args) -> int:
    repo_root = Path(args.repo_root)
    state = _load_state(repo_root)
    since = digest.scan_window_start(state, repo_root)
    now = _now()

    notes: list[str] = []
    candidates = sources.fetch_all(
        since, now, email=os.environ.get("NCBI_EMAIL", ""), notes=notes
    )

    payload = {
        "scan_window": {"since": since.isoformat(), "until": now.isoformat()},
        "notes": notes,
        "first_run": not (state or {}).get("last_successful_run"),
        "already_reported": [
            list(pair) for pair in sorted(digest.reported_pairs(state))
        ],
        "covered_serovars": digest.covered_serovars(repo_root),
        "candidates": [candidate.as_dict() for candidate in candidates],
    }
    Path(args.out).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        f"Scanning since {since:%Y-%m-%d} ({'first run' if payload['first_run'] else 'since last run'}). "
        f"{len(candidates)} candidates across "
        f"{len({c.source for c in candidates})} sources -> {args.out}"
    )
    for note in notes:
        print(f"  note: {note}")
    return 0


def cmd_deliver(args) -> int:
    repo_root = Path(args.repo_root)
    classified = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    state = _load_state(repo_root)
    run_timestamp = _now().isoformat()

    result = digest.build_digest(
        findings=[digest.Finding(**item) for item in classified.get("findings", [])],
        excluded=[
            digest.ExcludedItem(**item) for item in classified.get("excluded", [])
        ],
        coverage_gaps=[
            digest.CoverageGap(**item) for item in classified.get("coverage_gaps", [])
        ],
        state=state,
        repo_root=repo_root,
        run_timestamp=run_timestamp,
        # Carried from candidates.json so a bounded scan says so in the digest
        # itself, not just in the run log nobody reads.
        notes=classified.get("notes", []),
    )

    for issue in result.validation:
        print(f"  validation [{issue.kind}] {issue.serovar}: {issue.message}")

    if args.out:
        Path(args.out).write_text(result.html, encoding="utf-8")
        print(f"Digest written to {args.out}.")

    if args.no_send:
        # State is deliberately left alone: nothing was reported, so recording
        # these findings would lose them.
        print("Nothing sent (--no-send); state left unchanged.")
        return 0

    from wiki_monitor import delivery

    subject = args.subject or _subject(result, classified)
    message_id = delivery.send_digest(result.html, subject, os.environ)
    # Before writing state: from here on a failure means "sent but not recorded",
    # which the failure notice must say rather than claim nothing went out.
    SENT_MARKER.write_text(message_id or "sent", encoding="utf-8")
    print(f"Digest sent (Resend id {message_id}).")

    state_file = repo_root / STATE_PATH
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(result.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"State updated: {len(result.state['reported'])} reported entries.")
    return 0


def _subject(result, classified) -> str:
    shown = min(len(classified.get("findings", [])), digest.ACTIONABLE_CAP)
    when = datetime.now(timezone.utc).strftime("%d %b %Y")
    if shown == 0:
        return f"Salmonella Wiki Monitor — no actionable findings ({when})"
    plural = "" if shown == 1 else "s"
    return f"Salmonella Wiki Monitor — {shown} finding{plural} ({when})"


def cmd_fail(args) -> int:
    from wiki_monitor import delivery

    digest_sent = SENT_MARKER.is_file()
    try:
        message_id = delivery.send_failure(
            args.summary, args.run_url, os.environ, digest_sent=digest_sent
        )
    except delivery.ConfigError as error:
        # No transport configured. Say so and exit cleanly: the run is already
        # red, and failing here as well would only bury the original error.
        print(f"No failure notification sent — {error}")
        return 0
    print(f"Failure notice sent (Resend id {message_id}).")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wiki_monitor", description=__doc__)
    parser.add_argument("--repo-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="collect raw candidates")
    fetch.add_argument("--out", default="candidates.json")
    fetch.set_defaults(func=cmd_fetch)

    deliver = subparsers.add_parser("deliver", help="render, send, update state")
    deliver.add_argument("--findings", default="findings.json")
    deliver.add_argument("--subject", default="")
    deliver.add_argument(
        "--out",
        default="",
        metavar="PATH",
        help="also write the rendered digest HTML here",
    )
    deliver.add_argument(
        "--no-send",
        action="store_true",
        help="render and validate only; send nothing and leave state untouched",
    )
    deliver.set_defaults(func=cmd_deliver)

    fail = subparsers.add_parser("fail", help="send the failure notification")
    fail.add_argument("--summary", default="A scheduled run failed.")
    fail.add_argument("--run-url", default="")
    fail.set_defaults(func=cmd_fail)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
