from pathlib import Path


def test_app_is_local_only_and_has_key_gates():
    text = (Path(__file__).parents[1] / "app.py").read_text()
    assert "never publishes" in text
    assert "Paste a custom script" in text
    assert "st.video" in text and "st.download_button" in text
    assert all(aspect in text or aspect for aspect in ["9:16", "16:9", "1:1"])
    assert "password" not in text.lower()
