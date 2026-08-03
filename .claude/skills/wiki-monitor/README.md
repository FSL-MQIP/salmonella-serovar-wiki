# wiki-monitor — maintainer notes

`SKILL.md` is the instruction set Claude follows to produce a digest. This file is
for whoever changes the code underneath it.

## Run the tests after any change

```bash
python -m pytest
```

From the repository root, about 15 seconds, 82 tests. `pytest.ini` points at this
directory and puts it on `pythonpath`, so no environment setup is needed.

There is deliberately **no CI running these** — the monitor is a local tool, and a
workflow firing on every push produced three notifications per change for a signal
nobody was waiting on. That trade only holds if the suite is actually run, so run
it. Nothing in the suite touches the network: the adapters are driven by recorded
API responses and the git-anchored scan window against throwaway repositories.

## Layout

| Path | Role |
|---|---|
| `wiki_monitor/sources.py` | The three data-source adapters, normalising to `Candidate` |
| `wiki_monitor/digest.py` | Renders the digest, allocates reference numbers, validates targets, updates state |
| `wiki_monitor/cli.py` | `fetch`, `render`, `schema` — the deterministic halves either side of classification |
| `state.json` | Written only by `render --record`; records what has been reported |

`digest.py` is the one part with real invariants worth preserving: reference numbers
are allocated per target page and must not collide, and state records what was
*reported* rather than what was merely listed. Both are covered by tests whose names
say what they protect.

## If you change the findings.json contract

`python -m wiki_monitor schema` prints the field list generated from the dataclasses.
`SKILL.md` points Claude at that command rather than naming fields itself, because a
field list written into prose has already drifted once — a rename reached the code
and not the sentence, and a run following the stale sentence produced output the
renderer rejected.
