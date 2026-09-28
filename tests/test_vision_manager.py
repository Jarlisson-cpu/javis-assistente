from pathlib import Path

import pytest

from vision.manager import VisionManager


def test_ocr_extracts_bounded_text_from_supported_image(tmp_path: Path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"image")

    class FakeImage:
        size = (100, 50)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def load(self):
            pass

    manager = VisionManager(
        image_module=type("ImageModule", (), {"open": staticmethod(lambda path: FakeImage())}),
        ocr_engine=lambda image, lang: "texto reconhecido",
    )

    assert manager.extract_text(image_path) == "texto reconhecido"


def test_ocr_rejects_unsupported_and_oversized_files(tmp_path: Path):
    unsupported = tmp_path / "document.pdf"
    unsupported.write_bytes(b"pdf")
    oversized = tmp_path / "large.png"
    oversized.write_bytes(b"x" * (20 * 1024 * 1024 + 1))
    manager = VisionManager()

    with pytest.raises(ValueError, match="Formato"):
        manager.extract_text(unsupported)
    with pytest.raises(ValueError, match="Tamanho"):
        manager.extract_text(oversized)


def test_ocr_rejects_images_with_excessive_dimensions(tmp_path: Path):
    image_path = tmp_path / "large.png"
    image_path.write_bytes(b"image")

    class FakeImage:
        size = (100_000, 100_000)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    manager = VisionManager(
        image_module=type("ImageModule", (), {"open": staticmethod(lambda path: FakeImage())}),
        ocr_engine=lambda image, lang: "",
    )

    with pytest.raises(ValueError, match="Dimensões"):
        manager.extract_text(image_path)