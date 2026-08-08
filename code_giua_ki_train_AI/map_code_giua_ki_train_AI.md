# Map — code_giua_ki_train_AI (Chặng 6: Sentiment Analysis tiếng Việt)

Bản đồ chi tiết thư mục `code_giua_ki_train_AI/`. Xem `map.md` ở thư mục gốc dự án để có sơ đồ tổng thể.

## Mục lục

1. [Kiến trúc tổng thể](#1-kien-truc-tong-the)
2. [Entry Points (lệnh chạy)](#2-entry-points-lenh-chay)
3. [Web Demo (webapp/)](#3-web-demo-webapp)
4. [Thực nghiệm ML (scripts/)](#4-thuc-nghiem-ml-scripts)
5. [Quy ước code](#5-quy-uoc-code)

## 1. Kiến trúc tổng thể

```text
Thực nghiệm (Colab)                              Web demo (Colab + tunnel)
UIT-VSFC -> Fine-tune PhoBERT   ->              Flask /api/predict -> UI Tailwind
                |                                        |
                v                                        v
          models/best_model  ----------------->  scripts.finetune (inference cục bộ)
```

## 2. Entry Points (lệnh chạy)

| Lệnh | Chức năng |
|---|---|
| `python scripts/run_pipeline.py` | Toàn bộ pipeline (`--skip-baseline`, `--skip-finetune`) |
| `python scripts/demo_inference.py` | Demo 5 câu mẫu, in nhãn + xác suất % |
| `python webapp/run_web.py` | Flask + tunnel Cloudflared (`--no-tunnel`, `--port`) |

## 3. Web Demo (webapp/)

| File | Vai trò | File liên quan |
|---|---|---|
| `run_web.py` | Entry: khởi động Flask thread + tunnel, in link public | app.py |
| `app.py` | Flask app: /, /api/model-info, /api/train, /api/train-status, /api/predict | templates/, scripts/finetune.py, scripts/preprocess.py |
| `templates/index.html` | UI Tailwind CDN: 3 card, JS fetch API | app.py |
| `requirements.txt` | Deps: flask, cloudflared, transformers, torch, sklearn, pandas | - |

## 4. Thực nghiệm ML (scripts/)

| File | Vai trò | Chức năng |
|---|---|---|
| `run_pipeline.py` | Entry: orchestrator toàn bộ thực nghiệm | baseline, finetune, evaluate |
| `demo_inference.py` | Demo "Sản phẩm rất tệ!" + 5 câu mẫu | finetune.py |
| `config.py` | Config + HF_TOKEN + hf_login_if_needed() | toàn bộ |
| `preprocess.py` | Pipeline dữ liệu | download_uit_vsfc, normalize_text, clean_dataframe, prepare_dataset |
| `baseline.py` | Thực nghiệm 1 | run_baseline: TF-IDF + LogisticRegression |
| `finetune.py` | Thực nghiệm 3 | SentimentDataset, fine_tune, load_sentiment_model, predict_sentiment |
| `evaluate.py` | Đánh giá | compute_metrics, _align_labels, save_confusion_matrix, save_pr_curve, compare_models, evaluate_transformer |

## 5. Quy ước code

- File Header (File/Chức năng/Vai trò/File liên quan) ở mọi file.
- Docstring Google Style kèm giải thích logic cho mọi hàm.
- Entry point .py có bootstrap sys.path; import nặng đặt trong main() để --help nhanh.
- Flask gọi thẳng `scripts/` in-process; train chạy thread nền + poll status.
- Không emoji trong code/markdown.
