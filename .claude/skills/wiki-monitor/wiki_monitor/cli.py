"""Command line for the monitor's deterministic halves.

The run is deliberately split so the model's judgement sits between two
mechanical steps:

    fetch   -> candidates.json   (scan window, covered serovars, raw source items)
    ...the skill classifies each candidate against the Update Criteria...
    render  <- findings.json     (render, validate, and optionally record state)

Nothing here judges a candidate, and the classification step touches neither the
network nor the state file.

The digest is produced locally and read locally; there is no transport. Rendering
is therefore repeatable and free of consequence, and the one act that cannot be
undone — recording findings as reported, so they never appear again — is opt-in
via ``--record``.
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
#:
#: The scan window and the fetch's notes are deliberately absent: they are facts
#: recorded by `fetch`, not judgements, so `render` reads them from candidates.json
#: rather than asking for them to be copied across and risking their loss.
FINDINGS_KEYS = frozenset({"findings", "excluded", "coverage_gaps"})


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


def _read_candidates(path: Path) -> dict:
    """The scan window and fetch notes, if candidates.json is to hand.

    Optional on purpose: a hand-written findings.json still renders, just without a
    dated masthead.
    """
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "scan_window": payload.get("scan_window"),
        "notes": payload.get("notes", []),
    }


def _dated_name(stem: str, suffix: str) -> str:
    return f"{stem}-{_now():%Y-%m-%d}{suffix}"


def cmd_render(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    classified = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    _check_top_level(classified)
    state = _load_state(repo_root)
    run_timestamp = _now().isoformat()

    # The scan window and any bounds the fetch hit are read from candidates.json,
    # so the digest can date itself and disclose a partial scan without depending
    # on either being transcribed by hand.
    scan = _read_candidates(Path(args.candidates))

    result = digest.build_digest(
        findings=_records(digest.Finding, classified, "findings"),
        excluded=_records(digest.ExcludedItem, classified, "excluded"),
        coverage_gaps=_records(digest.CoverageGap, classified, "coverage_gaps"),
        state=state,
        repo_root=repo_root,
        run_timestamp=run_timestamp,
        notes=scan.get("notes", []),
        scan_window=scan.get("scan_window"),
    )

    for issue in result.validation:
        print(f"  needs attention [{issue.kind}] {issue.serovar}: {issue.message}")

    # Dated by default: a digest is a snapshot of one window, and overwriting the
    # last one loses the record of what was already reported.
    out = Path(args.out or _dated_name("digest", ".html"))
    _write(out, result.html)
    print(f"\n{_summary(result)}")
    print(f"Digest: {out.resolve().as_uri()}")

    if not args.record:
        print(
            "\nState unchanged. Read the digest, then re-run with --record to mark "
            "these\nfindings reported so they do not come back next time."
        )
        return 0

    _write(
        repo_root / STATE_PATH,
        json.dumps(result.state, indent=2, ensure_ascii=False) + "\n",
    )
    print(
        f"\nRecorded: {len(result.state['reported'])} findings will not be "
        f"reported again.\nState: {(repo_root / STATE_PATH)}"
    )
    return 0


def _summary(result: digest.DigestResult) -> str:
    bits = [f"{result.actionable_count} actionable finding(s)"]
    if result.validation:
        bits.append(f"{len(result.validation)} needing attention")
    return "Rendered " + ", ".join(bits) + "."


def cmd_schema(args: argparse.Namespace) -> int:
    """Print the exact findings.json contract, read off the dataclasses.

    SKILL.md is prose, and prose drifts: a field rename reached the code and the
    JSON example but not the sentence describing candidates, and a run following
    that sentence would have built findings.json with a field `render` rejects.
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


def main(argv: list[str] | None = None) -> int:
    # A Windows console defaults to cp1252, which cannot encode an em-dash or a
    # Greek letter — both of which appear in real paper titles and in this tool's
    # own output. Without this, printing a digest summary raises
    # UnicodeEncodeError on the machine this is meant to run on.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="wiki_monitor", description=__doc__)
    parser.add_argument("--repo-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="collect raw candidates")
    fetch.add_argument("--out", default="candidates.json")
    fetch.set_defaults(func=cmd_fetch)

    render = subparsers.add_parser(
        "render", help="build the digest from findings.json and validate it"
    )
    render.add_argument("--findings", default="findings.json")
    render.add_argument(
        "--candidates",
        default="candidates.json",
        metavar="PATH",
        help="fetch output, read for the scan window and any coverage bounds",
    )
    render.add_argument(
        "--out",
        default="",
        metavar="PATH",
        help="where to write the digest (default: digest-YYYY-MM-DD.html)",
    )
    render.add_argument(
        "--record",
        action="store_true",
        help=(
            "mark these findings reported so they never appear again. Do this only "
            "after reading the digest — it cannot be undone."
        ),
    )
    render.set_defaults(func=cmd_render)

    schema = subparsers.add_parser(
        "schema", help="print the authoritative findings.json field list"
    )
    schema.set_defaults(func=cmd_schema)

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
