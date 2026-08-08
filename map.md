# Map.md — Hệ thống Phân loại Cảm xúc tiếng Việt (code_giua_ki_train_AI)

> File map tổng hợp cấu trúc dự án. Folder tham chiếu chi tiết: `code_giua_ki_train_AI/` chứa `map_code_giua_ki_train_AI.md` (cập nhật theo từng giai đoạn phát triển).

## Sơ đồ tổng thể

```text
code_giua_ki_train_AI/
├── sentiment_colab.ipynb   # Notebook chạy toàn bộ thực nghiệm trên Colab
├── app/                    # [BACKEND] FastAPI - triển khai nội bộ (bảo mật dữ liệu)
├── scripts/                # [THỰC NGHIỆM ML] Huấn luyện & đánh giá trên Colab
├── data/                   # UIT-VSFC + data/processed
├── models/                 # best_model/ sau fine-tune
├── results/                # metrics JSON, figures, compare_table.md
└── utils/logs/             # File log backend
```

## Thành phần Backend (app/)

| File | Vai trò | Chức năng |
|---|---|---|
| `app/main.py` | Entry point | Tạo app, CORS, exception handlers, nạp model khi startup |
| `app/config.py` | Config | Pydantic Settings nạp từ `.env`, DIR_ROOT, MODEL_PATH |
| `app/logger.py` | Util | `get_logger()` logging có cấu trúc, RotatingFileHandler |
| `app/utils/response.py` | Util | `ApiSuccess`/`ApiError` + global exception handler |
| `app/schemas/sentiment_schema.py` | Schema | PredictRequest, PredictResponse, HealthResponse |
| `app/services/sentiment_service.py` | Service | `SentimentService` — tải model + inference cục bộ |
| `app/routers/sentiment_router.py` | Router | `POST /predict`, `GET /health` — chỉ validate + dispatch |

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
[Backend] POST /predict -> router (validate) -> SentimentService (inference cục bộ)
          -> ApiSuccess { sentiment, probabilities } -> Dashboard nội bộ
```

## Quy tắc

- Router không chứa business logic — chỉ gọi service (execution-rules Rule 1).
- Mọi endpoint trả `ApiSuccess`/`ApiError` (api-response-standard).
- Cấm `print()` trong `app/` — dùng `get_logger(__name__)` (logging-monitoring).
- Bí mật (API key, MODEL_PATH) trong `.env`, chỉ commit `.env.example`.
