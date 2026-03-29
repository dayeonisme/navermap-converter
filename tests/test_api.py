# tests/test_api.py
import io
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_upload_pdf_반환_주소_목록():
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    font_path = "C:/Windows/Fonts/malgun.ttf"
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("Malgun", font_path))
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if os.path.exists(font_path):
        c.setFont("Malgun", 12)
    c.drawString(100, 750, "서울특별시 강남구 테헤란로 152")
    c.save()
    buf.seek(0)
    response = client.post("/upload", files={"file": ("test.pdf", buf, "application/pdf")})
    assert response.status_code == 200
    data = response.json()
    assert "addresses" in data
    assert isinstance(data["addresses"], list)

def test_upload_지원안하는_형식_422():
    response = client.post("/upload", files={"file": ("test.txt", b"hello", "text/plain")})
    assert response.status_code == 422

def test_parse_text_주소_반환():
    response = client.post("/parse-text", json={"text": "서울특별시 강남구 테헤란로 152"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["addresses"]) >= 1
    assert data["addresses"][0]["status"] == "pending"

def test_parse_text_각_항목_필드():
    response = client.post("/parse-text", json={"text": "서울특별시 강남구 테헤란로 152"})
    item = response.json()["addresses"][0]
    assert "id" in item
    assert "raw_text" in item
    assert "display_text" in item
    assert "source_location" in item
    assert "status" in item

def test_login_status_반환():
    from unittest.mock import AsyncMock, patch
    mock_browser = AsyncMock()
    mock_browser.is_logged_in = AsyncMock(return_value=False)
    with patch('main.get_browser', return_value=mock_browser):
        response = client.get("/login-status")
    assert response.status_code == 200
    assert "logged_in" in response.json()

def test_retry_422_잘못된_id():
    response = client.post("/retry", json={"ids": ["nonexistent-id-12345"]})
    assert response.status_code == 422

def test_resolve_404_항목_없을때():
    response = client.post("/resolve/nonexistent-id", json={"candidate_index": 0})
    assert response.status_code == 404


def test_resolve_422_ambiguous_아닌_항목():
    from models import AddressItem
    import main
    item = AddressItem(raw_text="test", display_text="test addr", source_location="test", status="failed")
    main._item_registry[item.id] = item
    response = client.post(f"/resolve/{item.id}", json={"candidate_index": 0})
    assert response.status_code == 422
    del main._item_registry[item.id]


def test_resolve_409_작업중():
    from models import AddressItem
    import main
    item = AddressItem(raw_text="test", display_text="test addr", source_location="test", status="ambiguous")
    main._item_registry[item.id] = item
    main._job_active = True
    response = client.post(f"/resolve/{item.id}", json={"candidate_index": 0})
    assert response.status_code == 409
    main._job_active = False
    del main._item_registry[item.id]


def test_resolve_성공():
    from models import AddressItem
    from unittest.mock import AsyncMock, patch
    import main
    item = AddressItem(raw_text="test", display_text="서울역", source_location="test", status="ambiguous")
    main._item_registry[item.id] = item

    mock_page = AsyncMock()
    mock_browser = AsyncMock()
    mock_browser.get_page = AsyncMock(return_value=mock_page)

    with patch("main.get_browser", return_value=mock_browser), \
         patch("naver.map_saver.save_one_by_index", new=AsyncMock(return_value="success")):
        response = client.post(f"/resolve/{item.id}", json={"candidate_index": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert main._item_registry[item.id].status == "success"
    del main._item_registry[item.id]


def test_retry_422_ambiguous_id():
    # Set up an ambiguous item in the registry
    from models import AddressItem
    import main
    item = AddressItem(
        raw_text="test",
        display_text="test",
        source_location="test",
        status="ambiguous"
    )
    main._item_registry[item.id] = item
    response = client.post("/retry", json={"ids": [item.id]})
    assert response.status_code == 422
    # Clean up
    del main._item_registry[item.id]
