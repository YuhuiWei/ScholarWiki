from __future__ import annotations
import io
from pathlib import Path
import pytest
import fitz  # pymupdf


def _make_pdf(text: str, tmp_path: Path) -> Path:
    """Create a minimal single-page PDF with the given text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _make_xml(tmp_path: Path) -> Path:
    xml_content = """<?xml version="1.0"?>
<article>
  <title>Test Article</title>
  <abstract>This is the abstract text.</abstract>
  <body>This is the body content.</body>
</article>"""
    p = tmp_path / "test.xml"
    p.write_text(xml_content)
    return p


def test_extract_text_pdf(tmp_path):
    from scholarwiki.extraction.text_extractor import extract_text
    pdf_path = _make_pdf("Hello academic world", tmp_path)
    result = extract_text(pdf_path, "pdf")
    assert "Hello academic world" in result


def test_extract_text_xml(tmp_path):
    from scholarwiki.extraction.text_extractor import extract_text
    xml_path = _make_xml(tmp_path)
    result = extract_text(xml_path, "xml")
    assert "Test Article" in result
    assert "abstract text" in result
    assert "body content" in result


def test_extract_text_xml_no_tags(tmp_path):
    from scholarwiki.extraction.text_extractor import extract_text
    xml_path = _make_xml(tmp_path)
    result = extract_text(xml_path, "xml")
    assert "<title>" not in result
    assert "<abstract>" not in result


def test_extract_text_empty_pdf_raises(tmp_path):
    from scholarwiki.extraction.text_extractor import extract_text
    # PDF with no text layers
    doc = fitz.open()
    doc.new_page()  # blank page, no text
    pdf_path = tmp_path / "blank.pdf"
    doc.save(str(pdf_path))
    doc.close()
    with pytest.raises(ValueError, match="empty"):
        extract_text(pdf_path, "pdf")


def test_extract_text_malformed_xml_falls_back(tmp_path):
    from scholarwiki.extraction.text_extractor import extract_text
    bad_xml = tmp_path / "bad.xml"
    bad_xml.write_text("not xml at all <unclosed> content here")
    # Should not raise — falls back to raw text
    result = extract_text(bad_xml, "xml")
    assert "content here" in result
