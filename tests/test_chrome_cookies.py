from __future__ import annotations

import hashlib
import sqlite3

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from naver.chrome_cookies import _read_cookies


def _encrypt_v10(payload: bytes, key: bytes) -> bytes:
    padding = 16 - (len(payload) % 16)
    padded = payload + bytes([padding]) * padding
    cipher = Cipher(
        algorithms.AES(key),
        modes.CBC(b" " * 16),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    return b"v10" + encryptor.update(padded) + encryptor.finalize()


def _write_cookie_db(
    db_path,
    *,
    version: int,
    host: str,
    value: str,
    key: bytes,
    payload_host: str | None = None,
) -> None:
    payload = value.encode("utf-8")
    if version >= 24:
        payload = hashlib.sha256((payload_host or host).encode("utf-8")).digest() + payload

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE meta (key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR)")
    conn.execute(
        "CREATE TABLE cookies (name TEXT, value TEXT, host_key TEXT, path TEXT, is_secure INTEGER, encrypted_value BLOB)"
    )
    conn.execute("INSERT INTO meta (key, value) VALUES ('version', ?)", (str(version),))
    conn.execute(
        "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?)",
        ("NID_AUT", "", host, "/", 1, _encrypt_v10(payload, key)),
    )
    conn.commit()
    conn.close()


def test_read_cookies_v24_호스트해시_제거(tmp_path):
    db_path = tmp_path / "Cookies"
    key = b"k" * 16
    _write_cookie_db(db_path, version=24, host=".naver.com", value="real-cookie", key=key)

    cookies = _read_cookies(str(db_path), key)

    assert cookies[0]["value"] == "real-cookie"


def test_read_cookies_v23_값_그대로_반환(tmp_path):
    db_path = tmp_path / "Cookies"
    key = b"k" * 16
    _write_cookie_db(db_path, version=23, host=".naver.com", value="legacy-cookie", key=key)

    cookies = _read_cookies(str(db_path), key)

    assert cookies[0]["value"] == "legacy-cookie"


def test_read_cookies_v24_호스트해시_불일치시_건너뜀(tmp_path):
    db_path = tmp_path / "Cookies"
    key = b"k" * 16
    _write_cookie_db(
        db_path,
        version=24,
        host=".naver.com",
        payload_host=".other.com",
        value="wrong-host",
        key=key,
    )

    assert _read_cookies(str(db_path), key) == []
