# tests/test_api.py
import asyncio
import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from main import app

client = TestClient(app)

def test_upload_pdf_반환_주소_목록():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Seoul Gangnam")
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


def test_parse_text_서울_축약형_지번주소_세개_반환():
    text = (
        "서울 종로구 필운동 202\n"
        "서울 종로구 화동 138-21\n"
        "서울 마포구 상암동 33-4"
    )
    response = client.post("/parse-text", json={"text": text})

    assert response.status_code == 200
    assert [item["display_text"] for item in response.json()["addresses"]] == text.splitlines()


def test_index_직접입력_빈결과와_오류_안내_포함():
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "인식된 주소가 없습니다. 시·군·구와 번지를 포함해 입력해 주세요." in html
    assert "if (!res.ok)" in html
    assert "catch (e)" in html


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


@pytest.mark.asyncio
async def test_cancel_job_실행중_task_cancel_호출():
    import main

    task = MagicMock()
    task.done.return_value = False
    main._job_active = True
    main._job_cancelled = False
    main._job_task = task
    try:
        result = await main.cancel_job()

        assert result == {"status": "cancelling"}
        assert main._job_cancelled is True
        task.cancel.assert_called_once_with()
    finally:
        main._job_active = False
        main._job_cancelled = False
        main._job_task = None


@pytest.mark.asyncio
async def test_save_addresses_생성한_task_참조_보관():
    import main

    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_save(*_args):
        started.set()
        await release.wait()

    main._job_active = False
    main._job_task = None
    created_task = None
    original_create_task = asyncio.create_task

    def track_task(coro):
        nonlocal created_task
        created_task = original_create_task(coro)
        return created_task

    try:
        with patch("main._run_save", side_effect=blocked_save), \
             patch("main.asyncio.create_task", side_effect=track_task):
            result = await main.save_addresses(main.SaveRequest(addresses=[]))
            await started.wait()
            task = main._job_task

            assert result == {"status": "accepted"}
            assert isinstance(task, asyncio.Task)
    finally:
        release.set()
        if created_task is not None:
            await created_task
        main._job_active = False
        main._job_task = None


@pytest.mark.asyncio
async def test_run_save_대기중_cancelled_event와_상태정리():
    import main

    entered = asyncio.Event()

    async def wait_forever():
        entered.set()
        await asyncio.Event().wait()

    browser = MagicMock()
    browser.is_logged_in = AsyncMock(side_effect=wait_forever)
    main._progress_queue = asyncio.Queue()
    main._job_active = True

    with patch("main.get_browser", return_value=browser):
        task = asyncio.create_task(main._run_save([], None))
        main._job_task = task
        await entered.wait()
        task.cancel()
        await task

    assert main._job_active is False
    assert main._job_task is None
    assert await main._progress_queue.get() == {"type": "cancelled"}


@pytest.mark.asyncio
async def test_stream_progress_cancelled에서_종료():
    import main

    main._progress_queue = asyncio.Queue()
    await main._progress_queue.put({"type": "cancelled"})
    stream = main._stream_progress()

    assert "cancelled" in await stream.__anext__()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(stream.__anext__(), timeout=0.1)
