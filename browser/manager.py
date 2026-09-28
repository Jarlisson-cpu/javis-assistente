from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Callable


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("O endereço deve usar http ou https e conter um host.")
    if parsed.username or parsed.password:
        raise ValueError("URLs com credenciais embutidas não são permitidas.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError("Endereços locais não são permitidos pelo navegador seguro.")

    try:
        address = ipaddress.ip_address(hostname)
        addresses = [address]
    except ValueError:
        try:
            results = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ValueError("Não foi possível resolver o host solicitado.") from exc
        addresses = [ipaddress.ip_address(result[4][0]) for result in results]

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("O navegador bloqueou um endereço IP não público.")
    return url


class BrowserManager:
    def __init__(self, playwright_factory: Callable | None = None) -> None:
        self._playwright_factory = playwright_factory

    def _validate_url(self, url: str) -> str:
        return validate_public_url(url)

    def read_page(self, url: str, timeout_ms: int = 15000, max_chars: int = 12000) -> str:
        self._validate_url(url)
        if timeout_ms < 1000 or timeout_ms > 60000:
            raise ValueError("timeout_ms deve estar entre 1000 e 60000.")
        if max_chars < 1 or max_chars > 50000:
            raise ValueError("max_chars deve estar entre 1 e 50000.")

        factory = self._playwright_factory
        if factory is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError("Playwright não está instalado. Instale-o por requirements.txt.") from exc
            factory = sync_playwright

        with factory() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()

                def guard_request(route, request) -> None:
                    try:
                        self._validate_url(request.url)
                    except ValueError:
                        route.abort()
                        return
                    route.continue_()

                page.route("**/*", guard_request)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                return page.locator("body").inner_text(timeout=timeout_ms)[:max_chars]
            finally:
                browser.close()