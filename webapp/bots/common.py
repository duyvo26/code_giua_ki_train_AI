"""
File: common.py
Chức năng: Hàm dùng chung cho 2 bot: dựng nội dung reply sentiment + chunk text
Vai trò: Util - tách khỏi bot cụ thể để Telegram/Zalo dùng chung logic
File liên quan: webapp/bots/telegram_bot.py, webapp/bots/zalo_bot.py
"""

import threading

# Cache model + tokenizer dùng chung cho bot (tránh load lại mỗi tin nhắn)
_MODEL_CACHE: dict = {}
_MODEL_LOCK = threading.Lock()


def utf16_len(text: str) -> int:
    """Độ dài text tính theo đơn vị UTF-16 (khớp giới hạn ký tự của API)."""
    return len(text.encode("utf-16-le")) // 2


def chunk_text(text: str, max_chars: int) -> list[str]:
    """
    Chia text thành các đoạn ≤ max_chars (theo UTF-16).
    Telegram giới hạn ~4000, Zalo Bot Creator giới hạn 2000 ký tự.

    Logic:
      - Khi 1 chunk đầy, dấu "\n" ngăn cách được đặt vào ĐẦU chunk mới
        (current = "\n" + line) nên nối các chunk lại khớp đúng text gốc
      - Dòng đơn quá dài -> cắt cứng theo nửa max_chars
    """
    if utf16_len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        sep = "\n" if current else ""
        if current and utf16_len(current) + utf16_len(sep + line) > max_chars:
            chunks.append(current)
            current = "\n" + line
        else:
            current += sep + line
        while utf16_len(current) > max_chars:  # dòng đơn quá dài -> cắt cứng
            cut = max_chars // 2
            chunks.append(current[:cut])
            current = current[cut:]
    if current:
        chunks.append(current)
    return chunks


def _get_sentiment_model():
    """
    Tải model fine-tuned 1 lần rồi cache (có lock chống đua thread).

    Logic:
      - Nhiều thread bot cùng gọi predict -> chỉ load model 1 lần
      - Không có model -> trả (None, None), reply sẽ hướng dẫn train trước
    """
    global _MODEL_CACHE
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]
    with _MODEL_LOCK:
        if "model" in _MODEL_CACHE:
            return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]
        try:
            from scripts.finetune import load_sentiment_model

            model, tokenizer = load_sentiment_model()
            _MODEL_CACHE["model"] = model
            _MODEL_CACHE["tokenizer"] = tokenizer
            return model, tokenizer
        except OSError:
            return None, None


def build_sentiment_reply(text: str) -> str:
    """
    Dựng nội dung reply cho 1 bình luận: nhãn chính + xác suất % 3 lớp.

    Logic:
      - Gọi predict_sentiment() (scripts.finetune) - cùng model với web
      - Chưa có model -> trả hướng dẫn train (không crash bot)
    """
    from scripts.finetune import predict_sentiment

    model, tokenizer = _get_sentiment_model()
    if model is None:
        return "Chưa có model sentiment - hãy train trước (web: tab Huấn luyện)."

    result = predict_sentiment(text, model, tokenizer)
    probs = result["probabilities"]
    return "\n".join(
        [
            f"Nhan: {result['sentiment_vi']} (do tin cay {result['confidence'] * 100:.1f}%)",
            f"- Tieu cuc: {probs['Negative'] * 100:.1f}%",
            f"- Trung tinh: {probs['Neutral'] * 100:.1f}%",
            f"- Tich cuc: {probs['Positive'] * 100:.1f}%",
            f"Binh luan: {text[:200]}",
        ]
    )
