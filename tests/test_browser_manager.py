from types import SimpleNamespace

import pytest

from browser.manager import BrowserManager, validate_public_url


def test_public_url_validation_blocks_local_and_non_http_urls(monkeypatch):
    monkeypatch.setattr("browser.manager.socket.getaddrinfo", lambda *args, **kwargs: [])

    with pytest.raises(ValueError):
        validate_public_url("file:///C:/secret.txt")
    with pytest.raises(ValueError):
        validate_public_url("http://localhost/admin")
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1/")


def test_browser_manager_returns_bounded_page_text_and_closes_browser():
    state = {"closed": False, "navigated": None}

    class FakeBrowser:
        def new_page(self):
            return FakePage()

        def close(self):
            state["closed"] = True

    class FakePage:
        def route(self, pattern, callback):
            self.route_callback = callback

        def goto(self, url, **kwargs):
            state["navigated"] = url

        def locator(self, selector):
            return SimpleNamespace(inner_text=lambda timeout: "conteúdo" * 20)

    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: FakeBrowser()))
    manager = BrowserManager(playwright_factory=lambda: FakePlaywrightContext(playwright))
    manager._validate_url = lambda url: None

    result = manager.read_page("https://example.com", max_chars=30)

    assert len(result) == 30
    assert state["navigated"] == "https://example.com"
    assert state["closed"] is True


class FakePlaywrightContext:
    def __init__(self, playwright):
        self.playwright = playwright

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc_value, traceback):
        return False