"""
Thực nghiệm 3 - Fine-tuning PhoBERT-base-v2 trên dữ liệu UIT-VSFC.

Quy trình:
1. Tải tokenizer + mô hình pretrained `vinai/phobert-base-v2`.
2. Gắn classification head 3 lớp (Negative/Neutral/Positive).
3. Tokenize: text -> input_ids + attention_mask.
4. Huấn luyện bằng Trainer (Cross-Entropy, FP16 trên GPU).
5. Lưu mô hình tốt nhất về models/best_model (server nội bộ).
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

from .config import (
    BATCH_SIZE,
    BEST_MODEL_DIR,
    LEARNING_RATE,
    MAX_LEN,
    MODEL_DIR,
    NUM_EPOCHS,
    SEED,
    TRANSFORMER_MODEL,
)

MODEL_NAME = "PhoBERT-base-v2 (fine-tuned)"


class SentimentDataset(Dataset):
    """Dataset PyTorch: chứa sẵn input_ids, attention_mask, label."""

    def __init__(self, encodings: dict, labels: np.ndarray):
        self.encodings = encodings
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int):
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item


def build_datasets(
    splits: dict[str, pd.DataFrame],
    tokenizer,
    max_len: int = MAX_LEN,
) -> dict[str, SentimentDataset]:
    """Tokenize 3 split -> Dataset PyTorch (text -> input_ids)."""
    torch_datasets: dict[str, SentimentDataset] = {}
    for name, df in splits.items():
        encodings = tokenizer(
            df["text_clean"].tolist(),
            truncation=True,
            padding=False,
            max_length=max_len,
        )
        torch_datasets[name] = SentimentDataset(encodings, df["label_id"].to_numpy())
        print(f"[tokenize] {name}: {len(torch_datasets[name])} mẫu")
    return torch_datasets


def compute_metrics_fn(eval_pred) -> dict:
    """Hàm đánh giá trong quá trình fine-tune (dùng để chọn checkpoint tốt nhất)."""
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy_score(labels, preds),
        "f1_macro": f1_score(labels, preds, average="macro"),
    }


def fine_tune(
    splits: dict[str, pd.DataFrame],
    model_name: str = TRANSFORMER_MODEL,
    output_dir: str | Path = BEST_MODEL_DIR,
    num_epochs: int = NUM_EPOCHS,
    learning_rate: float = LEARNING_RATE,
    batch_size: int = BATCH_SIZE,
    weight_decay: float = 0.01,
    warmup_ratio: float = 0.1,
    seed: int = SEED,
    max_len: int = MAX_LEN,
    callbacks: list | None = None,
) -> Trainer:
    """
    Fine-tune PhoBERT trên train, tối ưu theo F1-macro trên valid,
    trả về Trainer đã huấn luyện xong.

    Args:
        weight_decay (float): hệ số giảm trọng số (weight decay) của AdamW
        warmup_ratio (float): tỷ lệ số bước warmup trên tổng số bước
            (web cho phép người dùng chỉnh trước khi bấm Train)
        callbacks (list | None): danh sách TrainerCallback bổ sung
            (ví dụ: callback cập nhật tiến trình epoch cho web Flask)
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    output_dir = Path(output_dir)
    ckpt_dir = output_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    print(f"[finetune] Tải pretrained: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=3,
        ignore_mismatched_sizes=True,
    )

    datasets = build_datasets(splits, tokenizer, max_len=max_len)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # Warmup theo tỷ lệ người dùng chọn (transformers v5 bỏ warmup_ratio)
    num_train_steps = int(np.ceil(len(datasets["train"]) / batch_size)) * num_epochs
    warmup_steps = int(warmup_ratio * num_train_steps)

    use_fp16 = torch.cuda.is_available()
    training_args = TrainingArguments(
        output_dir=str(ckpt_dir),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        warmup_steps=warmup_steps,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1_macro",
        greater_is_better=True,
        save_total_limit=2,
        logging_steps=50,
        fp16=use_fp16,
        seed=seed,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=datasets["train"],
        eval_dataset=datasets["valid"],
        data_collator=data_collator,
        compute_metrics=compute_metrics_fn,
        callbacks=callbacks,
    )

    print("[finetune] Bắt đầu huấn luyện trên GPU..." if use_fp16
          else "[finetune] Bắt đầu huấn luyện trên CPU...")
    t0 = time.time()
    trainer.train()
    print(f"[finetune] Xong. Thời gian: {time.time() - t0:.1f}s")

    # Lưu mô hình tốt nhất (load_best_model_at_end) về models/best_model
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[finetune] Đã lưu mô hình tốt nhất: {output_dir}")
    return trainer


def load_sentiment_model(
    model_dir: str | Path = BEST_MODEL_DIR,
):
    """Tải mô hình đã fine-tune từ thư mục cục bộ (cho inference / FastAPI)."""
    model_dir = Path(model_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    return model, tokenizer


def predict_sentiment(
    text: str,
    model,
    tokenizer,
    max_len: int = MAX_LEN,
) -> dict:
    """
    Dự báo cảm xúc cho 1 câu: trả về nhãn + xác suất % 3 lớp.
    Ví dụ: "Sản phẩm rất tệ!" -> Negative 98.7%, ...
    """
    from .config import LABEL_NAMES_EN, LABEL_NAMES_VI

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    enc = tokenizer(
        text,
        truncation=True,
        max_length=max_len,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        logits = model(**enc).logits
        probs = torch.softmax(logits, dim=-1)[0]

    pred_id = int(probs.argmax().item())
    probabilities = {
        name_en: float(probs[i].item())
        for i, name_en in enumerate(LABEL_NAMES_EN)
    }
    return {
        "text": text,
        "sentiment": LABEL_NAMES_EN[pred_id],
        "sentiment_vi": LABEL_NAMES_VI[pred_id],
        "confidence": float(probs[pred_id].item()),
        "probabilities": probabilities,
    }
