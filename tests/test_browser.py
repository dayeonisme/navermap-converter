# tests/test_browser.py
import pytest
import asyncio
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_is_logged_in_true_when_NID_AUT_쿠키_존재():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "abc123"}
    ])
    browser._page = mock_page
    browser._context = mock_context
    browser._started = True

    result = await browser.is_logged_in()
    assert result is True
    mock_page.goto.assert_called_once()

@pytest.mark.asyncio
async def test_is_logged_in_false_when_NID_AUT_쿠키_없음():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "OTHER_COOKIE", "value": "xyz"}
    ])
    browser._page = mock_page
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
