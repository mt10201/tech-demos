"""Small, polite client for the free Internet Archive APIs (no key needed)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import requests

from .rights import COMMERCIAL_OK_QUERY

BASE = "https://archive.org"
USER_AGENT = "tech-demos-internet-archive-explorer/0.1 (personal research; github.com/mt10201/tech-demos)"

COLLECTIONS = {
    "Prelinger films (ephemeral & industrial films)": {"collection": "prelinger", "mediatype": "movies"},
    "78rpm records (Great 78 Project)": {"collection": "78rpm", "mediatype": "audio"},
    "Live concerts (Live Music Archive / etree)": {"collection": "etree", "mediatype": "etree"},
    "Anything (free-text search)": {"collection": None, "mediatype": None},
}

MEDIA_TYPES = {
    "Any": None,
    "Movies / video": "movies",
    "Audio": "audio",
    "Live concerts (etree)": "etree",
    "Images": "image",
    "Texts": "texts",
}

LICENSE_FILTERS = ("All", "Commercial reuse OK only", "Flagged only (NC / ND / unknown)")

SORTS = {
    "Most downloaded": "downloads desc",
    "Newest year": "year desc",
    "Oldest year": "year asc",
    "Title A-Z": "titleSorter asc",
    "Recently added": "addeddate desc",
}

SEARCH_FIELDS = [
    "identifier", "title", "year", "date", "collection", "mediatype",
    "licenseurl", "rights", "creator", "downloads", "description",
]


_BAD = set('+-&|!(){}[]^"~*?:\\/')


def _escape(text: str) -> str:
    """Neutralise Lucene syntax in user text."""
    return "".join("\\" + c if c in _BAD else c for c in text)


def text_clause(text: str) -> str:
    """Free text -> Lucene clause. Balanced "double quotes" become exact phrases."""
    text = (text or "").strip()
    if not text:
        return ""
    tokens: list[str] = []
    if text.count('"') % 2 == 0:
        for i, chunk in enumerate(text.split('"')):
            if i % 2 == 1:
                if chunk.strip():
                    tokens.append('"' + _escape(chunk.strip()).replace('\\"', "") + '"')
            else:
                tokens += [_escape(w) for w in chunk.split()]
    else:
        tokens = [_escape(w) for w in text.split()]
    return "(" + " ".join(tokens) + ")" if tokens else ""


def build_query(
    collection: str | None = None,
    text: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    mediatype: str | None = None,
    license_filter: str = "All",
) -> str:
    parts: list[str] = []
    clause = text_clause(text)
    if clause:
        parts.append(clause)
    if collection:
        parts.append(f"collection:{collection}")
    if mediatype:
        parts.append(f"mediatype:{mediatype}")
    else:
        parts.append("-mediatype:collection")  # skip folders like artist collections
    if year_from is not None or year_to is not None:
        lo = year_from if year_from is not None else "*"
        hi = year_to if year_to is not None else "*"
        parts.append(f"year:[{lo} TO {hi}]")
    if license_filter == LICENSE_FILTERS[1]:
        parts.append(COMMERCIAL_OK_QUERY)
    elif license_filter == LICENSE_FILTERS[2]:
        parts.append(f"-{COMMERCIAL_OK_QUERY}")
    return " AND ".join(parts) if parts else "*:*"


@dataclass
class SearchResult:
    num_found: int
    docs: list[dict] = field(default_factory=list)


def make_session(cache_path: str | None = ".ia_cache", expire_seconds: int = 24 * 3600) -> requests.Session:
    """A requests session with a SQLite HTTP cache (falls back to plain requests)."""
    if cache_path:
        try:
            import requests_cache

            s = requests_cache.CachedSession(
                cache_path, backend="sqlite", expire_after=expire_seconds,
                allowable_codes=(200,), stale_if_error=True,
            )
        except Exception:  # pragma: no cover - optional dependency missing
            s = requests.Session()
    else:
        s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


class IAClient:
    """Search + metadata with a minimum gap between live (uncached) requests."""

    def __init__(self, session: requests.Session | None = None, min_interval: float = 1.0,
                 timeout: float = 30.0, max_retries: int = 3, sleep=time.sleep, clock=time.monotonic):
        self.session = session or make_session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self._lock = threading.Lock()
        self.live_requests = 0

    def _get(self, url: str, params=None) -> dict:
        for attempt in range(self.max_retries + 1):
            with self._lock:
                resp = self._send(url, params)
            if resp.status_code in (429, 503) and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else 2.0 * (2 ** attempt)
                except ValueError:
                    wait = 2.0 * (2 ** attempt)
                self._sleep(min(wait, 60.0))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("unreachable")  # pragma: no cover

    def _send(self, url, params):
        # Only live requests are throttled; cache hits return immediately.
        cached = False
        try:
            import requests_cache  # noqa: F401
            if hasattr(self.session, "cache"):
                req = requests.Request("GET", url, params=params, headers=self.session.headers).prepare()
                cached = self.session.cache.contains(request=req)
        except Exception:
            cached = False
        if not cached and self._last is not None:
            gap = self._clock() - self._last
            if gap < self.min_interval:
                self._sleep(self.min_interval - gap)
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if not getattr(resp, "from_cache", False):
            self._last = self._clock()
            self.live_requests += 1
        return resp

    def search(self, query: str, rows: int = 24, page: int = 1, sort: str | None = "downloads desc",
               fields: list[str] | None = None) -> SearchResult:
        params: list[tuple[str, str]] = [("q", query)]
        for f in fields or SEARCH_FIELDS:
            params.append(("fl[]", f))
        if sort:
            params.append(("sort[]", sort))
        params += [("rows", str(rows)), ("page", str(page)), ("output", "json")]
        data = self._get(f"{BASE}/advancedsearch.php", params=params)
        resp = data.get("response", {})
        return SearchResult(int(resp.get("numFound", 0)), list(resp.get("docs", [])))

    def metadata(self, identifier: str) -> dict:
        data = self._get(f"{BASE}/metadata/{identifier}")
        if not data or "metadata" not in data:
            raise LookupError(f"No metadata for {identifier!r}")
        return data
