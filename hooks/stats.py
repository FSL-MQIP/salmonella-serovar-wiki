"""MkDocs hook: compute dynamic statistics from serovar markdown files.

Registered in mkdocs.yml under the `hooks:` key.  The hook fires for every
page; it only does real work on the homepage (``index.md``) and the serovar
database landing page (``serovars/index.md``).

Stats are computed once per build and cached in ``_stats_cache``.
"""

from __future__ import annotations

import pathlib
import re

# ---------------------------------------------------------------------------
# Module-level cache so the scan only runs once per build invocation.
# ---------------------------------------------------------------------------
_stats_cache: dict | None = None


# ---------------------------------------------------------------------------
# Helper: detect table separator rows
# ---------------------------------------------------------------------------
def _is_separator(cell_text: str) -> bool:
    """Return True if *cell_text* looks like a Markdown table separator cell."""
    stripped = cell_text.strip()
    return bool(stripped) and all(ch in "- :" for ch in stripped) and "-" in stripped


# ---------------------------------------------------------------------------
# Core stats computation
# ---------------------------------------------------------------------------
def _compute_stats(docs_dir: pathlib.Path) -> dict:
    """Scan every serovar .md file and return a stats dict."""

    serovars_dir = docs_dir / "serovars"

    # Typhoidal serovars are identified purely by filename.
    typhoidal_filenames = {"typhi.md", "paratyphi-a.md", "paratyphi-b.md", "paratyphi-c.md"}

    total_serovars = 0
    typhoidal_count = 0
    bongori_count = 0
    human_outbreaks = 0
    animal_outbreaks = 0
    border_rejections = 0
    recalls = 0
    group_counts: dict[str, int] = {}

    for md_file in serovars_dir.rglob("*.md"):
        # Skip group/serogroup index pages — they are not individual serovar pages.
        if md_file.name == "index.md":
            continue

        total_serovars += 1
        group = md_file.parent.name
        group_counts[group] = group_counts.get(group, 0) + 1

        # Always read content — needed for bongori detection and table parsing.
        content = md_file.read_text(encoding="utf-8")

        # --- Typhoidal classification ---
        if md_file.name in typhoidal_filenames:
            typhoidal_count += 1

        # --- Bongori classification ---
        if "S. bongori" in content or "Salmonella bongori" in content:
            bongori_count += 1

        # --- Table row counting ---
        lines = content.splitlines()
        current_section: str | None = None
        past_separator = False

        for line in lines:
            if line.startswith("## "):
                past_separator = False
                if line.startswith("## Human Outbreaks"):
                    current_section = "human_outbreaks"
                elif line.startswith("## Animal Outbreaks"):
                    current_section = "animal_outbreaks"
                elif line.startswith("## Border Rejections"):
                    current_section = "rejections"
                elif line.startswith("## Recalls"):
                    current_section = "recalls"
                else:
                    current_section = None
                continue

            if current_section is None:
                continue

            if line.startswith("<sup>"):
                continue

            if not line.startswith("|"):
                continue

            cells = [c for c in line.split("|") if c.strip()]

            if not cells:
                continue

            if all(_is_separator(c) for c in cells):
                past_separator = True
                continue

            if not past_separator:
                continue

            # --- This is a real data row ---
            if current_section == "human_outbreaks":
                human_outbreaks += 1
            elif current_section == "animal_outbreaks":
                animal_outbreaks += 1
            elif current_section == "rejections":
                border_rejections += 1
            elif current_section == "recalls":
                recalls += 1

    nts_count = total_serovars - typhoidal_count - bongori_count

    return {
        "total": total_serovars,
        "typhoidal": typhoidal_count,
        "bongori": bongori_count,
        "nts": nts_count,
        "human_outbreaks": human_outbreaks,
        "animal_outbreaks": animal_outbreaks,
        "border_rejections": border_rejections,
        "recalls": recalls,
        "groups": group_counts,
    }


# ---------------------------------------------------------------------------
# Stat string builders
# ---------------------------------------------------------------------------
def _serovar_detail_string(stats: dict) -> str:
    """Build a parenthetical like '(109 non-typhoidal, 3 typhoidal, 1 *S. bongori*)'.

    Parts with zero count are omitted so the string stays clean even as the
    wiki grows to include (or exclude) bongori entries.
    """
    parts: list[str] = []
    if stats["nts"] > 0:
        parts.append(f"{stats['nts']} non-typhoidal")
    if stats["typhoidal"] > 0:
        parts.append(f"{stats['typhoidal']} typhoidal")
    if stats["bongori"] > 0:
        parts.append(f"{stats['bongori']} *S. bongori*")
    if parts:
        return f"{stats['total']} ({', '.join(parts)})"
    return str(stats["total"])


# ---------------------------------------------------------------------------
# MkDocs hook entry point
# ---------------------------------------------------------------------------
def _count_phrase(n: int) -> str:
    """Return '1 serovar' or 'N serovars'."""
    return f"{n} serovar" if n == 1 else f"{n} serovars"


def on_page_markdown(markdown: str, *, page, config, files, **kwargs) -> str:
    """Replace ``<!-- STATS:* -->`` placeholders on the homepage and serovar index."""
    global _stats_cache

    # Only act on pages that carry stats placeholders.
    if page.file.src_path not in ("index.md", "serovars/index.md"):
        return markdown

    # Compute stats once per build.
    if _stats_cache is None:
        docs_dir = pathlib.Path(config["docs_dir"])
        _stats_cache = _compute_stats(docs_dir)

    stats = _stats_cache

    # --- Build replacement strings ---
    serovars_str = _serovar_detail_string(stats)
    outbreaks_str = f"{stats['human_outbreaks']} human, {stats['animal_outbreaks']} animal"
    rejections_str = str(stats["border_rejections"])
    recalls_str = str(stats["recalls"])

    # --- Apply substitutions ---
    markdown = markdown.replace("<!-- STATS:serovars -->", serovars_str)
    markdown = markdown.replace("<!-- STATS:serovars_total -->", str(stats["total"]))
    markdown = re.sub(
        r"<!-- STATS:group:([\w-]+) -->",
        lambda m: _count_phrase(stats["groups"].get(m.group(1), 0)),
        markdown,
    )
    markdown = markdown.replace("<!-- STATS:outbreaks -->", outbreaks_str)
    markdown = markdown.replace("<!-- STATS:rejections -->", rejections_str)
    markdown = markdown.replace("<!-- STATS:recalls -->", recalls_str)

    return markdown
