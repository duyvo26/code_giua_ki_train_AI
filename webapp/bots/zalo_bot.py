"""
File: zalo_bot.py
Chức năng: Bot Zalo (Bot Creator / Marketplace - bot.zaloplatforms.com) long-polling
Vai trò: Bot - chạy thread nền trong webapp; KHÔNG cần webhook/HTTPS công khai
File liên quan: webapp/bots/config_manager.py, webapp/bots/common.py, webapp/app.py

API (xác minh từ plugin @openclaw/zalo + cấu hình n8n thực tế):
  - POST https://bot-api.zaloplatforms.com/bot<token>/getMe
  - POST https://bot-api.zaloplatforms.com/bot<token>/getUpdates  body {"timeout": "30"}
    * QUAN TRỌNG: trả 1 update duy nhất mỗi call (KHÔNG phải mảng như Telegram)
  - POST https://bot-api.zaloplatforms.com/bot<token>/sendMessage body {"chat_id", "text"}
  Response: {ok: true, ...} | lỗi: {ok: false, error_code, description}
  Giới hạn: text outbound 2000 ký tự (chunk UTF-16 an toàn)
  Base URL có thể khác tài khoản (vd bot-api.zapps.me) - cho phép nhập trên web.
"""

import threading
import time
from typing import Callable

import requests

from webapp.bots.common import build_sentiment_reply, chunk_text
from webapp.bots.config_manager import load_config, save_config

TEXT_CHUNK = 2000  # giới hạn Zalo API


class ZaloBot:
    """Bot Zalo Bot Creator: validate token, polling thread, gửi reply cảm xúc."""

    def __init__(self, on_log: Callable[[str, str], None] | None = None):
        self.on_log = on_log
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ---------- tiện ích ----------
    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log("zalo", message)

    def _cfg(self) -> dict:
        return load_config()["zalo"]

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _call(self, method: str, body: dict | None = None) -> dict:
        """
        Gọi API Zalo: POST {api_base}/bot{token}/{method}.
        Token nằm trong URL path (chuẩn Bot Creator).

        Logic:
          - Response luôn là JSON {ok: true/false, error_code, description}
          - Nếu server trả không phải JSON (vd trang 404 HTML) -> trả
            dict lỗi chuẩn thay vì để exception crash bot thread
        """
        cfg = self._cfg()
        token = cfg["token"].strip()
        base = (cfg.get("api_base") or "https://bot-api.zaloplatforms.com").rstrip("/")
        resp = requests.post(
            f"{base}/bot{token}/{method}",
            json=body,
            timeout=35,
        )
        try:
            return resp.json()
        except ValueError:
            return {
                "ok": False,
                "error_code": resp.status_code,
                "description": f"HTTP {resp.status_code} - {resp.text[:120]}",
            }

    def get_webhook_info(self) -> dict:
        """Đọc webhook đang cài (nếu có) - dùng để gỡ trước khi polling."""
        try:
            return self._call("getWebhookInfo")
        except requests.RequestException as exc:
            return {"ok": False, "description": f"Loi mang: {exc}"}

    def delete_webhook(self) -> dict:
        """
        Gỡ webhook - Zalo KHÔNG cho polling khi webhook đang cài
        (lỗi 400 "You cannot use this API while a webhook is set").
        """
        try:
            return self._call("deleteWebhook")
        except requests.RequestException as exc:
            return {"ok": False, "description": f"Loi mang: {exc}"}

    # ---------- API ----------
    def get_me(self) -> dict:
        """Kiểm tra token + base URL: gọi getMe. Trả {ok, error}."""
        cfg = self._cfg()
        if not cfg["token"].strip():
            return {"ok": False, "error": "Chua co token - tao bot tai bot.zaloplatforms.com"}
        try:
            data = self._call("getMe")
        except requests.RequestException as exc:
            return {"ok": False, "error": f"Loi mang (kiem tra API base): {exc}"}
        if not data.get("ok"):
            return {"ok": False, "error": data.get("description", "Token/API base khong hop le")}
        result = data.get("result") or {}
        return {"ok": True, "bot_name": result.get("display_name") or result.get("name") or ""}

    def send(self, chat_id: str, text: str) -> bool:
        """Gửi text tới chat_id, chunk 2000 ký tự."""
        ok_all = True
        for chunk in chunk_text(text, TEXT_CHUNK):
            try:
                data = self._call("sendMessage", {"chat_id": chat_id, "text": chunk})
                if not data.get("ok"):
                    self._log(f"[send] Loi: {data.get('description')}")
                    ok_all = False
            except requests.RequestException as exc:
                self._log(f"[send] Loi mang: {exc}")
                ok_all = False
        return ok_all

    # ---------- vòng lặp nhận tin ----------
    def start(self) -> dict:
        """
        Bật polling thread. Từ chối nếu chưa có token hoặc đang chạy.

        Logic:
          - Kiểm tra token bằng getMe trước
          - Tự gỡ webhook nếu đang cài (Zalo chặn getUpdates khi có webhook)
        """
        if self.is_running:
            return {"ok": False, "error": "Bot dang chay roi"}
        check = self.get_me()
        if not check["ok"]:
            return {"ok": False, "error": check["error"]}

        webhook_info = self.get_webhook_info()
        webhook_url = (webhook_info.get("result") or {}).get("url", "")
        if webhook_url:
            self._log(f"Phat hien webhook dang cai ({webhook_url}) - tu go de dung polling")
            removed = self.delete_webhook()
            if not removed.get("ok"):
                self._log(f"[warn] Go webhook that bai: {removed.get('description')}")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._log("Bot da bat (long-polling)")
        return {"ok": True, "message": f"Bot dang chay ({check.get('bot_name', '')})"}

    def stop(self) -> dict:
        """Dừng polling thread."""
        if not self.is_running:
            return {"ok": False, "error": "Bot chua chay"}
        self._stop_event.set()
        self._thread.join(timeout=3)
        self._log("Bot da dung")
        return {"ok": True, "message": "Da dung bot"}

    def _parse_update(self, data: dict) -> dict | None:
        """
        Parse 1 update Zalo: trả {chat_id, text} hoặc None.
        Zalo trả 1 update duy nhất; cấu trúc linh hoạt theo loại sự kiện
        (chat_id có thể nằm ở update, message hoặc from) nên tra cả 3.
        """
        update = data.get("update") or data.get("result") or data
        message = update.get("message") or update
        chat_id = (
            update.get("chat_id")
            or message.get("chat_id")
            or (update.get("from") or {}).get("id")
        )
        text = (message.get("text") or update.get("text") or "").strip()
        if chat_id is None or not text:
            return None
        return {"chat_id": str(chat_id), "text": text}

    def _poll_loop(self) -> None:
        """
        Vòng lặp getUpdates (1 update/call): phân tích -> reply.

        Logic:
          - error_code 408 (Request timeout) = long-polling hết hạn,
            KHÔNG có tin mới -> tiếp tục vòng lặp (không phải lỗi)
          - error_code 400 "webhook" = webhook còn cài -> gỡ 1 lần rồi tiếp tục
          - Lỗi khác -> log + dừng bot (tránh spam API)
        """
        webhook_retried = False
        while not self._stop_event.is_set():
            try:
                data = self._call("getUpdates", {"timeout": "30"})
            except requests.RequestException as exc:
                self._log(f"[poll] Loi mang: {exc} - thu lai 5s")
                time.sleep(5)
                continue

            if not data.get("ok"):
                error_code = data.get("error_code")
                description = data.get("description", "")
                if error_code == 408:
                    # long-polling hết thời gian chờ - bình thường, poll tiếp
                    continue
                if error_code == 400 and "webhook" in description.lower() and not webhook_retried:
                    self._log("Webhook dang cai - tu go va tiep tuc polling")
                    self.delete_webhook()
                    webhook_retried = True
                    continue
                self._log(f"[poll] Loi API ({error_code}): {description} - dung bot")
                self._stop_event.set()
                break
            webhook_retried = False

            parsed = self._parse_update(data)
            if parsed is None:
                time.sleep(1)
                continue
            # Lưu chat_id tự động để nút "Test" gửi được
            save_config({"zalo": {"chat_id": parsed["chat_id"]}})
            self._log(f"Nhan tu chat {parsed['chat_id']}: {parsed['text'][:80]}")
            reply = build_sentiment_reply(parsed["text"])
            self.send(parsed["chat_id"], reply)
            self._log("Da gui ket qua phan tich cam xuc")
            time.sleep(1)
