from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path

import fitz  # pymupdf


def extract_text(file_path: Path, file_type: str) -> str:
    """Extract plain text from a PDF or XML file.

    Args:
        file_path: Path to the file.
        file_type: 'pdf' or 'xml'.

    Returns:
        Plain text string with pages/sections joined by double newlines.

    Raises:
        ValueError: If text extraction yields an empty string.
    """
    if file_type == "pdf":
        text = _extract_pdf(file_path)
    else:
        text = _extract_xml(file_path)

    if not text.strip():
        raise ValueError(f"Text extraction yielded empty string for {file_path}")
    return text


def _extract_pdf(file_path: Path) -> str:
    doc = fitz.open(str(file_path))
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return "\n\n".join(pages)


def _extract_xml(file_path: Path) -> str:
    raw = file_path.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(raw)
        texts = [t.strip() for t in root.itertext() if t.strip()]
        return "\n\n".join(texts)
    except ET.ParseError:
        # Malformed XML: strip tags naively and return raw content
        import re
        stripped = re.sub(r"<[^>]+>", " ", raw)
        return " ".join(stripped.split())
