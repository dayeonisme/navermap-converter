# Chrome Cookie v24 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode Chrome v24 cookies without their host-hash prefix so Naver Chrome-session import succeeds.

**Architecture:** Read `meta.version` once per DB. For v24+, verify and strip `SHA-256(host_key)` from the decrypted payload; retain the existing v10/v20 decryption and v23 behavior.

**Tech Stack:** Python 3.9, SQLite, cryptography, pytest

## Global Constraints

- Only v24+ payloads with a matching host hash may be used.
- Older DB versions keep their existing decoded values.
- A malformed cookie is skipped without stopping other cookie imports.
- Tests use generated encrypted values and never real session data.

---

### Task 1: Add v24 prefix regression tests

**Files:**
- Create: `tests/test_chrome_cookies.py`
- Test: `tests/test_chrome_cookies.py`

- [ ] **Step 1: Build a temporary Chrome-style SQLite fixture**

Write helpers that create `meta(key, value)` and `cookies(name, value, host_key, path, is_secure, encrypted_value)`, then encrypt `hashlib.sha256(host.encode()).digest() + value.encode()` using AES-CBC with PKCS#7 padding and a `b"v10"` prefix.

- [ ] **Step 2: Add a failing v24 test**

```python
def test_read_cookies_v24_호스트해시_제거(tmp_path):
    db_path = tmp_path / "Cookies"
    key = b"k" * 16
    _write_cookie_db(db_path, version=24, host=".naver.com", value="real-cookie", key=key)

    cookies = _read_cookies(str(db_path), key)

    assert cookies[0]["value"] == "real-cookie"
```

- [ ] **Step 3: Add an older-version compatibility test**

```python
def test_read_cookies_v23_값_그대로_반환(tmp_path):
    db_path = tmp_path / "Cookies"
    key = b"k" * 16
    _write_cookie_db(db_path, version=23, host=".naver.com", value="legacy-cookie", key=key)

    assert _read_cookies(str(db_path), key)[0]["value"] == "legacy-cookie"
```

- [ ] **Step 4: Run tests and verify RED**

Run: `python3 -m pytest tests/test_chrome_cookies.py -v`

Expected: v24 test fails because the returned value includes the binary hash prefix; v23 test passes.

### Task 2: Strip verified v24 host hashes

**Files:**
- Modify: `naver/chrome_cookies.py:111-164`
- Test: `tests/test_chrome_cookies.py`

- [ ] **Step 1: Read DB version safely**

After connecting, read `meta.version`; use integer `0` if the table/key is unavailable or malformed.

- [ ] **Step 2: Verify and strip v24 payload prefix**

After decrypting and removing PKCS#7 padding, apply:

```python
if db_version >= 24:
    host_hash = hashlib.sha256(host.encode("utf-8")).digest()
    if not payload.startswith(host_hash):
        continue
    payload = payload[len(host_hash):]
value = payload.decode("utf-8", errors="ignore")
```

- [ ] **Step 3: Run cookie tests and verify GREEN**

Run: `python3 -m pytest tests/test_chrome_cookies.py -v`

Expected: v24 and v23 tests pass.

- [ ] **Step 4: Commit**

```bash
git add naver/chrome_cookies.py tests/test_chrome_cookies.py
git commit -m "fix: Chrome v24 쿠키 접두사 처리"
```

### Task 3: Verify actual Chrome import without disclosing values

- [ ] **Step 1:** Run all tests with `python3 -m pytest -q`.
- [ ] **Step 2:** Restart `python3 main.py`.
- [ ] **Step 3:** Read Chrome cookies and report only the count, the presence of `NID_AUT`/`NID_SES`, and whether either contains control characters.
- [ ] **Step 4:** Use `NaverBrowser.try_import_chrome_session()` and report only its boolean result and `is_logged_in()` result.
