# Chặng 6 — Hệ thống Phân loại Cảm xúc tiếng Việt (Sentiment Analysis)

**Trường Đại học Nam Cần Thơ — Môn: Máy học nâng cao (25MIT-1A)**
**Giảng viên hướng dẫn:** TS. Huỳnh Văn Huy
**Thực hiện (cá nhân, không nhóm):** Võ Khương Duy (2513464)

---

## 1. Giới thiệu

Thực nghiệm xây dựng **hệ thống phân loại cảm xúc bình luận tiếng Việt** bằng cách **tải mô hình Transformer mã nguồn mở (PhoBERT-base-v2) và fine-tune lại** trên dữ liệu thực tế — **không gọi API ChatGPT**. Toàn bộ quy trình chạy trên **Google Colab (GPU T4 free)**; mô hình sau đó được đóng gói vào **web demo Flask chạy nội bộ** — dữ liệu bình luận khách hàng không rời khỏi máy chủ doanh nghiệp.

| Thành phần | Giá trị |
|---|---|
| Bộ dữ liệu | **UIT-VSFC** (Vietnamese Students' Feedback Corpus, KSE 2018) — ~11.000 bình luận |
| Bài toán | Phân loại 3 lớp: Negative (0) / Neutral (1) / Positive (2) |
| Baseline | TF-IDF + Logistic Regression (scikit-learn) |
| Transformer | **PhoBERT-base-v2** (`vinai/phobert-base-v2`) — fine-tune bằng Hugging Face `Trainer` |
| Đối chứng | `wonrax/phobert-base-vietnamese-sentiment` (PhoBERT fine-tuned sẵn, không huấn luyện) |
| Chia dữ liệu | Train/Valid/Test chính thức theo paper (~80/10/10), test tách biệt tuyệt đối |
| Môi trường | Google Colab GPU (T4), FP16 |
| Web demo | Flask + Tailwind CSS (CDN) + Cloudflared tunnel |
| Triển khai | Web nội bộ (Flask) — không gửi dữ liệu ra ngoài |

## 2. Công nghệ áp dụng (cái gì → dùng ở đâu)

| Công nghệ / Thư viện | Vai trò trong dự án | File sử dụng |
|---|---|---|
| **Python 3** | Ngôn ngữ chính toàn bộ pipeline | tất cả `scripts/*.py`, `webapp/*.py` |
| **Hugging Face `transformers`** | Tải pretrained model, `AutoTokenizer`, `AutoModelForSequenceClassification`, `Trainer` (fine-tune), `DataCollatorWithPadding` | `scripts/finetune.py`, `scripts/evaluate.py` |
| **PhoBERT-base-v2** (`vinai/phobert-base-v2`) | Mô hình Transformer tiếng Việt được **fine-tune lại** (Thực nghiệm 3) — lõi của bài | `scripts/config.py` (TRANSFORMER_MODEL) |
| **PyTorch** | Backend tính toán: Dataset, DataLoader, tensor, GPU/FP16 | `scripts/finetune.py`, `scripts/evaluate.py` |
| **scikit-learn** | Baseline: `TfidfVectorizer` + `LogisticRegression`; metrics: accuracy, precision/recall/F1, confusion matrix, PR curve | `scripts/baseline.py`, `scripts/evaluate.py` |
| **Pandas** | Nạp/làm sạch dữ liệu CSV | `scripts/preprocess.py` |
| **Hugging Face Hub (datasets)** | Nguồn dữ liệu UIT-VSFC (3 file CSV train/valid/test) | `scripts/preprocess.py` |
| **Matplotlib + Seaborn** | Vẽ confusion matrix, PR curve, biểu đồ phân bố nhãn | `scripts/evaluate.py` |
| **Flask** | Web demo: 4 API + render giao diện | `webapp/app.py` |
| **Tailwind CSS (CDN)** | Giao diện web đẹp (dark theme, 3 card) — không cần build | `webapp/templates/index.html` |
| **Cloudflared** | Tunnel public web từ Colab ra internet (`*.trycloudflare.com`) | `webapp/run_web.py` |
| **Google Colab (T4 GPU)** | Hạ tầng chạy fine-tune, không cần máy mạnh | `sentiment_colab.ipynb` |
| **Git / GitHub** | Quản lý mã nguồn, notebook clone code từ GitHub | repo `duyvo26/code_giua_ki_train_AI` |

## 3. Quy trình tổng quát (9 bước) + công nghệ từng bước

```text
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ 1. Thu thập dữ liệu  │ → │ 2. Tiền xử lý        │ → │ 3. Gán nhãn          │
│ UIT-VSFC (HuggingFace)│   │ Rỗng/Dup/Missing     │   │ Neg=0/Neu=1/Pos=2    │
│      [pandas]        │   │ [pandas + regex]     │   │ [pandas]             │
└──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
           ↓                          ↓                          ↓
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ 4. Tokenizer         │ → │ 5. Chia dữ liệu      │ → │ 6. Fine-tuning       │
│ PhoBERT → input_ids  │   │ Train/Valid/Test     │   │ PhoBERT-base-v2 (GPU)│
│ [transformers]       │   │ [theo paper ~80/10/10]│   │ [Trainer + PyTorch] │
└──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
           ↓                          ↓                          ↓
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ 7. Đánh giá          │ → │ 8. Lưu mô hình       │ → │ 9. Inference         │
│ Acc/P/R/F1/CM/PR     │   │ models/best_model    │   │ "Sản phẩm rất tệ!"   │
│ [sklearn + seaborn]  │   │ [save_pretrained]    │   │ [Flask + Tailwind]   │
└──────────────────────┘   └──────────────────────┘   └──────→ Negative ──────┘
```

**Thực nghiệm 3 mức (trọng tâm so sánh trong báo cáo):**

| # | Thực nghiệm | Mô hình | Công nghệ | File |
|---|---|---|---|---|
| 1 | Baseline | TF-IDF + Logistic Regression | scikit-learn | `scripts/baseline.py` |
| 2 | Transformer sẵn có (đối chứng) | `wonrax/phobert-base-vietnamese-sentiment` | transformers (không huấn luyện) | `scripts/run_pipeline.py` → `_run_reference_model()` |
| 3 | **Fine-tuning** | `vinai/phobert-base-v2` trên UIT-VSFC | transformers Trainer + PyTorch (FP16) | `scripts/finetune.py` |

## 4. Cấu trúc repo

```text
code_giua_ki_train_AI/
├── sentiment_colab.ipynb   # Notebook MỎNG: cài thư viện → nhập token (tùy chọn) → xoá clone cũ + clone mới → gọi lệnh python
├── README.md               # Tài liệu này
├── map.md                  # Sơ đồ tổng thể + bảng công nghệ (tham khảo nhanh)
├── scripts/                # [THỰC NGHIỆM ML] toàn bộ logic, chạy bằng CLI
│   ├── run_pipeline.py     # [ENTRY] 1 lệnh chạy toàn bộ: preprocess → baseline → đối chứng → fine-tune → đánh giá → so sánh
│   ├── demo_inference.py   # [DEMO] in "Sản phẩm rất tệ!" + 5 câu mẫu (nhãn + xác suất %)
│   ├── config.py           # Cấu hình: model, nhãn, đường dẫn, HF_TOKEN (env) + hf_login_if_needed()
│   ├── preprocess.py       # Bước 1-3: tải UIT-VSFC + làm sạch + gán nhãn
│   ├── baseline.py         # Thực nghiệm 1: TF-IDF + Logistic Regression
│   ├── finetune.py         # Thực nghiệm 3: fine-tune PhoBERT-base-v2 (Trainer)
│   └── evaluate.py         # Bước 7: metrics, CM, PR curve, align nhãn, so sánh
├── webapp/                 # [WEB DEMO] Flask + Tailwind + Cloudflared
│   ├── run_web.py          # [ENTRY] Flask (thread nền) + tunnel, in link public
│   ├── app.py              # Flask: / (UI), /api/model-info, /api/train, /api/train-status, /api/predict
│   ├── templates/index.html# UI Tailwind CDN (3 card: thông tin model / train / dự đoán)
│   └── requirements.txt
├── data/                   # UIT-VSFC (tải tự động lần chạy đầu) + data/processed
├── models/                 # best_model/ (config.json + safetensors) sau fine-tune
└── results/                # metrics_*.json, figures/*.png, compare_table.md
```

## 5. Cách chạy

### 5.1 Trên Google Colab (cách chính)

1. Mở `sentiment_colab.ipynb` bằng Colab: `https://github.com/duyvo26/code_giua_ki_train_AI`.
2. Chọn **Runtime → Change runtime type → T4 GPU**.
3. Chạy lần lượt các cell **Runtime → Run all**. Notebook chỉ làm 3 việc:

```text
Cell 1   : kiểm tra GPU + cài thư viện (transformers, sklearn, flask, cloudflared...)
Cell 1.1 : (tùy chọn) nhập HF_TOKEN — bỏ trống Enter nếu không cần
Cell 2   : XOÁ CLONE CŨ + git clone bản mới nhất từ GitHub
Cell 3   : !python scripts/run_pipeline.py      ← toàn bộ thực nghiệm (~15-20 phút)
Cell 4   : !python scripts/demo_inference.py    ← demo "Sản phẩm rất tệ!"
Cell 5   : !python webapp/run_web.py            ← web demo + link public (giữ cell chạy)
```

### 5.2 Chạy trên máy cục bộ (đã có `models/best_model/`)

```bash
pip install -r webapp/requirements.txt
python scripts/run_pipeline.py --skip-finetune   # đánh giá lại model đã train
python scripts/demo_inference.py                 # demo inference
python webapp/run_web.py --no-tunnel             # web nội bộ tại http://localhost:8080
```

## 6. Luồng code chạy chi tiết

```text
!python scripts/run_pipeline.py
   │
   ├─ hf_login_if_needed()            # login HF (nếu có env HF_TOKEN)
   ├─ prepare_dataset()               # [preprocess.py] tải 3 CSV UIT-VSFC từ HuggingFace
   │    └─ clean_dataframe()          #   bỏ rỗng/dup/nhãn lỗi, chuẩn hoá, gán label_id
   │                                  #   -> lưu data/processed/{train,valid,test}.csv
   ├─ run_baseline()                  # [baseline.py] TF-IDF(1,2)-gram → LogisticRegression
   │                                  #   -> metrics_*.json + figures (CM, PR curve)
   ├─ _run_reference_model()          # [evaluate.py] wonrax đánh giá thẳng trên test
   │                                  #   + _align_labels() chuyển {NEG,POS,NEU} → {0,1,2}
   ├─ fine_tune()                     # [finetune.py] PhoBERT-base-v2:
   │   │    AutoTokenizer → input_ids (Bước 4)
   │   │    Trainer: Cross-Entropy, lr 2e-5, 3 epochs, FP16 (Bước 6)
   │   │    load_best_model_at_end (theo F1-macro trên valid)
   │   └─ save_pretrained()           # -> models/best_model/ (Bước 8)
   ├─ evaluate_transformer()          # model fine-tuned trên test → metrics (Bước 7)
   └─ compare_models()                # 3 mô hình → results/compare_table.md (bảng báo cáo)

!python scripts/demo_inference.py     # load models/best_model → predict_sentiment() từng câu
                                      # -> in nhãn + xác suất % (Bước 9)

!python webapp/run_web.py             # Flask thread nền (port 8080) + cloudflared
                                      # -> in link public https://xxx.trycloudflare.com
```

## 7. Web demo (Flask + Tailwind + Cloudflared)

**Giao diện (dark theme OLED, font Inter) gồm 3 tab:**

### Tab 1 - Tổng quan
| Khu vực | Mô tả | API phía sau |
|---|---|---|
| **4 KPI cards** | Accuracy · F1-macro · **Recall lớp Negative** · Thời gian train | `GET /api/model-info` |
| **Huấn luyện** | Bảng **tham số train** (model, epochs, lr, batch, warmup, optimizer, FP16, seed, kích thước dataset) + nút Train + thanh epoch + phase chips | `GET /api/train-config` + `POST /api/train` + `GET /api/train-status` |
| **Thông tin model** | Model gốc, số nhãn, Accuracy, F1, Precision/Recall macro, Recall Negative, đường dẫn | `GET /api/model-info` |
| **Phân tích dữ liệu** | ① Dữ liệu gốc ② Tiền xử lý (bảng làm sạch + 5 bước chuẩn hoá + Before/After thật) ③ Label mapping + phân bố ④ **Tokenization** (token chips, input_ids, attention_mask, thống kê 300 câu) ⑤ **Chia dữ liệu** (% + note test cách ly) | `GET /api/data-info` |
| **Log huấn luyện** | Terminal realtime: bắt print + log Trainer (loss, lr, epoch, eval acc/F1), màu theo level, auto-scroll, nút Sao chép/Xoá | `GET /api/train-log?since=N` (poll 2s) |
| **Dự đoán cảm xúc** | Textarea + 4 chip ví dụ + badge nhãn + 3 thanh xác suất % | `POST /api/predict` |

### Tab 2 - API · Model · Dataset
- **API URLs**: bảng endpoint tự sinh từ `app.url_map` + nút Sao chép + ví dụ curl
- **Model train**: id2label, bảng metrics từng lớp (P/R/F1/Support), **biểu đồ đánh giá** (learning curve, confusion matrix, PR curve), **bảng so sánh 3 mô hình** (cần chạy `run_pipeline.py`)
- **Model dataset**: nguồn UIT-VSFC (link HF + paper), thống kê làm sạch, label mapping, phân bố

### Tab 3 - Bots (Telegram + Zalo)
| Bot | Cấu hình | Nhận tin | Reply |
|---|---|---|---|
| **Telegram** | Token từ @BotFather (nhập ẩn trên web, lưu `utils/bot_config.json` gitignored) | Long-polling `getUpdates` (không cần webhook) | Nhãn + xác suất % 3 lớp qua `sendMessage` |
| **Zalo Bot Creator** | Token `id:secret` từ bot.zaloplatforms.com + **API base** (mặc định `bot-api.zaloplatforms.com`, có thể đổi vd `bot-api.zapps.me`) | Long-polling `getUpdates` (1 update/call) | Reply chunk ≤2000 ký tự |

- Chat ID tự lưu khi bot nhận tin đầu tiên; nút Kiểm tra token (`getMe`), Gửi test, Bật/Tắt polling, badge trạng thái, log bot realtime.
- Token chỉ nằm trong `utils/bot_config.json` (gitignored) — không bao giờ commit.

**Bảo mật dữ liệu:** tokenizer + model + inference chạy 100% cục bộ — bình luận khách hàng không gửi ra ngoài (Cloudflared chỉ là đường ống truyền web).

```text
Khách hàng → Website/App → Flask (Transformer cục bộ) → Negative/Positive → Dashboard doanh nghiệp
```

## 8. Kết quả thực nghiệm

| Mô hình | Accuracy | Precision | Recall | F1 | Recall lớp Negative |
|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | **0.8913** | 0.8617 | 0.6499 | 0.6531 | **0.9702** |
| PhoBERT fine-tuned sẵn (tham chiếu) | … | … | … | … | … |
| **PhoBERT-base-v2 fine-tuned** | … | … | … | … | … |

> Số liệu lấy từ `results/compare_table.md` sau khi chạy notebook. **Không cam kết >95%** — báo cáo số đo thực tế trên tập test.

## 9. Ghi chú khoa học quan trọng (cho báo cáo)

1. **Bài toán:** phân loại cảm xúc 3 lớp; "phát hiện bình luận tiêu cực" là ứng dụng cụ thể → nhấn mạnh **Recall lớp Negative** (bao nhiêu phàn nàn thật sự bị bỏ sót).
2. **Không xoá stopword:** Transformer tận dụng ngữ cảnh toàn câu; tiền xử lý chỉ chuẩn hóa encoding/khoảng trắng/bỏ rỗng/dup.
3. **Test set cách ly tuyệt đối**, chỉ dùng 1 lần cuối cùng.
4. **Đối chứng 3 mức** (truyền thống → Transformer sẵn có → Transformer fine-tune) là phần thuyết phục nhất của báo cáo.
5. Thực nghiệm 2 dùng mô hình công khai `wonrax/phobert-base-vietnamese-sentiment` — chỉ mang tính tham chiếu; thứ tự nhãn được align tự động về chuẩn 0=Neg/1=Neu/2=Pos khi đánh giá.
6. **Transformers v5:** `Trainer` không còn nhận `tokenizer=`, `warmup_ratio` thay bằng `warmup_steps` — code đã tương thích.

## 10. Tài liệu tham khảo

- Van Nguyen, K., et al. *UIT-VSFC: Vietnamese students' feedback corpus for sentiment analysis.* KSE 2018.
- Nguyen, D. Q., & Nguyen, A. T. *PhoBERT: Pre-trained language models for Vietnamese.* EMNLP Findings 2020.
- Hugging Face: [ura-hcmut/UIT-VSFC](https://huggingface.co/datasets/ura-hcmut/UIT-VSFC), [vinai/phobert-base-v2](https://huggingface.co/vinai/phobert-base-v2), [wonrax/phobert-base-vietnamese-sentiment](https://huggingface.co/wonrax/phobert-base-vietnamese-sentiment).
