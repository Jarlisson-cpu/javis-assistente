from __future__ import annotations

import re
import webbrowser
from typing import Callable
from urllib.parse import quote, urlencode


class CommunicationManager:
    def __init__(self, opener: Callable[[str], bool] | None = None) -> None:
        self._opener = opener or webbrowser.open

    def open_email_draft(self, recipient: str, subject: str, body: str) -> bool:
        recipient = recipient.strip()
        if len(recipient) > 254 or not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", recipient
        ):
            raise ValueError("Endereço de e-mail inválido.")
        if any(character in subject for character in "\r\n"):
            raise ValueError("O assunto não pode conter quebras de linha.")
        if len(subject) > 200 or len(body) > 10_000:
            raise ValueError("Assunto ou mensagem excede o limite permitido.")

        encoded_recipient = quote(recipient, safe="@.+-_")
        query = urlencode({"subject": subject, "body": body})
        url = f"mailto:{encoded_recipient}?{query}"
        return bool(self._opener(url))