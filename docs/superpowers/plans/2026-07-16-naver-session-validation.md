# Naver Session Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject incomplete or expired Naver login cookies and convert login-page iframe detachment into the existing session-recovery flow.

**Architecture:** Centralize cookie validity in a pure helper used by all login checks. Keep list creation behavior unchanged except for classifying an exception as `SESSION_EXPIRED` when the page has redirected to Naver login, allowing `main.py` to clear cookies, import Chrome cookies, and retry once.

**Tech Stack:** Python 3.9, Playwright async API, pytest 8.3, unittest.mock

## Global Constraints

- Require both `NID_AUT` and `NID_SES` with non-empty values.
- Treat missing expiration or `expires == -1` as valid for the current browser session.
- Reject a cookie with an explicit expiration earlier than the current time.
- Reuse one cookie-validation helper in `is_logged_in()`, Chrome import validation, and `wait_for_login()`.
- Preserve the existing one-retry limit in `main.py`.
- Preserve non-login list-creation errors in `리스트 생성 실패 [단계]: 원인` format.

---

## File Map

- Modify `naver/browser.py`: central cookie validation and consistent login checks.
- Modify `naver/map_saver.py`: reclassify iframe errors after a login redirect.
- Modify `tests/test_browser.py`: session-cookie regression coverage.
- Modify `tests/test_map_saver.py`: redirect/detached-frame regression coverage.

### Task 1: Validate the complete Naver login cookie pair

**Files:**
- Modify: `naver/browser.py:10-13,81-133`
- Modify: `tests/test_browser.py`

**Interfaces:**
- Consumes: Playwright cookie dictionaries containing `name`, `value`, and optional `expires`.
- Produces: `_has_valid_login_cookies(cookies: list, now: float | None = None) -> bool`; existing `NaverBrowser` public method signatures stay unchanged.

- [ ] **Step 1: Replace the old one-cookie tests with failing pair-validity tests**

Update `tests/test_browser.py` to import `time`, then replace the first two tests with:

```python
@pytest.mark.asyncio
async def test_is_logged_in_true_when_필수쿠키_모두_유효():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()
    browser._context = AsyncMock()
    browser._context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "aut", "expires": time.time() + 3600},
        {"name": "NID_SES", "value": "ses", "expires": -1},
    ])
    browser._started = True

    assert await browser.is_logged_in() is True


@pytest.mark.asyncio
async def test_is_logged_in_false_when_NID_SES_누락():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()
    browser._context = AsyncMock()
    browser._context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "aut", "expires": time.time() + 3600},
    ])
    browser._started = True

    assert await browser.is_logged_in() is False


@pytest.mark.asyncio
async def test_is_logged_in_false_when_NID_SES_만료():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()
    browser._context = AsyncMock()
    browser._context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "aut", "expires": time.time() + 3600},
        {"name": "NID_SES", "value": "ses", "expires": time.time() - 1},
    ])
    browser._started = True

    assert await browser.is_logged_in() is False
```

- [ ] **Step 2: Add a failing Chrome-import validation test**

Append to `tests/test_browser.py` and add `patch` to the unittest.mock import:

```python
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
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
python3 -m pytest tests/test_browser.py -v
```

Expected: the missing/expired `NID_SES` tests fail because the current implementation checks only `NID_AUT`; the Chrome import test returns the wrong result and calls `add_cookies()`.

- [ ] **Step 4: Add the shared cookie validator**

In `naver/browser.py`, import `time`, replace `LOGIN_COOKIE`, and add:

```python
LOGIN_COOKIES = {"NID_AUT", "NID_SES"}


def _has_valid_login_cookies(cookies: list, now: float | None = None) -> bool:
    current_time = time.time() if now is None else now
    cookies_by_name = {
        cookie.get("name"): cookie
        for cookie in cookies
        if cookie.get("name") in LOGIN_COOKIES and cookie.get("value")
    }
    if set(cookies_by_name) != LOGIN_COOKIES:
        return False
    for cookie in cookies_by_name.values():
        expires = cookie.get("expires", -1)
        if expires not in (-1, None) and expires < current_time:
            return False
    return True
```

- [ ] **Step 5: Use the validator in all three login paths**

Replace `is_logged_in()`'s loop with:

```python
        cookies = await self._context.cookies()
        return _has_valid_login_cookies(cookies)
```

Replace the Chrome `has_auth` check with:

```python
            if not _has_valid_login_cookies(chrome_cookies):
                return False
```

Replace `wait_for_login()`'s `any(...)` condition with:

```python
            if _has_valid_login_cookies(cookies):
```

Update the three docstrings to refer to both required login cookies.

- [ ] **Step 6: Run browser tests and verify GREEN**

Run:

```bash
python3 -m pytest tests/test_browser.py -v
```

Expected: all browser tests pass.

- [ ] **Step 7: Commit cookie validation**

```bash
git add naver/browser.py tests/test_browser.py
git commit -m "fix: 네이버 로그인 쿠키 쌍 검증"
```

### Task 2: Convert iframe detachment after login redirect

**Files:**
- Modify: `naver/map_saver.py:41-102`
- Modify: `tests/test_map_saver.py`

**Interfaces:**
- Consumes: `_create_list(page, list_name)` and the page's current `url` after a Playwright exception.
- Produces: `RuntimeError("SESSION_EXPIRED")` for login redirects; existing step-specific `RuntimeError` for other failures.

- [ ] **Step 1: Add failing redirect and non-redirect tests**

Add `PropertyMock` to the unittest.mock import and append:

```python
@pytest.mark.asyncio
async def test_create_list_frame_detached_로그인리다이렉트_session_expired():
    from naver.map_saver import _create_list
    from naver import selectors as S

    page = AsyncMock()
    frame = AsyncMock()
    frame.query_selector_all = AsyncMock(return_value=[])
    frame.click = AsyncMock(side_effect=Exception("Frame was detached"))
    type(page).url = PropertyMock(side_effect=[S.MAP_URL, S.MAP_URL, S.MAP_URL, "https://nid.naver.com/nidlogin.login"])

    with patch("naver.map_saver._get_my_place_frame", return_value=frame), \
         patch("naver.map_saver._screenshot", new=AsyncMock()):
        with pytest.raises(RuntimeError, match="^SESSION_EXPIRED$"):
            await _create_list(page, "Auto_20260716_1558")


@pytest.mark.asyncio
async def test_create_list_frame_error_로그인아니면_단계오류_유지():
    from naver.map_saver import _create_list
    from naver import selectors as S

    page = AsyncMock()
    page.url = S.MAP_URL
    frame = AsyncMock()
    frame.query_selector_all = AsyncMock(return_value=[])
    frame.click = AsyncMock(side_effect=Exception("selector missing"))

    with patch("naver.map_saver._get_my_place_frame", return_value=frame), \
         patch("naver.map_saver._screenshot", new=AsyncMock()):
        with pytest.raises(RuntimeError, match=r"리스트 생성 실패 \[create_list_button\]: selector missing"):
            await _create_list(page, "Auto_20260716_1558")
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python3 -m pytest \
  tests/test_map_saver.py::test_create_list_frame_detached_로그인리다이렉트_session_expired \
  tests/test_map_saver.py::test_create_list_frame_error_로그인아니면_단계오류_유지 -v
```

Expected: the redirect test fails with `리스트 생성 실패 [create_list_button]`; the non-redirect test already documents the retained behavior.

- [ ] **Step 3: Reclassify an exception when the page is now on login**

Change `_create_list()`'s generic exception handler to:

```python
    except Exception as e:
        if "nidlogin" in page.url:
            raise RuntimeError("SESSION_EXPIRED") from e
        await _screenshot(page, f"create_list_fail_{step}")
        raise RuntimeError(f"리스트 생성 실패 [{step}]: {e}")
```

- [ ] **Step 4: Run map-saver tests and verify GREEN**

Run:

```bash
python3 -m pytest tests/test_map_saver.py -v
```

Expected: all map-saver tests pass.

- [ ] **Step 5: Commit redirect recovery**

```bash
git add naver/map_saver.py tests/test_map_saver.py
git commit -m "fix: 로그인 리다이렉트 세션 만료 처리"
```

### Task 3: Regression and running-server verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: all updated session and save-flow code.
- Produces: fresh automated and running-server evidence without creating a Naver list during verification.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Restart the local server**

Stop the process listening on port 8000, then run:

```bash
/usr/bin/python3 main.py
```

Expected: Uvicorn reports `http://127.0.0.1:8000`.

- [ ] **Step 3: Verify the stale saved session is rejected**

Run:

```bash
curl -sS http://127.0.0.1:8000/login-status
```

Expected with the reproduced cookie metadata: `{ "logged_in": false }`, because `NID_SES` is expired.

- [ ] **Step 4: Inspect commits and working tree**

Run:

```bash
git diff HEAD~2 --check
git status --short
```

Expected: no whitespace errors; only the user's pre-existing untracked screenshot files remain.
