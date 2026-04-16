from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def ensure_tesseract() -> None:
    if shutil.which("tesseract") is None:
        raise RuntimeError(
            "tesseract not found. Install with: sudo apt install tesseract-ocr tesseract-ocr-spa"
        )


def ensure_pdftoppm() -> None:
    if shutil.which("pdftoppm") is None:
        raise RuntimeError(
            "pdftoppm not found. Install with: sudo apt install poppler-utils"
        )


def ocr_pdf(pdf_path: str | Path, lang: str = "spa", dpi: int = 200) -> str:
    pdf_path = Path(pdf_path)
    ensure_tesseract()
    ensure_pdftoppm()

    text_parts: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefix = str(tmp_path / "page")

        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), prefix],
            check=True,
            capture_output=True,
        )

        for png in sorted(tmp_path.glob("page-*.png")):
            r = subprocess.run(
                ["tesseract", str(png), "stdout", "-l", lang, "--psm", "6"],
                check=True,
                capture_output=True,
                text=True,
            )
            text_parts.append(r.stdout)

    return "\n\n".join(text_parts).strip()
