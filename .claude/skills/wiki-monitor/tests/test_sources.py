"""Adapter behaviour, driven by recorded responses.

Every test injects a fake ``http`` callable, so nothing here touches the network.
The fixture payloads mirror the real field names and shapes, confirmed against
the live APIs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from wiki_monitor import sources

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)
SINCE = datetime(2026, 7, 1, tzinfo=timezone.utc)


def responder(payload, record=None):
    """An http stub returning *payload*, appending each URL to *record*."""

    def _http(url):
        if record is not None:
            record.append(url)
        return payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    return _http


# ---------------------------------------------------------------------------
# openFDA
# ---------------------------------------------------------------------------
OPENFDA_PAYLOAD = {
    "meta": {"results": {"total": 2}},
    "results": [
        {
            "recall_number": "F-1234-2026",
            "report_date": "20260715",
            "recalling_firm": "Example Foods Inc",
            "product_description": "Tahini, 16 oz jars",
            "reason_for_recall": "Product may be contaminated with Salmonella Agona",
            "classification": "Class I",
            "status": "Ongoing",
            "distribution_pattern": "Nationwide",
            "city": "Fresno",
            "state": "CA",
            "country": "United States",
        },
        {
            "recall_number": "F-5678-2026",
            "report_date": "20260720",
            "recalling_firm": "Second Firm",
            "product_description": "Frozen breaded chicken",
            "reason_for_recall": "Salmonella Enteritidis contamination",
            "classification": "Class I",
            "status": "Completed",
            "distribution_pattern": "TX, OK",
            "city": "Austin",
            "state": "TX",
            "country": "United States",
        },
    ],
}


def test_openfda_normalises_a_recall(wiki_repo):
    candidates = sources.fetch_openfda(NOW, http=responder(OPENFDA_PAYLOAD))

    first = candidates[0]
    assert first.source == "openfda"
    assert first.source_id == "F-1234-2026"  # the state dedup key
    assert first.published == "2026-07-15"
    assert "Tahini" in first.title
    assert "Salmonella Agona" in first.summary
    assert "Example Foods Inc" in first.summary


def test_openfda_queries_a_rolling_sixty_day_window():
    """Regardless of the scan-since date, to absorb openFDA's publication lag."""
    seen = []
    sources.fetch_openfda(NOW, http=responder(OPENFDA_PAYLOAD, seen))

    assert "report_date:[20260603+TO+20260802]" in seen[0]


def test_openfda_treats_no_matches_as_a_quiet_week():
    """A zero-match search returns HTTP 404; that is not a run failure."""

    def not_found(url):
        raise sources.NotFound(url)

    assert sources.fetch_openfda(NOW, http=not_found) == []


def test_openfda_says_so_when_it_did_not_see_the_whole_window():
    """A first page must not read as a complete scan."""
    payload = {
        "meta": {"results": {"total": 137}},
        "results": OPENFDA_PAYLOAD["results"],
    }
    notes = []

    sources.fetch_openfda(NOW, http=responder(payload), notes=notes)

    assert len(notes) == 1
    assert "2 of 137" in notes[0]
    assert "135 were not considered" in notes[0]


def test_openfda_stays_quiet_when_it_saw_everything():
    notes = []

    sources.fetch_openfda(NOW, http=responder(OPENFDA_PAYLOAD), notes=notes)

    assert notes == []


def test_openfda_collapses_a_repeated_recall_number():
    payload = {"results": [OPENFDA_PAYLOAD["results"][0]] * 3}

    candidates = sources.fetch_openfda(NOW, http=responder(payload))

    assert [c.source_id for c in candidates] == ["F-1234-2026"]


# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------
PUBMED_EFETCH = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">40123456</PMID>
      <Article>
        <Journal><Title>Applied and Environmental Microbiology</Title></Journal>
        <ArticleTitle>Novel AMR plasmid in Salmonella enterica serovar Agona</ArticleTitle>
        <Abstract>
          <AbstractText>We describe a 295 kb IncHI2 plasmid carrying 16 resistance genes.</AbstractText>
        </Abstract>
        <ArticleDate><Year>2026</Year><Month>7</Month><Day>9</Day></ArticleDate>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_pubmed_normalises_a_paper():
    calls = []

    def http(url):
        calls.append(url)
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["40123456"]}}).encode()
        return PUBMED_EFETCH

    candidates = sources.fetch_pubmed(SINCE, NOW, http=http, email="x@example.org")

    assert len(candidates) == 1
    paper = candidates[0]
    assert paper.source == "pubmed"
    assert paper.source_id == "40123456"
    assert paper.title.startswith("Novel AMR plasmid")
    assert paper.url == "https://pubmed.ncbi.nlm.nih.gov/40123456/"
    assert paper.published == "2026-07-09"
    assert "IncHI2 plasmid" in paper.summary
    assert "Applied and Environmental Microbiology" in paper.summary


PUBMED_MIXED_CONTENT = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">40222222</PMID>
      <Article>
        <Journal><Title>Journal of <i>Salmonella</i> Studies</Title></Journal>
        <ArticleTitle>Colistin resistance in <i>Salmonella</i> Kedougou ST1543</ArticleTitle>
        <Abstract>
          <AbstractText>Median lethal time (LT<sub>50</sub>) fell sharply, and the <i>mcr-1</i> gene was present in every isolate.</AbstractText>
        </Abstract>
        <ArticleDate><Year>2026</Year><Month>7</Month><Day>9</Day></ArticleDate>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_pubmed_keeps_text_that_inline_markup_interrupts():
    """PubMed marks up titles and abstracts with <i> and <sub>.

    Reading only ``.text`` stops at the first such tag: a real abstract lost 928
    of 2016 characters that way, cutting off at LT<sub>50</sub> and dropping the
    result. A title can lose the serovar name the same way.
    """

    def http(url):
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["40222222"]}}).encode()
        return PUBMED_MIXED_CONTENT

    paper = sources.fetch_pubmed(SINCE, NOW, http=http)[0]

    assert "Kedougou" in paper.title, "the serovar name follows an <i> element"
    assert paper.title == "Colistin resistance in Salmonella Kedougou ST1543"
    assert "mcr-1" in paper.summary, "text after a second inline tag survives"
    assert "every isolate" in paper.summary, "the tail of the abstract survives"
    assert "Journal of Salmonella Studies" in paper.summary


def test_pubmed_windows_the_search_on_the_scan_dates():
    calls = []

    def http(url):
        calls.append(url)
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": []}}).encode()
        return PUBMED_EFETCH

    sources.fetch_pubmed(SINCE, NOW, http=http)

    assert "mindate=2026/07/01" in calls[0]
    assert "maxdate=2026/08/02" in calls[0]
    assert f"tool={sources.PUBMED_TOOL}" in calls[0], "NCBI asks callers to identify"


def test_pubmed_skips_the_fetch_when_the_search_is_empty():
    calls = []

    def http(url):
        calls.append(url)
        return json.dumps({"esearchresult": {"idlist": []}}).encode()

    assert sources.fetch_pubmed(SINCE, NOW, http=http) == []
    assert len(calls) == 1, "no efetch call when there is nothing to fetch"


# ---------------------------------------------------------------------------
# Food Safety News
# ---------------------------------------------------------------------------
def rss(*items: str) -> bytes:
    body = "".join(items)
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        f"{body}</channel></rss>"
    ).encode()


def item(title, link, guid, pub_date, description="Some news."):
    """One RSS item, CDATA-wrapped the way the live Food Safety News feed is."""
    return (
        f"<item><title><![CDATA[{title}]]></title><link>{link}</link>"
        f"<guid isPermaLink='false'>{guid}</guid>"
        f"<pubDate>{pub_date}</pubDate>"
        f"<description><![CDATA[{description}]]></description></item>"
    )


def test_food_safety_news_normalises_an_item():
    feed = rss(
        item(
            "FDA investigates Salmonella outbreak",
            "https://www.foodsafetynews.com/2026/07/fda-investigates/",
            "6a6ab76d6b9369000110f416",
            "Thu, 30 Jul 2026 04:04:12 GMT",
            "<p>Cases across <b>12</b> states.</p>",
        )
    )

    candidates = sources.fetch_food_safety_news(SINCE, http=responder(feed))

    assert len(candidates) == 1
    news = candidates[0]
    assert news.source == "food-safety-news"
    assert news.source_id == "6a6ab76d6b9369000110f416"
    assert news.published == "2026-07-30"
    assert news.summary == "Cases across 12 states.", "HTML tags stripped"


def test_food_safety_news_ignores_items_from_before_the_scan_window():
    feed = rss(
        item("Old news", "https://x/1", "guid-old", "Mon, 01 Jun 2026 00:00:00 GMT"),
        item("New news", "https://x/2", "guid-new", "Thu, 30 Jul 2026 00:00:00 GMT"),
    )

    candidates = sources.fetch_food_safety_news(SINCE, http=responder(feed))

    assert [c.source_id for c in candidates] == ["guid-new"]


def test_food_safety_news_skips_an_item_with_an_unparseable_date():
    feed = rss(item("Broken", "https://x/1", "guid-1", "not a date"))

    assert sources.fetch_food_safety_news(SINCE, http=responder(feed)) == []


# ---------------------------------------------------------------------------
# All three together
# ---------------------------------------------------------------------------
def test_all_three_sources_feed_one_candidate_list():
    """So a single digest can rank across sources rather than per source."""

    def http(url):
        if "api.fda.gov" in url:
            return json.dumps(OPENFDA_PAYLOAD).encode()
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["40123456"]}}).encode()
        if "efetch" in url:
            return PUBMED_EFETCH
        return rss(
            item("News", "https://x/1", "guid-1", "Thu, 30 Jul 2026 00:00:00 GMT")
        )

    candidates = sources.fetch_all(SINCE, NOW, http=http)

    assert {c.source for c in candidates} == {
        "openfda",
        "pubmed",
        "food-safety-news",
    }
