from __future__ import annotations

import ctypes
import os
import webbrowser
from typing import Callable
from urllib.parse import quote_plus


class MediaManager:
    _media_keys = {
        "play_pause": 0xB3,
        "next": 0xB0,
        "previous": 0xB1,
        "volume_up": 0xAF,
        "volume_down": 0xAE,
    }

    def __init__(
        self,
        opener: Callable[[str], bool] | None = None,
        key_sender: Callable[[int], None] | None = None,
    ) -> None:
        self._opener = opener or webbrowser.open
        self._key_sender = key_sender or self._send_windows_media_key

    @staticmethod
    def _send_windows_media_key(virtual_key: int) -> None:
        if os.name != "nt":
            raise RuntimeError("Controles de mídia estão disponíveis apenas no Windows.")
        keybd_event = ctypes.windll.user32.keybd_event
        keybd_event(virtual_key, 0, 0, 0)
        keybd_event(virtual_key, 0, 0x0002, 0)

    def control(self, action: str) -> None:
        try:
            virtual_key = self._media_keys[action]
        except KeyError as exc:
            raise ValueError("Controle de mídia não suportado.") from exc
        self._key_sender(virtual_key)

    def search(self, query: str, kind: str = "video") -> bool:
        query = query.strip()
        if not query or len(query) > 500:
            raise ValueError("A busca deve ter entre 1 e 500 caracteres.")
        if kind == "music":
            url = f"https://music.youtube.com/search?q={quote_plus(query)}"
        elif kind == "video":
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        else:
            raise ValueError("Tipo de mídia deve ser 'music' ou 'video'.")
        return bool(self._opener(url))