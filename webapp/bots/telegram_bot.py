"""
File: telegram_bot.py
Chức năng: Bot Telegram - long-polling getUpdates, phân tích cảm xúc, reply
Vai trò: Bot - chạy thread nền trong webapp; không cần webhook/public URL
File liên quan: webapp/bots/config_manager.py, webapp/bots/common.py, webapp/app.py

API (Bot API chính thức):
  - GET  https://api.telegram.org/bot<token>/getMe
  - GET  https://api.telegram.org/bot<token>/getUpdates?offset=N&timeout=25  (trả MẢNG)
  - POST https://api.telegram.org/bot<token>/sendMessage {chat_id, text}
Lưu ý: 409 conflict nếu 2 poller dùng cùng token - phải dừng bot cũ trước.
"""

import threading
import time
from typing import Callable

import requests

from webapp.bots.common import build_sentiment_reply, chunk_text
from webapp.bots.config_manager import load_config, save_config

API_BASE = "https://api.telegram.org"
TEXT_CHUNK = 4000


class TelegramBot:
    """Bot Telegram: validate token, polling thread, gửi reply cảm xúc."""

    def __init__(self, on_log: Callable[[str, str], None] | None = None):
        self.on_log = on_log
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ---------- tiện ích ----------
    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log("telegram", message)

    def _token(self) -> str:
        return load_config()["telegram"]["token"].strip()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------- API ----------
    def get_me(self) -> dict:
        """Kiểm tra token: gọi getMe, 401 = token sai. Trả {ok, error}."""
        token = self._token()
        if not token:
            return {"ok": False, "error": "Chua co token - nhap token tu BotFather"}
        try:
            resp = requests.get(f"{API_BASE}/bot{token}/getMe", timeout=15).json()
        except requests.RequestException as exc:
            return {"ok": False, "error": f"Loi mang: {exc}"}
        if not resp.get("ok"):
            return {"ok": False, "error": resp.get("description", "Token khong hop le")}
        return {"ok": True, "username": resp["result"].get("username", "")}

    def send(self, chat_id: str, text: str) -> bool:
        """Gửi text tới chat_id, tự chia chunk nếu quá giới hạn."""
        token = self._token()
        ok_all = True
        for chunk in chunk_text(text, TEXT_CHUNK):
            try:
                resp = requests.post(
                    f"{API_BASE}/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                    timeout=15,
                ).json()
                if not resp.get("ok"):
                    self._log(f"[send] Loi: {resp.get('description')}")
                    ok_all = False
            except requests.RequestException as exc:
                self._log(f"[send] Loi mang: {exc}")
                ok_all = False
        return ok_all

    # ---------- vòng lặp nhận tin ----------
    def start(self) -> dict:
        """Bật polling thread. Từ chối nếu chưa có token hoặc đang chạy."""
        if self.is_running:
            return {"ok": False, "error": "Bot dang chay roi"}
        check = self.get_me()
        if not check["ok"]:
            return {"ok": False, "error": check["error"]}
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._log("Bot da bat (long-polling)")
        return {"ok": True, "message": f"Bot dang chay (@{check.get('username', '')})"}

    def stop(self) -> dict:
        """Dừng polling thread."""
        if not self.is_running:
            return {"ok": False, "error": "Bot chua chay"}
        self._stop_event.set()
        self._thread.join(timeout=3)
        self._log("Bot da dung")
        return {"ok": True, "message": "Da dung bot"}

    def _poll_loop(self) -> None:
        """
        Vòng lặp getUpdates: nhận tin nhắn text -> phân tích -> reply.

        Logic:
          - Lỗi 409 "webhook is active" -> tự gỡ webhook 1 lần rồi poll tiếp
            (giống Zalo: polling và webhook loại trừ nhau)
          - Lỗi khác -> log + dừng bot
        """
        offset = 0
        webhook_retried = False
        while not self._stop_event.is_set():
            try:
                resp = requests.post(
                    f"{API_BASE}/bot{self._token()}/getUpdates",
                    json={"offset": offset, "timeout": 25},
                    timeout=35,
                ).json()
            except requests.RequestException as exc:
                self._log(f"[poll] Loi mang: {exc} - thu lai 5s")
                time.sleep(5)
                continue
            if not resp.get("ok"):
                description = resp.get("description", "")
                if "webhook" in description.lower() and not webhook_retried:
                    self._log("Webhook dang cai - tu go va tiep tuc polling")
                    requests.post(f"{API_BASE}/bot{self._token()}/deleteWebhook", timeout=15)
                    webhook_retried = True
                    continue
                self._log(f"[poll] Loi API: {description} - dung bot")
                self._stop_event.set()
                break
            webhook_retried = False
            for update in resp.get("result", []):
                offset = update.get("update_id", 0) + 1
                message = update.get("message") or {}
                text = (message.get("text") or "").strip()
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if not text or chat_id is None:
                    continue
                if text.startswith("/"):
                    continue  # bỏ qua lệnh
                # Lưu chat_id tự động để nút "Test" gửi được
                save_config({"telegram": {"chat_id": str(chat_id)}})
                self._log(f"Nhan tu chat {chat_id}: {text[:80]}")
                reply = build_sentiment_reply(text)
                self.send(str(chat_id), reply)
                self._log("Da gui ket qua phan tich cam xuc")
            time.sleep(0.5)
