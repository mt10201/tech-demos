# Internet Archive Explorer: plan

## Goal
Find free films, 78rpm records and live concert recordings on archive.org, preview them, download them, and know at a
glance whether each one is safe for **commercial** reuse (product videos, YouTube, ads).

## MVP (single user, local)
- Search by preset collection (Prelinger films, 78rpm records, Live Music Archive / etree) or anything (free text).
- Filters: year range, media type, license / rights (all, commercial-reuse OK only, flagged only).
- Results grid with thumbnails and a clear **Commercial reuse OK?** flag.
- Item view: video / audio player, file list with one-click downloads.
- CSV export: title, identifier, year, collection, license URL, rights text, commercial flag, source URL.
- Gentle on the Archive: disk cache (24 h) and a minimum gap between live requests, identifying User-Agent.

**Out:** accounts / uploads, bulk downloading of whole collections, legal advice, full-text (OCR) search,
the Wayback Machine, scraping beyond the public APIs.

## Slices
1. `iaexplorer/rights.py`: classify `licenseurl` + `rights` -> OK (public domain, CC0, CC-BY, CC-BY-SA) or
   flagged (NC, ND, other, unknown). Strict: no declared license = flagged.
2. `iaexplorer/client.py`: query builder + Advanced Search + Metadata API client (cache + throttle).
3. `iaexplorer/media.py`: pick playable derivatives, list downloadable files, build URLs; CSV export rows.
4. `app.py`: Streamlit UI (sidebar filters, results grid, item detail, CSV).
5. Offline tests with mocked HTTP (`responses`), screenshots + short walkthrough video, README.

## Stack
- **Streamlit**: one-file UI with native video/audio players and deferred download buttons.
- **requests + requests-cache**: boring HTTP with a SQLite cache, so repeat searches cost the Archive nothing.
- **pandas**: results table and CSV export.
- **pytest + responses**: offline tests with mocked Archive responses.
- APIs: `advancedsearch.php` (search), `/metadata/<id>` (files and rights), `/services/img/<id>` (thumbnails),
  `/download/<id>/<file>` (media). All free, no key.

## Folder layout
```
apps/internet-archive-explorer/
  PLAN.md  README.md  requirements.txt  app.py
  iaexplorer/  __init__.py  rights.py  client.py  media.py
  tests/       conftest.py  test_rights.py  test_client.py  test_media.py
  scripts/     capture.py (screenshots + walkthrough video)
  media/       screenshots + walkthrough
```

## Deferred
- Save favourites / "use in video" shortlist shared with the video bot.
- Clip trimming (ffmpeg) and waveform previews.
- Per-file license overrides, and US public-domain-by-date rules for old sound recordings.
- Scrape-API cursor paging for >10k result exports.
