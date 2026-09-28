from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_OCR_TEXT = 12_000
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class VisionManager:
    def __init__(self, image_module: Any = None, ocr_engine: Callable | None = None) -> None:
        self._image_module = image_module
        self._ocr_engine = ocr_engine

    def extract_text(self, image_path: str | Path, language: str = "por+eng") -> str:
        path = Path(image_path)
        if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError("Formato de imagem não suportado.")
        if not path.is_file():
            raise ValueError("Arquivo de imagem não encontrado.")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Tamanho da imagem excede o limite de 20 MiB.")

        image_module = self._image_module
        ocr_engine = self._ocr_engine
        if image_module is None or ocr_engine is None:
            try:
                from PIL import Image
                import pytesseract
            except ImportError as exc:
                raise RuntimeError("OCR exige Pillow e pytesseract instalados.") from exc
            image_module = image_module or Image
            ocr_engine = ocr_engine or pytesseract.image_to_string

        with image_module.open(path) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Dimensões da imagem excedem o limite seguro de pixels.")
            image.load()
            text = ocr_engine(image, lang=language)
        return str(text).strip()[:MAX_OCR_TEXT]