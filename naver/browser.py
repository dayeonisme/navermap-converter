# naver/browser.py
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

COOKIES_PATH = Path(__file__).parent.parent / "sessions" / "naver_cookies.json"
NAVER_MAIN = "https://www.naver.com"
LOGIN_COOKIE = "NID_AUT"
POLL_INTERVAL = 2  # seconds

# Playwright add_cookies에서 허용하는 필드만 남김 (Chrome 전용 필드 제거)
_COOKIE_FIELDS = {"name", "value", "url", "domain", "path", "expires", "httpOnly", "secure", "sameSite"}
# sameSite에 허용되는 값 (Playwright CDP 스펙)
_VALID_SAMESITE = {"Strict", "Lax", "None"}


def _sanitize_cookies(cookies: list) -> list:
    result = []
    for c in cookies:
        cookie = {k: v for k, v in c.items() if k in _COOKIE_FIELDS}
        # CDP에서 허용하지 않는 sameSite 값 제거
        if "sameSite" in cookie and cookie["sameSite"] not in _VALID_SAMESITE:
            del cookie["sameSite"]
        result.append(cookie)
    return result


class NaverBrowser:
    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._started = False

    async def start(self):
        """Start browser and load session cookies."""
        if self._started:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        self._page = await self._context.new_page()

        if COOKIES_PATH.exists():
            try:
                cookies = _sanitize_cookies(json.loads(COOKIES_PATH.read_text()))
                for cookie in cookies:
                    try:
                        await self._context.add_cookies([cookie])
                    except Exception:
                        pass
            except Exception as e:
                print(f"[browser] Warning: could not load session cookies: {e}", file=sys.stderr)

        self._started = True

    async def get_page(self) -> Page:
        await self.start()
        return self._page

    async def new_page(self) -> Page:
        """새 탭 생성. 같은 context를 공유하므로 쿠키/로그인 상태 유지."""
        await self.start()
        return await self._context.new_page()

    async def is_logged_in(self) -> bool:
        """Check login state: NID_AUT cookie must exist and not be expired."""
        await self.start()
        import time
        cookies = await self._context.cookies()
        for c in cookies:
            if c["name"] == LOGIN_COOKIE:
                expires = c.get("expires", -1)
                if expires != -1 and expires < time.time():
                    return False
                return True
        return False

    async def try_import_chrome_session(self) -> bool:
        """Chrome에서 Naver 쿠키를 읽어 세션에 추가. NID_AUT가 있으면 True 반환."""
        try:
            from naver.chrome_cookies import get_naver_cookies_from_chrome
            chrome_cookies = get_naver_cookies_from_chrome()
            if not chrome_cookies:
                return False
            has_auth = any(c["name"] == LOGIN_COOKIE for c in chrome_cookies)
            if not has_auth:
                return False
            await self.start()
            # 쿠키를 개별로 추가 — 일부 쿠키가 invalid 필드를 갖더라도 나머지를 로드
            added = 0
            sanitized = _sanitize_cookies(chrome_cookies)
            print(f"[browser] Chrome 쿠키 {len(sanitized)}개 임포트 시도", file=sys.stderr)
            for cookie in sanitized:
                try:
                    await self._context.add_cookies([cookie])
                    added += 1
                except Exception as ce:
                    print(f"[browser] 쿠키 추가 실패 name={cookie.get('name')} domain={cookie.get('domain')}: {ce}", file=sys.stderr)
            if added == 0:
                print("[browser] Chrome 쿠키 임포트 실패: 추가된 쿠키 없음", file=sys.stderr)
                return False
            await self._save_cookies()
            print(f"[browser] Chrome 세션 쿠키 임포트 완료 ({added}개)", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[browser] Chrome 쿠키 임포트 실패: {e}", file=sys.stderr)
            return False

    async def wait_for_login(self, timeout: int = 120) -> bool:
        """Wait for user to manually log in by polling NID_AUT cookie."""
        await self._page.goto(NAVER_MAIN)
        elapsed = 0
        while elapsed < timeout:
            cookies = await self._context.cookies()
            if any(c["name"] == LOGIN_COOKIE for c in cookies):
                await self._save_cookies()
                return True
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        return False

    async def _save_cookies(self):
        """Save current session cookies to file."""
        COOKIES_PATH.parent.mkdir(exist_ok=True)
        cookies = await self._context.cookies()
        COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._started = False
