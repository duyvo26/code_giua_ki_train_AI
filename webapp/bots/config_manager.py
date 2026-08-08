"""
File: config_manager.py
Chức năng: Đọc/ghi cấu hình bot (Telegram, Zalo) vào utils/bot_config.json
Vai trò: Config - nơi DUY NHẤT chứa token bot; file nằm ngoài git (gitignored)
File liên quan: webapp/bots/telegram_bot.py, webapp/bots/zalo_bot.py, webapp/app.py

Cấu trúc file:
{
  "telegram": {"token": "", "chat_id": ""},
  "zalo": {"token": "", "api_base": "https://bot-api.zaloplatforms.com", "chat_id": ""}
}
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "utils" / "bot_config.json"

DEFAULTS: dict = {
    "telegram": {"token": "", "chat_id": ""},
    "zalo": {
        "token": "",
        # Một số tài khoản dùng base khác (vd bot-api.zapps.me) - cho phép sửa trên web
        "api_base": "https://bot-api.zaloplatforms.com",
        "chat_id": "",
    },
}


def load_config() -> dict:
    """
    Đọc config từ file, ghép với mặc định để tránh thiếu key.
    File chưa tồn tại -> trả về config mặc định (chưa có token).
    """
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for bot_type in cfg:
                if isinstance(saved.get(bot_type), dict):
                    cfg[bot_type].update(saved[bot_type])
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(updates: dict) -> dict:
    """
    Lưu config: chỉ cập nhật các key được gửi lên (merge), giữ nguyên phần còn lại.

    Logic:
      - updates dạng {"telegram": {"token": "..."}, "zalo": {...}}
      - Token trống không được ghi đè (tránh xoá nhầm token khi gửi form trống)
    """
    cfg = load_config()
    for bot_type, fields in updates.items():
        if bot_type not in cfg or not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if key == "token" and not str(value or "").strip():
                continue
            cfg[bot_type][key] = value
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def mask_token(token: str) -> str:
    """Che token: chỉ hiện 4 ký tự đầu + 4 ký tự cuối (nếu đủ dài)."""
    token = str(token or "")
    if len(token) <= 8:
        return "***" if token else ""
    return f"{token[:4]}...{token[-4:]}"


def public_config() -> dict:
    """
    Config an toàn để gửi lên web: token được che, các trường còn lại thật.
    """
    cfg = load_config()
    return {
        bot_type: {
            key: (mask_token(value) if key == "token" else value)
            for key, value in fields.items()
        }
        for bot_type, fields in cfg.items()
    }
