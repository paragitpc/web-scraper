from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


MIN_TEXT_PER_PAGE = 80


@dataclass
class ExtractionResult:
    text: str
    pages: int
    chars_per_page: float
    method: str
    likely_scanned: bool


def extract_native(pdf_path: str | Path) -> ExtractionResult:
    pdf_path = Path(pdf_path)
    pages_text: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            pages_text.append(t)

    full_text = "\n\n".join(pages_text).strip()
    n_pages = len(pages_text)
    chars_per_page = (len(full_text) / n_pages) if n_pages > 0 else 0
    likely_scanned = chars_per_page < MIN_TEXT_PER_PAGE

    return ExtractionResult(
        text=full_text,
        pages=n_pages,
        chars_per_page=chars_per_page,
        method="native",
        likely_scanned=likely_scanned,
    )


def extract_text(
    pdf_path: str | Path,
    use_ocr_fallback: bool = False,
) -> ExtractionResult:
    result = extract_native(pdf_path)
    if not result.likely_scanned:
        return result
    if not use_ocr_fallback:
        return result
    try:
        from pipeline.ocr import ocr_pdf
        ocr_text = ocr_pdf(pdf_path)
        return ExtractionResult(
            text=ocr_text,
            pages=result.pages,
            chars_per_page=(len(ocr_text) / result.pages) if result.pages else 0,
            method="ocr",
            likely_scanned=True,
        )
    except ImportError:
        return result
