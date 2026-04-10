# parser/pdf_parser.py
from pathlib import Path
from typing import List
import pdfplumber
from models import AddressItem
from parser.text_parser import extract_addresses

def _ocr_page(page) -> str:
    """pdfplumber 페이지를 이미지로 변환 후 OCR."""
    import sys
    try:
        import pytesseract
    except ImportError:
        print(
            "[pdf_parser] OCR 불가: pytesseract 미설치. `pip install pytesseract` 후 "
            "Tesseract OCR 엔진(https://github.com/tesseract-ocr/tesseract)과 "
            "한국어 데이터(kor.traineddata)를 설치하세요.",
            file=sys.stderr,
        )
        return ""

    try:
        pil_image = page.to_image(resolution=300).original
        return pytesseract.image_to_string(pil_image, lang="kor+eng")
    except pytesseract.TesseractNotFoundError:
        print(
            "[pdf_parser] OCR 불가: Tesseract 실행 파일을 찾을 수 없습니다. "
            "Tesseract OCR 엔진을 설치하고 PATH에 추가하세요. "
            "한국어 지원은 kor.traineddata 파일도 필요합니다.",
            file=sys.stderr,
        )
        return ""

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
