"""
File: schedules.py
Chuc nang: Lich hen quet tu dong - web mo tab FB dung gio, extension tu quet + tat tab
Vai tro: Config/Util - noi DUY NHAT luu danh sach lich hen (utils/schedules.json, gitignored)
File lien quan: webapp/app.py

Cau truc file luu tru:
{
  "schedules": [
    {
      "id": "abc123",
      "url": "https://www.facebook.com/groups/762609615053439",
      "interval_seconds": 300,
      "last_run_at": null,
      "next_run_at": 1754700000.0,
      "enabled": true
    }
  ]
}

Luong hoat dong:
  - Web UI goi GET /api/schedules/next de poll (10s): tra lich den gio
    (now >= next_run_at, enabled) NHUNG KHONG doi trang thai
  - Web JS window.open(url + "?closetab=true"); thanh cong (khong bi popup
    blocker) thi POST /api/schedules/ack -> mark_triggered
  - Bi chặn -> khong ack -> lan poll sau van con due (khong mat lich)
"""

import json
import secrets
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "utils" / "schedules.json"


def _load() -> list[dict]:
    """Doc danh sach lich hen tu file; chua co/loi -> rong."""
    if not CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        items = data.get("schedules") if isinstance(data, dict) else None
        return [s for s in items if isinstance(s, dict)] if isinstance(items, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(schedules: list[dict]) -> None:
    """Ghi danh sach lich hen vao file (tao thu muc cha neu chua co)."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"schedules": schedules}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _fmt_time(ts: float | None) -> str:
    """Dinh dang epoch -> '%Y-%m-%d %H:%M:%S' (None -> '')."""
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def list_schedules() -> list[dict]:
    """
    Danh sach lich hen (kem thoi gian doc duoc dang text).

    Returns:
        list[dict]: Moi lich co them {last_run, next_run} dang text
    """
    schedules = []
    for s in _load():
        item = dict(s)
        item["last_run"] = _fmt_time(item.get("last_run_at"))
        item["next_run"] = _fmt_time(item.get("next_run_at"))
        schedules.append(item)
    return schedules


def add_schedule(url: str, interval_seconds: int) -> dict:
    """
    Them 1 lich hen moi (lan chay dau tien sau interval_seconds).

    Args:
        url (str): URL group Facebook
        interval_seconds (int): Khoang cach giua cac lan quet (giay)

    Returns:
        dict: Lich hen vua them
    """
    now = time.time()
    schedule = {
        "id": secrets.token_hex(6),
        "url": url,
        "interval_seconds": int(interval_seconds),
        "last_run_at": None,
        "next_run_at": now + int(interval_seconds),
        "enabled": True,
    }
    schedules = _load()
    schedules.append(schedule)
    _save(schedules)
    return schedule


def remove_schedule(schedule_id: str) -> bool:
    """
    Xoa 1 lich hen.

    Returns:
        bool: True neu xoa duoc, False neu khong ton tai
    """
    schedules = _load()
    remaining = [s for s in schedules if s.get("id") != schedule_id]
    if len(remaining) == len(schedules):
        return False
    _save(remaining)
    return True


def toggle_schedule(schedule_id: str) -> bool:
    """
    Bat/tat (enabled) 1 lich hen.

    Returns:
        bool: True neu doi duoc, False neu khong ton tai
    """
    schedules = _load()
    for s in schedules:
        if s.get("id") == schedule_id:
            s["enabled"] = not s.get("enabled", True)
            _save(schedules)
            return True
    return False


def due_schedules(now: float | None = None) -> list[dict]:
    """
    Lich hen DEN GIO (enabled va now >= next_run_at).

    Logic:
      - KHONG doi trang thai - viec nay do POST /api/schedules/ack lam
        (tranh mat lich khi window.open bi popup blocker chan)

    Args:
        now (float | None): Thoi diem so sanh (mac dinh time.time())

    Returns:
        list[dict]: Danh sach lich den gio ({id, url, interval_seconds})
    """
    now = now if now is not None else time.time()
    return [
        {"id": s["id"], "url": s["url"], "interval_seconds": s["interval_seconds"]}
        for s in _load()
        if s.get("enabled", True) and (s.get("next_run_at") or 0) <= now
    ]


def mark_triggered(schedule_ids: list[str]) -> int:
    """
    Danh dau lich da duoc mo tab (sau khi window.open thanh cong).

    Logic:
      - last_run_at = now, next_run_at = now + interval_seconds
      - Chi cap nhat lich co trong danh sach truyen vao

    Args:
        schedule_ids (list[str]): Danh sach id da mo thanh cong

    Returns:
        int: So lich da cap nhat
    """
    if not schedule_ids:
        return 0
    now = time.time()
    schedules = _load()
    updated = 0
    for s in schedules:
        if s.get("id") in schedule_ids:
            s["last_run_at"] = now
            s["next_run_at"] = now + int(s.get("interval_seconds", 60))
            updated += 1
    if updated:
        _save(schedules)
    return updated
