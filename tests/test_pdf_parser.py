# tests/test_pdf_parser.py
import pytest
from pathlib import Path
from parser.pdf_parser import parse_pdf

FIXTURES = Path("tests/fixtures")

def test_텍스트_pdf_파싱():
    items = parse_pdf(FIXTURES / "sample_text.pdf")
    assert len(items) >= 2
    texts = [i.display_text for i in items]
    assert any("테헤란로" in t for t in texts)
    assert any("효원로" in t for t in texts)

def test_source_location_형식():
    items = parse_pdf(FIXTURES / "sample_text.pdf")
    assert all("PDF" in i.source_location for i in items)
    assert all("페이지" in i.source_location for i in items)
