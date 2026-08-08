# Map.md — Hệ thống Phân loại Cảm xúc tiếng Việt (code_giua_ki_train_AI)

> File map tổng hợp cấu trúc dự án. Folder tham chiếu chi tiết: `code_giua_ki_train_AI/` chứa `map_code_giua_ki_train_AI.md` (cập nhật theo từng giai đoạn phát triển). Xem README.md để hiểu cách chạy và công nghệ áp dụng.

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

## Công nghệ áp dụng (tóm tắt)

| Công nghệ | Dùng để làm gì |
|---|---|
| `transformers` + `vinai/phobert-base-v2` | Fine-tune Transformer tiếng Việt (Trainer, FP16) |
| `transformers` + `wonrax/...` | Đối chứng (Thực nghiệm 2, không huấn luyện) |
| scikit-learn (TF-IDF + LogisticRegression) | Baseline (Thực nghiệm 1) + metrics/CM/PR curve |
| PyTorch | Dataset, DataLoader, inference GPU |
| pandas | Nạp + làm sạch UIT-VSFC |
| Flask + Tailwind CDN | Web demo (thông tin model / train / dự đoán) |
| Cloudflared | Tunnel public từ Colab |
| Colab T4 GPU | Hạ tầng fine-tune |

## Entry points (lệnh chạy chính)

| Lệnh | Chức năng |
|---|---|
| `python scripts/run_pipeline.py` | Chạy toàn bộ pipeline (flag: `--skip-baseline`, `--skip-finetune`) |
| `python scripts/demo_inference.py` | Demo "Sản phẩm rất tệ!" + 5 câu mẫu |
| `python webapp/run_web.py` | Flask + Cloudflared tunnel, in link public (`--no-tunnel` chạy nội bộ) |

## Luồng dữ liệu

```text
[Colab] UIT-VSFC -> preprocess -> baseline -> đối chứng wonrax -> fine-tune PhoBERT-base-v2
                                                                          |
[Web] Flask (/api/predict) -> load_sentiment_model -> inference cục bộ   ↓
       -> { sentiment, probabilities } -> UI Tailwind / Dashboard   models/best_model
[Web] /api/train -> thread nền fine_tune(splits) -> cập nhật models/best_model
```

## Quy tắc

- Web gọi thẳng `scripts/` (in-process) — không có API trung gian trên Colab.
- `/api/train` chạy thread nền, `/api/train-status` để frontend poll — không treo web.
- Model + inference chạy 100% cục bộ — dữ liệu bình luận không gửi ra ngoài (Cloudflared chỉ là đường ống web).
- Token HF đọc từ env `HF_TOKEN` (không ghi vào code — GitHub chặn secret).
