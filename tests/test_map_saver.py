# tests/test_map_saver.py
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_save_one_단일결과_success():
    from naver.map_saver import _save_one

    page = AsyncMock()
    frame = AsyncMock()

    result_el = AsyncMock()
    frame.query_selector_all = AsyncMock(return_value=[result_el])

    with patch("naver.map_saver._get_search_frame", return_value=frame), \
         patch("naver.map_saver._save_in_entry_frame", new=AsyncMock(return_value=True)):
        result = await _save_one(page, "서울역", "AUTO_20260405")

    assert result["status"] == "success"
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_save_one_결과없음_failed():
    from naver.map_saver import _save_one

    page = AsyncMock()
    frame = AsyncMock()
    frame.query_selector_all = AsyncMock(return_value=[])

    with patch("naver.map_saver._get_search_frame", return_value=frame):
        result = await _save_one(page, "존재하지않는주소xyz", "AUTO_20260405")

    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_save_one_복수결과_ambiguous():
    from naver.map_saver import _save_one

    page = AsyncMock()
    frame = AsyncMock()

    # Two results → ambiguous
    el1, el2 = AsyncMock(), AsyncMock()
    for el in (el1, el2):
        name_el = AsyncMock()
        name_el.inner_text = AsyncMock(return_value="서울역")
        addr_el = AsyncMock()
        addr_el.inner_text = AsyncMock(return_value="서울 중구")
        async def _qs(sel, n=name_el, a=addr_el):
            from naver import selectors as S
            return n if sel == S.SEARCH_RESULT_NAME else a
        el.query_selector = _qs
    frame.query_selector_all = AsyncMock(return_value=[el1, el2])

    with patch("naver.map_saver._get_search_frame", return_value=frame):
        result = await _save_one(page, "서울역", "AUTO_20260405")

    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


@pytest.mark.asyncio
async def test_save_one_iframe없음_failed():
    from naver.map_saver import _save_one

    page = AsyncMock()

    with patch("naver.map_saver._get_search_frame", return_value=None):
        result = await _save_one(page, "서울역", "AUTO_20260405")

    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_save_one_entry_frame_저장실패_failed():
    from naver.map_saver import _save_one

    page = AsyncMock()
    frame = AsyncMock()
    result_el = AsyncMock()
    frame.query_selector_all = AsyncMock(return_value=[result_el])

    with patch("naver.map_saver._get_search_frame", return_value=frame), \
         patch("naver.map_saver._save_in_entry_frame", new=AsyncMock(return_value=False)):
        result = await _save_one(page, "서울역", "AUTO_20260405")

    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_save_in_entry_frame_리스트없음_failed():
    from naver.map_saver import _save_in_entry_frame

    page = AsyncMock()
    entry_frame = AsyncMock()
    # No matching list items
    other_item = AsyncMock()
    other_item.inner_text = AsyncMock(return_value="다른리스트")
    entry_frame.query_selector_all = AsyncMock(return_value=[other_item])

    with patch("naver.map_saver._get_entry_frame", side_effect=[None, None, None, None, None,
                                                                  None, None, None, None, entry_frame]):
        result = await _save_in_entry_frame(page, "AUTO_20260405")

    assert result is False


@pytest.mark.asyncio
async def test_save_in_entry_frame_성공():
    from naver.map_saver import _save_in_entry_frame

    page = AsyncMock()
    entry_frame = AsyncMock()
    list_item = AsyncMock()
    list_item.inner_text = AsyncMock(return_value="AUTO_20260405")
    entry_frame.query_selector_all = AsyncMock(return_value=[list_item])

    with patch("naver.map_saver._get_entry_frame", return_value=entry_frame):
        result = await _save_in_entry_frame(page, "AUTO_20260405")

    assert result is True


@pytest.mark.asyncio
async def test_save_addresses_to_naver_순차저장():
    from naver.map_saver import save_addresses_to_naver
    from models import AddressItem

    item1 = AddressItem(raw_text="a", display_text="서울역", source_location="test")
    item2 = AddressItem(raw_text="b", display_text="강남역", source_location="test")
    registry = {item1.id: item1, item2.id: item2}
    queue = asyncio.Queue()

    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_browser.get_page = AsyncMock(return_value=mock_page)

    addresses = [{"id": item1.id, "display_text": item1.display_text},
                 {"id": item2.id, "display_text": item2.display_text}]

    with patch("naver.map_saver._create_list", new=AsyncMock()), \
         patch("naver.map_saver._save_one", new=AsyncMock(return_value={"status": "success", "candidates": []})):
        await save_addresses_to_naver(mock_browser, "AUTO_20260405", addresses, registry, queue)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    assert registry[item1.id].status == "success"
    assert registry[item2.id].status == "success"
    done_event = next(e for e in events if e.get("type") == "done")
    assert done_event["summary"]["success"] == 2


@pytest.mark.asyncio
async def test_save_addresses_to_naver_취소():
    from naver.map_saver import save_addresses_to_naver
    from models import AddressItem

    item = AddressItem(raw_text="a", display_text="서울역", source_location="test")
    registry = {item.id: item}
    queue = asyncio.Queue()

    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_browser.get_page = AsyncMock(return_value=mock_page)

    with patch("naver.map_saver._create_list", new=AsyncMock()), \
         patch("naver.map_saver._save_one", new=AsyncMock(return_value={"status": "success", "candidates": []})):
        await save_addresses_to_naver(
            mock_browser, "AUTO_20260405",
            [{"id": item.id, "display_text": item.display_text}],
            registry, queue,
            is_cancelled=lambda: True,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    assert any(e.get("type") == "cancelled" for e in events)
    # Item should not have been saved
    assert item.status == "pending"
