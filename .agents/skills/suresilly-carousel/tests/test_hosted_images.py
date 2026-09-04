"""A reachable host must still serve all nine exact checked PNGs."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import post_to_ig as post


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    slides = tmp_path / "slides"
    slides.mkdir()
    data = {}
    for n in range(1, 10):
        name = f"{n:02}_slide.png"
        raw = b"checked image bytes " + bytes([n])
        (slides / name).write_bytes(raw)
        data[f"https://example.com/{name}"] = (200, raw)
    calls = []

    class Response:
        def __init__(self, status, raw):
            self.status_code, self.raw = status, raw
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_content(self, chunk_size):
            yield self.raw[:5]
            yield self.raw[5:]

    def get(url, **kwargs):
        calls.append(url)
        assert kwargs == dict(stream=True, timeout=(5, 10), allow_redirects=False)
        value = data[url]
        if isinstance(value, Exception):
            raise value
        return Response(*value)
    monkeypatch.setattr(post.requests, "get", get)
    monkeypatch.setattr(post.requests, "post", lambda *a, **k: pytest.fail("unexpected Instagram write"))
    monkeypatch.setattr(post, "require_posting_allowed", lambda: None)
    return tmp_path, data, calls


def test_all_nine_match(hosted):
    folder, data, calls = hosted
    post.check_hosted_images(folder, list(data))
    assert calls == list(data)


@pytest.mark.parametrize("fault", ["404", "redirect", "changed", "truncated", "oversized", "timeout"])
def test_bad_ninth_image_blocks_the_set(hosted, fault):
    folder, data, calls = hosted
    last = list(data)[-1]
    raw = data[last][1]
    replacements = {"404": (404, b""), "redirect": (302, b""),
                    "changed": (200, b"X" + raw[1:]), "truncated": (200, raw[:-1]),
                    "oversized": (200, raw + b"X"), "timeout": post.requests.Timeout("test")}
    data[last] = replacements[fault]
    with pytest.raises((ValueError, post.requests.Timeout)):
        post.check_hosted_images(folder, list(data))
    assert len(calls) == 9


def test_missing_url_stops_before_network(hosted):
    folder, data, calls = hosted
    with pytest.raises(ValueError, match="nine"):
        post.check_hosted_images(folder, list(data)[:-1])
    assert not calls


def test_http_is_refused_before_network(hosted):
    folder, data, calls = hosted
    with pytest.raises(ValueError, match="HTTPS"):
        post.check_hosted_images(folder, [url.replace("https:", "http:") for url in data])
    assert not calls


def test_publisher_reports_host_failure_before_any_instagram_write(hosted, monkeypatch):
    import bibliography
    folder, data, calls = hosted
    md = folder / "carousel.md"
    md.write_text("## Caption\nA test caption")
    data[list(data)[-1]] = (404, b"")
    monkeypatch.setattr(bibliography, "require_deck_support", lambda _: None)
    monkeypatch.setattr(post, "check_export", lambda *a: None)
    monkeypatch.setenv("IG_USER_ID", "test-user")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(sys, "argv", ["post_to_ig.py", "--carousel", str(md), "--base-url", "https://example.com"])
    outputs = []
    monkeypatch.setattr(post, "publication_outputs", lambda **values: outputs.append(values))
    with pytest.raises(SystemExit, match="Nothing was posted"):
        post.main()
    assert outputs[0]["stage"] == "hosting"
    assert "09_slide.png" in outputs[0]["reason"]
    assert len(calls) == 9
