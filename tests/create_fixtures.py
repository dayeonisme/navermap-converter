# tests/create_fixtures.py — run once to generate test PDF
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

os.makedirs("tests/fixtures", exist_ok=True)

# Register a Korean TTF font so pdfplumber can extract the text correctly
_FONT_PATH = r"C:/Windows/Fonts/malgun.ttf"
pdfmetrics.registerFont(TTFont("MalgunGothic", _FONT_PATH))

def make_text_pdf():
    c = canvas.Canvas("tests/fixtures/sample_text.pdf")
    c.setFont("MalgunGothic", 12)
    c.drawString(100, 750, "서울특별시 강남구 테헤란로 152")
    c.drawString(100, 730, "경기도 수원시 팔달구 효원로 1")
    c.save()

make_text_pdf()
print("Fixtures created.")
