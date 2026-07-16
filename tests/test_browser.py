# tests/test_browser.py
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_is_logged_in_true_when_필수쿠키_모두_유효():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "aut", "expires": time.time() + 3600},
        {"name": "NID_SES", "value": "ses", "expires": -1},
    ])
    browser._context = mock_context
    browser._started = True

    result = await browser.is_logged_in()
    assert result is True

@pytest.mark.asyncio
async def test_is_logged_in_false_when_NID_SES_누락():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "aut", "expires": time.time() + 3600},
    ])
    browser._context = mock_context
    browser._started = True

    result = await browser.is_logged_in()
    assert result is False


@pytest.mark.asyncio
async def test_is_logged_in_false_when_NID_SES_만료():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "aut", "expires": time.time() + 3600},
        {"name": "NID_SES", "value": "ses", "expires": time.time() - 1},
    ])
    browser._context = mock_context
    browser._started = True

    result = await browser.is_logged_in()
    assert result is False

@pytest.mark.asyncio
async def test_wait_for_login_timeout_false():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[])
    browser._page = mock_page
    browser._context = mock_context
    browser._started = True

    result = await browser.wait_for_login(timeout=2)
    assert result is False


@pytest.mark.asyncio
async def test_try_import_chrome_session_false_when_NID_SES_누락():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()
    browser._started = True
    browser._context = AsyncMock()

    with patch(
        "naver.chrome_cookies.get_naver_cookies_from_chrome",
        return_value=[{"name": "NID_AUT", "value": "aut"}],
    ):
        assert await browser.try_import_chrome_session() is False

    browser._context.add_cookies.assert_not_called()
