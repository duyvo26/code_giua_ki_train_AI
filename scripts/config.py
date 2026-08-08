"""
Cấu hình chung cho thực nghiệm Sentiment Analysis tiếng Việt (Chặng 6).

Mọi đường dẫn được tính tương đối từ thư mục gốc của repo
(thư mục chứa `scripts/`), nên code chạy ổn định trên Colab
dù thư mục làm việc hiện tại có khác.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = PROJECT_ROOT / "models"
BEST_MODEL_DIR = MODEL_DIR / "best_model"
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURE_DIR = RESULTS_DIR / "figures"

# --- Mô hình ------------------------------------------------------------
# Mô hình Transformer tiếng Việt được fine-tune lại (Thực nghiệm 3)
TRANSFORMER_MODEL = "vinai/phobert-base-v2"

# Mô hình PhoBERT đã được fine-tune sẵn, dùng làm đối chứng
# (Thực nghiệm 2) - không huấn luyện thêm
PUBLIC_SENTIMENT_MODEL = "wonrax/phobert-base-vietnamese-sentiment"

# --- Nhãn ---------------------------------------------------------------
# 0 = Negative, 1 = Neutral, 2 = Positive
LABEL_NAMES_VI = ["Tiêu cực", "Trung tính", "Tích cực"]
LABEL_NAMES_EN = ["Negative", "Neutral", "Positive"]
LABEL_TO_ID = {"negative": 0, "neutral": 1, "positive": 2}
ID_TO_LABEL = {0: "negative", 1: "neutral", 2: "positive"}

# --- Dữ liệu ------------------------------------------------------------
# UIT-VSFC (Vietnamese Students' Feedback Corpus) - paper KSE 2018
# Đã chia sẵn train/valid/test chính thức theo paper (ti lệ ~80/10/10)
DATA_URLS = {
    "train": (
        "https://huggingface.co/datasets/ura-hcmut/UIT-VSFC/"
        "resolve/main/UIT-VSFC_train.csv"
    ),
    "valid": (
        "https://huggingface.co/datasets/ura-hcmut/UIT-VSFC/"
        "resolve/main/UIT-VSFC_valid.csv"
    ),
    "test": (
        "https://huggingface.co/datasets/ura-hcmut/UIT-VSFC/"
        "resolve/main/UIT-VSFC_test.csv"
    ),
}

# --- Huấn luyện ---------------------------------------------------------
SEED = 42
MAX_LEN = 256
NUM_LABELS = 3
NUM_EPOCHS = 3
LEARNING_RATE = 2e-5
BATCH_SIZE = 16

# --- Hugging Face -------------------------------------------------------
# Token đọc từ biến môi trường HF_TOKEN (KHÔNG ghi token vào code - GitHub
# Push Protection sẽ chặn commit chứa secret). Đặt khi cần tải model gated:
#   export HF_TOKEN=hf_xxx            (Linux/Mac/Colab shell)
#   os.environ["HF_TOKEN"] = "hf_xxx" (trong notebook trước khi chạy pipeline)
# Lưu ý: các model mặc định (phobert-base-v2, wonrax) đều public,
# không cần token - login chỉ là tuỳ chọn.

def hf_login_if_needed() -> None:
    """
    Đăng nhập Hugging Face nếu có biến môi trường HF_TOKEN.

    Logic:
      - Không có HF_TOKEN -> in ghi chú bỏ qua (model public không cần token)
      - Có HF_TOKEN -> login; token lỗi (bị revoke/hết hạn) chỉ cảnh báo,
        không dừng pipeline vì model public vẫn tải được
    """
    import os

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("[hf] Chua co bien env HF_TOKEN - bo qua (model public, khong can token)")
        return
    try:
        from huggingface_hub import login

        login(token=token)
        print("[hf] Da dang nhap Hugging Face (HF_TOKEN)")
    except Exception as exc:  # noqa: BLE001 - login lỗi không chặn pipeline
        print(f"[hf][warn] HF login that bai - tiep tuc voi model public: {exc}")
