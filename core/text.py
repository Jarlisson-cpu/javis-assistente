"""Normalização de texto para comandos digitados ou falados.

Transcrições de voz chegam sem pontuação e com variações ("abre o chrome",
"Jarvis, por favor abra o Chrome!"). Todo casamento de comandos usa
`normalize` para que as duas formas sejam tratadas da mesma maneira.
"""

from __future__ import annotations

import re
import unicodedata

_POLITE_PREFIXES = (
    "ei jarvis",
    "ok jarvis",
    "oi jarvis",
    "jarvis",
    "por favor",
    "por gentileza",
    "eu quero que voce",
    "quero que voce",
    "eu queria que voce",
    "voce pode",
    "voce poderia",
    "voce consegue",
    "pode",
    "poderia",
    "consegue",
    "da pra",
    "favor",
)

_NUMBER_WORDS = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
    "cem": 100,
    "meia": 30,
}


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize(text: str, *, drop_polite: bool = True) -> str:
    """Minúsculas, sem acentos, sem pontuação nas pontas e espaços colapsados."""
    value = strip_accents(text or "").lower()
    value = re.sub(r"[﻿​-‍⁠]", "", value)  # BOM e caracteres invisíveis
    value = re.sub(r"[\"“”'`´!?¿¡;]+", " ", value)
    value = re.sub(r"(?<!\d),|,(?!\d)", " ", value)  # mantém a vírgula decimal (3,5)
    value = re.sub(r"\s+", " ", value).strip(" ,.:-")
    if drop_polite:
        changed = True
        while changed:
            changed = False
            for prefix in _POLITE_PREFIXES:
                if value == prefix:
                    break
                if value.startswith(prefix + " "):
                    value = value[len(prefix) + 1 :].strip(" ,.:-")
                    changed = True
        value = re.sub(r"\s+por favor$", "", value)
    return value


def parse_number(value: str | None) -> int | None:
    """Converte "50", "cinquenta", "vinte e cinco" ou "meia" em inteiro."""
    if value is None:
        return None
    cleaned = normalize(value, drop_polite=False).replace("%", "").replace("por cento", "").strip()
    if not cleaned:
        return None
    if re.fullmatch(r"\d+", cleaned):
        return int(cleaned)

    total = 0
    found = False
    for word in re.split(r"\s+|-", cleaned):
        if word == "e":
            continue
        if word not in _NUMBER_WORDS:
            return None
        total += _NUMBER_WORDS[word]
        found = True
    return total if found else None


NUMBER_PATTERN = (
    r"\d+|(?:(?:zero|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|"
    r"quatorze|catorze|quinze|dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta|"
    r"cinquenta|sessenta|setenta|oitenta|noventa|cem|meia)(?:\s+e\s+|\s+)?)+"
)
