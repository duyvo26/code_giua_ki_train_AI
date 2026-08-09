"""
File: history.py
Chuc nang: Lich su du lieu da nhan tu extension / phan tich tren web
Vai tro: Config/Util - ghi danh sach ban ghi vao results/api_history.json (gitignored)
File lien quan: webapp/app.py

Cau truc file luu tru:
{
  "entries": [
    {
      "ts": "2026-08-09 12:00:00",
      "source": "extension" | "web",
      "posts": 5,
      "comments": 40,
      "negative": 3,
      "threshold": 70.0,
      "sent_to": ["telegram"],
      "urls": ["https://www.facebook.com/groups/..."]
    }
  ]
}

Quy tac:
  - Giu toi da MAX_ENTRIES ban ghi (200) - cu nhat bi xoa
  - list_history tra ban ghi moi nhat truoc
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = PROJECT_ROOT / "results" / "api_history.json"

MAX_ENTRIES = 200


def _load() -> list[dict]:
    """Doc danh sach ban ghi tu file; chua co/loi -> rong."""
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    """Ghi danh sach ban ghi vao file (tao thu muc results neu chua co)."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_history(entry: dict) -> dict:
    """
    Them 1 ban ghi lich su moi (cu nhat bi xoa neu vuot MAX_ENTRIES).

    Args:
        entry (dict): {source, posts, comments, negative, threshold, sent_to, urls}

    Returns:
        dict: Ban ghi vua them
    """
    entries = _load()
    entries.append(entry)
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    _save(entries)
    return entry


def update_last_history(updates: dict) -> bool:
    """
    Cap nhat them thong tin cho ban ghi moi nhat (vd sent_to sau khi gui bot).

    Logic:
      - Dung cho luong extension: ban ghi duoc ghi khi phan tich xong,
        sau do bot gui xong thi patch lai truong sent_to

    Args:
        updates (dict): Cac truong can cap nhat (vd {"sent_to": ["telegram"]})

    Returns:
        bool: True neu cap nhat duoc, False neu khong co ban ghi
    """
    entries = _load()
    if not entries:
        return False
    entries[-1].update(updates)
    _save(entries)
    return True


def list_history(limit: int = 50) -> list[dict]:
    """
    Danh sach lich su, ban ghi moi nhat truoc.

    Args:
        limit (int): So ban ghi toi da tra ve (mac dinh 50)

    Returns:
        list[dict]: Cac ban ghi da sap xep moi -> cu
    """
    entries = _load()
    entries.reverse()  # moi nhat truoc
    return entries[: max(1, min(limit, MAX_ENTRIES))]
