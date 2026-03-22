# naver/browser.py
class NaverBrowser:
    async def is_logged_in(self) -> bool:
        return False
    async def wait_for_login(self, timeout: int = 120) -> bool:
        return False
    async def get_page(self):
        return None
    async def close(self):
        pass
