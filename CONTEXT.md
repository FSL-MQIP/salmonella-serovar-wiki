# Salmonella Serovar Wiki

A curated MkDocs site published by the Cornell Food Safety Laboratory, giving one
standardised profile page per *Salmonella* serovar. This document defines the language
the project uses, so that both people and agents describe the same thing the same way.

## Language

### The wiki itself

**Serovar**:
A serologically distinct variant of *Salmonella*, identified by its antigenic formula.
_Avoid_: strain, subtype, variant, type

**Serovar page**:
The markdown profile for one serovar, following the standardised nine-section format.
_Avoid_: article, entry, profile page

**Covered serovar**:
A serovar that currently has a serovar page. Coverage is a deliberate editorial choice,
not a claim about which serovars exist.

**Section**:
One of the nine `##` headings on a serovar page. Four of them — **Human Outbreaks**,
**Animal Outbreaks**, **Border Rejections**, **Recalls** — hold tables that grow over
time. **Genetic Characteristics** holds prose that gets amended.

**Reference**:
A numbered citation under a page's `## References` heading, pointed at from the body by
a `<sup>N</sup>` marker. Numbering is per page and sequential.

### The monitor

**Monitor**:
The automated process that scans external data sources on a schedule and produces a
digest. The monitor never edits the wiki itself.
_Avoid_: bot, scraper, agent

**Digest**:
The weekly HTML email the monitor produces. Sent to Renato and Anna, with Luke copied.
_Avoid_: newsletter, report, summary, alert

**Actionable finding**:
An item in a digest that names at least one covered serovar, satisfies an **Update
criterion**, and maps to exactly one target page and one target section. Findings that
name only *Salmonella* spp., with no serovar, are not actionable.

**Update criterion**:
One of the four published tests in `docs/data-sources.md` that a finding must satisfy to
be actionable: substantial public health concern, novel commodity, final investigation
update, or (for literature) novel characteristic. Every actionable finding cites which
criterion it satisfies and why, so the reasoning is checkable rather than asserted.

**Wiki-ready entry**:
The paste-ready markdown an actionable finding carries — a table row for the four
tabular sections, or a prose sentence for Genetic Characteristics.

**Target page** / **Target section**:
The serovar page and the section within it that a wiki-ready entry belongs in.

**Coverage gap**:
A serovar that appeared in a scanned data source but has no serovar page. Reported in
its own digest section as a candidate for new coverage. The monitor never drafts the
page itself — creating one requires the At a Glance block, which `MAINTENANCE.md` §5.5
reserves for the Technical Lead.

## Relationships

- A **digest** contains zero or more **actionable findings**
- A source item (a paper, outbreak report, or recall) that names more than one covered
  serovar produces one **actionable finding** per covered serovar, each independently
  checked against the **Update criteria** on its own **target page** — the item is not
  collapsed onto a single "primary" serovar
- An **actionable finding** resolves to exactly one **target page** and one **target section**
- A **wiki-ready entry** appends to a table, or amends prose, in its **target section**
- A table row cites a **reference** through a `<sup>N</sup>` marker; adding a row therefore
  also appends to `## References`. Because **reference** numbering is per page, two
  findings landing on the same **target page** in the same run must not claim the same
  footnote number — numbering is coordinated per page per run, not per finding

## Example dialogue

> **Dev:** "The CDC page says the outbreak source was backyard poultry. Does that go in the Associated source column?"
>
> **Domain expert:** "Yes — that column holds the **food vehicle**, and the link on it goes to wherever we got the claim. Don't put the CDC citation *in* the column as the text; the citation is a **reference** at the bottom of the page, and the row points at it with a superscript number."
>
> **Dev:** "So one row can carry a food vehicle, a link, and a reference marker, all meaning different things?"
>
> **Domain expert:** "Right. And none of those is the **data source** — that's CDC, the place we scanned. Three different senses of the word 'source'."

## Scan window

Every run scans since the last successful run, recorded in the monitor's state. The
first run has no prior state, so it anchors instead to the most recent commit touching
`docs/serovars/` — derived from git history at run time, not a hardcoded day count. As
of this writing that commit is 2026-05-04, so the first live run would backfill roughly
90 days, which is expected to exceed the 5-finding cap and populate a long "Reviewed but
not included" list.

## Source scope

The monitor's v1 source set is intentionally narrow: **openFDA** food enforcement,
**PubMed** E-utilities, and the **Food Safety News** Salmonella-tagged feed. All three
expose real per-record dates, are searchable or filterable by serovar or topic, and
require no API key or bot-evasion workaround.

**CDC**, **FSIS**, **RASFF**, and **NCBI Pathogen Detection** are deferred, not
rejected. Each is already catalogued in `docs/data-sources.md` as a source the wiki
draws on, but none exposes a plain, key-free, date-filterable interface a scheduled job
can rely on without extra infrastructure — a headless browser, bot-fingerprint evasion,
or a paid cloud query engine. Extending the monitor to one of them is a well-scoped
future ticket, not a v1 blocker.

## Flagged ambiguities

- **"Source" was used three ways** — resolved into three distinct terms:
  - **Food vehicle** — the implicated food or exposure (`Cucumbers`, `Backyard poultry`, `Not identified`). This is what the `Associated source` *column* actually contains, despite its name.
  - **Reference** — the numbered citation under `## References`.
  - **Data source** — an upstream system the monitor scans (CDC, openFDA, PubMed, RASFF), as catalogued in `docs/data-sources.md`.

  The column heading `Associated source` is entrenched across 109+ pages and is not worth
  renaming, but anything generating rows must fill it with the **food vehicle**. The
  previous monitor got this wrong and emitted the literal string `Associated source` as a
  row value.

- **"Digest" cadence was ambiguous** — `MAINTENANCE.md` §2 said biweekly; the monitor that
  actually ran was weekly. Resolved: **weekly**. §2 needs correcting to match.
