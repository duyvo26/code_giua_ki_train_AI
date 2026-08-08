# Map — code_giua_ki_train_AI (Chặng 6: Sentiment Analysis tiếng Việt)

Bản đồ chi tiết thư mục `code_giua_ki_train_AI/`. Xem `map.md` ở thư mục gốc dự án để có sơ đồ tổng thể.

## Mục lục

1. [Kiến trúc tổng thể](#1-kien-truc-tong-the)
2. [Backend (app/)](#2-backend-app)
3. [Thực nghiệm ML (scripts/)](#3-thuc-nghiem-ml-scripts)
4. [Quy ước code](#4-quy-uoc-code)

## 1. Kiến trúc tổng thể

```text
Thực nghiệm (Colab)                      Triển khai (Server nội bộ DNC)
UIT-VSFC -> Fine-tune PhoBERT   ->       FastAPI /predict -> Dashboard
                |                                |
                v                                v
          models/best_model  ------------->  SentimentService (inference cục bộ)
```

## 2. Backend (app/)

| File | Vai trò | File liên quan |
|---|---|---|
| `main.py` | Entry point: tạo app, CORS, handler, include router | routers/, utils/response.py, services/ |
| `config.py` | Pydantic Settings, DIR_ROOT từ .env | .env, main.py, logger.py, services/ |
| `logger.py` | get_logger() console + file rotating | utils/logs/app.log |
| `utils/response.py` | ApiSuccess, ApiError, exception handlers | routers/, main.py |
| `schemas/sentiment_schema.py` | PredictRequest, PredictResponse, HealthResponse | routers/ |
| `services/sentiment_service.py` | SentimentService: load model, predict | routers/, config.py |
| `routers/sentiment_router.py` | POST /predict, GET /health (chỉ dispatch) | schemas/, services/ |

## 3. Thực nghiệm ML (scripts/)

| File | Vai trò | Chức năng |
|---|---|---|
| `config.py` | Config | MODEL_NAME, nhãn, URL dữ liệu, siêu tham số |
| `preprocess.py` | Pipeline dữ liệu | download_uit_vsfc, normalize_text, clean_dataframe, prepare_dataset |
| `baseline.py` | Thực nghiệm 1 | run_baseline: TF-IDF + LogisticRegression |
| `finetune.py` | Thực nghiệm 3 | SentimentDataset, fine_tune, load_sentiment_model, predict_sentiment |
| `evaluate.py` | Đánh giá | compute_metrics, save_confusion_matrix, save_pr_curve, compare_models, evaluate_transformer |

## 4. Quy ước code

- File Header (File/Chức năng/Vai trò/File liên quan) ở mọi file.
- Docstring Google Style kèm giải thích logic cho mọi hàm.
- Router không logic, service chứa logic AI, response chuẩn ApiSuccess/ApiError.
- Logging qua `get_logger(__name__)`, cấm print trong app/.
- Không emoji trong code/markdown.
