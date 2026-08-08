# Map.md — Hệ thống Phân loại Cảm xúc tiếng Việt (code_giua_ki_train_AI)

> File map tổng hợp cấu trúc dự án. Folder tham chiếu chi tiết: `code_giua_ki_train_AI/` chứa `map_code_giua_ki_train_AI.md` (cập nhật theo từng giai đoạn phát triển).

## Sơ đồ tổng thể

```text
code_giua_ki_train_AI/
├── sentiment_colab.ipynb   # Notebook MỎNG: xoá clone cũ + clone mới + gọi lệnh python
├── scripts/                # [THỰC NGHIỆM ML] mọi logic ở đây, chạy bằng CLI
├── webapp/                 # [WEB DEMO] Flask + Tailwind, expose qua Cloudflared
├── data/                   # UIT-VSFC + data/processed
├── models/                 # best_model/ sau fine-tune
└── results/                # metrics JSON, figures, compare_table.md
```

## Entry points (lệnh chạy chính)

| Lệnh | Chức năng |
|---|---|
| `python scripts/run_pipeline.py` | Chạy toàn bộ pipeline (flag: `--skip-baseline`, `--skip-finetune`) |
| `python scripts/demo_inference.py` | Demo "Sản phẩm rất tệ!" + 5 câu mẫu |
| `python webapp/run_web.py` | Flask + Cloudflared tunnel, in link public (`--no-tunnel` chạy nội bộ) |

## Thành phần Web Demo (webapp/)

| File | Vai trò | Chức năng |
|---|---|---|
| `webapp/run_web.py` | Entry point | Khởi động Flask (thread) + tunnel Cloudflared, parse + in link public |
| `webapp/app.py` | Web app | Flask: `/` (UI), `/api/model-info`, `/api/train`, `/api/train-status`, `/api/predict` |
| `webapp/templates/index.html` | UI | Tailwind CDN: 3 card (thông tin model / train / dự đoán) |
| `webapp/requirements.txt` | Deps | flask, cloudflared, transformers, torch, scikit-learn, pandas |

## Thành phần Thực nghiệm ML (scripts/)

| File | Vai trò | Chức năng |
|---|---|---|
| `scripts/run_pipeline.py` | Entry point | Orchestrator: preprocess → baseline → đối chứng → fine-tune → đánh giá → so sánh |
| `scripts/demo_inference.py` | Demo | In nhãn + xác suất % cho 5 câu mẫu (Bước 9) |
| `scripts/config.py` | Config | Model, nhãn, đường dẫn, HF_TOKEN + `hf_login_if_needed()` |
| `scripts/preprocess.py` | Pipeline | Tải UIT-VSFC, làm sạch, gán nhãn (Bước 1-3) |
| `scripts/baseline.py` | Baseline | TF-IDF + Logistic Regression (Thực nghiệm 1) |
| `scripts/finetune.py` | Training | Fine-tune PhoBERT-base-v2 (Thực nghiệm 3) |
| `scripts/evaluate.py` | Evaluation | Metrics, confusion matrix, PR curve, align nhãn, so sánh |

## Luồng dữ liệu

```text
[Colab] UIT-VSFC -> preprocess -> baseline -> finetune PhoBERT -> models/best_model
                                                                    |
[Web] Flask (/api/predict) -> load_sentiment_model -> inference cục bộ
       -> { sentiment, probabilities } -> UI Tailwind / Dashboard nội bộ
[Web] /api/train -> thread nền fine_tune(splits) -> cập nhật models/best_model
```

## Quy tắc

- Web gọi thẳng `scripts/` (in-process) — không có API trung gian trên Colab.
- `/api/train` chạy thread nền, `/api/train-status` để frontend poll — không treo web.
- Model + inference chạy 100% cục bộ — dữ liệu bình luận không gửi ra ngoài (Cloudflared chỉ là đường ống web).
