"""Adapter behaviour, driven by recorded responses.

Every test injects a fake ``http`` callable, so nothing here touches the network.
The fixture payloads mirror the real field names and shapes, confirmed against
the live APIs.
"""

from __future__ import annotations

import json
import re
import urllib.error
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
    assert first.data_source == "openfda"
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
    assert paper.data_source == "pubmed"
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


def test_pubmed_does_not_require_the_words_serovar_or_serotype():
    """Requiring them was measured to miss half the serovar-relevant literature.

    Over one 90-day window, 204 papers matched that filter and 205 more named a
    covered serovar the conventional way — "Salmonella Typhimurium" — and were
    invisible. Narrowing to the covered-serovar list instead would empty the
    Coverage gaps section, which is made of *uncovered* serovars.
    """
    assert "serovar[" not in sources.PUBMED_TERM
    assert "serotype[" not in sources.PUBMED_TERM
    assert sources.PUBMED_TERM == "Salmonella[Title/Abstract]"


def test_pubmed_fetches_ids_in_chunks_a_get_url_can_carry():
    calls = []
    ids = [str(40000000 + n) for n in range(250)]

    def http(url):
        calls.append(url)
        if "esearch" in url:
            return json.dumps(
                {"esearchresult": {"idlist": ids, "count": str(len(ids))}}
            ).encode()
        return PUBMED_EFETCH

    sources.fetch_pubmed(SINCE, NOW, http=http)

    efetches = [u for u in calls if "efetch" in u]
    assert len(efetches) == 3, "250 ids in chunks of 100"
    assert all(len(u) < 8000 for u in efetches), "each URL stays GET-sized"


def test_pubmed_takes_the_newest_when_it_has_to_truncate():
    seen = []

    def http(url):
        seen.append(url)
        return json.dumps({"esearchresult": {"idlist": []}}).encode()

    sources.fetch_pubmed(SINCE, NOW, http=http)

    assert "sort=pub_date" in seen[0]


def test_pubmed_pages_through_the_whole_window():
    """A truncated candidate pool is permanently lost: identifiers past retmax
    are never offered again, so the search pages with retstart until it has
    everything. A 90-day backfill measured 505 of 905 papers silently dropped."""
    ids = [str(41000000 + n) for n in range(250)]
    searches = []

    def http(url):
        if "esearch" in url:
            searches.append(url)
            start = int(re.search(r"retstart=(\d+)", url).group(1)) if "retstart=" in url else 0
            return json.dumps(
                {"esearchresult": {"idlist": ids[start : start + 100], "count": "250"}}
            ).encode()
        return PUBMED_EFETCH

    notes = []
    sources.fetch_pubmed(SINCE, NOW, http=http, retmax=100, notes=notes)

    assert len(searches) == 3, "250 ids in pages of 100"
    assert notes == [], "nothing was dropped, so nothing to disclose"


def test_pubmed_notes_what_the_safety_ceiling_drops():
    ids = [str(41000000 + n) for n in range(150)]

    def http(url):
        if "esearch" in url:
            start = int(re.search(r"retstart=(\d+)", url).group(1)) if "retstart=" in url else 0
            return json.dumps(
                {"esearchresult": {"idlist": ids[start : start + 100], "count": "9999"}}
            ).encode()
        return PUBMED_EFETCH

    notes = []
    sources.fetch_pubmed(SINCE, NOW, http=http, retmax=100, max_ids=150, notes=notes)

    assert len(notes) == 1
    assert "150 most recent of 9999" in notes[0]
    assert "9849" in notes[0], "the dropped count is stated"


def test_default_http_paces_ncbi_calls(monkeypatch):
    """NCBI allows 3 E-utilities requests per second; paging through a backfill
    fires ~20 back-to-back and drew a live HTTP 429 without pacing."""
    # A real monotonic clock is far from zero, so the first call is unpaced.
    sleeps, clock = [], iter(100.0 + x * 0.01 for x in range(100))
    monkeypatch.setattr(sources.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(sources.time, "sleep", sleeps.append)

    class FakeResponse:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        sources.urllib.request, "urlopen", lambda req, timeout: FakeResponse()
    )

    sources.default_http(f"{sources.EUTILS}/esearch.fcgi?db=pubmed")
    sources.default_http(f"{sources.EUTILS}/esearch.fcgi?db=pubmed&retstart=100")
    sources.default_http("https://www.fda.gov/some-page")

    assert len(sleeps) == 1, "second NCBI call paced; non-NCBI call not paced"
    assert 0 < sleeps[0] <= sources._NCBI_MIN_INTERVAL


def test_default_http_retries_once_on_too_many_requests(monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(sources.time, "sleep", sleeps.append)

    class FakeResponse:
        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", {"Retry-After": "3"}, None
            )
        return FakeResponse()

    monkeypatch.setattr(sources.urllib.request, "urlopen", urlopen)

    assert sources.default_http("https://example.org/x") == b"ok"
    assert len(calls) == 2
    assert 3.0 in sleeps, "the Retry-After header is honoured"


def test_pubmed_stops_paging_when_a_page_comes_back_empty():
    """A count larger than what the server will actually return must not loop."""
    calls = []

    def http(url):
        if "esearch" in url:
            calls.append(url)
            start = "retstart=" in url
            payload = {"esearchresult": {"idlist": [] if start else ["41000001"], "count": "50"}}
            return json.dumps(payload).encode()
        return PUBMED_EFETCH

    sources.fetch_pubmed(SINCE, NOW, http=http, retmax=100)

    assert len(calls) == 2, "one page, one empty follow-up, then stop"


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
    assert news.data_source == "food-safety-news"
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


def test_food_safety_news_says_so_when_the_feed_does_not_reach_the_window_start():
    """An RSS feed has a fixed length and no date parameter.

    So the feed, not the scan window, can be what bounds this source — which a
    90-day first-run backfill will always hit. The test is whether the oldest item
    predates the window, not how many items came back.
    """
    feed = rss(
        item("Recent", "https://x/1", "g1", "Thu, 30 Jul 2026 00:00:00 GMT"),
        item("Also recent", "https://x/2", "g2", "Mon, 27 Jul 2026 00:00:00 GMT"),
    )
    notes = []
    since = datetime(2026, 5, 4, tzinfo=timezone.utc)

    sources.fetch_food_safety_news(since, http=responder(feed), notes=notes)

    assert len(notes) == 1
    assert "reaches back only to 2026-07-27" in notes[0]
    assert "opens 2026-05-04" in notes[0]


def test_food_safety_news_stays_quiet_when_the_feed_covers_the_window():
    feed = rss(
        item("Old enough", "https://x/1", "g1", "Mon, 15 Jun 2026 00:00:00 GMT"),
        item("Newer", "https://x/2", "g2", "Thu, 30 Jul 2026 00:00:00 GMT"),
    )
    notes = []

    sources.fetch_food_safety_news(SINCE, http=responder(feed), notes=notes)

    assert notes == []


def test_food_safety_news_skips_an_item_with_an_unparseable_date():
    feed = rss(item("Broken", "https://x/1", "guid-1", "not a date"))

    assert sources.fetch_food_safety_news(SINCE, http=responder(feed)) == []


# ---------------------------------------------------------------------------
# FDA CORE outbreak investigations
# ---------------------------------------------------------------------------
def core_row(
    posted,
    ref,
    pathogen,
    product,
    count,
    inv_status,
    outbreak_status="Ongoing",
    advisory="",
):
    """One investigation row, marked up the way the live CORE table is.

    The pathogen cell links the genus name and puts the serovar after a <br>;
    a "See Advisory" case-count cell carries the advisory link.
    """
    count_cell = (
        f'<a href="{advisory}">See</a><br><a href="{advisory}">Advisory</a>'
        if advisory
        else count
    )
    return (
        f'<tr><td><p class="text-align-center">{posted}</p></td>'
        f"<td><p>{ref}</p></td>"
        f"<td><p>{pathogen}</p></td>"
        f"<td><p>{product}</p></td>"
        f"<td><p>{count_cell}</p></td>"
        f"<td><p>{inv_status}</p></td>"
        f"<td><p>{outbreak_status}</p></td>"
        "<td><p>✔</p></td><td><p>&nbsp;</p></td>"
        "<td><p>✔</p></td><td><p>&nbsp;</p></td></tr>"
    )


def core_page(*rows: str) -> bytes:
    header = (
        "<tr><th>Date Posted</th><th>Reference #</th><th>Pathogen or Cause of "
        "Illness</th><th>Product(s) Linked to Illnesses (if any)</th>"
        "<th>Total Case Count</th><th>Investigation Status</th>"
        "<th>Outbreak/ Event Status</th><th>Recall Initiated</th>"
        "<th>FDA Traceback Initiated</th><th>FDA Inspection Initiated</th>"
        "<th>FDA Sampling Initiated</th></tr>"
    )
    return f"<html><body><table>{header}{''.join(rows)}</table></body></html>".encode()


SALMONELLA_CELL = (
    '<a href="/food/foodborne-pathogens/salmonella-salmonellosis">'
    "<em>Salmonella</em></a><br>Javiana"
)


def test_fda_core_normalises_a_closed_investigation():
    """Only a Closed row is final — and wiki-shaped — so only closures become
    candidates."""
    page = core_page(
        core_row(
            "7/22/2026",
            "1395",
            SALMONELLA_CELL,
            "Jalapeño&nbsp;<br>Peppers",
            "",
            "Closed",
            outbreak_status="Ended",
            advisory="https://www.fda.gov/food/outbreak-investigation-salmonella-jalapeno-august-2026",
        )
    )

    candidates = sources.fetch_fda_core(NOW, http=responder(page))

    assert len(candidates) == 1
    inv = candidates[0]
    assert inv.data_source == "fda-core"
    assert inv.source_id == "1395"
    assert inv.published == "2026-07-22"
    assert "Salmonella Javiana" in inv.title
    assert "Jalapeño Peppers" in inv.title
    assert inv.url == (
        "https://www.fda.gov/food/outbreak-investigation-salmonella-jalapeno-august-2026"
    )
    assert "Investigation status: Closed" in inv.summary
    assert "Case count: See Advisory" in inv.summary


def test_fda_core_keeps_a_numeric_case_count():
    page = core_page(
        core_row(
            "7/8/2026", "1387",
            SALMONELLA_CELL.replace("Javiana", "Oranienburg"),
            "Not Yet Identified", "99", "Closed",
        )
    )

    inv = sources.fetch_fda_core(NOW, http=responder(page))[0]

    assert "Case count: 99" in inv.summary
    assert inv.url == sources.FDA_CORE_URL, "no advisory link, so the table page"


def test_fda_core_ignores_other_pathogens():
    page = core_page(
        core_row("7/22/2026", "1400", "<em>Listeria</em>", "Cheese", "12", "Closed")
    )

    assert sources.fetch_fda_core(NOW, http=responder(page)) == []


def test_fda_core_routes_active_rows_to_the_active_list_not_to_candidates():
    """An Active row changes under the reader — counts and status update in
    place — so it is displayed live each run, never classified or recorded.
    It becomes a candidate when it closes. See ADR 0005."""
    page = core_page(
        core_row(
            "1/14/2026", "1358", SALMONELLA_CELL, "Moringa", "23", "Active",
            advisory="https://www.fda.gov/food/outbreak-investigation-salmonella-moringa",
        ),
        core_row("2/1/2026", "1360", SALMONELLA_CELL, "Eggs", "45", "Active"),
    )
    active = []

    candidates = sources.fetch_fda_core(NOW, http=responder(page), active=active)

    assert candidates == []
    assert [row["reference"] for row in active] == ["1358", "1360"]
    with_advisory, without = active
    assert "Salmonella Javiana" in with_advisory["pathogen"]
    assert with_advisory["product"] == "Moringa"
    assert with_advisory["case_count"] == "See Advisory"
    assert with_advisory["investigation_status"] == "Active"
    assert with_advisory["posted"] == "2026-01-14"
    assert with_advisory["url"].endswith("moringa")
    assert without["case_count"] == "45"
    assert without["url"] == sources.FDA_CORE_URL


def test_fda_core_drops_closed_rows_older_than_the_lookback():
    """A closure has no date of its own — the row keeps its posted date — so
    closures are bounded by a rolling lookback rather than the scan window."""
    page = core_page(
        core_row("2/25/2026", "1366", SALMONELLA_CELL, "Cantaloupe", "70", "Closed"),
        core_row("6/19/2024", "1234", SALMONELLA_CELL, "Jalapeno", "90", "Closed"),
    )

    candidates = sources.fetch_fda_core(NOW, http=responder(page))

    assert [c.source_id for c in candidates] == ["1366"], (
        "a closure inside the lookback survives; a two-year-old one ages out"
    )


def test_fda_core_says_so_when_no_salmonella_row_parses():
    """The live table always carries dozens of Salmonella rows, so zero parsed
    means the layout changed — which must not read as a quiet week."""
    notes = []
    page = b"<html><body><div>redesigned page, no table</div></body></html>"

    assert sources.fetch_fda_core(NOW, http=responder(page), notes=notes) == []
    assert len(notes) == 1
    assert "no Salmonella investigation rows" in notes[0]


def test_fda_core_treats_not_found_as_empty():
    def not_found(url):
        raise sources.NotFound(url)

    assert sources.fetch_fda_core(NOW, http=not_found) == []


# ---------------------------------------------------------------------------
# All sources together
# ---------------------------------------------------------------------------
def test_all_sources_feed_one_candidate_list():
    """So a single digest can rank across sources rather than per source."""

    def http(url):
        if "api.fda.gov" in url:
            return json.dumps(OPENFDA_PAYLOAD).encode()
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["40123456"]}}).encode()
        if "efetch" in url:
            return PUBMED_EFETCH
        if "www.fda.gov" in url:
            return core_page(
                core_row("7/22/2026", "1395", SALMONELLA_CELL, "Peppers", "9", "Closed"),
                core_row("8/1/2026", "1401", SALMONELLA_CELL, "Eggs", "12", "Active"),
            )
        return rss(
            item("News", "https://x/1", "guid-1", "Thu, 30 Jul 2026 00:00:00 GMT")
        )

    active = []
    candidates = sources.fetch_all(SINCE, NOW, http=http, active=active)

    assert {c.data_source for c in candidates} == {
        "openfda",
        "pubmed",
        "food-safety-news",
        "fda-core",
    }
    assert [row["reference"] for row in active] == ["1401"], (
        "fetch_all carries the active-investigation list through"
    )
