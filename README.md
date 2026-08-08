# Chặng 6 — Hệ thống Phân loại Cảm xúc tiếng Việt (Sentiment Analysis)

**Trường Đại học Nam Cần Thơ — Môn: Máy học nâng cao (25MIT-1A)**
**Giảng viên hướng dẫn:** TS. Huỳnh Văn Huy
**Thực hiện (cá nhân, không nhóm):** Võ Khương Duy (2513464)

---

## 1. Giới thiệu

Thực nghiệm xây dựng **hệ thống phân loại cảm xúc bình luận tiếng Việt** bằng cách **tải mô hình Transformer mã nguồn mở và fine-tune lại** trên dữ liệu của doanh nghiệp — không gọi API ChatGPT. Toàn bộ quy trình chạy trên **Google Colab (GPU T4 free)**, mô hình sau đó được triển khai trên **server nội bộ bằng FastAPI** để đảm bảo dữ liệu khách hàng không rời khỏi doanh nghiệp.

| Thành phần | Giá trị |
|---|---|
| Bộ dữ liệu | **UIT-VSFC** (Vietnamese Students' Feedback Corpus, KSE 2018) — ~11.000 bình luận |
| Bài toán | Phân loại 3 lớp: Negative (0) / Neutral (1) / Positive (2) |
| Baseline | TF-IDF + Logistic Regression |
| Transformer | **PhoBERT-base-v2** (`vinai/phobert-base-v2`) fine-tune bằng Hugging Face `Trainer` |
| Chia dữ liệu | Train/Valid/Test chính thức theo paper (~80/10/10), test tách biệt tuyệt đối |
| Môi trường | Google Colab GPU (T4), FP16 |
| Triển khai | FastAPI nội bộ (không gửi dữ liệu ra ngoài) |

## 2. Quy trình tổng quát (9 bước)

```text
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ 1. Thu thập dữ liệu  │ → │ 2. Tiền xử lý        │ → │ 3. Gán nhãn          │
│ UIT-VSFC (HuggingFace)│   │ Rỗng/Dup/Missing     │   │ Neg=0/Neu=1/Pos=2    │
└──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
           ↓                          ↓                          ↓
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ 4. Tokenizer         │ → │ 5. Chia dữ liệu      │ → │ 6. Fine-tuning       │
│ PhoBERT → input_ids  │   │ Train/Valid/Test     │   │ PhoBERT-base-v2 (GPU) │
└──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
           ↓                          ↓                          ↓
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ 7. Đánh giá          │ → │ 8. Lưu mô hình       │ → │ 9. Inference         │
│ Acc/P/R/F1/CM/PR     │   │ models/best_model    │   │ "Sản phẩm rất tệ!"   │
└──────────────────────┘   └──────────────────────┘   └──────→ Negative ──────┘
```

**Thực nghiệm 3 mức (trọng tâm so sánh trong báo cáo):**

| # | Thực nghiệm | Mô hình | Cách chạy |
|---|---|---|---|
| 1 | Baseline | TF-IDF + Logistic Regression | `scripts/baseline.py` |
| 2 | Transformer sẵn có (đối chứng) | `wonrax/phobert-base-vietnamese-sentiment` (PhoBERT fine-tuned sẵn) | không huấn luyện |
| 3 | **Fine-tuning** | `vinai/phobert-base-v2` trên UIT-VSFC | `scripts/finetune.py` |

## 3. Cấu trúc repo

```text
code_giua_ki_train_AI/
├── sentiment_colab.ipynb   # Notebook MỎNG: clone code (xoá clone cũ) + gọi lệnh python
├── README.md
├── map.md                  # Sơ đồ tổng thể dự án
├── scripts/                # [THỰC NGHIỆM ML] toàn bộ logic nằm ở đây, chạy bằng CLI
│   ├── run_pipeline.py     # [ENTRY] 1 lệnh chạy toàn bộ: preprocess→baseline→đối chứng→fine-tune→đánh giá
│   ├── demo_inference.py   # [DEMO] in "Sản phẩm rất tệ!" + 5 câu mẫu (nhãn + xác suất %)
│   ├── config.py           # Cấu hình: model, nhãn, đường dẫn, HF_TOKEN + hf_login_if_needed()
│   ├── preprocess.py       # Bước 1-3: tải dữ liệu + tiền xử lý + gán nhãn
│   ├── baseline.py         # Thực nghiệm 1: TF-IDF + Logistic Regression
│   ├── finetune.py         # Thực nghiệm 3: fine-tune PhoBERT-base-v2
│   └── evaluate.py         # Bước 7: metrics, confusion matrix, PR curve, so sánh
├── webapp/                 # [WEB DEMO] Flask + Tailwind - chạy trên Colab, expose qua Cloudflared
│   ├── run_web.py          # [ENTRY] Flask (thread nền) + tunnel Cloudflared, in link public
│   ├── app.py              # Flask: /api/model-info, /api/train, /api/train-status, /api/predict
│   ├── templates/index.html # UI Tailwind CDN (thông tin model / train / dự đoán)
│   └── requirements.txt
├── data/                   # UIT-VSFC (tải tự động) + data/processed
├── models/                 # best_model/ sau fine-tune
└── results/                # metrics JSON, figures, compare_table.md
```

## 4. Chạy trên Google Colab

1. Mở `sentiment_colab.ipynb` bằng Colab: `https://github.com/duyvo26/code_giua_ki_train_AI`.
2. Chọn **Runtime → Change runtime type → T4 GPU**.
3. Chạy lần lượt các cell **Runtime → Run all**. Notebook chỉ làm 3 việc: cài thư viện → **xoá clone cũ + clone bản mới** → chạy lệnh python:

```text
!python scripts/run_pipeline.py    # toàn bộ thực nghiệm (fine-tune ~15-20 phút)
!python scripts/demo_inference.py  # demo "Sản phẩm rất tệ!"
!python webapp/run_web.py          # web demo Flask + link public Cloudflared
```

Chạy lại nhanh (model đã có sẵn, không retrain): `python scripts/run_pipeline.py --skip-finetune`.

## 5. Web demo Flask (chạy trên Colab, public qua Cloudflared)

Notebook cell cuối chạy `python webapp/run_web.py` — khởi động **Flask web** trong thread nền và mở **Cloudflared tunnel**, in ra link public `https://xxx.trycloudflare.com` mở trên trình duyệt bất kỳ (điện thoại, máy tính).

**Giao diện (Tailwind, dark theme) gồm 3 chức năng:**

| Chức năng | Mô tả |
|---|---|
| **Thông tin model** | Bảng thông số PhoBERT fine-tuned: model gốc, số nhãn, Accuracy, F1-macro, **Recall lớp Negative**, thời gian train |
| **Train lại** | Fine-tune chạy thread nền, hiển thị tiến trình epoch + trạng thái, trang web không bị treo |
| **Dự đoán cảm xúc** | Nhập bình luận → nhãn + xác suất % 3 lớp (Negative/Neutral/Positive) dạng thanh màu |

Dự đoán ví dụ:

```json
{
  "text": "Sản phẩm rất tệ!",
  "sentiment": "Negative",
  "sentiment_vi": "Tiêu cực",
  "confidence": 0.987,
  "probabilities_vi": {"Tiêu cực": 0.987, "Trung tính": 0.008, "Tích cực": 0.005}
}
```

**Chạy nội bộ (không cần tunnel, sau khi có `models/best_model/`):**

```bash
pip install -r webapp/requirements.txt
python webapp/run_web.py --no-tunnel
# mở http://localhost:8080
```

**Điểm bảo mật:** tokenizer + mô hình + inference chạy 100% cục bộ — bình luận khách hàng không bao giờ được gửi ra API bên ngoài (Cloudflared chỉ là đường ống truyền web, model vẫn nằm trên máy chạy).

```text
Khách hàng → Website/App → Flask (Transformer cục bộ) → Negative/Positive → Dashboard doanh nghiệp
```

## 6. Bảng kết quả (điền sau khi chạy thực tế)

| Mô hình | Accuracy | Precision | Recall | F1 | Recall lớp Negative |
|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | … | … | … | … | … |
| PhoBERT fine-tuned sẵn (tham chiếu) | … | … | … | … | … |
| **PhoBERT-base-v2 fine-tuned** | … | … | … | … | … |

> Số liệu lấy từ `results/compare_table.md` sau khi chạy notebook. **Không cam kết >95%** — báo cáo số đo thực tế trên tập test.

## 7. Ghi chú khoa học quan trọng (cho báo cáo)

1. **Bài toán:** phân loại cảm xúc 3 lớp; "phát hiện bình luận tiêu cực" là ứng dụng cụ thể → nhấn mạnh **Recall lớp Negative** (bao nhiêu phàn nàn thật sự bị bỏ sót).
2. **Không xoá stopword:** Transformer tận dụng ngữ cảnh toàn câu; tiền xử lý chỉ chuẩn hóa encoding/khoảng trắng/bỏ rỗng/dup.
3. **Test set cách ly tuyệt đối**, chỉ dùng 1 lần cuối cùng.
4. **Đối chứng 3 mức** (truyền thống → Transformer sẵn có → Transformer fine-tune) là phần thuyết phục nhất của báo cáo.
5. Thực nghiệm 2 dùng mô hình công khai `wonrax/phobert-base-vietnamese-sentiment` (PhoBERT fine-tuned sẵn) — chỉ mang tính tham chiếu; thứ tự nhãn của model được align tự động về chuẩn 0=Neg/1=Neu/2=Pos khi đánh giá.

## 8. Tài liệu tham khảo

- Van Nguyen, K., et al. *UIT-VSFC: Vietnamese students' feedback corpus for sentiment analysis.* KSE 2018.
- Nguyen, D. Q., & Nguyen, A. T. *PhoBERT: Pre-trained language models for Vietnamese.* EMNLP Findings 2020.
- Hugging Face: [ura-hcmut/UIT-VSFC](https://huggingface.co/datasets/ura-hcmut/UIT-VSFC), [vinai/phobert-base-v2](https://huggingface.co/vinai/phobert-base-v2), [wonrax/phobert-base-vietnamese-sentiment](https://huggingface.co/wonrax/phobert-base-vietnamese-sentiment).
