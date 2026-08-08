# Map.md — Hệ thống Phân loại Cảm xúc tiếng Việt (code_giua_ki_train_AI)

> File map tổng hợp cấu trúc dự án. Folder tham chiếu chi tiết: `code_giua_ki_train_AI/` chứa `map_code_giua_ki_train_AI.md` (cập nhật theo từng giai đoạn phát triển).

## Sơ đồ tổng thể

```text
code_giua_ki_train_AI/
├── sentiment_colab.ipynb   # Notebook chạy toàn bộ thực nghiệm + web demo trên Colab
├── webapp/                 # [WEB DEMO] Flask + Tailwind, expose qua Cloudflared
├── scripts/                # [THỰC NGHIỆM ML] Huấn luyện & đánh giá trên Colab
├── data/                   # UIT-VSFC + data/processed
├── models/                 # best_model/ sau fine-tune
└── results/                # metrics JSON, figures, compare_table.md
```

## Thành phần Web Demo (webapp/)

| File | Vai trò | Chức năng |
|---|---|---|
| `webapp/app.py` | Web app | Flask: `/` (UI), `/api/model-info`, `/api/train`, `/api/train-status`, `/api/predict` |
| `webapp/templates/index.html` | UI | Tailwind CDN: 3 card (thông tin model / train / dự đoán) |
| `webapp/requirements.txt` | Deps | flask, cloudflared, transformers, torch, scikit-learn, pandas |

## Thành phần Thực nghiệm ML (scripts/)

| File | Vai trò | Chức năng |
|---|---|---|
| `scripts/config.py` | Config | Model, nhãn, đường dẫn, siêu tham số |
| `scripts/preprocess.py` | Pipeline | Tải UIT-VSFC, làm sạch, gán nhãn (Bước 1-3) |
| `scripts/baseline.py` | Baseline | TF-IDF + Logistic Regression (Thực nghiệm 1) |
| `scripts/finetune.py` | Training | Fine-tune PhoBERT-base (Thực nghiệm 3) |
| `scripts/evaluate.py` | Evaluation | Metrics, confusion matrix, PR curve, so sánh |

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
