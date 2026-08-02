---
name: wiki-monitor
description: Run the weekly Salmonella Wiki Monitor — scan openFDA, PubMed and Food Safety News for developments relevant to the wiki's covered serovars, judge each against the published Update Criteria, and email a paste-ready digest. Use when running the scheduled monitor, or when asked to produce a digest by hand.
---

# Weekly Salmonella Wiki Monitor

You scan three public data sources, judge what you find against the wiki's own
published Update Criteria, and produce a digest the Project Lead can paste
straight into the right page and section.

**You never edit a serovar page.** Content changes go through human review. The
only file this run may write is `.claude/skills/wiki-monitor/state.json`, and the
`deliver` command writes it for you.

Two commands bracket your work. They handle the network, the reference
numbering, the caps, and the state file, so you do only the part that needs
judgement: deciding what matters and writing the wiki-ready entry.

## 1. Fetch

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor fetch --out candidates.json
```

`candidates.json` gives you:

- `scan_window` — what period this run covers, and `first_run` if there is no prior state
- `notes` — anything the fetch had to bound; **repeat these in the digest** if present
- `already_reported` — `(source id, serovar)` pairs from earlier runs. Never report these again
- `covered_serovars` — the 113 serovars that have a page. This is what "covered" means
- `candidates` — each with `source`, `source_id`, `title`, `url`, `published`, `summary`

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

Rank the findings you keep, most important first — the first five become the
digest's actionable findings and the rest are listed as reviewed. Everything you
considered and rejected goes in `excluded` with the reason you rejected it.

### Writing the entry

`entry` is paste-ready markdown matching the target section's existing shape.
Read the target page first and copy its column order exactly.

- **Human Outbreaks** — `| Year | Location | Associated source | Number of cases |`
- **Animal Outbreaks** — same shape as Human Outbreaks
- **Border Rejections** — `| Year | Exporting country | Importing country | Associated source | Product category |`
- **Recalls** — `| Year | Location | Recalled food | Type |`
- **Genetic Characteristics** — a prose sentence, not a row

`Associated source` holds the **food vehicle** — `Cucumbers`, `Backyard poultry`,
`Not identified` — as a markdown link to where the claim came from. It does *not*
hold the string "Associated source", and it is not the citation. A previous
monitor got this wrong.

Where the entry cites its source, write the literal placeholder `{footnote}`
inside a `<sup>` tag and set `citation_url`. The module replaces it with the
correct next reference number for that page and hands you the `## References`
line to paste. Never guess a number yourself.

```
| 2026 | US: multistate | [Tahini](https://example.org/recall)<sup>{footnote}</sup> | Ready-to-Eat food |
```

If an entry needs no citation, leave `citation_url` empty and omit `{footnote}`.

### Write `findings.json`

```json
{
  "findings": [
    {
      "source": "openfda",
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
      "source": "food-safety-news",
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
      "source": "pubmed",
      "source_id": "40123456",
      "title": "MDR Salmonella Kentucky ST198 in poultry",
      "url": "https://pubmed.ncbi.nlm.nih.gov/40123456/"
    }
  ]
}
```

Every field is required. `serovar` on an excluded item may be `"unknown"` if the
candidate named none.

## 3. Deliver

Check your work before sending:

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor deliver \
  --findings findings.json --dry-run digest.html
```

This renders the digest and prints any validation problems without sending.
**Fix anything it flags** — a `missing-page` or `missing-section` means you named
a target that does not exist, and an `unresolved-footnote` means an entry expects
a citation you did not supply. Then send:

```bash
PYTHONPATH=.claude/skills/wiki-monitor python -m wiki_monitor deliver --findings findings.json
```

That sends the digest, writes `state.json`, and prints how many entries it
recorded. Commit `state.json` — and nothing else.

## If a run fails

Let it fail. The workflow's failure step notifies the Technical Lead alone. Do
not send a digest describing the failure, and do not send a partial digest: a
quiet week and a broken run must never look alike.
