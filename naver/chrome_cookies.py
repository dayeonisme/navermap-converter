# naver/chrome_cookies.py
"""Chrome에서 Naver 쿠키를 추출하는 유틸리티 (macOS / Windows / Linux)."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
from typing import List


def get_naver_cookies_from_chrome() -> List[dict]:
    """Chrome의 Naver 쿠키를 읽어 Playwright 호환 형식으로 반환.
    실패 시 빈 리스트 반환 (예외를 올리지 않음).
    """
    try:
        cookie_db, aes_key = _find_cookie_db_and_key()
        if cookie_db is None or aes_key is None:
            return []

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            shutil.copy2(cookie_db, tmp.name)
            tmp_path = tmp.name

        try:
            return _read_cookies(tmp_path, aes_key)
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        print(f"[chrome_cookies] Chrome 쿠키 읽기 실패: {e}", file=sys.stderr)
        return []


def _find_cookie_db_and_key():
    """OS별 Chrome 쿠키 DB 경로와 AES 키를 반환. 찾지 못하면 (None, None)."""
    system = platform.system()

    if system == "Darwin":
        return _darwin_cookie_db_and_key()
    elif system == "Windows":
        return _windows_cookie_db_and_key()
    elif system == "Linux":
        return _linux_cookie_db_and_key()
    else:
        print(f"[chrome_cookies] 지원하지 않는 OS: {system}", file=sys.stderr)
        return None, None


# ── macOS ──────────────────────────────────────────────────────────────────

def _darwin_cookie_db_and_key():
    import subprocess

    base = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    cookie_db = _find_cookie_file(base)
    if cookie_db is None:
        return None, None

    try:
        master_key = subprocess.check_output(
            ["security", "find-generic-password", "-w", "-a", "Chrome", "-s", "Chrome Safe Storage"],
            stderr=subprocess.DEVNULL,
        ).strip()
        aes_key = hashlib.pbkdf2_hmac("sha1", master_key, b"saltysalt", 1003, 16)
        return cookie_db, aes_key
    except Exception as e:
        print(f"[chrome_cookies] macOS Keychain 읽기 실패: {e}", file=sys.stderr)
        return None, None


# ── Windows ────────────────────────────────────────────────────────────────

def _windows_cookie_db_and_key():
    import json
    import base64

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    base = os.path.join(local_app_data, "Google", "Chrome", "User Data", "Default")
    cookie_db = _find_cookie_file(base)
    if cookie_db is None:
        return None, None

    # Read encrypted_key from Local State
    local_state_path = os.path.join(local_app_data, "Google", "Chrome", "User Data", "Local State")
    if not os.path.exists(local_state_path):
        return None, None

    try:
        import win32crypt  # type: ignore
        with open(local_state_path, encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)[5:]  # strip DPAPI prefix
        aes_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return cookie_db, aes_key
    except ImportError:
        print("[chrome_cookies] Windows: pywin32 미설치 — Chrome 쿠키 임포트 불가", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"[chrome_cookies] Windows DPAPI 복호화 실패: {e}", file=sys.stderr)
        return None, None


# ── Linux ──────────────────────────────────────────────────────────────────

def _linux_cookie_db_and_key():
    base = os.path.expanduser("~/.config/google-chrome/Default")
    if not os.path.isdir(base):
        base = os.path.expanduser("~/.config/chromium/Default")
    cookie_db = _find_cookie_file(base)
    if cookie_db is None:
        return None, None

    # Linux Chrome uses a fixed password "peanuts" with PBKDF2
    aes_key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)
    return cookie_db, aes_key


# ── Shared ─────────────────────────────────────────────────────────────────

def _find_cookie_file(base: str):
    for candidate in [
        os.path.join(base, "Network", "Cookies"),
        os.path.join(base, "Cookies"),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def _read_cookies(db_path: str, aes_key: bytes) -> List[dict]:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name, value, host_key, path, is_secure, encrypted_value "
        "FROM cookies WHERE host_key LIKE '%naver.com'"
    ).fetchall()
    conn.close()

    cookies = []
    for name, value, host, path, is_secure, enc_value in rows:
        if enc_value and enc_value[:3] == b"v10":
            try:
                # macOS/Linux Chrome: AES-128-CBC, IV = 0x20 * 16, PKCS7 패딩
                cipher = Cipher(
                    algorithms.AES(aes_key),
                    modes.CBC(b" " * 16),
                    backend=default_backend(),
                )
                dec = cipher.decryptor()
                raw = dec.update(enc_value[3:]) + dec.finalize()
                pad = raw[-1]
                value = raw[:-pad].decode("utf-8", errors="ignore")
            except Exception:
                continue
        elif enc_value and enc_value[:3] == b"v20":
            # Windows Chrome 80+: AES-256-GCM
            # Format: b"v20" + 12-byte nonce + ciphertext + 16-byte tag
            # AESGCM.decrypt() expects ciphertext||tag as a single bytes object
            try:
                nonce = enc_value[3:15]
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                aesgcm = AESGCM(aes_key)
                value = aesgcm.decrypt(nonce, enc_value[15:], None).decode("utf-8", errors="ignore")
            except Exception:
                continue

        if not value:
            continue

        domain = host if host.startswith(".") else host
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": bool(is_secure),
        })

    return cookies
