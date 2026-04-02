# naver/map_saver.py
import asyncio
from typing import Dict
from models import AddressItem
from naver.browser import NaverBrowser
from naver import selectors as S


async def _screenshot(page, step: str):
    """실패 시 디버그 스크린샷 저장."""
    import sys
    from pathlib import Path
    try:
        path = Path(__file__).parent.parent / "sessions" / f"debug_{step}.png"
        path.parent.mkdir(exist_ok=True)
        await page.screenshot(path=str(path), full_page=False)
        print(f"[debug] 스크린샷 저장: {path}", file=sys.stderr)
    except Exception as se:
        print(f"[debug] 스크린샷 실패: {se}", file=sys.stderr)


async def _create_list(page, list_name: str) -> None:
    """Create a new private list on Naver Maps. Raises RuntimeError on failure."""
    import sys
    step = "init"
    try:
        step = "goto"
        await page.goto(S.MAP_URL, wait_until="load")
        await page.wait_for_timeout(2000)  # JS 초기화 대기
        print(f"[map_saver] 페이지 로드 완료: {page.url}", file=sys.stderr)

        step = "my_place_menu"
        await page.click(S.MY_PLACE_MENU, timeout=10000)
        await page.wait_for_timeout(1000)

        step = "create_list_button"
        await page.click(S.CREATE_LIST_BUTTON, timeout=10000)
        await page.wait_for_timeout(500)

        step = "list_name_input"
        await page.fill(S.LIST_NAME_INPUT, list_name)
        await page.wait_for_timeout(300)

        step = "privacy_private"
        await page.click(S.LIST_PRIVACY_PRIVATE, timeout=5000)
        await page.wait_for_timeout(300)

        step = "confirm"
        await page.click(S.LIST_CONFIRM_BUTTON, timeout=5000)
        await page.wait_for_timeout(1000)

    except Exception as e:
        await _screenshot(page, f"create_list_fail_{step}")
        raise RuntimeError(f"리스트 생성 실패 [{step}]: {e}")


async def _extract_candidates(results) -> list:
    """Extract name and address text from each search result element."""
    candidates = []
    for el in results:
        name_el = await el.query_selector(S.SEARCH_RESULT_NAME)
        addr_el = await el.query_selector(S.SEARCH_RESULT_ADDR)
        name = (await name_el.inner_text()).strip() if name_el else ""
        addr = (await addr_el.inner_text()).strip() if addr_el else ""
        candidates.append({"name": name, "address": addr})
    return candidates


async def _save_one(page, address: str, list_name: str) -> dict:
    """Search for address and save to named list.
    Returns {"status": "success"|"failed"|"ambiguous", "candidates": [...]}
    """
    try:
        await page.goto(S.MAP_URL, wait_until="load")
        await page.wait_for_timeout(2000)

        # Search
        await page.fill(S.SEARCH_INPUT, address)
        await page.click(S.SEARCH_SUBMIT)
        await page.wait_for_timeout(2000)

        # Count results
        results = await page.query_selector_all(S.SEARCH_RESULT_ITEM)
        if len(results) == 0:
            return {"status": "failed", "candidates": []}
        if len(results) > 1:
            candidates = await _extract_candidates(results)
            return {"status": "ambiguous", "candidates": candidates}

        # Click save button
        await page.click(S.PLACE_SAVE_BUTTON, timeout=5000)
        await page.wait_for_timeout(500)

        # Select target list by name
        list_items = await page.query_selector_all(S.LIST_ITEM_SELECTOR)
        for item in list_items:
            text = await item.inner_text()
            if list_name in text:
                await item.click()
                await page.wait_for_timeout(500)
                return {"status": "success", "candidates": []}

        return {"status": "failed", "candidates": []}
    except Exception as e:
        import sys
        print(f"[map_saver] Error saving '{address}': {type(e).__name__}: {e}", file=sys.stderr)
        return {"status": "failed", "candidates": []}


async def save_one_by_index(page, address: str, list_name: str, index: int) -> str:
    """Re-search address and save the result at the given index. Returns 'success'|'failed'."""
    try:
        await page.goto(S.MAP_URL)
        await page.wait_for_load_state("networkidle", timeout=15000)

        await page.fill(S.SEARCH_INPUT, address)
        await page.click(S.SEARCH_SUBMIT)
        await page.wait_for_timeout(2000)

        results = await page.query_selector_all(S.SEARCH_RESULT_ITEM)
        if index >= len(results):
            return "failed"

        await results[index].click()
        await page.wait_for_timeout(1000)

        await page.click(S.PLACE_SAVE_BUTTON, timeout=5000)
        await page.wait_for_timeout(500)

        list_items = await page.query_selector_all(S.LIST_ITEM_SELECTOR)
        for item in list_items:
            text = await item.inner_text()
            if list_name in text:
                await item.click()
                await page.wait_for_timeout(500)
                return "success"

        return "failed"
    except Exception as e:
        import sys
        print(f"[map_saver] Error resolving '{address}' index={index}: {type(e).__name__}: {e}", file=sys.stderr)
        return "failed"


async def save_addresses_to_naver(
    browser: NaverBrowser,
    list_name: str,
    addresses: list,
    item_registry: Dict[str, AddressItem],
    queue: asyncio.Queue,
    is_cancelled=None,
) -> None:
    """Create list then save addresses sequentially. Streams progress via queue.
    is_cancelled: optional callable returning bool — checked between each item.
    """
    page = await browser.get_page()

    # Create list first — raises RuntimeError if it fails (stops entire batch)
    await _create_list(page, list_name)

    summary = {"success": 0, "failed": 0, "ambiguous": 0}

    for addr_dict in addresses:
        if is_cancelled and is_cancelled():
            await queue.put({"type": "cancelled"})
            return

        id_ = addr_dict["id"]
        display_text = addr_dict["display_text"]

        result = await _save_one(page, display_text, list_name)
        status = result["status"]

        # Update registry
        if id_ in item_registry:
            item_registry[id_].status = status
            item_registry[id_].candidates = result["candidates"]

        summary[status] = summary.get(status, 0) + 1
        await queue.put({"id": id_, "status": status, "candidates": result["candidates"]})

    await queue.put({"type": "done", "summary": summary})
