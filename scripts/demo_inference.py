"""
File: demo_inference.py
Chức năng: Demo dự báo cảm xúc với các câu bình luận mẫu (Bước 9 - Inference)
Vai trò: Demo - in xác suất % 3 lớp cho "Sản phẩm rất tệ!" và các câu mẫu
File liên quan: scripts/finetune.py, models/best_model

Cách dùng:
    python scripts/demo_inference.py
"""

import sys
from pathlib import Path

# Bootstrap: đảm bảo thư mục gốc repo nằm trong sys.path để import scripts.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EXAMPLES = [
    "Sản phẩm rất tệ!",
    "Sản phẩm rất tốt, giao hàng nhanh",
    "Chất lượng tạm được",
    "Giảng viên nhiệt tình, giảng bài dễ hiểu",
    "Sản phẩm tệ, dùng 2 ngày đã hỏng, không đáng tiền",
]


def main() -> None:
    """
    Demo inference: tải model fine-tuned và dự báo 5 câu mẫu.

    Logic:
      - load_sentiment_model() đọc model từ models/best_model (cục bộ)
      - predict_sentiment() tokenize -> forward -> softmax -> nhãn + xác suất
      - Thiếu model -> hướng dẫn chạy run_pipeline.py trước
    """
    from scripts.finetune import load_sentiment_model, predict_sentiment

    try:
        model, tokenizer = load_sentiment_model()
    except OSError as exc:
        print(f"Chua co model: {exc}")
        print("Hay chay truoc: python scripts/run_pipeline.py")
        return

    for text in EXAMPLES:
        result = predict_sentiment(text, model, tokenizer)
        probs = " | ".join(
            f"{k}: {v * 100:.1f}%" for k, v in result["probabilities"].items()
        )
        print(f"Cau: {text}")
        print(f"  -> {result['sentiment']} ({result['sentiment_vi']})"
              f" | do tin cay: {result['confidence'] * 100:.1f}%")
        print(f"     {probs}\n")


if __name__ == "__main__":
    main()
