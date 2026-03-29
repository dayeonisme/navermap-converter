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
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        if COOKIES_PATH.exists():
            try:
                cookies = json.loads(COOKIES_PATH.read_text())
                await self._context.add_cookies(cookies)
            except Exception as e:
                print(f"[browser] Warning: could not load session cookies: {e}", file=sys.stderr)

        self._started = True

    async def get_page(self) -> Page:
        await self.start()
        return self._page

    async def is_logged_in(self) -> bool:
        """Check login state by looking for NID_AUT cookie (no page navigation)."""
        await self.start()
        cookies = await self._context.cookies()
        return any(c["name"] == LOGIN_COOKIE for c in cookies)

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
            await self._context.add_cookies(chrome_cookies)
            await self._save_cookies()
            print("[browser] Chrome 세션 쿠키 임포트 완료", file=sys.stderr)
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
