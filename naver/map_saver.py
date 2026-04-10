# naver/map_saver.py
import asyncio
import sys
import urllib.parse
from pathlib import Path
from typing import Dict
from models import AddressItem
from naver.browser import NaverBrowser
from naver import selectors as S


async def _screenshot(page, step: str):
    """실패 시 디버그 스크린샷 저장."""
    try:
        path = Path(__file__).parent.parent / "sessions" / f"debug_{step}.png"
        path.parent.mkdir(exist_ok=True)
        await page.screenshot(path=str(path), full_page=False)
        print(f"[debug] 스크린샷 저장: {path}", file=sys.stderr)
    except Exception as se:
        print(f"[debug] 스크린샷 실패: {se}", file=sys.stderr)


def _get_my_place_frame(page):
    """myPlaceBookmarkFolderListIframe 프레임 반환. 없으면 None."""
    return next((f for f in page.frames if f.name == S.MY_PLACE_IFRAME), None)


async def _list_exists(frame, list_name: str) -> bool:
    """내 장소 iframe이 열린 상태에서 list_name 리스트가 이미 존재하는지 확인."""
    try:
        items = await frame.query_selector_all(S.LIST_ITEM_SELECTOR)
        for item in items:
            text = await item.inner_text()
            if list_name in text:
                return True
    except Exception:
        pass
    return False


async def _create_list(page, list_name: str) -> None:
    """Create a new private list on Naver Maps (skip if already exists).
    Raises RuntimeError on failure."""
    step = "init"
    try:
        step = "goto"
        await page.goto(S.MAP_URL, wait_until="load")
        await page.wait_for_timeout(2000)  # JS 초기화 대기
        print(f"[map_saver] 페이지 로드 완료: {page.url}", file=sys.stderr)

        step = "my_place_menu"
        await page.click(S.MY_PLACE_MENU, timeout=10000)

        # 클릭 후 로그인 페이지로 리다이렉트됐으면 세션 만료
        if "nidlogin" in page.url:
            raise RuntimeError("SESSION_EXPIRED")

        step = "my_place_iframe"
        # headless 환경에서 iframe 로드가 느릴 수 있어 최대 10초 폴링
        frame = None
        for _ in range(20):
            await page.wait_for_timeout(500)
            if "nidlogin" in page.url:
                raise RuntimeError("SESSION_EXPIRED")
            frame = _get_my_place_frame(page)
            if frame is not None:
                break
        if frame is None:
            await _screenshot(page, "my_place_iframe_not_found")
            raise RuntimeError(f"내 장소 iframe({S.MY_PLACE_IFRAME})을 찾을 수 없음")

        # 같은 날 이미 리스트가 존재하면 생성 건너뜀
        if await _list_exists(frame, list_name):
            print(f"[map_saver] 리스트 '{list_name}' 이미 존재 — 재사용", file=sys.stderr)
            return

        step = "create_list_button"
        await frame.click(S.CREATE_LIST_BUTTON, timeout=10000)
        await page.wait_for_timeout(500)

        step = "list_name_input"
        await frame.fill(S.LIST_NAME_INPUT, list_name)
        await page.wait_for_timeout(300)

        step = "privacy_private"
        # 첫 번째 label = 비공개
        privacy_labels = await frame.query_selector_all(S.LIST_PRIVACY_PRIVATE)
        if not privacy_labels:
            raise RuntimeError("비공개 옵션 버튼을 찾을 수 없음")
        await privacy_labels[0].click()
        await page.wait_for_timeout(300)

        step = "confirm"
        await frame.click(S.LIST_CONFIRM_BUTTON, timeout=5000)
        await page.wait_for_timeout(1000)

    except RuntimeError:
        raise
    except Exception as e:
        await _screenshot(page, f"create_list_fail_{step}")
        raise RuntimeError(f"리스트 생성 실패 [{step}]: {e}")


def _get_search_frame(page):
    """searchIframe(pcmap.place.naver.com) 프레임 반환. 없으면 None."""
    return next((f for f in page.frames if "pcmap.place.naver.com" in f.url), None)


def _get_entry_frame(page):
    """entryIframe 프레임 반환. 없으면 None."""
    return next((f for f in page.frames if f.name == S.ENTRY_IFRAME), None)


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


async def _save_in_entry_frame(page, list_name: str) -> bool:
    """entryIframe 내에서 저장 버튼 클릭 → 리스트 선택 → 저장 확인.
    Returns True on success, False on failure."""
    # entryIframe 등장 대기 (최대 5초)
    for _ in range(10):
        entry_frame = _get_entry_frame(page)
        if entry_frame is not None:
            break
        await page.wait_for_timeout(500)
    else:
        print("[map_saver] entryIframe not found after waiting", file=sys.stderr)
        return False

    try:
        await entry_frame.click(S.PLACE_SAVE_BUTTON, timeout=5000)
        # 저장 다이얼로그 로드 대기 (최대 3초 폴링)
        list_items = []
        for _ in range(6):
            await page.wait_for_timeout(500)
            list_items = await entry_frame.query_selector_all(S.PLACE_SAVE_LIST_ITEM)
            if list_items:
                break

        all_texts = []
        for item in list_items:
            text = await item.inner_text()
            all_texts.append(text.strip())
            if list_name in text:
                await item.click()
                await page.wait_for_timeout(500)
                await entry_frame.click(S.PLACE_SAVE_CONFIRM, timeout=3000)
                await page.wait_for_timeout(500)
                return True

        print(f"[map_saver] entryIframe 리스트 목록: {all_texts}", file=sys.stderr)
        print(f"[map_saver] 찾는 리스트명: {list_name!r} — 일치 없음", file=sys.stderr)
        # 리스트 항목이 없으면 다른 selector로 재시도 — 모든 button 클래스 로깅
        all_btns = await entry_frame.eval_on_selector_all(
            "button, a[role='button']",
            "els => els.map(e => ({ cls: e.className, text: e.innerText?.slice(0,40) }))"
        )
        print(f"[map_saver] entryIframe 전체 버튼: {all_btns[:20]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[map_saver] entryIframe save error: {type(e).__name__}: {e}", file=sys.stderr)
        return False


async def _try_address_place(page, list_name: str):
    """이 주소의 장소 섹션의 첫 번째 장소를 entryIframe으로 저장.
    Returns: True (저장 성공), False (장소 찾았지만 저장 실패), None (장소 섹션 없음).
    """
    await page.wait_for_timeout(2000)
    first_place = await page.query_selector(".end_inner.place button.link_space")
    if first_place is None:
        return None  # 장소 섹션 없음 → _save_address_page 로 fallback 가능
    await first_place.click()
    await page.wait_for_timeout(1000)
    ok = await _save_in_entry_frame(page, list_name)
    return ok  # True or False (이미 페이지 이동됨 — fallback 불가)


async def _save_address_page(page, list_name: str) -> bool:
    """/address/ 페이지에서 주소 카드의 저장 버튼 클릭 → 메인 DOM 리스트 선택.
    Returns True on success, False on failure."""
    await page.wait_for_timeout(2000)
    save_btn = await page.query_selector(S.ADDRESS_SAVE_BUTTON)
    if save_btn is None:
        print("[map_saver] /address/ btn_favorite 없음", file=sys.stderr)
        return False
    await save_btn.click()
    # 리스트 선택 항목 로드 대기 (최대 5초)
    for _ in range(10):
        items = await page.query_selector_all(S.PLACE_SAVE_LIST_ITEM)
        if items:
            break
        await page.wait_for_timeout(500)
    items = await page.query_selector_all(S.PLACE_SAVE_LIST_ITEM)
    all_texts = []
    for item in items:
        text = await item.inner_text()
        all_texts.append(text.strip())
        if list_name in text:
            await item.click()
            await page.wait_for_timeout(500)
            await page.click(S.PLACE_SAVE_CONFIRM, timeout=3000)
            await page.wait_for_timeout(500)
            return True
    print(f"[map_saver] /address/ 리스트 목록: {all_texts}", file=sys.stderr)
    print(f"[map_saver] 찾는 리스트명: {list_name!r} — 일치 없음", file=sys.stderr)
    return False


async def _save_one(page, address: str, list_name: str) -> dict:
    """Search for address and save to named list.
    Returns {"status": "success"|"failed"|"ambiguous", "candidates": [...]}
    """
    try:
        search_url = S.SEARCH_URL.format(query=urllib.parse.quote(address))
        await page.goto(search_url, wait_until="load")
        await page.wait_for_timeout(1000)

        # /address/ 리다이렉트 → 단일 주소 결과 직접 표시 (메인 프레임에 렌더링, iframe 없음)
        if "/address/" in page.url:
            # 이 주소의 장소 섹션에 장소가 있으면 첫 번째 장소를 entryIframe으로 저장
            place_result = await _try_address_place(page, list_name)
            if place_result is None:
                # 장소 섹션 없음 → 주소 자체를 리스트에 저장
                success = await _save_address_page(page, list_name)
            else:
                # 장소 클릭 후 결과 (페이지 이미 이동됨 — address 저장 불가)
                success = place_result
            return {"status": "success" if success else "failed", "candidates": []}

        # searchIframe 콘텐츠 로드 대기 (최대 10초)
        frame = None
        for _ in range(20):
            await page.wait_for_timeout(500)
            frame = _get_search_frame(page)
            if frame is not None:
                results_check = await frame.query_selector_all(S.SEARCH_RESULT_ITEM)
                if results_check or await frame.query_selector("body"):
                    break
            frame = None

        if frame is None:
            await _screenshot(page, "search_frame_not_found")
            print(f"[map_saver] searchIframe not found for '{address}'", file=sys.stderr)
            return {"status": "failed", "candidates": []}

        results = await frame.query_selector_all(S.SEARCH_RESULT_ITEM)
        if len(results) == 0:
            return {"status": "failed", "candidates": []}
        if len(results) > 1:
            candidates = await _extract_candidates(results)
            return {"status": "ambiguous", "candidates": candidates}

        # 단일 결과 클릭 → entryIframe 로드 대기
        await results[0].click()
        await page.wait_for_timeout(1000)

        success = await _save_in_entry_frame(page, list_name)
        return {"status": "success" if success else "failed", "candidates": []}
    except Exception as e:
        print(f"[map_saver] Error saving '{address}': {type(e).__name__}: {e}", file=sys.stderr)
        return {"status": "failed", "candidates": []}


async def save_one_by_index(page, address: str, list_name: str, index: int) -> str:
    """Re-search address and save the result at the given index. Returns 'success'|'failed'."""
    try:
        search_url = S.SEARCH_URL.format(query=urllib.parse.quote(address))
        await page.goto(search_url, wait_until="load")
        await page.wait_for_timeout(1000)

        if "/address/" in page.url:
            success = await _save_address_page(page, list_name)
            return "success" if success else "failed"

        frame = None
        for _ in range(20):
            await page.wait_for_timeout(500)
            frame = _get_search_frame(page)
            if frame is not None:
                results_check = await frame.query_selector_all(S.SEARCH_RESULT_ITEM)
                if results_check or await frame.query_selector("body"):
                    break

        if frame is None:
            print(f"[map_saver] searchIframe not found for '{address}'", file=sys.stderr)
            return "failed"

        results = await frame.query_selector_all(S.SEARCH_RESULT_ITEM)
        if index >= len(results):
            return "failed"

        await results[index].click()
        await page.wait_for_timeout(1000)

        success = await _save_in_entry_frame(page, list_name)
        return "success" if success else "failed"
    except Exception as e:
        print(f"[map_saver] Error resolving '{address}' index={index}: {type(e).__name__}: {e}", file=sys.stderr)
        return "failed"


async def _navigate_to_list(list_name: str) -> None:
    """저장 완료 후 새 headed 브라우저를 열어 해당 리스트를 표시.
    headless 저장 브라우저와 분리된 독립 인스턴스로 실행."""
    from playwright.async_api import async_playwright as _async_playwright
    from naver.browser import COOKIES_PATH, _sanitize_cookies
    import json as _json
    try:
        pw = await _async_playwright().start()
        br = await pw.chromium.launch(headless=False, channel="chrome")
        ctx = await br.new_context()
        if COOKIES_PATH.exists():
            for c in _sanitize_cookies(_json.loads(COOKIES_PATH.read_text())):
                try:
                    await ctx.add_cookies([c])
                except Exception:
                    pass
        page = await ctx.new_page()
        await page.goto(S.MAP_URL, wait_until="load")
        await page.wait_for_timeout(2000)
        await page.click(S.MY_PLACE_MENU, timeout=10000)
        await page.wait_for_timeout(2000)
        frame = _get_my_place_frame(page)
        if frame is None:
            return
        items = await frame.query_selector_all(S.LIST_ITEM_SELECTOR)
        for item in items:
            text = await item.inner_text()
            if list_name in text:
                await item.click()
                return
        # 창을 닫지 않고 유지 — 사용자가 확인 후 직접 닫음
    except Exception as e:
        print(f"[map_saver] 리스트 이동 실패: {e}", file=sys.stderr)


async def save_addresses_to_naver(
    browser: NaverBrowser,
    list_name: str,
    addresses: list,
    item_registry: Dict[str, AddressItem],
    queue: asyncio.Queue,
    is_cancelled=None,
    create_list: bool = True,
) -> None:
    """Create list then save addresses sequentially. Streams progress via queue.
    is_cancelled: optional callable returning bool — checked between each item.
    create_list: if False, skip list creation (user-provided existing list name).
    """
    page = await browser.get_page()

    print(f"[map_saver] save_addresses_to_naver: list_name={list_name!r} create_list={create_list}", file=sys.stderr)

    # Create list first — raises RuntimeError if it fails (stops entire batch)
    if create_list:
        await _create_list(page, list_name)
    else:
        print(f"[map_saver] 리스트 생성 건너뜀 — 기존 리스트 사용: {list_name!r}", file=sys.stderr)

    summary = {"success": 0, "failed": 0, "ambiguous": 0}

    for addr_dict in addresses:
        if is_cancelled and is_cancelled():
            await queue.put({"type": "cancelled"})
            return

        id_ = addr_dict["id"]
        display_text = addr_dict["display_text"]

        # 새 탭에서 실행 — _create_list의 MY_PLACE 패널 SPA 상태와 격리
        tab = await browser.new_page()
        try:
            result = await _save_one(tab, display_text, list_name)
        finally:
            await tab.close()
        status = result["status"]

        # Update registry
        if id_ in item_registry:
            item_registry[id_].status = status
            item_registry[id_].candidates = result["candidates"]

        summary[status] = summary.get(status, 0) + 1
        await queue.put({"type": "item_saved", "id": id_, "status": status, "candidates": result["candidates"]})

    await queue.put({"type": "done", "summary": summary})
