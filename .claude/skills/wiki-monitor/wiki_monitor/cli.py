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
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from wiki_monitor import digest, sources

#: The monitor's only permitted write, besides nothing at all.
STATE_PATH = Path(".claude/skills/wiki-monitor/state.json")

#: Dropped in the workspace the moment a digest is away, so the failure path can
#: tell "never sent" from "sent, then something later broke". Never committed.
SENT_MARKER = Path("digest-sent.marker")


def _load_state(repo_root: Path) -> dict | None:
    path = repo_root / STATE_PATH
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write(path: Path, text: str) -> None:
    """Write *text* to *path*, creating parent directories.

    Every failure names the path that was actually asked for. Letting the OS error
    through instead reports whichever component it tripped on — a parent that is a
    file blames the parent, not the output path the caller chose.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise OutputError(f"Cannot write {path}: {error.strerror or error}") from error


def cmd_fetch(args: argparse.Namespace) -> int:
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
    _write(Path(args.out), json.dumps(payload, indent=2, ensure_ascii=False))

    print(
        f"Scanning since {since:%Y-%m-%d} ({'first run' if payload['first_run'] else 'since last run'}). "
        f"{len(candidates)} candidates across "
        f"{len({c.data_source for c in candidates})} sources -> {args.out}"
    )
    for note in notes:
        print(f"  note: {note}")
    return 0


class FindingsError(Exception):
    """findings.json does not match the shape the renderer expects."""


class OutputError(Exception):
    """A file the run was asked to write could not be written."""


#: Everything findings.json may contain. A key outside this set is a mistake, and
#: has to be a loud one: a misspelled "findings" would otherwise leave the renderer
#: with nothing to show and produce a digest reading "No actionable findings this
#: run" — a broken run wearing a quiet week's clothes.
FINDINGS_KEYS = frozenset({"notes", "findings", "excluded", "coverage_gaps"})


def _check_top_level(classified: dict) -> None:
    if not isinstance(classified, dict):
        raise FindingsError(
            f"findings.json must be an object, not {type(classified).__name__}"
        )
    unknown = sorted(set(classified) - FINDINGS_KEYS)
    if unknown:
        raise FindingsError(
            f"findings.json has unrecognised top-level {unknown}. "
            f"Allowed: {sorted(FINDINGS_KEYS)}. Check for a typo — a misspelled "
            "key would silently produce an empty digest."
        )


def _records(record_type, classified: dict, key: str) -> list:
    """Build *record_type* from ``classified[key]``, naming any mismatch.

    findings.json is written by a model following SKILL.md, so a wrong or missing
    field is a live possibility. Constructing the dataclass directly would raise a
    bare TypeError from inside a comprehension; this says which entry and which
    field, because that is what tells the run how to fix it.
    """
    expected = {field.name for field in fields(record_type)}
    built = []
    for index, item in enumerate(classified.get(key, [])):
        if not isinstance(item, dict):
            raise FindingsError(f"{key}[{index}] is {type(item).__name__}, not an object")
        non_text = sorted(k for k, v in item.items() if not isinstance(v, str))
        if non_text:
            raise FindingsError(
                f"{key}[{index}] has non-text values for {non_text}; every field "
                "is a string. Numbers reach the renderer and fail there instead."
            )
        unexpected = sorted(set(item) - expected)
        missing = sorted(expected - set(item))
        if unexpected or missing:
            raise FindingsError(
                f"{key}[{index}] does not match {record_type.__name__}: "
                + ", ".join(
                    part
                    for part in (
                        f"unexpected {unexpected}" if unexpected else "",
                        f"missing {missing}" if missing else "",
                    )
                    if part
                )
                + f". Expected exactly {sorted(expected)}."
            )
        built.append(record_type(**item))
    return built


def cmd_deliver(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    classified = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    _check_top_level(classified)
    state = _load_state(repo_root)
    run_timestamp = _now().isoformat()

    result = digest.build_digest(
        findings=_records(digest.Finding, classified, "findings"),
        excluded=_records(digest.ExcludedItem, classified, "excluded"),
        coverage_gaps=_records(digest.CoverageGap, classified, "coverage_gaps"),
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
        _write(Path(args.out), result.html)
        print(f"Digest written to {args.out}.")

    # The gate is enforced here, not only described in SKILL.md. The workflow
    # already refuses to trust prose for committing; sending — which reaches real
    # people and cannot be undone — should not be the one guarantee left resting
    # on a model following instructions.
    if args.no_send or not _sending_enabled():
        reason = "--no-send" if args.no_send else "MONITOR_SEND is not true"
        # State is deliberately left alone: nothing was reported, so recording
        # these findings would lose them.
        print(f"Nothing sent ({reason}); state left unchanged.")
        return 0

    from wiki_monitor import delivery

    subject = _subject(result)
    message_id = delivery.send_digest(result.html, subject, os.environ)
    # Before writing state: from here on a failure means "sent but not recorded",
    # which the failure notice must say rather than claim nothing went out.
    _write(SENT_MARKER, message_id or "sent")
    print(f"Digest sent (Resend id {message_id}).")

    _write(
        repo_root / STATE_PATH,
        json.dumps(result.state, indent=2, ensure_ascii=False) + "\n",
    )
    print(f"State updated: {len(result.state['reported'])} reported entries.")
    return 0


def _sending_enabled() -> bool:
    return os.environ.get("MONITOR_SEND", "").strip().lower() == "true"


def _subject(result: digest.DigestResult) -> str:
    """Describe what the digest actually shows.

    Counted from the rendered result, not from the classifier's input: findings
    already reported in an earlier run are dropped before the cap applies, so an
    input count could promise five findings above a body that shows none.
    """
    shown = result.actionable_count
    when = datetime.now(timezone.utc).strftime("%d %b %Y")
    if shown == 0:
        return f"Salmonella Wiki Monitor — no actionable findings ({when})"
    plural = "" if shown == 1 else "s"
    return f"Salmonella Wiki Monitor — {shown} finding{plural} ({when})"


def cmd_schema(args: argparse.Namespace) -> int:
    """Print the exact findings.json contract, read off the dataclasses.

    SKILL.md is prose, and prose drifts: a field rename reached the code and the
    JSON example but not the sentence describing candidates, and a run following
    that sentence would have built findings.json with a field `deliver` rejects.
    A session can also be served a cached copy of SKILL.md older than the code.
    This command is generated from the dataclasses themselves, so it cannot drift.
    """
    for key, record_type in (
        ("findings", digest.Finding),
        ("excluded", digest.ExcludedItem),
        ("coverage_gaps", digest.CoverageGap),
    ):
        names = [field.name for field in fields(record_type)]
        print(f"{key}[] — every entry needs exactly these {len(names)} fields:")
        for name in names:
            print(f"    {name}")
        print("    (all values are strings; no other field is accepted)")
    print(f"\nTop-level keys, all optional: {sorted(FINDINGS_KEYS)}")
    print("Any other top-level key is an error — a typo there would otherwise")
    print("render an empty digest that reads like a quiet week.")
    print(
        "\nCopy data_source and source_id straight from the candidate object "
        "rather than\nretyping them."
    )
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiki_monitor", description=__doc__)
    parser.add_argument("--repo-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="collect raw candidates")
    fetch.add_argument("--out", default="candidates.json")
    fetch.set_defaults(func=cmd_fetch)

    deliver = subparsers.add_parser("deliver", help="render, send, update state")
    deliver.add_argument("--findings", default="findings.json")
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

    schema = subparsers.add_parser(
        "schema", help="print the authoritative findings.json field list"
    )
    schema.set_defaults(func=cmd_schema)

    fail = subparsers.add_parser("fail", help="send the failure notification")
    fail.add_argument("--summary", default="A scheduled run failed.")
    fail.add_argument("--run-url", default="")
    fail.set_defaults(func=cmd_fail)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FindingsError, OutputError) as error:
        # These describe a fixable mistake in the run's own output. A traceback
        # buries that; the run needs to read the sentence and act on it.
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
