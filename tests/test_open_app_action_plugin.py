"""Testes para o plugin de abertura de apps."""

import os
import shutil

from plugins.open_app_action.__init__ import OpenAppPlugin


def test_resolve_executable_handles_chrome_and_browser_aliases(monkeypatch):
    plugin = OpenAppPlugin()
    monkeypatch.setattr(shutil, "which", lambda name: "chrome.exe" if name in ("chrome", "chromium", "msedge", "edge") else None)
    monkeypatch.setattr(os.path, "exists", lambda path: False)

    assert plugin._resolve_executable("chrome") == "chrome.exe"
    assert plugin._resolve_executable("navegador") == "chrome.exe"


def test_resolve_executable_handles_folder_aliases(monkeypatch):
    plugin = OpenAppPlugin()
    user_dir = os.path.expandvars("%USERPROFILE%")
    monkeypatch.setattr(shutil, "which", lambda name: "explorer.exe" if name == "explorer" else None)
    monkeypatch.setattr(os.path, "exists", lambda path: True if path in (os.path.join(user_dir, "Documents"), os.path.join(user_dir, "Desktop"), os.path.join(user_dir, "Downloads")) else False)

    assert plugin._resolve_executable("documentos") == os.path.join(user_dir, "Documents")
    assert plugin._resolve_executable("desktop") == os.path.join(user_dir, "Desktop")
    assert plugin._resolve_executable("downloads") == os.path.join(user_dir, "Downloads")
    assert plugin._resolve_executable("google.com") == "https://google.com"
    assert plugin._resolve_executable("www.github.com") == "https://www.github.com"
    assert plugin._resolve_executable("google", site_command=True) == "https://www.google.com"
    assert plugin._resolve_executable("google.com") == "https://google.com"
    assert plugin._resolve_executable("www.github.com") == "https://www.github.com"
