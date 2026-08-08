"""
File: sentiment_service.py
Chức năng: Tải mô hình PhoBERT fine-tuned và thực hiện dự báo cảm xúc
Vai trò: Service - chứa toàn bộ logic AI (inference), router chỉ gọi vào đây
File liên quan: app/routers/sentiment_router.py, app/config.py, models/best_model
"""

from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

LABEL_NAMES_EN = ["Negative", "Neutral", "Positive"]
LABEL_NAMES_VI = ["Tiêu cực", "Trung tính", "Tích cực"]


class ModelNotFoundError(Exception):
    """Ngoại lệ khi thư mục mô hình chưa tồn tại hoặc chưa được fine-tune."""


class SentimentService:
    """
    Dịch vụ phân loại cảm xúc: khởi tạo model 1 lần, dự báo nhiều lần.

    Điểm bảo mật: tokenizer + model + inference chạy 100% cục bộ trên
    server nội bộ - dữ liệu bình luận khách hàng không gửi ra API ngoài.
    """

    def __init__(self, model_path: Path | None = None):
        """
        Logic:
          - model_path lấy từ settings.MODEL_PATH (config từ .env)
          - model/tokenizer được tải lười: chỉ tải khi load() được gọi
        """
        self.model_path = model_path or settings.model_path_resolved
        self._model = None
        self._tokenizer = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load(self) -> None:
        """
        Tải model + tokenizer từ models/best_model vào bộ nhớ.
        Nếu thư mục chưa tồn tại (chưa fine-tune), ném ModelNotFoundError
        kèm hướng dẫn chạy notebook Colab.
        """
        if self._model is not None:
            return
        if not self.model_path.exists():
            raise ModelNotFoundError(
                f"Khong tim thay mo hinh tai {self.model_path}. "
                "Hay chay fine-tune tren Colab (sentiment_colab.ipynb) "
                "roi dua models/best_model ve thu muc du an."
            )
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self._model.to(self._device)
        self._model.eval()
        logger.info("Da tai mo hinh tu %s (device: %s)", self.model_path, self._device)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def predict(self, text: str) -> dict:
        """
        Dự báo cảm xúc 1 bình luận: trả nhãn + xác suất % 3 lớp.

        Logic:
          - Tokenizer chuyển text thành input_ids (Bước 4 của pipeline)
          - model chạy forward -> logits -> softmax -> xác suất
          - pred_id là chỉ số xác suất cao nhất, map sang tên nhãn
        """
        self.load()
        encodings = self._tokenizer(
            text,
            truncation=True,
            max_length=settings.MAX_SEQ_LEN,
            return_tensors="pt",
        ).to(self._device)

        with torch.no_grad():
            logits = self._model(**encodings).logits
            probs = torch.softmax(logits, dim=-1)[0]

        pred_id = int(probs.argmax().item())
        return {
            "text": text,
            "sentiment": LABEL_NAMES_EN[pred_id],
            "sentiment_vi": LABEL_NAMES_VI[pred_id],
            "confidence": float(probs[pred_id].item()),
            "probabilities": {
                name_en: float(probs[i].item())
                for i, name_en in enumerate(LABEL_NAMES_EN)
            },
        }


sentiment_service = SentimentService()
