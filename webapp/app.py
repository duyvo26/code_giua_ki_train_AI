"""
File: app.py
Chức năng: Flask web demo - xem thông tin model, train lại, dự đoán cảm xúc
Vai trò: Web app - chạy trong Colab, expose qua Cloudflared tunnel; gọi trực tiếp scripts/
File liên quan: webapp/templates/index.html, scripts/finetune.py, scripts/preprocess.py
"""

import json
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Thư mục gốc repo (webapp/ nằm ngay trong repo nên lấy cha của webapp/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config import (  # noqa: E402
    BEST_MODEL_DIR,
    LABEL_NAMES_EN,
    LABEL_NAMES_VI,
    RESULTS_DIR,
)
from scripts.preprocess import prepare_dataset  # noqa: E402

# Trainer v5 yêu cầu callback kế thừa TrainerCallback, nếu không sẽ
# AttributeError on_init_end khi Trainer gọi các hook (lỗi đã gặp khi
# dùng class trần trong nút Train của web)
from transformers import TrainerCallback  # noqa: E402

app = Flask(__name__)

# Trạng thái train toàn cục, web poll /api/train-status mỗi 3 giây
TRAIN_STATE = {"running": False, "done": False, "message": "idle", "epoch": 0}


class TrainProgressCallback(TrainerCallback):
    """
    Callback Hugging Face Trainer cập nhật epoch vào TRAIN_STATE
    để web hiển thị tiến trình theo thời gian thực.
    """

    def on_epoch_end(self, args, state, control, **kwargs):
        TRAIN_STATE["epoch"] = state.epoch


def _read_json(path: Path) -> dict | None:
    """Đọc file JSON an toàn, trả None nếu không tồn tại hoặc lỗi."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@app.get("/")
def index():
    """Trang chủ: render giao diện Tailwind."""
    return render_template("index.html")


@app.get("/health")
def health():
    """
    Kiểm tra server sẵn sàng (dùng cho run_web.py chờ Flask khởi động
    và cho dashboard giám sát nội bộ).
    """
    return jsonify({"status": "ok", "model_loaded": (BEST_MODEL_DIR / "config.json").exists()})


@app.get("/api/model-info")
def model_info():
    """
    Thông tin model đã train: đọc config của PhoBERT fine-tuned + metrics.

    Logic:
      - models/best_model/config.json -> loại model gốc, số nhãn, id2label
      - results/metrics_phobert_finetuned.json -> accuracy, F1, recall Negative
      - Chưa có model -> trả exists=false để UI hiện nút Train
    """
    config = _read_json(BEST_MODEL_DIR / "config.json")
    metrics = _read_json(RESULTS_DIR / "metrics_phobert_finetuned.json")

    info = {"exists": config is not None, "model": None, "metrics": metrics}
    if config is not None:
        info["model"] = {
            "model_type": config.get("model_type", "unknown"),
            "num_labels": config.get("num_labels", 3),
            "id2label": config.get("id2label", {}),
            "path": str(BEST_MODEL_DIR),
        }
    return jsonify(info)


@app.post("/api/predict")
def predict():
    """
    Dự đoán cảm xúc 1 bình luận.

    Logic:
      - Nhận JSON {text} từ frontend
      - Gọi predict_sentiment() (scripts.finetune) -> nhãn + xác suất 3 lớp
      - Lỗi thiếu model -> trả 500 kèm hướng dẫn train trước
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Vui lòng nhập bình luận"}), 400

    try:
        from scripts.finetune import load_sentiment_model, predict_sentiment

        model, tokenizer = load_sentiment_model()
        result = predict_sentiment(text, model, tokenizer)
        # Map sang tên tiếng Việt để UI hiển thị trực tiếp
        result["probabilities_vi"] = {
            name_vi: result["probabilities"][name_en]
            for name_en, name_vi in zip(LABEL_NAMES_EN, LABEL_NAMES_VI)
        }
        return jsonify(result)
    except OSError as exc:
        return jsonify({"error": f"Chưa có model: {exc}. Hãy bấm Train trước."}), 500


@app.post("/api/train")
def train():
    """
    Train lại mô hình PhoBERT trong thread nền, web không bị treo.

    Logic:
      - Nếu đang train -> từ chối (409)
      - Thread nền gọi prepare_dataset() (cache CSV nhanh) + fine_tune()
      - TRAIN_STATE cập nhật running/done/epoch để frontend poll
    """
    if TRAIN_STATE["running"]:
        return jsonify({"error": "Mô hình đang được huấn luyện, vui lòng chờ"}), 409

    def _run_train():
        TRAIN_STATE.update(running=True, done=False, message="preparing", epoch=0)
        try:
            splits, _ = prepare_dataset()
            from scripts.finetune import fine_tune

            # Callback cập nhật epoch vào TRAIN_STATE để web hiển thị tiến trình
            fine_tune(splits, callbacks=[TrainProgressCallback()])
            TRAIN_STATE.update(running=False, done=True, message="done")
        except Exception as exc:  # noqa: BLE001 - lỗi nền cần báo về web
            TRAIN_STATE.update(running=False, done=False, message=f"error: {exc}")

    threading.Thread(target=_run_train, daemon=True).start()
    return jsonify({"started": True, "note": "Training chạy nền, thời gian ~15-20 phút"})


@app.get("/api/train-status")
def train_status():
    """Trạng thái huấn luyện - frontend poll mỗi 3 giây."""
    return jsonify(TRAIN_STATE)


if __name__ == "__main__":
    # Chạy trực tiếp (không qua Colab): python webapp/app.py
    app.run(host="0.0.0.0", port=8080, debug=False)
