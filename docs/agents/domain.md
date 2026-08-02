# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase.

This is a **single-context** repo: one `CONTEXT.md` and one `docs/adr/` at the root.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the project's glossary and domain language.
- **`docs/adr/`** — read the ADRs that touch the area you're about to work in.

If either doesn't exist, **proceed silently**. Don't flag their absence and don't
suggest creating them upfront. The producer skill (`/grill-with-docs`) creates them
lazily, when terms or decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md
├── docs/
│   ├── adr/
│   │   ├── 0001-....md
│   │   └── 0002-....md
│   ├── agents/          ← this directory
│   └── serovars/        ← published wiki content
└── mkdocs.yml
```

Note that `docs/` is the MkDocs source directory for the published site. `docs/agents/`
and `docs/adr/` are excluded from the build via `exclude_docs` in `mkdocs.yml` — if you
add another internal docs directory under `docs/`, exclude it there too or it will be
published to https://fsl-mqip.github.io/salmonella-serovar-wiki/.

## Use the glossary's vocabulary

When your output names a domain concept — an issue title, a refactor proposal, a
hypothesis, a test name — use the term as defined in `CONTEXT.md`. Don't drift to
synonyms the glossary explicitly avoids.

This matters more than usual here: serovar nomenclature is load-bearing and easy to
get subtly wrong. If the concept you need isn't in the glossary yet, that's a signal —
either you're inventing language the project doesn't use (reconsider), or there's a
real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than
silently overriding:

> _Contradicts ADR-0007 (…) — but worth reopening because…_
