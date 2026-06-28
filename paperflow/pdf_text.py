from __future__ import annotations

from pathlib import Path


def extract_pdf_snippet(path: str | Path, max_chars: int = 3000) -> str:
    """Extract a conservative first-page text snippet from a local PDF path."""

    pdf_path = Path(path).expanduser()
    if not pdf_path.exists() or not pdf_path.is_file():
        return ""

    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(str(pdf_path))
        if not reader.pages:
            return ""
        text = reader.pages[0].extract_text() or ""
    except Exception:
        return ""

    return " ".join(text.split())[:max_chars]
