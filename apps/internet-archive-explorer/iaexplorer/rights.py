"""Classify an Internet Archive item's license for COMMERCIAL reuse.

Strict rule: only public domain, CC0, CC-BY and CC-BY-SA count as OK.
Anything NonCommercial, NoDerivatives, any other license, or no declared license is flagged.
This is a screening aid, not legal advice: always read the item page before using it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

OK = "OK"
FLAGGED = "FLAGGED"


@dataclass(frozen=True)
class RightsVerdict:
    status: str  # OK or FLAGGED
    label: str  # human-readable license family
    reason: str  # why

    @property
    def commercial_ok(self) -> bool:
        return self.status == OK


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value if v is not None)
    return str(value)


_CC_RE = re.compile(r"creativecommons\.org/licenses/([a-z\-]+)/?", re.I)

_NEGATED_PD = re.compile(
    r"\b(not|no longer|isn't|is not|never)\b[^.]{0,30}public\s+domain", re.I
)


def classify(licenseurl=None, rights=None) -> RightsVerdict:
    url = _as_text(licenseurl).strip().lower()
    text = _as_text(rights).strip()

    if url:
        if "publicdomain/zero" in url:
            return RightsVerdict(OK, "CC0", "CC0 public-domain dedication")
        if "publicdomain/mark" in url or "/licenses/publicdomain" in url:
            return RightsVerdict(OK, "Public domain", "Public Domain Mark / dedication")
        m = _CC_RE.search(url)
        if m:
            code = m.group(1).lower()
            parts = set(code.split("-"))
            label = "CC " + code.upper()
            if "nc" in parts:
                return RightsVerdict(FLAGGED, label, "NonCommercial: no commercial use")
            if "nd" in parts:
                return RightsVerdict(FLAGGED, label, "NoDerivatives: can't edit into a video")
            if code in ("by", "by-sa"):
                why = "Attribution required" + (", share-alike" if code == "by-sa" else "")
                return RightsVerdict(OK, label, why)
            return RightsVerdict(FLAGGED, label, "Unrecognised Creative Commons variant")
        return RightsVerdict(FLAGGED, "Other license", f"Unrecognised license URL: {url[:80]}")

    if text:
        low = text.lower()
        if re.search(r"public\s+domain", low) and not _NEGATED_PD.search(low):
            if re.search(r"non-?commercial|all rights reserved", low):
                return RightsVerdict(FLAGGED, "Rights text", "Rights text mentions restrictions")
            return RightsVerdict(OK, "Public domain (rights text)", "Rights statement says public domain")
        return RightsVerdict(FLAGGED, "Rights text", "Rights statement only; no open license")

    return RightsVerdict(FLAGGED, "Unknown", "No license declared on the item")


# Server-side pre-filter for "commercial OK only": narrows the search to items whose
# licenseurl looks like PD / CC0 / CC-BY / CC-BY-SA. Results are still re-checked with classify().
COMMERCIAL_OK_QUERY = (
    r"(licenseurl:*publicdomain* OR licenseurl:*\/by\/* OR licenseurl:*\/by-sa\/*)"
)
