# naver/chrome_cookies.py
"""macOS Chrome에서 Naver 쿠키를 추출하는 유틸리티."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import List


def get_naver_cookies_from_chrome() -> List[dict]:
    """Chrome의 Naver 쿠키를 읽어 Playwright 호환 형식으로 반환.
    실패 시 빈 리스트 반환 (예외를 올리지 않음).
    """
    try:
        cookie_db = os.path.expanduser(
            "~/Library/Application Support/Google/Chrome/Default/Network/Cookies"
        )
        if not os.path.exists(cookie_db):
            return []

        # macOS Keychain에서 Chrome 암호화 키 가져오기
        master_key = subprocess.check_output(
            ["security", "find-generic-password", "-w", "-a", "Chrome", "-s", "Chrome Safe Storage"],
            stderr=subprocess.DEVNULL,
        ).strip()

        # PBKDF2로 16바이트 AES 키 생성
        aes_key = hashlib.pbkdf2_hmac("sha1", master_key, b"saltysalt", 1003, 16)

        # Chrome이 DB를 잠글 수 있으므로 임시 복사본 사용
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
                cipher = Cipher(
                    algorithms.AES(aes_key),
                    modes.CBC(b" " * 16),
                    backend=default_backend(),
                )
                dec = cipher.decryptor()
                raw = dec.update(enc_value[3:]) + dec.finalize()
                pad = raw[-1]  # PKCS7 패딩 제거
                value = raw[:-pad].decode("utf-8", errors="ignore")
            except Exception:
                continue  # 복호화 실패 시 해당 쿠키 건너뜀

        if not value:
            continue

        # Playwright add_cookies() 형식: domain에 점(.) 접두사 필요
        domain = host if host.startswith(".") else host
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": bool(is_secure),
        })

    return cookies
