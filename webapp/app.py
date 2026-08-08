"""
File: app.py
Chức năng: Flask web demo - thông tin model, train (có log realtime), dự đoán,
           phân tích dữ liệu UIT-VSFC (data gốc, tiền xử lý, mapping nhãn)
Vai trò: Web app - chạy trong Colab, expose qua Cloudflared tunnel; gọi trực tiếp scripts/
File liên quan: webapp/templates/index.html, scripts/finetune.py, scripts/preprocess.py, scripts/config.py
"""

import contextlib
import io
import itertools
import json
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

# Thư mục gốc repo (webapp/ nằm ngay trong repo nên lấy cha của webapp/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config import (  # noqa: E402
    BATCH_SIZE,
    BEST_MODEL_DIR,
    DATA_DIR,
    FIGURE_DIR,
    LABEL_NAMES_EN,
    LABEL_NAMES_VI,
    LABEL_TO_ID,
    LEARNING_RATE,
    MAX_LEN,
    NUM_EPOCHS,
    PROCESSED_DIR,
    RESULTS_DIR,
    SEED,
    TRANSFORMER_MODEL,
)
from scripts.preprocess import clean_dataframe, normalize_text, prepare_dataset  # noqa: E402

# Bots Telegram/Zalo: config + instance dùng chung toàn app
from webapp.bots.config_manager import load_config, public_config, save_config  # noqa: E402
from webapp.bots.telegram_bot import TelegramBot  # noqa: E402
from webapp.bots.zalo_bot import ZaloBot  # noqa: E402

# Trainer v5 yêu cầu callback kế thừa TrainerCallback, nếu không sẽ
# AttributeError on_init_end khi Trainer gọi các hook (lỗi đã gặp khi
# dùng class trần trong nút Train của web)
from transformers import TrainerCallback  # noqa: E402

app = Flask(__name__)

# Trạng thái train toàn cục, web poll /api/train-status mỗi 3 giây
TRAIN_STATE = {"running": False, "done": False, "message": "idle", "epoch": 0}

# Log huấn luyện realtime: deque giữ tối đa 500 dòng, id tăng dần để
# frontend poll /api/train-log?since=<id cuối> chỉ nhận dòng mới
TRAIN_LOG: deque = deque(maxlen=500)
LOG_SEQ = itertools.count(1)

# Log bot (Telegram/Zalo) - mỗi bot 1 deque, poll qua /api/bot/log
BOT_LOGS: dict[str, deque] = {"telegram": deque(maxlen=200), "zalo": deque(maxlen=200)}
BOT_LOG_SEQ = itertools.count(1)


def _bot_log(bot_type: str, message: str) -> None:
    """Callback từ bot thread: thêm dòng vào BOT_LOGS tương ứng."""
    BOT_LOGS.get(bot_type, deque()).append(
        {
            "id": next(BOT_LOG_SEQ),
            "ts": time.strftime("%H:%M:%S"),
            "level": "INFO",
            "msg": message,
        }
    )


telegram_bot = TelegramBot(on_log=_bot_log)
zalo_bot = ZaloBot(on_log=_bot_log)


def _append_log(message: str, level: str = "INFO") -> None:
    """Thêm 1 dòng vào TRAIN_LOG kèm timestamp và mức độ (INFO/EPOCH/ERROR)."""
    TRAIN_LOG.append(
        {
            "id": next(LOG_SEQ),
            "ts": time.strftime("%H:%M:%S"),
            "level": level,
            "msg": message,
        }
    )


class TrainProgressCallback(TrainerCallback):
    """
    Callback Hugging Face Trainer cập nhật epoch vào TRAIN_STATE
    để web hiển thị tiến trình theo thời gian thực.
    """

    def on_epoch_end(self, args, state, control, **kwargs):
        TRAIN_STATE["epoch"] = state.epoch


class LogCaptureCallback(TrainerCallback):
    """
    Callback bắt log của Trainer: mỗi bước log (loss, lr, eval) được
    format thành dòng đưa vào TRAIN_LOG để web hiển thị realtime.
    """

    def on_log(self, args, state, control, logs, **kwargs):
        entry = logs
        if not entry:
            return
        epoch = entry.get("epoch")
        # Phòng trường hợp log entry thiếu key "epoch" -> không format
        # (None:.2f sẽ TypeError làm chết Trainer giữa chừng)
        parts = [f"epoch {epoch:.2f}"] if epoch is not None else []
        for key in ("loss", "learning_rate", "eval_accuracy", "eval_f1_macro"):
            if key in entry and entry[key] is not None:
                parts.append(f"{key}={entry[key]:.4f}" if isinstance(entry[key], float) else f"{key}={entry[key]}")
        _append_log(" ".join(parts), "EPOCH")


class _LogWriter(io.StringIO):
    """
    Bắt print() từ fine_tune()/prepare_dataset() (vd "[finetune] ...",
    "[tokenize] ...") đẩy vào TRAIN_LOG thay vì stdout console.

    Lọc nhiễu:
      - Mã màu ANSI (tqdm dùng \x1b[A để cập nhật progress bar)
      - Dòng progress bar tqdm (chứa "it/s]" hoặc bắt đầu bằng "0%|")
      - Raw dict log của Trainer ('{loss': ...) - đã có dòng format đẹp
        từ LogCaptureCallback nên không cần lặp lại
    """

    ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

    def write(self, text: str) -> int:
        clean = self.ANSI_RE.sub("", text)
        for raw_line in clean.split("\r"):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("{") and line.endswith("}"):
                continue
            if re.match(r"^\s*\d+%\|", line) or "it/s]" in line or "s/it]" in line:
                continue
            _append_log(line, "INFO")
        return len(text)


def _read_json(path: Path) -> dict | None:
    """Đọc file JSON an toàn, trả None nếu không tồn tại hoặc lỗi."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _validate_train_params(data: dict) -> dict:
    """
    Kiểm tra + giới hạn tham số train gửi từ web (tránh giá trị phá huỷ).

    Logic:
      - Thiếu key -> dùng mặc định từ scripts/config.py
      - Giá trị ngoài khoảng cho phép -> kẹp về biên gần nhất
    """

    def clamp(key: str, default: float, lo: float, hi: float, cast=float) -> float:
        try:
            value = cast(data.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(lo, min(hi, value))

    return {
        "epochs": clamp("epochs", NUM_EPOCHS, 1, 10, int),
        "learning_rate": clamp("learning_rate", LEARNING_RATE, 1e-6, 1e-2, float),
        "batch_size": clamp("batch_size", BATCH_SIZE, 2, 64, int),
        "max_len": clamp("max_len", MAX_LEN, 64, 512, int),
        "weight_decay": clamp("weight_decay", 0.01, 0.0, 0.1, float),
        "warmup_ratio": clamp("warmup_ratio", 0.1, 0.0, 0.5, float),
        "seed": clamp("seed", SEED, 0, 2**31 - 1, int),
    }


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


# Mô tả cho tab "API URLs" trên web - nguồn duy nhất cho /api/endpoints
ENDPOINT_DESCRIPTIONS = {
    "/health": "Kiểm tra server sẵn sàng",
    "/api/model-info": "Thông tin model đã train + metrics (Accuracy, F1, Recall Negative)",
    "/api/train-config": "Tham số huấn luyện + kích thước bộ dữ liệu",
    "/api/data-info": "Phân tích dữ liệu UIT-VSFC (data gốc, tiền xử lý, mapping nhãn)",
    "/api/predict": "Dự đoán cảm xúc 1 bình luận (POST {\"text\": \"...\"})",
    "/api/train": "Bắt đầu train lại với tham số tuỳ chỉnh (POST)",
    "/api/train-status": "Trạng thái huấn luyện - frontend poll",
    "/api/train-log": "Log huấn luyện tăng dần (GET ?since=N)",
    "/api/endpoints": "Danh sách API của hệ thống",
}


@app.get("/api/endpoints")
def endpoints():
    """
    Danh sách API của hệ thống - tự sinh từ app.url_map nên không bao giờ
    lệch với route thật, kèm mô tả từ ENDPOINT_DESCRIPTIONS.
    """
    items = []
    for rule in app.url_map.iter_rules():
        if rule.rule == "/health" or rule.rule.startswith("/api"):
            methods = sorted(m for m in rule.methods if m in ("GET", "POST"))
            items.append(
                {
                    "path": rule.rule,
                    "methods": methods,
                    "description": ENDPOINT_DESCRIPTIONS.get(rule.rule, ""),
                }
            )
    return jsonify({"endpoints": items})


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


@app.get("/api/train-config")
def train_config():
    """
    Tham số huấn luyện + kích thước bộ dữ liệu.
    Trả về cấu hình từ scripts/config.py (nguồn duy nhất, không hardcode
    lại trong web) và số dòng thực tế từ data/processed/*.csv.
    """
    sizes = {}
    for split in ("train", "valid", "test"):
        path = PROCESSED_DIR / f"{split}.csv"
        if path.exists():
            sizes[split] = len(pd.read_csv(path))
        else:
            sizes[split] = None

    return jsonify(
        {
            "model": TRANSFORMER_MODEL,
            "num_labels": 3,
            "epochs": NUM_EPOCHS,
            "learning_rate": LEARNING_RATE,
            "batch_size": BATCH_SIZE,
            "max_len": MAX_LEN,
            "warmup_ratio": 0.1,
            "weight_decay": 0.01,
            "optimizer": "AdamW (Hugging Face default)",
            "fp16": True,
            "seed": SEED,
            "dataset_sizes": sizes,
        }
    )


# Cache tokenizer + thống kê token (lazy, tính 1 lần) - tránh tải lại mỗi poll
_TOKENIZER_CACHE = None
_TOKEN_STATS_CACHE = None


def _tokenization_info() -> dict | None:
    """
    Thông tin Bước 4 (Tokenization) cho web: tokenizer PhoBERT, vocab size,
    thống kê token trên 300 câu mẫu + 1 ví dụ text -> tokens -> input_ids/mask.

    Logic:
      - Tải AutoTokenizer của đúng model dùng fine-tune (phobert-base-v2)
      - Chỉ tokenize 300 câu mẫu để API không bị treo; kết quả cache
      - Lỗi tải tokenizer -> trả None (web hiển thị ghi chú, không vỡ)
    """
    global _TOKENIZER_CACHE, _TOKEN_STATS_CACHE
    if not (PROCESSED_DIR / "train.csv").exists():
        return None
    if _TOKENIZER_CACHE is None:
        try:
            from transformers import AutoTokenizer

            _TOKENIZER_CACHE = AutoTokenizer.from_pretrained(TRANSFORMER_MODEL)
        except Exception as exc:  # noqa: BLE001 - không có mạng/model -> bỏ qua
            print(f"[data-info][warn] Khong tai duoc tokenizer: {exc}")
            return None
    tokenizer = _TOKENIZER_CACHE

    if _TOKEN_STATS_CACHE is None:
        df = pd.read_csv(PROCESSED_DIR / "train.csv").head(300)
        lengths = [len(tokenizer.encode(str(t))) for t in df["text_clean"]]
        _TOKEN_STATS_CACHE = {
            "mean": round(float(np.mean(lengths)), 2),
            "median": int(np.median(lengths)),
            "max": int(np.max(lengths)),
            "n_samples": len(lengths),
        }

    raw_text = str(pd.read_csv(DATA_DIR / "uit_vsfc_train.csv")["text"].iloc[0])
    enc = tokenizer(raw_text)
    input_ids = enc["input_ids"]
    return {
        "tokenizer": TRANSFORMER_MODEL,
        "vocab_size": int(getattr(tokenizer, "vocab_size", 0) or len(tokenizer)),
        "model_max_len": MAX_LEN,
        "steps": [
            "Text → Tokens (BPE của PhoBERT)",
            "Thêm special tokens: [CLS] ... [SEP]",
            "Token → input_ids (số nguyên)",
            "Tạo attention_mask (1 = token thật, 0 = padding)",
        ],
        "stats": _TOKEN_STATS_CACHE,
        "examples": [
            {
                "text": raw_text,
                "tokens": tokenizer.convert_ids_to_tokens(input_ids),
                "input_ids": input_ids,
                "attention_mask": enc.get(
                    "attention_mask", [1] * len(input_ids)
                ),
            }
        ],
    }


@app.get("/api/data-info")
def data_info():
    """
    Phân tích dữ liệu UIT-VSFC: data gốc, tiền xử lý, label mapping.

    Logic:
      - Đọc 3 CSV raw (data/uit_vsfc_*.csv) + processed (data/processed/*.csv)
      - Chạy LẠI đúng clean_dataframe()/normalize_text() của pipeline để số
        liệu web khớp 100% với báo cáo (không duplicate logic riêng)
      - Trả: thống kê làm sạch từng split, phân bố nhãn, mapping 3 lớp,
        ví dụ before/after chuẩn hoá từ dữ liệu thật
    """
    raw_files = {s: DATA_DIR / f"uit_vsfc_{s}.csv" for s in ("train", "valid", "test")}
    if not all(p.exists() for p in raw_files.values()):
        return jsonify(
            {
                "exists": False,
                "note": "Chưa có dữ liệu UIT-VSFC - hãy chạy pipeline (hoặc nút Train) trước.",
            }
        )

    raw = {s: pd.read_csv(p) for s, p in raw_files.items()}

    stats = {}
    for s, df in raw.items():
        _, st = clean_dataframe(df)
        stats[s] = st

    # Ví dụ before/after: 4 dòng đầu của train (raw -> sau normalize_text)
    samples = []
    for _, row in raw["train"].head(4).iterrows():
        samples.append({"raw": str(row["text"]), "clean": normalize_text(str(row["text"]))})

    # Mapping nhãn: negative -> 0 -> Tiêu cực ...
    mapping = [
        {
            "label": label,
            "id": label_id,
            "en": LABEL_NAMES_EN[label_id],
            "vi": LABEL_NAMES_VI[label_id],
        }
        for label, label_id in LABEL_TO_ID.items()
    ]

    # Phân bố nhãn theo split (count + %)
    distribution = {}
    for s in ("train", "valid", "test"):
        dist = stats[s]["phan_bo_lop"]
        total = stats[s]["so_dong_con_lai"] or 1
        distribution[s] = [
            {
                "id": label_id,
                "vi": LABEL_NAMES_VI[label_id],
                "en": LABEL_NAMES_EN[label_id],
                "count": dist.get(label_id, 0),
                "pct": round(dist.get(label_id, 0) / total * 100, 2),
            }
            for label_id in (0, 1, 2)
        ]

    # Bước 5 - Chia dữ liệu: % mỗi split so với tổng sau làm sạch
    total_clean = sum(stats[s]["so_dong_con_lai"] for s in stats) or 1
    split = {
        s: {
            "rows": stats[s]["so_dong_con_lai"],
            "pct": round(stats[s]["so_dong_con_lai"] / total_clean * 100, 1),
        }
        for s in ("train", "valid", "test")
    }

    return jsonify(
        {
            "exists": True,
            "columns": list(raw["train"].columns),
            "stats": stats,
            "samples": samples,
            "mapping": mapping,
            "distribution": distribution,
            "split": split,
            "tokenization": _tokenization_info(),
            "preprocess_steps": [
                "Sửa lỗi encoding (latin-1 -> utf-8)",
                "Gộp nhiều khoảng trắng/tab/xuống dòng thành 1",
                "Bỏ khoảng trắng thừa quanh dấu câu",
                "Chuẩn hoá lowercase (không xoá dấu tiếng Việt)",
                "Loại bỏ dòng rỗng, duplicate, nhãn không hợp lệ",
                "KHÔNG xoá stopword - Transformer cần ngữ cảnh toàn câu",
            ],
        }
    )


@app.get("/figures/<path:filename>")
def figure_file(filename: str):
    """
    Serve ảnh PNG từ results/figures cho web (learning curve, CM, PR curve).

    Bảo mật: resolve() tuyệt đối rồi kiểm tra nằm trong FIGURE_DIR -
    chặn path traversal (../).
    """
    base = FIGURE_DIR.resolve()
    target = (base / filename).resolve()
    if not target.is_file() or base not in target.parents:
        return jsonify({"error": "Khong tim thay figure"}), 404
    return send_file(str(target), mimetype="image/png")


@app.get("/api/figures")
def figures():
    """Danh sách biểu đồ PNG đã sinh (results/figures/*.png)."""
    if not FIGURE_DIR.exists():
        return jsonify({"figures": []})
    files = sorted(p.name for p in FIGURE_DIR.glob("*.png"))
    return jsonify({"figures": files})


@app.get("/api/compare")
def compare():
    """
    Bảng so sánh 3 mô hình từ results/compare_table.json (sinh bởi
    scripts/run_pipeline.py). Chưa có -> exists=false, web hiển thị ghi chú.
    """
    data = _read_json(RESULTS_DIR / "compare_table.json")
    return jsonify({"exists": data is not None, "rows": data or []})


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
      - Nhận tham số tuỳ chỉnh {epochs, learning_rate, batch_size, max_len,
        weight_decay, warmup_ratio, seed} -> validate -> truyền vào fine_tune()
      - Thread nền gọi prepare_dataset() (cache CSV nhanh) + fine_tune()
      - TRAIN_STATE + TRAIN_LOG cập nhật realtime để frontend poll
    """
    if TRAIN_STATE["running"]:
        return jsonify({"error": "Mô hình đang được huấn luyện, vui lòng chờ"}), 409

    data = request.get_json(silent=True) or {}
    params = _validate_train_params(data)
    TRAIN_STATE["params"] = params

    def _run_train():
        TRAIN_STATE.update(running=True, done=False, message="preparing", epoch=0)
        param_line = ", ".join(f"{k}={v}" for k, v in params.items())
        _append_log(f"=== BAT DAU HUAN LUYEN | {param_line} ===", "EPOCH")
        try:
            from scripts.evaluate import (
                evaluate_transformer,
                print_metrics_table,
                save_confusion_matrix,
                save_learning_curve,
                save_metrics_json,
                save_pr_curve,
            )
            from scripts.finetune import fine_tune, load_sentiment_model

            # Bắt print() của pipeline -> TRAIN_LOG (web hiển thị realtime)
            writer = _LogWriter()
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                splits, _ = prepare_dataset()
                _append_log("[phase] Tien xu ly du lieu xong - tokenize & fine-tune...", "EPOCH")
                trainer = fine_tune(
                    splits,
                    num_epochs=params["epochs"],
                    learning_rate=params["learning_rate"],
                    batch_size=params["batch_size"],
                    max_len=params["max_len"],
                    weight_decay=params["weight_decay"],
                    warmup_ratio=params["warmup_ratio"],
                    seed=params["seed"],
                    callbacks=[TrainProgressCallback(), LogCaptureCallback()],
                )
                # Biểu đồ hội tụ (train loss + eval F1 theo epoch)
                save_learning_curve(trainer)
                # Đánh giá ngay trên test -> sinh metrics JSON + CM + PR curve
                # (giống run_pipeline.py, để KPI/model-info/tab Model hiển thị đúng)
                _append_log("[phase] Danh gia tren tap test...", "EPOCH")
                model, tokenizer = load_sentiment_model()
                metrics, y_true, y_pred, proba = evaluate_transformer(
                    model,
                    tokenizer,
                    splits["test"],
                    model_name="PhoBERT-base-v2 (fine-tuned)",
                )
                print_metrics_table(metrics)
                save_confusion_matrix(
                    y_true, y_pred, "phobert_finetuned",
                    "Confusion Matrix - PhoBERT-base-v2 fine-tuned",
                )
                save_pr_curve(
                    y_true, proba, "phobert_finetuned",
                    "Precision-Recall - PhoBERT-base-v2 fine-tuned",
                )
                save_metrics_json(metrics, "phobert_finetuned")
            TRAIN_STATE.update(running=False, done=True, message="done")
            _append_log("=== HOAN TAT - model da luu tai models/best_model ===", "EPOCH")
        except Exception as exc:  # noqa: BLE001 - lỗi nền cần báo về web
            TRAIN_STATE.update(running=False, done=False, message=f"error: {exc}")
            _append_log(f"LOI: {exc}", "ERROR")

    threading.Thread(target=_run_train, daemon=True).start()
    return jsonify({"started": True, "note": "Training chạy nền, thời gian ~15-20 phút"})


@app.get("/api/train-status")
def train_status():
    """
    Trạng thái huấn luyện - frontend poll mỗi 3 giây.

    Logic:
      - total_epochs lấy từ params đã chọn khi bấm Train (không hardcode 3)
        để progress bar + dòng "epoch x / N" hiển thị đúng số epochs người dùng nhập
    """
    return jsonify(
        {
            **TRAIN_STATE,
            "total_epochs": TRAIN_STATE.get("params", {}).get("epochs", 3),
        }
    )


@app.get("/api/train-log")
def train_log():
    """
    Log huấn luyện tăng dần: trả các dòng có id > since.

    Logic:
      - since = id dòng cuối mà frontend đã nhận -> chỉ gửi dòng mới,
        tránh gửi lại toàn bộ 500 dòng mỗi lần poll (2s)
    """
    since = request.args.get("since", 0, type=int)
    lines = [line for line in TRAIN_LOG if line["id"] > since]
    return jsonify(
        {
            "lines": lines,
            "epoch": TRAIN_STATE["epoch"],
            "running": TRAIN_STATE["running"],
        }
    )


# =====================================================================
# Bots Telegram & Zalo
# =====================================================================

_BOT_INSTANCES = {
    "telegram": telegram_bot,
    "zalo": zalo_bot,
}


def _resolve_bot(bot_type: str):
    """Lấy instance bot theo loại (telegram/zalo) hoặc trả None."""
    return _BOT_INSTANCES.get(bot_type)


@app.get("/api/bot/config")
def bot_config():
    """
    Config bot an toàn: token được che (4 ký tự đầu + cuối),
    các trường còn lại (chat_id, api_base) gửi thật để điền form.
    """
    return jsonify(public_config())


@app.post("/api/bot/config")
def bot_config_save():
    """
    Lưu config bot: merge từng trường, token trống KHÔNG ghi đè.
    Nếu bot đang chạy -> dừng để áp dụng cấu hình mới (polling đọc token
    từ config mỗi vòng nên chỉ cần chặn vòng hiện tại).
    """
    data = request.get_json(silent=True) or {}
    save_config(data)
    notes = []
    for bot_type, bot in _BOT_INSTANCES.items():
        if bot.is_running and bot_type in data:
            bot.stop()
            notes.append(f"Bot {bot_type} da dung de ap dung cau hinh - bam Bat de chay lai")
    return jsonify({"ok": True, "config": public_config(), "notes": notes})


@app.post("/api/bot/test")
def bot_test():
    """
    Test bot: validate token (getMe) + gửi câu mẫu "Sản phẩm rất tệ!"
    tới chat_id đã lưu (nếu có). Trả kết quả chi tiết cho web.
    """
    bot_type = (request.get_json(silent=True) or {}).get("type", "")
    bot = _resolve_bot(bot_type)
    if bot is None:
        return jsonify({"ok": False, "error": "Loai bot khong hop le"}), 400

    check = bot.get_me()
    if not check["ok"]:
        return jsonify({"ok": False, "error": check["error"]})

    cfg = load_config()[bot_type]
    chat_id = str(cfg.get("chat_id") or "").strip()
    if not chat_id:
        return jsonify(
            {
                "ok": False,
                "error": "Token hop le nhung chua co chat_id - hay nhac tin cho bot truoc, "
                         "hoac nhap chat_id vao o cau hinh",
            }
        )

    test_text = "Sản phẩm rất tệ!"
    sent = bot.send(chat_id, f"[TEST] Binh luan: {test_text}")
    if not sent:
        return jsonify({"ok": False, "error": "Gui tin nhan test that bai - xem log bot"})
    return jsonify(
        {
            "ok": True,
            "message": f"Token hop le ({check}) va da gui tin test toi chat {chat_id}",
        }
    )


@app.post("/api/bot/start")
def bot_start():
    """Bật polling của bot theo loại (telegram/zalo)."""
    bot_type = (request.get_json(silent=True) or {}).get("type", "")
    bot = _resolve_bot(bot_type)
    if bot is None:
        return jsonify({"ok": False, "error": "Loai bot khong hop le"}), 400
    result = bot.start()
    return jsonify(result), (200 if result["ok"] else 400)


@app.post("/api/bot/stop")
def bot_stop():
    """Dừng polling của bot theo loại."""
    bot_type = (request.get_json(silent=True) or {}).get("type", "")
    bot = _resolve_bot(bot_type)
    if bot is None:
        return jsonify({"ok": False, "error": "Loai bot khong hop le"}), 400
    result = bot.stop()
    return jsonify(result), (200 if result["ok"] else 400)


@app.get("/api/bot/status")
def bot_status():
    """Trạng thái 2 bot: đang chạy?, có token?, chat_id, id log cuối."""
    status = {}
    for bot_type, bot in _BOT_INSTANCES.items():
        cfg = load_config()[bot_type]
        status[bot_type] = {
            "running": bot.is_running,
            "has_token": bool(cfg.get("token", "").strip()),
            "chat_id": cfg.get("chat_id", ""),
        }
    return jsonify(status)


@app.get("/api/bot/log")
def bot_log():
    """Log bot tăng dần theo since (poll 2s, giống /api/train-log)."""
    bot_type = request.args.get("type", "")
    since = request.args.get("since", 0, type=int)
    log = BOT_LOGS.get(bot_type)
    if log is None:
        return jsonify({"lines": []})
    return jsonify({"lines": [line for line in log if line["id"] > since]})


if __name__ == "__main__":
    # Chạy trực tiếp (không qua Colab): python webapp/app.py
    app.run(host="0.0.0.0", port=8080, debug=False)
