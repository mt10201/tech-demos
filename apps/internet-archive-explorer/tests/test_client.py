import pytest
import requests
import responses

from iaexplorer.client import LICENSE_FILTERS, IAClient, build_query, make_session, text_clause

SEARCH_URL = "https://archive.org/advancedsearch.php"

SEARCH_PAYLOAD = {
    "responseHeader": {"status": 0},
    "response": {"numFound": 2, "start": 0, "docs": [
        {"identifier": "DuckandC1951", "title": "Duck and Cover", "year": 1951, "mediatype": "movies",
         "collection": ["prelinger", "fav-someone"], "licenseurl": "http://creativecommons.org/licenses/publicdomain/"},
        {"identifier": "gd77-05-08", "title": "Grateful Dead Live", "mediatype": "etree",
         "collection": ["GratefulDead", "etree", "stream_only"]},
    ]},
}


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def plain_client(**kw):
    fc = FakeClock()
    c = IAClient(make_session(cache_path=None), sleep=fc.sleep, clock=fc.clock, **kw)
    return c, fc


def test_build_query_collection_years_license():
    q = build_query("prelinger", "", 1950, 1960, "movies", LICENSE_FILTERS[1])
    assert q.startswith("collection:prelinger AND mediatype:movies AND year:[1950 TO 1960]")
    assert "licenseurl:*publicdomain*" in q and r"licenseurl:*\/by\/*" in q


def test_build_query_flagged_only_is_negated():
    q = build_query("etree", "", None, None, "etree", LICENSE_FILTERS[2])
    assert " AND -(licenseurl:*publicdomain*" in q


def test_build_query_free_text_skips_collection_folders():
    q = build_query(None, "mount shasta", None, None, None)
    assert q == "(mount shasta) AND -mediatype:collection"


def test_text_clause_escapes_and_keeps_phrases():
    assert text_clause('"mount shasta" train') == '("mount shasta" train)'
    assert text_clause("AC/DC: live!") == r"(AC\/DC\: live\!)"
    assert text_clause('unbalanced "quote') == r'(unbalanced \"quote)'
    assert text_clause("   ") == ""


def test_open_year_bound():
    assert "year:[1920 TO *]" in build_query("78rpm", "", 1920, None, "audio")


@responses.activate
def test_search_parses_and_sends_params():
    responses.add(responses.GET, SEARCH_URL, json=SEARCH_PAYLOAD)
    c, _ = plain_client()
    r = c.search("collection:prelinger", rows=12, page=3, sort="downloads desc")
    assert r.num_found == 2 and r.docs[0]["identifier"] == "DuckandC1951"
    sent = responses.calls[0].request
    assert "rows=12" in sent.url and "page=3" in sent.url and "output=json" in sent.url
    assert "fl%5B%5D=licenseurl" in sent.url and "sort%5B%5D=downloads+desc" in sent.url
    assert sent.headers["User-Agent"].startswith("tech-demos-internet-archive-explorer")


@responses.activate
def test_throttle_spaces_live_requests():
    responses.add(responses.GET, SEARCH_URL, json=SEARCH_PAYLOAD)
    c, fc = plain_client(min_interval=1.0)
    for _ in range(3):
        c.search("x")
    assert c.live_requests == 3
    assert fc.sleeps == [pytest.approx(1.0), pytest.approx(1.0)]


@responses.activate
def test_retries_429_with_retry_after():
    responses.add(responses.GET, SEARCH_URL, status=429, headers={"Retry-After": "5"})
    responses.add(responses.GET, SEARCH_URL, json=SEARCH_PAYLOAD)
    c, fc = plain_client(min_interval=0)
    assert c.search("x").num_found == 2
    assert 5.0 in fc.sleeps


@responses.activate
def test_gives_up_after_retries():
    for _ in range(5):
        responses.add(responses.GET, SEARCH_URL, status=503)
    c, _ = plain_client(min_interval=0, max_retries=2)
    with pytest.raises(requests.HTTPError):
        c.search("x")
    assert len(responses.calls) == 3


@responses.activate
def test_metadata_and_missing_item():
    responses.add(responses.GET, "https://archive.org/metadata/DuckandC1951",
                  json={"metadata": {"identifier": "DuckandC1951"}, "files": []})
    responses.add(responses.GET, "https://archive.org/metadata/nope", json={})
    c, _ = plain_client(min_interval=0)
    assert c.metadata("DuckandC1951")["metadata"]["identifier"] == "DuckandC1951"
    with pytest.raises(LookupError):
        c.metadata("nope")


@responses.activate
def test_disk_cache_avoids_second_live_request(tmp_path):
    responses.add(responses.GET, SEARCH_URL, json=SEARCH_PAYLOAD)
    fc = FakeClock()
    c = IAClient(make_session(str(tmp_path / "cache")), sleep=fc.sleep, clock=fc.clock)
    c.search("collection:prelinger")
    c.search("collection:prelinger")
    assert len(responses.calls) == 1
    assert c.live_requests == 1
    assert fc.sleeps == []  # cache hits are not throttled
