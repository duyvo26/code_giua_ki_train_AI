"""
File: api_keys.py
Chuc nang: Quan ly API key cho extension gui data ve web
Vai tro: Config/Util - noi DUY NHAT luu danh sach API key (utils/api_keys.json, gitignored)
File lien quan: webapp/app.py

Cau truc file luu tru:
{
  "keys": [
    {"key": "abc123...", "name": "extension", "created_at": "2026-08-09 10:00:00"}
  ]
}

Quy tac:
  - Key sinh bang secrets.token_hex(16) -> 32 ky tu, khong doan duoc
  - Khong co login - bat ky ai co URL web cung goi duoc /api/keys/*
    (chay qua Cloudflared tunnel, chi dung cho muc dich demo)
"""

import json
import secrets
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "utils" / "api_keys.json"

KEY_LENGTH = 32  # token_hex(16) -> 32 ky tu


def _load() -> list[dict]:
    """Doc danh sach key tu file; file chua co/loi -> danh sach rong."""
    if not CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        keys = data.get("keys") if isinstance(data, dict) else None
        return [k for k in keys if isinstance(k, dict)] if isinstance(keys, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(keys: list[dict]) -> None:
    """Ghi danh sach key vao file (tao thu muc cha neu chua co)."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"keys": keys}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_keys() -> list[dict]:
    """
    Danh sach API key hien co.

    Returns:
        list[dict]: [{key, name, created_at}] - thoi gian moi nhat truoc
    """
    keys = _load()
    keys.sort(key=lambda k: k.get("created_at", ""), reverse=True)
    return keys


def generate_api_key(name: str = "") -> dict:
    """
    Sinh 1 API key moi (32 ky tu) va luu vao file.

    Logic:
      - name trong/khong co -> dung "extension"
      - created_at = thoi gian hien tai (dinh dang %Y-%m-%d %H:%M:%S)

    Args:
        name (str): Ten tuy chon de nhan dien key (vi du "extension A")

    Returns:
        dict: {"key", "name", "created_at"} key moi sinh
    """
    keys = _load()
    entry = {
        "key": secrets.token_hex(16),
        "name": (name or "").strip() or "extension",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    keys.append(entry)
    _save(keys)
    return entry


def revoke_api_key(key: str) -> bool:
    """
    Xoa 1 API key khoi danh sach.

    Args:
        key (str): API key can xoa

    Returns:
        bool: True neu tim thay va xoa duoc, False neu khong ton tai
    """
    keys = _load()
    remaining = [k for k in keys if k.get("key") != key]
    if len(remaining) == len(keys):
        return False
    _save(remaining)
    return True


def is_valid_api_key(key: str) -> bool:
    """
    Kiem tra API key hop le (ton tai trong file).

    Logic:
      - So sanh truc tiep toan bo key (khong hash vi la key ngau nhien
        dai 32 ky tu, file la noi quan ly duy nhat)

    Args:
        key (str): API key can kiem tra

    Returns:
        bool: True neu hop le
    """
    if not key:
        return False
    return any(k.get("key") == key for k in _load())
