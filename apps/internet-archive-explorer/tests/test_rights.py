import pytest

from iaexplorer.rights import classify


@pytest.mark.parametrize("url,label", [
    ("http://creativecommons.org/licenses/publicdomain/", "Public domain"),
    ("http://creativecommons.org/publicdomain/mark/1.0/", "Public domain"),
    ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
    ("https://creativecommons.org/licenses/by/4.0/", "CC BY"),
    ("http://creativecommons.org/licenses/by-sa/3.0/us/", "CC BY-SA"),
    (["HTTPS://CreativeCommons.org/licenses/by/2.0/"], "CC BY"),
])
def test_commercial_ok(url, label):
    v = classify(url, None)
    assert v.commercial_ok and v.label == label


@pytest.mark.parametrize("url", [
    "http://creativecommons.org/licenses/by-nc/3.0/",
    "http://creativecommons.org/licenses/by-nc-sa/2.5/ca/",
    "https://creativecommons.org/licenses/by-nc-nd/4.0/",
    "https://creativecommons.org/licenses/by-nd/4.0/",
    "https://creativecommons.org/licenses/sampling+/1.0/",
    "https://example.com/my-license",
])
def test_flagged_licenses(url):
    assert not classify(url, None).commercial_ok


def test_nc_reason_and_nd_reason():
    assert "NonCommercial" in classify("https://creativecommons.org/licenses/by-nc-nd/4.0/").reason
    assert "NoDerivatives" in classify("https://creativecommons.org/licenses/by-nd/4.0/").reason


def test_unknown_when_nothing_declared():
    v = classify(None, None)
    assert not v.commercial_ok and v.label == "Unknown"
    assert not classify("", "").commercial_ok


def test_rights_text():
    assert classify(None, "This film is in the public domain.").commercial_ok
    assert not classify(None, "This recording is not in the public domain.").commercial_ok
    assert not classify(None, "Public domain in the US; non-commercial use only elsewhere").commercial_ok
    assert not classify(None, "Taper permission: trading only, no sales.").commercial_ok


def test_license_url_beats_rights_text():
    v = classify("https://creativecommons.org/licenses/by-nc/4.0/", "public domain")
    assert not v.commercial_ok
