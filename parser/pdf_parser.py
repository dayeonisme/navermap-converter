# parser/pdf_parser.py
from pathlib import Path
from typing import List
import pdfplumber
from models import AddressItem
from parser.text_parser import extract_addresses

def _ocr_page(page) -> str:
    """pdfplumber 페이지를 이미지로 변환 후 OCR."""
    try:
        import pytesseract
    except ImportError:
        return ""

    # pdfplumber page.to_image()로 PIL 이미지 직접 획득 (pdf2image 불필요)
    pil_image = page.to_image(resolution=300).original
    return pytesseract.image_to_string(pil_image, lang="kor+eng")

def parse_pdf(path: Path) -> List[AddressItem]:
    """PDF 파일에서 주소 추출. 텍스트 추출 실패 시 OCR 폴백."""
    items: List[AddressItem] = []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            source = f"PDF {page_num}페이지"
            text = page.extract_text() or ""

            if not text.strip():
                text = _ocr_page(page)

            items.extend(extract_addresses(text, source_prefix=source))

    return items
