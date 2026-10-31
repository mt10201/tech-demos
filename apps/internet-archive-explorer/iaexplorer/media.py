"""File picking, URLs and CSV rows for Internet Archive items."""
from __future__ import annotations

from urllib.parse import quote

import pandas as pd

from .rights import classify

BASE = "https://archive.org"

# Preferred playable derivatives, best first.
VIDEO_FORMATS = ["h.264 IA", "h.264", "MPEG4", "512Kb MPEG4", "HiRes MPEG4", "Ogg Video", "WebM"]
AUDIO_FORMATS = ["VBR MP3", "MP3", "128Kbps MP3", "64Kbps MP3", "Ogg Vorbis", "Flac", "FLAC", "24bit Flac", "WAVE"]

VIDEO_EXT = (".mp4", ".m4v", ".ogv", ".webm")
AUDIO_EXT = (".mp3", ".ogg", ".flac", ".wav", ".m4a")

SKIP_FORMATS = {
    "Metadata", "Archive BitTorrent", "Item Tile", "Thumbnail", "JPEG Thumb", "Storj Upload Log",
    "Storj Upload Trigger", "Unknown", "Columbia Peaks", "Spectrogram", "PNG", "Animated GIF",
    "Web Video Text Tracks", "Intermediate ASR JSON", "Checksums", "Text", "Item Image",
}
SKIP_SUFFIX = ("_meta.sqlite", "_meta.xml", "_files.xml", "_reviews.xml", ".torrent", ".log", ".trigger")


def details_url(identifier: str) -> str:
    return f"{BASE}/details/{quote(identifier)}"


def thumbnail_url(identifier: str) -> str:
    return f"{BASE}/services/img/{quote(identifier)}"


def download_url(identifier: str, name: str) -> str:
    return f"{BASE}/download/{quote(identifier)}/{quote(name)}"


def first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def doc_year(doc: dict):
    y = first(doc.get("year"))
    if y not in (None, ""):
        try:
            return int(str(y)[:4])
        except ValueError:
            pass
    d = first(doc.get("date"))
    if d:
        try:
            return int(str(d)[:4])
        except ValueError:
            return None
    return None


def display_collections(value) -> str:
    """Join collections, dropping users' favourites lists (fav-*)."""
    if value is None:
        return ""
    items = value if isinstance(value, (list, tuple)) else [value]
    keep = [str(c) for c in items if c and not str(c).startswith("fav-")]
    return "; ".join(keep)


def _size(f: dict) -> int:
    try:
        return int(f.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def human_size(n: int) -> str:
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"  # pragma: no cover


def _rank(fmt: str, order: list[str]) -> int:
    return order.index(fmt) if fmt in order else len(order)


def playable_files(files: list[dict]) -> dict[str, list[dict]]:
    """Return {'video': [...], 'audio': [...]} best-first, one entry per file."""
    video, audio = [], []
    for f in files or []:
        name = str(f.get("name", ""))
        fmt = str(f.get("format", ""))
        low = name.lower()
        if "/" in name and ".thumbs/" in low:
            continue
        if fmt in VIDEO_FORMATS or (low.endswith(VIDEO_EXT) and fmt not in SKIP_FORMATS):
            video.append(f)
        elif fmt in AUDIO_FORMATS or (low.endswith(AUDIO_EXT) and fmt not in SKIP_FORMATS):
            audio.append(f)
    video.sort(key=lambda f: (_rank(str(f.get("format")), VIDEO_FORMATS), name_key(f)))
    # Audio: keep track order, but prefer browser-friendly formats.
    audio.sort(key=lambda f: (_rank(str(f.get("format")), AUDIO_FORMATS) > 3, name_key(f)))
    return {"video": video, "audio": audio}


def name_key(f: dict) -> str:
    return str(f.get("name", "")).lower()


def best_audio_tracks(files: list[dict]) -> list[dict]:
    """One browser-playable file per track (MP3 / Ogg first), in name order."""
    audio = playable_files(files)["audio"]
    mp3 = [f for f in audio if str(f.get("format")) in AUDIO_FORMATS[:4] or name_key(f).endswith(".mp3")]
    if mp3:
        return sorted(mp3, key=name_key)
    ogg = [f for f in audio if name_key(f).endswith(".ogg")]
    return sorted(ogg or audio, key=name_key)


def downloadable_files(files: list[dict]) -> list[dict]:
    """Media and documents worth offering, largest first within originals then derivatives."""
    out = []
    for f in files or []:
        name = str(f.get("name", ""))
        fmt = str(f.get("format", ""))
        if not name or fmt in SKIP_FORMATS or name.endswith(SKIP_SUFFIX) or ".thumbs/" in name:
            continue
        out.append(f)
    out.sort(key=lambda f: (f.get("source") != "original", -_size(f)))
    return out


CSV_COLUMNS = [
    "title", "identifier", "year", "collection", "mediatype", "commercial_ok", "license",
    "license_reason", "license_url", "rights", "creator", "source_url",
]


def doc_to_row(doc: dict) -> dict:
    v = classify(doc.get("licenseurl"), doc.get("rights"))
    rights = doc.get("rights")
    if isinstance(rights, (list, tuple)):
        rights = " ".join(str(r) for r in rights)
    creator = doc.get("creator")
    if isinstance(creator, (list, tuple)):
        creator = "; ".join(str(c) for c in creator)
    ident = str(doc.get("identifier", ""))
    return {
        "title": str(first(doc.get("title")) or ident),
        "identifier": ident,
        "year": doc_year(doc),
        "collection": display_collections(doc.get("collection")),
        "mediatype": first(doc.get("mediatype")) or "",
        "commercial_ok": "YES" if v.commercial_ok else "NO - check",
        "license": v.label,
        "license_reason": v.reason,
        "license_url": first(doc.get("licenseurl")) or "",
        "rights": (rights or "").strip(),
        "creator": creator or "",
        "source_url": details_url(ident),
    }


def docs_to_frame(docs: list[dict]) -> pd.DataFrame:
    rows = [doc_to_row(d) for d in docs]
    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    df["year"] = df["year"].astype("Int64")
    return df


def to_csv_bytes(docs: list[dict]) -> bytes:
    return docs_to_frame(docs).to_csv(index=False).encode("utf-8")
