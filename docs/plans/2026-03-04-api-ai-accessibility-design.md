# Design: API Exposure & AI Agent Accessibility for the Salmonella Serovar Wiki

**Date:** 2026-03-04  
**Status:** Brainstorm / Pre-implementation  
**Audience:** External researchers, developers, and AI agents  
**Scope:** Read-only access to the 111 curated serovar pages

---

## 1. Context

The Salmonella Serovar Wiki is a **static MkDocs Material site** deployed to GitHub Pages. It contains 111 serovar pages, each following a consistent eight-section schema:

| Section | Content type |
|---|---|
| At a Glance | Antigenic formula, serogroup, NCBI link |
| Background Information | Narrative prose |
| Genetic Characteristics | Narrative prose |
| Animal Reservoir | Narrative prose |
| Geographical Distribution | Narrative prose |
| Human/Animal Outbreaks | Structured table (year, location, source, cases) |
| Border Rejections | Structured table (year, countries, source, category) |
| Recalls | Structured table (year, location, food, type) |
| References | Numbered URL list |

The site already produces a `search/search_index.json` (1,013 section-level entries) and a `sitemap.xml` at build time. No backend or API currently exists. The goal is to make this content **programmatically accessible to external developers and AI agents** without requiring a hosted server.

---

## 2. Problem Statement

AI agents and developers currently have no structured way to:

- Retrieve a machine-readable profile for a specific serovar by name or antigenic formula
- Query across all serovars (e.g., "which serovars are associated with poultry outbreaks?")
- Embed wiki content into RAG (Retrieval-Augmented Generation) pipelines
- Discover available serovars and their canonical URLs programmatically
- Invoke the wiki as a tool from within an AI agent framework (e.g., LangChain, Claude, GPT)

---

## 3. Proposed Approaches

Three approaches are proposed, ordered from lowest to highest implementation effort. They are **complementary rather than mutually exclusive** — the recommended path is to implement them in sequence.

---

### Approach A — Static JSON Data Feed (GitHub-hosted, zero infrastructure)

**What it is:** A build-time script that parses all 111 Markdown files and emits structured JSON artifacts committed to the repository and served via GitHub Pages (or the raw GitHub CDN).

**Artifacts produced:**

- `api/serovars/index.json` — a manifest of all serovars with name, serogroup, antigenic formula, and canonical URL
- `api/serovars/{slug}.json` — one file per serovar with all sections parsed into structured fields
- `api/serovars/full.json` — a single concatenated file for bulk download

**How AI agents consume it:**

An agent can `GET https://fsl-mqip.github.io/salmonella-serovar-wiki/api/serovars/typhimurium.json` and receive a structured JSON object. The index file allows discovery. No authentication, no rate limits, no server costs.

**Trade-offs:**

| Pros | Cons |
|---|---|
| Zero hosting cost — runs entirely on GitHub Actions + Pages | No query/filter capability; agents must download and filter client-side |
| Automatically kept in sync with content via CI | JSON files add ~1–2 MB to the repository |
| Works immediately with any HTTP client or AI tool | No semantic search; keyword matching only |
| No new infrastructure to maintain | Requires a one-time Markdown parser script |

**Recommendation:** This is the **foundation** that all other approaches build on. It should be implemented first.

---

### Approach B — `llms.txt` + `llms-full.txt` Standard (AI crawler convention)

**What it is:** A pair of plain-text files placed at the site root, following the emerging [llms.txt convention](https://llmstxt.org/) proposed for AI-readable site summaries. This is a lightweight complement to Approach A.

- `llms.txt` — a concise Markdown index listing all serovar pages with one-line descriptions and links
- `llms-full.txt` — the full concatenated plain-text content of all 111 serovar pages, stripped of HTML/Markdown syntax, suitable for direct ingestion into an LLM context window

**How AI agents consume it:**

LLM-based agents and crawlers (e.g., Perplexity, OpenAI's web browsing tool, custom RAG pipelines) increasingly check for `llms.txt` at the domain root as a hint for structured content. A single `fetch("https://fsl-mqip.github.io/salmonella-serovar-wiki/llms.txt")` gives an agent a navigable map of the entire wiki.

**Trade-offs:**

| Pros | Cons |
|---|---|
| Trivially generated at build time alongside Approach A | Not yet a formal standard; adoption is still emerging |
| Immediately improves discoverability for LLM web-browsing tools | `llms-full.txt` may be large (~500 KB); agents must chunk it themselves |
| No infrastructure required | Does not enable structured queries |

**Recommendation:** Implement alongside Approach A as it adds negligible complexity.

---

### Approach C — Model Context Protocol (MCP) Server

**What it is:** A lightweight **MCP server** (a JSON-RPC 2.0 protocol used by Claude, Cursor, and other AI agent frameworks) that exposes the wiki as a set of callable **tools**. The server reads the static JSON feed from Approach A and provides structured tool endpoints.

**Tools exposed:**

| Tool name | Description |
|---|---|
| `list_serovars` | Returns the full index of serovars with name, serogroup, and slug |
| `get_serovar` | Returns the full structured profile for a serovar by name or slug |
| `search_serovars` | Full-text search across all serovar content |
| `get_outbreaks` | Returns outbreak records filtered by food source, year range, or location |
| `get_border_rejections` | Returns border rejection records with optional filters |

**Deployment options:**

The MCP server can be deployed as a **serverless function** (Cloudflare Workers, Vercel Edge, or AWS Lambda) reading the static JSON feed, keeping hosting costs near zero. Alternatively, it can be packaged as a **local npm/Python package** that developers run alongside their agent.

**Trade-offs:**

| Pros | Cons |
|---|---|
| Native integration with Claude Desktop, Cursor, and LangChain MCP adapters | Requires a hosted endpoint (small cost) or local install |
| Enables structured, filtered queries — not just raw data retrieval | More implementation effort than A or B |
| Agents can call `get_serovar("Typhimurium")` as a first-class tool | Requires maintenance of the server alongside the wiki |
| Supports agentic workflows (multi-step reasoning over serovar data) | |

**Recommendation:** Implement after A and B are stable. This is the highest-value option for AI agent integration.

---

## 4. Recommended Implementation Sequence

```
Phase 1 (low effort, high impact):
  → Approach A: Static JSON feed (build script + GitHub Actions)
  → Approach B: llms.txt / llms-full.txt (generated alongside JSON)

Phase 2 (medium effort, highest AI agent value):
  → Approach C: MCP server reading the Phase 1 JSON feed
```

---

## 5. JSON Schema Design (for Approach A)

Each per-serovar JSON file should follow this schema:

```json
{
  "name": "Typhimurium",
  "slug": "typhimurium",
  "serogroup": "O:4 (B)",
  "antigenic_formula": "1,4,[5],12:i:1,2",
  "ncbi_pathogen_detection_url": "https://www.ncbi.nlm.nih.gov/pathogens/isolates/",
  "url": "https://fsl-mqip.github.io/salmonella-serovar-wiki/serovars/group-b/typhimurium/",
  "source_file": "docs/serovars/group-b/typhimurium.md",
  "last_updated": "2026-02-27",
  "sections": {
    "background": "<plain text>",
    "genetic_characteristics": "<plain text>",
    "animal_reservoir": "<plain text>",
    "geographical_distribution": "<plain text>"
  },
  "outbreaks": [
    { "year": "2024-2025", "location": "US: multistate", "source": "Cucumbers", "cases": "113", "reference_url": "..." }
  ],
  "border_rejections": [
    { "year": "2025", "exporting_country": "Brazil", "importing_country": "Netherlands", "source": "Frozen chicken meat", "category": "Poultry meat and poultry meat products", "reference_url": "..." }
  ],
  "recalls": [
    { "year": "2024-2025", "location": "US: multistate", "food": "Cucumbers", "type": "Fruits and vegetables", "reference_url": "..." }
  ],
  "references": [
    "https://academic.oup.com/jac/..."
  ]
}
```

---

## 6. Open Questions for Next Steps

1. **Hosting for MCP server:** Should Approach C be deployed as a public hosted endpoint (Cloudflare Workers / Vercel) or distributed as a local package for developers to self-host?
2. **Versioning:** Should the JSON feed be versioned (e.g., `api/v1/serovars/`) to allow future schema changes without breaking consumers?
3. **License/attribution:** Should the JSON feed include a `citation` field pointing to the mSphere paper to encourage proper attribution?
4. **Scope of Approach C filters:** Are outbreak filters by food category, year range, and country sufficient, or are additional query dimensions needed (e.g., by antimicrobial resistance profile)?

---

## 7. Next Step

Invoke the **writing-plans** skill to create a detailed implementation plan for Phase 1 (Approaches A and B).
