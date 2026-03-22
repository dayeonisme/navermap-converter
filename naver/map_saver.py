# naver/map_saver.py
import asyncio
from typing import Dict
from models import AddressItem
from naver.browser import NaverBrowser
from naver import selectors as S


async def _create_list(page, list_name: str) -> None:
    """Create a new private list on Naver Maps. Raises RuntimeError on failure."""
    try:
        await page.goto(S.MAP_URL)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Click My Places menu
        await page.click(S.MY_PLACE_MENU, timeout=10000)
        await page.wait_for_timeout(1000)

        # Click Create New List
        await page.click(S.CREATE_LIST_BUTTON, timeout=10000)
        await page.wait_for_timeout(500)

        # Enter list name
        await page.fill(S.LIST_NAME_INPUT, list_name)
        await page.wait_for_timeout(300)

        # Select private visibility
        await page.click(S.LIST_PRIVACY_PRIVATE, timeout=5000)
        await page.wait_for_timeout(300)

        # Confirm
        await page.click(S.LIST_CONFIRM_BUTTON, timeout=5000)
        await page.wait_for_timeout(1000)

    except Exception as e:
        raise RuntimeError(f"리스트 생성 실패: {e}")


async def _save_one(page, address: str, list_name: str) -> str:
    """Search for address and save to named list. Returns 'success'|'failed'|'ambiguous'."""
    try:
        await page.goto(S.MAP_URL)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Search
        await page.fill(S.SEARCH_INPUT, address)
        await page.click(S.SEARCH_SUBMIT)
        await page.wait_for_timeout(2000)

        # Count results
        results = await page.query_selector_all(S.SEARCH_RESULT_ITEM)
        if len(results) == 0:
            return "failed"
        if len(results) > 1:
            return "ambiguous"

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
                return "success"

        return "failed"
    except Exception as e:
        # Log error type so users know if it's a selector issue vs. address not found
        import sys
        print(f"[map_saver] Error saving '{address}': {type(e).__name__}: {e}", file=sys.stderr)
        return "failed"


async def save_addresses_to_naver(
    browser: NaverBrowser,
    list_name: str,
    addresses: list[dict],
    item_registry: Dict[str, AddressItem],
    queue: asyncio.Queue,
) -> None:
    """Create list then save addresses sequentially. Streams progress via queue."""
    page = await browser.get_page()

    # Create list first — raises RuntimeError if it fails (stops entire batch)
    await _create_list(page, list_name)

    summary = {"success": 0, "failed": 0, "ambiguous": 0}

    for addr_dict in addresses:
        id_ = addr_dict["id"]
        display_text = addr_dict["display_text"]

        status = await _save_one(page, display_text, list_name)

        # Update registry
        if id_ in item_registry:
            item_registry[id_].status = status

        summary[status] = summary.get(status, 0) + 1
        await queue.put({"id": id_, "status": status})

    await queue.put({"type": "done", "summary": summary})
