"""
Bước 7: Đánh giá mô hình.

- Accuracy, Precision, Recall, F1 theo từng lớp + macro/weighted.
- Confusion Matrix, Precision-Recall Curve (One-vs-Rest, nhấn mạnh lớp Negative).
- Lưu kết quả JSON + bảng so sánh các mô hình dạng Markdown.
- Hàm đánh giá Transformer trên tập test dùng chung cho Thực nghiệm 2 và 3.
"""

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    precision_recall_fscore_support,
)

from .config import FIGURE_DIR, LABEL_NAMES_EN, LABEL_NAMES_VI, RESULTS_DIR

CLASSES = [0, 1, 2]


def _ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str = "model",
    train_time: float = 0.0,
) -> dict:
    """
    Tính đầy đủ các chỉ số đánh giá. Recall lớp Negative (index 0)
    là chỉ số quan trọng nhất cho bài toán phát hiện phàn nàn khách hàng.
    """
    accuracy = float(accuracy_score(y_true, y_pred))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=CLASSES, average=None, zero_division=0
    )
    macro = precision_recall_fscore_support(
        y_true, y_pred, labels=CLASSES, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        y_true, y_pred, labels=CLASSES, average="weighted", zero_division=0
    )

    metrics = {
        "model": model_name,
        "accuracy": accuracy,
        "precision": {str(c): float(p) for c, p in zip(CLASSES, precision)},
        "recall": {str(c): float(r) for c, r in zip(CLASSES, recall)},
        "f1": {str(c): float(f) for c, f in zip(CLASSES, f1)},
        "support": {str(c): int(s) for c, s in zip(CLASSES, support)},
        "precision_macro": float(macro[0]),
        "recall_macro": float(macro[1]),
        "f1_macro": float(macro[2]),
        "precision_weighted": float(weighted[0]),
        "recall_weighted": float(weighted[1]),
        "f1_weighted": float(weighted[2]),
        # Chỉ số kinh doanh quan trọng: trong các bình luận tiêu cực thật,
        # mô hình phát hiện được bao nhiêu phần trăm.
        "negative_recall": float(recall[0]),
        "train_time_seconds": float(train_time),
    }
    return metrics


def print_metrics_table(metrics: dict) -> None:
    """In bảng chỉ số theo từng lớp (vi, en)."""
    print(f"\n=== {metrics['model']} ===")
    print(f"Accuracy: {metrics['accuracy']:.4f} | "
          f"Macro P/R/F1: {metrics['precision_macro']:.4f}/"
          f"{metrics['recall_macro']:.4f}/{metrics['f1_macro']:.4f} | "
          f"Train time: {metrics['train_time_seconds']:.1f}s")
    print(f"{'Lớp':<10} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>8}")
    for c in CLASSES:
        print(f"{LABEL_NAMES_VI[c]:<10} "
              f"{metrics['precision'][str(c)]:>10.4f} "
              f"{metrics['recall'][str(c)]:>8.4f} "
              f"{metrics['f1'][str(c)]:>8.4f} "
              f"{metrics['support'][str(c)]:>8}")
    print(f"-> Recall lớp Negative (0): {metrics['negative_recall']:.4f} "
          f"({metrics['negative_recall'] * 100:.2f}%)")


def save_confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    name: str,
    title: str,
) -> str:
    """Lưu confusion matrix (nhãn tiếng Việt) ra results/figures."""
    _ensure_dirs()
    cm = confusion_matrix(y_true, y_pred, labels=CLASSES)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=LABEL_NAMES_VI,
        yticklabels=LABEL_NAMES_VI,
        ax=ax,
    )
    ax.set_xlabel("Dự đoán")
    ax.set_ylabel("Thực tế")
    ax.set_title(title)
    plt.tight_layout()
    path = FIGURE_DIR / f"confusion_matrix_{name}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[figure] Đã lưu: {path}")
    return str(path)


def save_pr_curve(
    y_true: np.ndarray,
    proba: np.ndarray,
    name: str,
    title: str,
) -> str:
    """
    Precision-Recall curve One-vs-Rest cho từng lớp.
    Lớp Negative (0) được tô đậm — chỉ số quan trọng nhất với doanh nghiệp.
    """
    _ensure_dirs()
    fig, ax = plt.subplots(figsize=(7, 5))
    for c in CLASSES:
        y_bin = (y_true == c).astype(int)
        precision, recall, _ = precision_recall_curve(y_bin, proba[:, c])
        ap = average_precision_score(y_bin, proba[:, c])
        color = "#d62728" if c == 0 else None
        lw = 2.5 if c == 0 else 1.5
        ax.plot(
            recall,
            precision,
            color=color,
            lw=lw,
            label=f"{LABEL_NAMES_VI[c]} (AP={ap:.3f})",
        )
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(title)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    plt.tight_layout()
    path = FIGURE_DIR / f"pr_curve_{name}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[figure] Đã lưu: {path}")
    return str(path)


def save_metrics_json(metrics: dict, name: str) -> str:
    """Lưu metrics JSON vào results/."""
    _ensure_dirs()
    path = RESULTS_DIR / f"metrics_{name}.json"
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[json] Đã lưu: {path}")
    return str(path)


def compare_models(all_metrics: list[dict], path: str | Path | None = None) -> str:
    """
    Tạo bảng so sánh các mô hình -> lưu JSON + Markdown.
    Bảng này được trích trực tiếp vào báo cáo.
    """
    _ensure_dirs()
    rows = []
    for m in all_metrics:
        rows.append(
            {
                "Mô hình": m["model"],
                "Accuracy": round(m["accuracy"], 4),
                "Precision": round(m["precision_macro"], 4),
                "Recall": round(m["recall_macro"], 4),
                "F1": round(m["f1_macro"], 4),
                "Recall lớp Negative": round(m["negative_recall"], 4),
                "Train time (s)": round(m["train_time_seconds"], 2),
            }
        )
    table = pd.DataFrame(rows)

    path = path or RESULTS_DIR / "compare_table.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(table.to_markdown(index=False))
    (RESULTS_DIR / "compare_table.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== BẢNG SO SÁNH CÁC MÔ HÌNH ===")
    print(table.to_string(index=False))
    print(f"[markdown] Đã lưu: {path}")
    return str(path)


def evaluate_transformer(
    model,
    tokenizer,
    df_test: pd.DataFrame,
    batch_size: int = 32,
    model_name: str = "transformer",
    id2label: dict | None = None,
) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    """
    Chạy Transformer trên tập test, trả về (metrics, y_true, y_pred, proba).
    Dùng chung cho Thực nghiệm 2 (model sẵn có) và Thực nghiệm 3 (fine-tuned).

    Args:
        id2label (dict | None): id2label của model (model.config.id2label).
            Model sẵn có có thể có thứ tự nhãn khác chuẩn của dự án
            (vd {0:'NEG',1:'POS',2:'NEU'}) nên cần align về 0=neg/1=neu/2=pos.
    """
    import torch
    from torch.utils.data import DataLoader

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    y_true = df_test["label_id"].to_numpy()
    all_logits = []

    data_loader = DataLoader(
        df_test["text_clean"].tolist(),
        batch_size=batch_size,
    )
    with torch.no_grad():
        for batch_texts in data_loader:
            enc = tokenizer(
                list(batch_texts),
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            ).to(device)
            logits = model(**enc).logits
            all_logits.append(logits.cpu())

    logits = torch.cat(all_logits, dim=0).numpy()
    proba = np.exp(logits - logits.max(axis=1, keepdims=True))
    proba = proba / proba.sum(axis=1, keepdims=True)
    y_pred = proba.argmax(axis=1)

    # Nếu model có id2label riêng, align y_pred + proba về thứ tự chuẩn
    if id2label is not None:
        y_pred, proba = _align_labels(y_pred, proba, id2label)

    metrics = compute_metrics(y_true, y_pred, model_name=model_name)
    return metrics, y_true, y_pred, proba


def _align_labels(
    y_pred: np.ndarray,
    proba: np.ndarray,
    id2label: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Đưa dự đoán của model về id chuẩn: 0=negative, 1=neutral, 2=positive.

    Logic:
      - Đọc id2label của model, chuẩn hoá tên nhãn (lowercase, NEG->negative...)
      - Lớp có tên 'pos'/'pos' viết tắt được map qua dict short
      - y_pred: thay id cũ bằng id chuẩn tương ứng
      - proba: hoán vị cột theo thứ tự chuẩn để PR curve đúng từng lớp
    """
    from .config import LABEL_TO_ID

    short_names = {"neg": "negative", "pos": "positive", "neu": "neutral"}
    idx_to_canon: dict[int, int] = {}
    for idx in range(proba.shape[1]):
        name = str(id2label.get(str(idx), "")).lower().strip()
        if name in short_names:
            name = short_names[name]
        if name not in LABEL_TO_ID:
            raise ValueError(f"Khong map duoc nhan cua model '{name}' (idx={idx})")
        idx_to_canon[idx] = LABEL_TO_ID[name]
    if sorted(idx_to_canon.values()) != [0, 1, 2]:
        raise ValueError(f"id2label cua model thieu lop: {id2label}")

    y_pred = np.array([idx_to_canon[int(i)] for i in y_pred])
    proba_aligned = np.zeros((proba.shape[0], 3), dtype=proba.dtype)
    for idx, canon in idx_to_canon.items():
        proba_aligned[:, canon] = proba[:, idx]
    return y_pred, proba_aligned
