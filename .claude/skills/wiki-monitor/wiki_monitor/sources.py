"""The data-source adapters.

Each normalises one upstream feed into a :class:`Candidate` — the common shape
the classification step reads.  These are thin boundary adapters: they fetch and
reshape, and make no judgement about whether a candidate is worth reporting.

Every network call goes through an injected ``http`` callable, so tests drive
these against recorded responses instead of the live APIs.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

USER_AGENT = (
    "salmonella-serovar-wiki-monitor/1.0 "
    "(+https://github.com/FSL-MQIP/salmonella-serovar-wiki)"
)

#: openFDA publishes recalls roughly 11 days late, so the recall query always
#: sweeps a rolling window regardless of the nominal scan-since date.  Records
#: already reported are filtered out later by the state dedup key.
OPENFDA_WINDOW_DAYS = 60

#: openFDA's documented ceiling for a single call.
OPENFDA_MAX_LIMIT = 1000

OPENFDA_URL = "https://api.fda.gov/food/enforcement.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
FOOD_SAFETY_NEWS_FEED = "https://www.foodsafetynews.com/tag/salmonella/feed/"

#: FDA CORE's table of foodborne-illness outbreak investigations.  Unlike the
#: openFDA enforcement records — which publish ~11 days late and almost never
#: name a serovar — this table posts investigations while they are active, names
#: the serovar, and carries the case count, food vehicle and investigation
#: status.  It is the primary surface behind much of Food Safety News's outbreak
#: reporting, and docs/data-sources.md already lists it as a wiki source.
FDA_CORE_URL = (
    "https://www.fda.gov/food/outbreaks-foodborne-illness/"
    "investigations-foodborne-illness-outbreaks"
)

#: Every Salmonella paper in the window, with no further narrowing.
#:
#: Requiring the literal words "serovar" or "serotype" looked like a cheap way to
#: get serovar-level literature and was measured to miss half of it: over one
#: 90-day window, 204 papers matched that filter while 205 more named a covered
#: serovar the conventional way — "Salmonella Typhimurium" — and were invisible.
#:
#: Narrowing to the wiki's own covered-serovar list would be worse still: a paper
#: about an *uncovered* serovar is what a Coverage gap is made of, so filtering
#: them out would silently empty that section. Whether a paper is relevant is the
#: classifier's judgement, and the digest's caps bound the cost of asking it.
PUBMED_TERM = "Salmonella[Title/Abstract]"

#: NCBI asks that every E-utilities caller identify itself.
PUBMED_TOOL = "salmonella-serovar-wiki-monitor"

#: PMIDs per efetch call. The ids travel in the URL, so a whole backfill's worth
#: in one request would exceed what a GET can carry.
PUBMED_FETCH_CHUNK = 100

#: Safety ceiling on identifiers collected per run.  The search pages until it
#: has the whole window — a single-page fetch measured 505 of 905 papers
#: silently dropped, and dropped identifiers are never offered again — so this
#: exists only to bound a runaway window, far above the ~900 a 90-day backfill
#: produces.  Hitting it is disclosed as a note.
PUBMED_MAX_IDS = 4000


class NotFound(Exception):
    """The upstream returned 404.  For openFDA this means "no matching records"."""


@dataclass(frozen=True)
class Candidate:
    """One raw item from a data source, before any classification."""

    data_source: str  # "openfda" | "pubmed" | "food-safety-news" | "fda-core"
    source_id: str  # recall number | PMID | RSS GUID | CORE ref # — the state dedup key
    title: str
    url: str
    published: str  # ISO date, as the source reported it
    summary: str  # the text the classifier reads

    def as_dict(self) -> dict:
        return asdict(self)


#: NCBI allows three E-utilities requests per second without an API key.
#: Paging through a long backfill fires ~20 calls back-to-back, which drew a
#: live HTTP 429; spacing the calls out keeps the whole run under the limit.
_NCBI_MIN_INTERVAL = 0.34
_last_ncbi_call = 0.0


def default_http(url: str) -> bytes:
    """Fetch *url*, raising :class:`NotFound` on 404.

    Calls to NCBI are paced to its documented rate limit, and a 429 from any
    host is retried once after the pause the server asks for — a rate-limited
    page must not abort a whole fetch.
    """
    global _last_ncbi_call
    if url.startswith(EUTILS):
        wait = _NCBI_MIN_INTERVAL - (time.monotonic() - _last_ncbi_call)
        if wait > 0:
            time.sleep(wait)
        _last_ncbi_call = time.monotonic()

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise NotFound(url) from error
            if error.code == 429 and attempt == 1:
                time.sleep(_retry_after_seconds(error))
                continue
            raise


def _retry_after_seconds(error: urllib.error.HTTPError, default: float = 2.0) -> float:
    try:
        return float(error.headers.get("Retry-After", default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# openFDA food enforcement
# ---------------------------------------------------------------------------
def fetch_openfda(
    now: datetime,
    http=default_http,
    limit: int = OPENFDA_MAX_LIMIT,
    notes: list | None = None,
) -> list[Candidate]:
    """Recalls mentioning Salmonella, over a rolling window ending at *now*."""
    start = (now - timedelta(days=OPENFDA_WINDOW_DAYS)).strftime("%Y%m%d")
    end = now.strftime("%Y%m%d")
    query = (
        f"report_date:[{start}+TO+{end}]"
        "+AND+reason_for_recall:%22Salmonella%22"
    )
    url = f"{OPENFDA_URL}?search={query}&limit={limit}"

    try:
        payload = json.loads(http(url))
    except NotFound:
        # A zero-match search is a quiet week, not a failure.
        return []

    # One page at openFDA's documented maximum covers this query many times over
    # — a 60-day Salmonella window runs to a few dozen recalls — but say so
    # rather than pass off a first page as the whole window.
    total = payload.get("meta", {}).get("results", {}).get("total")
    returned = len(payload.get("results", []))
    if notes is not None and isinstance(total, int) and total > returned:
        notes.append(
            f"openFDA: took {returned} of {total} matching recalls in the rolling "
            f"{OPENFDA_WINDOW_DAYS}-day window (limit={limit}); "
            f"{total - returned} were not considered."
        )

    candidates = []
    for record in payload.get("results", []):
        recall_number = record.get("recall_number")
        if not recall_number:
            continue
        candidates.append(
            Candidate(
                data_source="openfda",
                source_id=recall_number,
                title=_first_sentence(record.get("product_description", "")),
                url=(
                    "https://api.fda.gov/food/enforcement.json"
                    f"?search=recall_number:%22{recall_number}%22"
                ),
                published=_openfda_date(record.get("report_date", "")),
                summary=_openfda_summary(record),
            )
        )
    return _deduplicate(candidates)


def _openfda_summary(record: dict) -> str:
    parts = [
        f"Recalling firm: {record.get('recalling_firm', 'unknown')}",
        f"Classification: {record.get('classification', 'unknown')}",
        f"Status: {record.get('status', 'unknown')}",
        f"Location: {record.get('city', '')}, {record.get('state', '')}"
        f" {record.get('country', '')}".strip(),
        f"Distribution: {record.get('distribution_pattern', 'unknown')}",
        f"Product: {record.get('product_description', '')}",
        f"Reason: {record.get('reason_for_recall', '')}",
    ]
    return "\n".join(part for part in parts if part.strip())


def _openfda_date(compact: str) -> str:
    """Turn openFDA's ``YYYYMMDD`` into an ISO date."""
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    return compact


# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------
def fetch_pubmed(
    since: datetime,
    now: datetime,
    http=default_http,
    email: str = "",
    retmax: int = 400,
    notes: list | None = None,
    max_ids: int = PUBMED_MAX_IDS,
) -> list[Candidate]:
    """Salmonella papers indexed between *since* and *now*, newest first.

    The search pages through the whole window rather than truncating at one
    page: identifiers past the first page are never offered again on a later
    run, so a single-page fetch silently and permanently dropped most of a long
    backfill.  Only the ``max_ids`` safety ceiling can still bound the pool,
    and hitting it appends a note so the digest discloses the partial scan.
    """
    identifiers, total = _pubmed_search(since, now, http, email, retmax, max_ids)
    if notes is not None and total > len(identifiers):
        notes.append(
            f"PubMed: took the {len(identifiers)} most recent of {total} matching "
            f"papers in this window (safety ceiling {max_ids}); "
            f"{total - len(identifiers)} were not considered."
        )
    if not identifiers:
        return []
    return _pubmed_fetch(identifiers, http, email)


def _pubmed_search(
    since: datetime, now: datetime, http, email: str, retmax: int, max_ids: int
) -> tuple[list[str], int]:
    """Every PMID in the window, paging with ``retstart`` up to *max_ids*."""
    base = (
        f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json"
        f"&term={urllib.parse.quote(PUBMED_TERM)}"
        f"&datetype=edat&mindate={since:%Y/%m/%d}&maxdate={now:%Y/%m/%d}"
        # Newest first, so that if the ceiling does truncate, what survives is
        # the most recent rather than an arbitrary slice.
        f"&sort=pub_date&retmax={retmax}&tool={PUBMED_TOOL}"
    )
    if email:
        base += f"&email={urllib.parse.quote(email)}"

    identifiers: list[str] = []
    total = 0
    while True:
        url = base if not identifiers else f"{base}&retstart={len(identifiers)}"
        try:
            payload = json.loads(http(url))
        except NotFound:
            break
        result = payload.get("esearchresult", {})
        page = result.get("idlist", [])
        try:
            total = int(result.get("count", len(page)))
        except (TypeError, ValueError):
            total = len(page)
        # An empty page ends the loop even when the reported count says more:
        # the count is what must not be trusted into an infinite loop.
        if not page:
            break
        identifiers.extend(page)
        if len(identifiers) >= total or len(identifiers) >= max_ids:
            break
    return identifiers[:max_ids], total


def _pubmed_fetch(identifiers: list[str], http, email: str) -> list[Candidate]:
    """Fetch metadata for *identifiers*, in chunks a GET URL can carry."""
    candidates: list[Candidate] = []
    for start in range(0, len(identifiers), PUBMED_FETCH_CHUNK):
        chunk = identifiers[start : start + PUBMED_FETCH_CHUNK]
        candidates.extend(_pubmed_fetch_chunk(chunk, http, email))
    return _deduplicate(candidates)


def _pubmed_fetch_chunk(identifiers: list[str], http, email: str) -> list[Candidate]:
    url = (
        f"{EUTILS}/efetch.fcgi?db=pubmed&retmode=xml&rettype=abstract"
        f"&id={','.join(identifiers)}&tool={PUBMED_TOOL}"
    )
    if email:
        url += f"&email={urllib.parse.quote(email)}"
    try:
        root = ElementTree.fromstring(http(url))
    except NotFound:
        return []

    candidates = []
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID", default="").strip()
        if not pmid:
            continue
        # PubMed marks up titles and abstracts with inline elements — <i> around
        # genus names, <sub>/<sup> in expressions like LT<sub>50</sub>. Reading
        # only ``.text`` stops at the first such tag: one real abstract lost 928
        # of its 2016 characters that way, cutting off mid-result.
        title = _all_text(article.find(".//ArticleTitle")).strip()
        abstract = " ".join(
            _all_text(node).strip() for node in article.iter("AbstractText")
        ).strip()
        journal = _all_text(article.find(".//Journal/Title")).strip()
        candidates.append(
            Candidate(
                data_source="pubmed",
                source_id=pmid,
                title=title,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                published=_pubmed_date(article),
                summary="\n".join(
                    part for part in (f"Journal: {journal}" if journal else "", abstract)
                    if part
                ),
            )
        )
    return _deduplicate(candidates)


def _pubmed_date(article: ElementTree.Element) -> str:
    for path in (".//ArticleDate", ".//PubMedPubDate[@PubStatus='entrez']"):
        node = article.find(path)
        if node is None:
            continue
        year = node.findtext("Year", default="")
        month = node.findtext("Month", default="01").zfill(2)
        day = node.findtext("Day", default="01").zfill(2)
        if year:
            return f"{year}-{month}-{day}"
    return article.findtext(".//PubDate/Year", default="")


# ---------------------------------------------------------------------------
# Food Safety News
# ---------------------------------------------------------------------------
def fetch_food_safety_news(
    since: datetime, http=default_http, notes: list | None = None
) -> list[Candidate]:
    """Items from the Salmonella-tagged feed published since *since*.

    An RSS feed carries a fixed number of recent items with no date parameter, so
    the feed itself — not the scan window — can be what bounds this source. The
    test for that is whether the feed reaches back past *since*: if its oldest
    item is newer than the window start, the earlier part of the window was never
    on offer. A long first-run backfill will always trip this.
    """
    try:
        root = ElementTree.fromstring(http(FOOD_SAFETY_NEWS_FEED))
    except NotFound:
        return []

    dates = [
        parsed
        for parsed in (
            _rss_date(item.findtext("pubDate", default="")) for item in root.iter("item")
        )
        if parsed is not None
    ]
    if notes is not None and dates and min(dates) > since:
        notes.append(
            f"Food Safety News: the feed reaches back only to "
            f"{min(dates):%Y-%m-%d}, but this run's window opens "
            f"{since:%Y-%m-%d}; anything Salmonella-tagged before "
            f"{min(dates):%Y-%m-%d} was not on offer."
        )

    candidates = []
    for item in root.iter("item"):
        published = _rss_date(item.findtext("pubDate", default=""))
        if published is None or published <= since:
            continue
        guid = (item.findtext("guid") or item.findtext("link") or "").strip()
        if not guid:
            continue
        candidates.append(
            Candidate(
                data_source="food-safety-news",
                source_id=guid,
                title=(item.findtext("title") or "").strip(),
                url=(item.findtext("link") or "").strip(),
                published=published.date().isoformat(),
                summary=_strip_tags(_all_text(item.find("description"))),
            )
        )
    return _deduplicate(candidates)


def _rss_date(raw: str) -> datetime | None:
    if not raw.strip():
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# FDA CORE outbreak investigations
# ---------------------------------------------------------------------------
_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TABLE_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
#: Advisory pages live at /food/outbreaks-foodborne-illness/outbreak-investigation-…
#: A looser "any absolute fda.gov link" match picked up the genus link or the
#: generic safe-food-handling page on rows that have no advisory.
_FDA_LINK = re.compile(r'href="(https://www\.fda\.gov/[^"]*outbreak-investigation[^"]*)"')


def fetch_fda_core(
    since: datetime, http=default_http, notes: list | None = None
) -> list[Candidate]:
    """Salmonella rows from FDA CORE's outbreak-investigations table.

    Rows are edited in place over an investigation's life — case counts and
    statuses update on the same row — so an Active investigation stays a
    candidate whatever its posted date (state dedup retires it once reported),
    while a Closed row matters only when posted inside the window: a closure
    posted this window is what Update Criterion 3 is for.
    """
    try:
        page = http(FDA_CORE_URL).decode("utf-8", errors="replace")
    except NotFound:
        return []

    candidates = []
    salmonella_rows = 0
    for row in _TABLE_ROW.findall(page):
        cells = [_cell_text(cell) for cell in _TABLE_CELL.findall(row)]
        # Columns: posted, reference, pathogen, product, case count,
        # investigation status, outbreak status, then per-action checkmarks.
        if len(cells) < 7 or "Salmonella" not in cells[2]:
            continue
        salmonella_rows += 1
        posted = _core_date(cells[0])
        reference = cells[1]
        if posted is None or not reference:
            continue
        if cells[5].strip().lower() != "active" and posted <= since:
            continue
        advisory = _FDA_LINK.search(row)
        candidates.append(
            Candidate(
                data_source="fda-core",
                source_id=reference,
                title=f"{cells[2]} investigation — {cells[3]}",
                url=advisory.group(1) if advisory else FDA_CORE_URL,
                published=posted.date().isoformat(),
                summary="\n".join(
                    [
                        f"Pathogen: {cells[2]}",
                        f"Product: {cells[3]}",
                        f"Case count: {cells[4] or 'not stated'}",
                        f"Investigation status: {cells[5]}",
                        f"Outbreak/event status: {cells[6]}",
                    ]
                ),
            )
        )

    if notes is not None and salmonella_rows == 0:
        notes.append(
            "FDA CORE: no Salmonella investigation rows parsed from the outbreak "
            "table — the live table always carries dozens, so the page layout has "
            "likely changed and this source went unscanned."
        )
    return _deduplicate(candidates)


def _cell_text(cell: str) -> str:
    """A table cell's visible text: tags out, entities resolved, spacing flat."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", cell)).split())


def _core_date(raw: str) -> datetime | None:
    """Parse the table's ``M/D/YYYY`` posted date as midnight UTC."""
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# All sources
# ---------------------------------------------------------------------------
def fetch_all(
    since: datetime,
    now: datetime,
    http=default_http,
    email: str = "",
    notes: list | None = None,
) -> list[Candidate]:
    """Every candidate from every source, so one digest can rank across them."""
    return [
        *fetch_openfda(now, http=http, notes=notes),
        *fetch_pubmed(since, now, http=http, email=email, notes=notes),
        *fetch_food_safety_news(since, http=http, notes=notes),
        *fetch_fda_core(since, http=http, notes=notes),
    ]


def _deduplicate(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse repeats of the same source id within one fetch."""
    seen, unique = set(), []
    for candidate in candidates:
        if candidate.source_id in seen:
            continue
        seen.add(candidate.source_id)
        unique.append(candidate)
    return unique


def _first_sentence(text: str, limit: int = 120) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rsplit(" ", 1)[0] + "…"


def _all_text(node: ElementTree.Element | None) -> str:
    """Every text fragment under *node*, including inside child elements.

    ``findtext`` and ``.text`` stop at the first child element and drop the rest,
    which silently truncates any mixed-content field — an RSS description with
    inline markup, or a PubMed title or abstract carrying ``<i>`` or ``<sub>``.
    """
    if node is None:
        return ""
    return "".join(node.itertext())


def _strip_tags(html_text: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html_text).split())
