"""
File: run_pipeline.py
Chức năng: Chạy toàn bộ pipeline thực nghiệm từ CLI - chỉ 1 lệnh duy nhất
Vai trò: Entry point - preprocess -> baseline -> đối chứng -> fine-tune -> đánh giá -> so sánh
File liên quan: scripts/config.py, preprocess.py, baseline.py, finetune.py, evaluate.py

Cách dùng:
    python scripts/run_pipeline.py                # chạy đầy đủ (fine-tune ~15-20 phút)
    python scripts/run_pipeline.py --skip-finetune # dùng model đã train sẵn, không retrain
    python scripts/run_pipeline.py --skip-baseline # bỏ baseline TF-IDF (đã chạy rồi)
"""

import argparse
import sys
from pathlib import Path

# Bootstrap: đảm bảo thư mục gốc repo nằm trong sys.path để import scripts.*
# (chạy `python scripts/run_pipeline.py` từ bất kỳ đâu)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chay toan bo pipeline thuc nghiem Sentiment Analysis tieng Viet"
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Bo qua Thuc nghiem 1 (TF-IDF + Logistic Regression)",
    )
    parser.add_argument(
        "--skip-finetune",
        action="store_true",
        help="Khong retrain - dung model da luu o models/best_model",
    )
    return parser


def _run_reference_model(splits: dict) -> dict:
    """
    Thực nghiệm 2: đánh giá mô hình PhoBERT fine-tuned sẵn (wonrax)
    trên tập test - không huấn luyện gì thêm.

    Logic:
      - Tải model công khai từ HF (public, không cần token)
      - Truyền id2label để evaluate_transformer align thứ tự nhãn
        (wonrax: {0:NEG, 1:POS, 2:NEU} -> chuẩn {0:neg, 1:neu, 2:pos})
    """
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from scripts.config import PUBLIC_SENTIMENT_MODEL
    from scripts.evaluate import (
        evaluate_transformer,
        print_metrics_table,
        save_confusion_matrix,
        save_metrics_json,
        save_pr_curve,
    )

    print("\n=== Thuc nghiem 2: PhoBERT fine-tuned san (doi chung) ===")
    tokenizer = AutoTokenizer.from_pretrained(PUBLIC_SENTIMENT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(PUBLIC_SENTIMENT_MODEL)
    id2label = getattr(model.config, "id2label", {})
    print("id2label:", id2label)

    metrics, y_true, y_pred, proba = evaluate_transformer(
        model,
        tokenizer,
        splits["test"],
        model_name="PhoBERT fine-tuned sẵn (tham chiếu)",
        id2label=id2label,
    )
    print_metrics_table(metrics)
    save_confusion_matrix(
        y_true, y_pred, "public_pretrained", "Confusion Matrix - PhoBERT fine-tuned sẵn"
    )
    save_pr_curve(y_true, proba, "public_pretrained", "Precision-Recall - PhoBERT fine-tuned sẵn")
    save_metrics_json(metrics, "public_pretrained")
    return metrics


def _run_finetune_and_eval(splits: dict, skip_finetune: bool) -> dict | None:
    """
    Thực nghiệm 3: fine-tune PhoBERT-base-v2 rồi đánh giá trên tập test.
    Nếu model đã tồn tại và --skip-finetune, chỉ đánh giá model cũ.

    Logic:
      - fine_tune() lưu checkpoint tốt nhất vào models/best_model
      - evaluate_transformer chạy inference trên test (test chưa từng
        xuất hiện trong huấn luyện -> đo khả năng tổng quát thật)
    """
    from scripts.config import BEST_MODEL_DIR
    from scripts.evaluate import (
        evaluate_transformer,
        print_metrics_table,
        save_confusion_matrix,
        save_learning_curve,
        save_metrics_json,
        save_pr_curve,
    )
    from scripts.finetune import fine_tune, load_sentiment_model

    print("\n=== Thuc nghiem 3: Fine-tuning PhoBERT-base-v2 ===")
    trainer = None
    if not skip_finetune:
        trainer = fine_tune(splits)
        # Biểu đồ hội tụ (loss + F1 theo epoch) -> results/figures/learning_curve.png
        save_learning_curve(trainer)
    elif not (BEST_MODEL_DIR / "config.json").exists():
        print("[warn] --skip-finetune nhung chua co models/best_model."
              " Bo qua thuc nghiem 3.")
        return None

    model, tokenizer = load_sentiment_model()
    metrics, y_true, y_pred, proba = evaluate_transformer(
        model,
        tokenizer,
        splits["test"],
        model_name="PhoBERT-base-v2 (fine-tuned)",
    )
    print_metrics_table(metrics)
    save_confusion_matrix(
        y_true, y_pred, "phobert_finetuned", "Confusion Matrix - PhoBERT-base-v2 fine-tuned"
    )
    save_pr_curve(y_true, proba, "phobert_finetuned", "Precision-Recall - PhoBERT-base-v2 fine-tuned")
    save_metrics_json(metrics, "phobert_finetuned")
    return metrics


def main() -> None:
    args = _build_parser().parse_args()

    # Import chậm bên trong main() để --help chạy nhanh không cần thư viện nặng
    from scripts.baseline import run_baseline
    from scripts.config import BEST_MODEL_DIR, hf_login_if_needed
    from scripts.evaluate import (
        compare_models,
        evaluate_transformer,
        print_metrics_table,
        save_confusion_matrix,
        save_metrics_json,
        save_pr_curve,
    )
    from scripts.preprocess import prepare_dataset, show_summary

    hf_login_if_needed()

    # Bước 1-3: dữ liệu + tiền xử lý (tải UIT-VSFC, làm sạch, gán nhãn)
    print("=== Bước 1-3: Du lieu & Tien xu ly (UIT-VSFC) ===")
    splits, summaries = prepare_dataset()
    show_summary(summaries)

    metrics: list[dict] = []

    # Bước 4-6 (Thực nghiệm 1): baseline TF-IDF + LR
    if not args.skip_baseline:
        print("\n=== Thuc nghiem 1: TF-IDF + Logistic Regression (baseline) ===")
        metrics.append(run_baseline(splits))
    else:
        print("\n[skip] Thuc nghiem 1 (baseline)")

    # Thực nghiệm 2: model sẵn có (đối chứng)
    metrics.append(_run_reference_model(splits))

    # Thực nghiệm 3: fine-tune + đánh giá
    ft_metrics = _run_finetune_and_eval(splits, args.skip_finetune)
    if ft_metrics is not None:
        metrics.append(ft_metrics)

    # Bước 7-8: bảng so sánh -> results/compare_table.md
    print("\n=== Bang so sanh 3 mo hinh ===")
    compare_models(metrics)


if __name__ == "__main__":
    main()
