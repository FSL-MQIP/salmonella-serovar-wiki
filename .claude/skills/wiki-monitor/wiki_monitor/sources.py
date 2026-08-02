"""The three data-source adapters.

Each normalises one upstream feed into a :class:`Candidate` — the common shape
the classification step reads.  These are thin boundary adapters: they fetch and
reshape, and make no judgement about whether a candidate is worth reporting.

Every network call goes through an injected ``http`` callable, so tests drive
these against recorded responses instead of the live APIs.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

USER_AGENT = (
    "salmonella-serovar-wiki-monitor/1.0 "
    "(+https://github.com/FSL-MQIP/salmonella-serovar-wiki)"
)

#: openFDA publishes recalls roughly 11 days late, so the recall query always
#: sweeps a rolling window regardless of the nominal scan-since date.  Records
#: already reported are filtered out later by the state dedup key.
OPENFDA_WINDOW_DAYS = 60

OPENFDA_URL = "https://api.fda.gov/food/enforcement.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
FOOD_SAFETY_NEWS_FEED = "https://www.foodsafetynews.com/tag/salmonella/feed/"

#: PubMed is asked for serovar-level Salmonella literature; judging whether a
#: paper reports a *novel* characteristic is the classifier's job, not the query's.
PUBMED_TERM = (
    "Salmonella[Title/Abstract] AND "
    "(serovar[Title/Abstract] OR serotype[Title/Abstract])"
)

#: NCBI asks that every E-utilities caller identify itself.
PUBMED_TOOL = "salmonella-serovar-wiki-monitor"


class NotFound(Exception):
    """The upstream returned 404.  For openFDA this means "no matching records"."""


@dataclass(frozen=True)
class Candidate:
    """One raw item from a data source, before any classification."""

    source: str  # "openfda" | "pubmed" | "food-safety-news"
    source_id: str  # recall number | PMID | RSS GUID — the state dedup key
    title: str
    url: str
    published: str  # ISO date, as the source reported it
    summary: str  # the text the classifier reads

    def as_dict(self) -> dict:
        return asdict(self)


def default_http(url: str) -> bytes:
    """Fetch *url*, raising :class:`NotFound` on 404."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NotFound(url) from error
        raise


# ---------------------------------------------------------------------------
# openFDA food enforcement
# ---------------------------------------------------------------------------
def fetch_openfda(now: datetime, http=default_http, limit: int = 100) -> list[Candidate]:
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

    candidates = []
    for record in payload.get("results", []):
        recall_number = record.get("recall_number")
        if not recall_number:
            continue
        candidates.append(
            Candidate(
                source="openfda",
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
    retmax: int = 200,
    notes: list | None = None,
) -> list[Candidate]:
    """Serovar-level Salmonella papers indexed between *since* and *now*.

    Appends a note when the window holds more papers than ``retmax`` returns, so
    a truncated candidate pool is never mistaken for the whole window — a long
    first-run backfill is exactly where that would otherwise happen silently.
    """
    identifiers, total = _pubmed_search(since, now, http, email, retmax)
    if notes is not None and total > len(identifiers):
        notes.append(
            f"PubMed: took the {len(identifiers)} most recent of {total} matching "
            f"papers in this window (retmax={retmax}); {total - len(identifiers)} "
            "were not considered."
        )
    if not identifiers:
        return []
    return _pubmed_fetch(identifiers, http, email)


def _pubmed_search(since, now, http, email, retmax) -> tuple[list[str], int]:
    url = (
        f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json"
        f"&term={urllib.parse.quote(PUBMED_TERM)}"
        f"&datetype=edat&mindate={since:%Y/%m/%d}&maxdate={now:%Y/%m/%d}"
        f"&retmax={retmax}&tool={PUBMED_TOOL}"
    )
    if email:
        url += f"&email={urllib.parse.quote(email)}"
    try:
        payload = json.loads(http(url))
    except NotFound:
        return [], 0
    result = payload.get("esearchresult", {})
    identifiers = result.get("idlist", [])
    try:
        total = int(result.get("count", len(identifiers)))
    except (TypeError, ValueError):
        total = len(identifiers)
    return identifiers, total


def _pubmed_fetch(identifiers, http, email) -> list[Candidate]:
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
        title = article.findtext(".//ArticleTitle", default="").strip()
        abstract = " ".join(
            (node.text or "").strip()
            for node in article.iter("AbstractText")
        ).strip()
        journal = article.findtext(".//Journal/Title", default="").strip()
        candidates.append(
            Candidate(
                source="pubmed",
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


def _pubmed_date(article) -> str:
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
def fetch_food_safety_news(since: datetime, http=default_http) -> list[Candidate]:
    """Items from the Salmonella-tagged feed published since *since*."""
    try:
        root = ElementTree.fromstring(http(FOOD_SAFETY_NEWS_FEED))
    except NotFound:
        return []

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
                source="food-safety-news",
                source_id=guid,
                title=(item.findtext("title") or "").strip(),
                url=(item.findtext("link") or "").strip(),
                published=published.date().isoformat(),
                summary=_strip_tags(_all_text(item.find("description"))),
            )
        )
    return _deduplicate(candidates)


def _rss_date(raw: str):
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
# All three
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
        *fetch_openfda(now, http=http),
        *fetch_pubmed(since, now, http=http, email=email, notes=notes),
        *fetch_food_safety_news(since, http=http),
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


def _all_text(node) -> str:
    """Every text fragment under *node*.

    The feed CDATA-wraps its descriptions, so the markup arrives as text — but a
    feed that inlined real child elements instead would lose everything after
    the first tag under ``findtext``.
    """
    if node is None:
        return ""
    return " ".join(node.itertext())


def _strip_tags(html_text: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html_text).split())
