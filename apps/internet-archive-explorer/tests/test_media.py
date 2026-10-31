import csv
import io

from iaexplorer.media import (best_audio_tracks, display_collections, doc_to_row, doc_year, download_url,
                              downloadable_files, human_size, playable_files, to_csv_bytes)

FILM_FILES = [
    {"name": "DuckandC1951.mpeg", "format": "MPEG2", "source": "original", "size": "256413203"},
    {"name": "DuckandC1951.ia.mp4", "format": "h.264 IA", "source": "derivative", "size": "53299301"},
    {"name": "DuckandC1951_512kb.mp4", "format": "512Kb MPEG4", "source": "derivative", "size": "39240901"},
    {"name": "DuckandC1951.ogv", "format": "Ogg Video", "source": "derivative", "size": "39412437"},
    {"name": "DuckandC1951.mp3", "format": "MP3", "source": "derivative", "size": "4438016"},
    {"name": "DuckandC1951.thumbs/DuckandC1951_000001.jpg", "format": "Thumbnail", "source": "derivative"},
    {"name": "DuckandC1951_meta.xml", "format": "Metadata", "source": "original"},
    {"name": "DuckandC1951_archive.torrent", "format": "Archive BitTorrent", "source": "metadata"},
]

RECORD_FILES = [
    {"name": "02 - Side B.flac", "format": "Flac", "source": "original", "size": "30000000"},
    {"name": "01 - Side A.flac", "format": "Flac", "source": "original", "size": "31000000"},
    {"name": "02 - Side B.mp3", "format": "VBR MP3", "source": "derivative", "size": "3000000", "title": "Side B"},
    {"name": "01 - Side A.mp3", "format": "VBR MP3", "source": "derivative", "size": "3100000", "title": "Side A"},
    {"name": "01 - Side A.png", "format": "PNG", "source": "derivative"},
]


def test_video_pick_prefers_h264():
    v = playable_files(FILM_FILES)["video"]
    assert v[0]["name"] == "DuckandC1951.ia.mp4"
    assert all(".thumbs/" not in f["name"] for f in v)


def test_audio_tracks_mp3_in_track_order():
    names = [f["name"] for f in best_audio_tracks(RECORD_FILES)]
    assert names == ["01 - Side A.mp3", "02 - Side B.mp3"]


def test_audio_falls_back_to_flac():
    names = [f["name"] for f in best_audio_tracks([f for f in RECORD_FILES if f["format"] == "Flac"])]
    assert names == ["01 - Side A.flac", "02 - Side B.flac"]


def test_downloadable_skips_metadata_and_thumbs_originals_first():
    names = [f["name"] for f in downloadable_files(FILM_FILES)]
    assert names[0] == "DuckandC1951.mpeg"
    assert not any(n.endswith((".xml", ".torrent")) or ".thumbs/" in n for n in names)
    assert "DuckandC1951.mp3" in names


def test_download_url_quotes_spaces():
    assert download_url("abc", "01 - Side A.mp3") == "https://archive.org/download/abc/01%20-%20Side%20A.mp3"


def test_collections_drop_favourites():
    assert display_collections(["prelinger", "fav-bob", "fav-x"]) == "prelinger"
    assert display_collections("78rpm") == "78rpm"
    assert display_collections(None) == ""


def test_doc_year_falls_back_to_date():
    assert doc_year({"year": "1951"}) == 1951
    assert doc_year({"date": "1942-01-01T00:00:00Z"}) == 1942
    assert doc_year({"date": "unknown"}) is None
    assert doc_year({}) is None


def test_human_size():
    assert human_size(0) == "?"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


def test_csv_export_columns_and_flags():
    docs = [
        {"identifier": "DuckandC1951", "title": "Duck and Cover", "year": 1951, "mediatype": "movies",
         "collection": ["prelinger", "fav-a"], "licenseurl": "http://creativecommons.org/licenses/publicdomain/"},
        {"identifier": "gd77", "title": ["Grateful Dead Live"], "mediatype": "etree",
         "collection": ["etree"], "rights": "Trading only, no sales."},
        {"identifier": "ncitem", "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"},
    ]
    rows = list(csv.DictReader(io.StringIO(to_csv_bytes(docs).decode())))
    for col in ("title", "identifier", "year", "collection", "license_url", "rights", "source_url", "commercial_ok"):
        assert col in rows[0]
    assert rows[0]["commercial_ok"] == "YES" and rows[0]["collection"] == "prelinger"
    assert rows[0]["source_url"] == "https://archive.org/details/DuckandC1951"
    assert rows[1]["commercial_ok"].startswith("NO") and rows[1]["rights"] == "Trading only, no sales."
    assert rows[1]["year"] == ""
    assert rows[2]["commercial_ok"].startswith("NO") and rows[2]["title"] == "ncitem"


def test_row_license_label():
    assert doc_to_row({"identifier": "x", "licenseurl": "https://creativecommons.org/licenses/by-sa/4.0/"})[
        "license"] == "CC BY-SA"
