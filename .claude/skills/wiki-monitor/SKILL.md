---
name: wiki-monitor
description: Generate the Salmonella Wiki digest — scan openFDA, PubMed, Food Safety News and FDA CORE outbreak investigations for developments relevant to the wiki's covered serovars, judge each against the published Update Criteria, and produce a paste-ready digest to read locally. Use when asked to run the monitor, check for new Salmonella findings, or produce a digest.
---

# Salmonella Wiki Monitor

You scan four public data sources, judge what you find against the wiki's own
published Update Criteria, and produce a digest whose entries can be pasted
straight into the right page and section.

This runs locally and the digest is read locally. Nothing is emailed and nothing
is published, so **rendering is free of consequence — render as often as you
like.** Exactly one action cannot be undone: `--record`, which marks findings as
reported so they never appear in a future digest. Do that only after the digest
has been read.

**You never edit a serovar page.** Content changes go through human review. The
only file this run may write is `.claude/skills/wiki-monitor/state.json`, and only
when `--record` is passed.

Two commands bracket your work. They handle the network, the reference numbering,
the caps and the state file, so your work is the part that needs judgement:
deciding what matters, and writing the wiki-ready entry.

## 1. Fetch

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor fetch --out candidates.json
```

`candidates.json` gives you:

- `scan_window` — what period this run covers, and `first_run` if there is no prior state
- `notes` — anything the fetch had to bound. You need not carry these anywhere;
  `render` reads them from this file and leads the digest with them, so a partial
  scan is never read as a complete one
- `already_reported` — `(source id, serovar)` pairs from earlier runs. Never report these again
- `covered_serovars` — the 113 serovars that have a page. This is what "covered" means
- `candidates` — each with `data_source`, `source_id`, `title`, `url`, `published`,
  `summary`. Carry `data_source` and `source_id` through to `findings.json`
  unchanged; the field is `data_source`, never `source` — `render` rejects the
  old name outright

A first run has no prior state, so its window reaches back to the last commit
touching the serovar pages — roughly 90 days, and several hundred candidates.
Expect most of them to be irrelevant.

## 2. Classify

Read `docs/data-sources.md` for the four Update Criteria, and `CONTEXT.md` for the
project's vocabulary. Then judge every candidate.

A candidate becomes an **actionable finding** only if all of these hold:

1. It names at least one serovar in `covered_serovars`. A candidate naming only
   *Salmonella* spp. with no serovar is **not** actionable.
2. It satisfies at least one Update Criterion, and you can say which and why.
3. It maps to exactly one target page and one target section.

Three rules that are easy to get wrong:

- **Fan out multi-serovar items.** A recall or paper naming three covered
  serovars produces *three* findings, each checked against the criteria on its
  own target page. Do not collapse them onto a "primary" serovar.
- **An uncovered serovar is a coverage gap, not a finding.** Add it to
  `coverage_gaps`. Never draft a new serovar page — that needs an At a Glance
  block, which `MAINTENANCE.md` §5.5 reserves for the Technical Lead.
- **Check the target page before claiming novelty.** "Novel commodity" means the
  food vehicle is not already on that page; "novel characteristic" means the
  genetic/AMR/reservoir trait is not already described there. Read the page.

Rank the findings you keep, most important first. Every event finding — an
outbreak, recall, or investigation update — renders actionable, because each is
a unique occurrence and deferring one costs freshness. Only literature findings
(criterion "novel characteristic") are capped: the top five render actionable
and the rest are listed as reviewed, competing again next run. The outbreak
criterion is deliberately low (≥2 linked cases), so qualifying is not ranking:
weigh case counts, deaths, resistance, and novelty, and expect a 2-case outbreak
to sit below larger or more novel findings. The reviewing expert, not the
monitor, decides what a small outbreak is worth — your job is to surface it
with the facts that inform that call. Everything you
considered and rejected goes in `excluded` with the reason you rejected it.

### Writing the entry

`entry` is paste-ready markdown matching the target section's existing shape.

**Read the target section and copy the column order you find there.** The pages are
the authority, not this file — a schema written down here would go stale the first
time someone adds a column, and you would not notice. The four tabular sections
take a row; **Genetic Characteristics** takes a prose sentence, not a row.

Two things the shape alone will not tell you:

- `Associated source` holds the **food vehicle** — `Cucumbers`, `Backyard poultry`,
  `Not identified` — as a markdown link to where the claim came from. It does *not*
  hold the string "Associated source", and it is not the citation. A previous
  monitor got this wrong.
- Match the neighbouring rows' conventions for how a value is written, not just
  which column it goes in: how locations are phrased, whether a year or a range is
  used, how an unknown is expressed.

Where the entry cites its source, write the literal placeholder `{footnote}`
inside a `<sup>` tag and set `citation_url`. The module replaces it with the
correct next reference number for that page and hands you the `## References`
line to paste. Never guess a number yourself.

```
| 2026 | US: multistate | [Tahini](https://example.org/recall)<sup>{footnote}</sup> | Ready-to-Eat food |
```

If an entry needs no citation, leave `citation_url` empty and omit `{footnote}`.

### Write `findings.json`

Before you write it, get the field list from the code rather than from this file —
these instructions are prose and can lag behind, and your copy of them may be
older than the repository:

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor schema
```

The example below shows the shape; that command is the authority on field names.

```json
{
  "findings": [
    {
      "data_source": "openfda",
      "source_id": "F-1234-2026",
      "serovar": "Agona",
      "target_page": "docs/serovars/group-b/agona.md",
      "target_section": "Recalls",
      "criterion": "novel commodity",
      "criterion_reason": "Tahini is not yet documented on the Agona page.",
      "entry": "| 2026 | US: multistate | [Tahini](https://example.org/recall)<sup>{footnote}</sup> | Ready-to-Eat food |",
      "citation_url": "https://example.org/recall"
    }
  ],
  "excluded": [
    {
      "data_source": "food-safety-news",
      "source_id": "6a6ab76d...",
      "serovar": "Agona",
      "title": "Routine sampling finds Salmonella in pet treats",
      "url": "https://www.foodsafetynews.com/...",
      "exclusion_reason": "No serovar named beyond Salmonella spp."
    }
  ],
  "coverage_gaps": [
    {
      "serovar": "Kentucky",
      "data_source": "pubmed",
      "source_id": "40123456",
      "title": "MDR Salmonella Kentucky ST198 in poultry",
      "url": "https://pubmed.ncbi.nlm.nih.gov/40123456/"
    }
  ]
}
```

Every field is required. `serovar` on an excluded item may be `"unknown"` if the
candidate named none.

## 3. Render

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor render \
  --findings findings.json
```

The digest is written to `reports/digest-YYYY-MM-DD.html` and dates itself with the window
it covers, so a saved one stays identifiable. **Keep `candidates.json` where it is**
— `render` reads the scan window and the fetch's bounds from it.

This builds the digest, prints anything that needs attention, and leaves
`state.json` alone. **Fix what it flags and render again** — repeating this costs
nothing:

- `missing-page` / `missing-section` — you named a target that does not exist
- `unresolved-footnote` — an entry expects a citation you did not supply
- an error about `findings.json` — run `python -m wiki_monitor schema` and compare

Then give the reader the path it prints, and say what is in the digest: how many
actionable findings, which serovars, and anything that needed attention. Do not
paraphrase the findings themselves — the digest is the artefact, and its entries
are meant to be read and pasted as written.

## 4. Record — only when asked

If, and only if, the reader has seen the digest and wants these findings marked
as dealt with:

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor render \
  --findings findings.json --record
```

This writes `state.json` so those findings never appear in a future digest.
**There is no way to undo it**, and a finding recorded but not acted on is simply
lost — see `docs/adr/0001-digest-reports-findings-once.md`. Do not pass `--record`
on your own initiative, and do not `git commit` anything.

## If something fails

Say so plainly and stop. **Never present a partial digest as a complete one** — a
quiet week and a broken run must not look alike, and the reader has no other way
to tell them apart.

If a source is unreachable, report which one and that its part of the window went
unscanned. If `fetch` reports a `notes` entry, that is a bound on what was
available, not a failure — carry it into `findings.json` so the digest says so.

Do not pass `--record` after a failure. Findings that were never properly reviewed
would be silently retired.
