"""
Bước 1-3: Tải dữ liệu UIT-VSFC, tiền xử lý và gán nhãn.

- Tải 3 split train/valid/test chính thức của UIT-VSFC (paper KSE 2018)
  từ Hugging Face Hub về thư mục `data/`.
- Chuẩn hoá văn bản (encoding, khoảng trắng, lowercase), loại bỏ bản ghi
  rỗng, duplicate, nhãn không hợp lệ.
- Gán nhãn số: negative=0, neutral=1, positive=2.
- KHÔNG xoá stopword: Transformer cần ngữ cảnh toàn câu.
"""

import re
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, DATA_URLS, LABEL_TO_ID, PROCESSED_DIR


def download_uit_vsfc(data_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """
    Tải UIT-VSFC về máy (nếu chưa có) và trả về dict 3 split.
    """
    data_dir = data_dir or DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    splits: dict[str, pd.DataFrame] = {}
    for name, url in DATA_URLS.items():
        path = data_dir / f"uit_vsfc_{name}.csv"
        if not path.exists():
            print(f"[download] {name}: {url}")
            df = pd.read_csv(url)
            df.to_csv(path, index=False)
        splits[name] = pd.read_csv(path)
        print(f"  -> {name}: {len(splits[name])} dòng")
    return splits


def normalize_text(text: str) -> str:
    """
    Chuẩn hoá văn bản: sửa encoding lỗi, gộp khoảng trắng, bỏ ký tự thừa.
    Không xoá dấu tiếng Việt, không xoá stopword.
    """
    if not isinstance(text, str):
        return ""
    # Sửa lỗi encoding kiểu "cafÃ©" -> "café" (fallback latin-1)
    try:
        fixed = text.encode("utf-8", errors="ignore").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        fixed = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
    # Gộp nhiều khoảng trắng / tab / xuống dòng thành 1 khoảng trắng
    fixed = re.sub(r"\s+", " ", fixed)
    # Bỏ khoảng trắng thừa quanh dấu câu phổ biến
    fixed = re.sub(r"\s+([.,!?;:])", r"\1", fixed)
    return fixed.strip().lower()


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Làm sạch dataframe: bỏ rỗng, duplicate, nhãn lỗi; gán label_id.
    Trả về (df sạch, thống kê).
    """
    stats = {"so_dong_goc": len(df)}

    df = df.copy()
    df["text_clean"] = df["text"].map(normalize_text)

    n_empty = int((df["text_clean"].str.len() == 0).sum())
    df = df[df["text_clean"].str.len() > 0]

    n_dup = int(df["text_clean"].duplicated().sum())
    df = df.drop_duplicates(subset=["text_clean"], keep="first")

    n_bad_label = int((~df["label"].isin(LABEL_TO_ID)).sum())
    df = df[df["label"].isin(LABEL_TO_ID)]

    df["label_id"] = df["label"].map(LABEL_TO_ID)

    stats.update(
        {
            "so_dong_rong": n_empty,
            "so_dong_duplicate": n_dup,
            "so_dong_nhan_loi": n_bad_label,
            "so_dong_con_lai": len(df),
            "phan_bo_lop": (
                df["label_id"].value_counts().sort_index().to_dict()
            ),
        }
    )
    return df[["text_clean", "label", "label_id"]].reset_index(drop=True), stats


def prepare_dataset(
    data_dir: str | Path | None = None,
    processed_dir: str | Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:
    """
    Pipeline dữ liệu đầy đủ: tải -> làm sạch -> lưu CSV đã xử lý.
    Trả về (dict split sạch, dict thống kê từng split).
    """
    processed_dir = processed_dir or PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)

    raw = download_uit_vsfc(data_dir)
    cleaned: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict] = {}
    for name, df in raw.items():
        clean_df, stats = clean_dataframe(df)
        clean_df.to_csv(processed_dir / f"{name}.csv", index=False)
        cleaned[name] = clean_df
        summaries[name] = stats
    return cleaned, summaries


def show_summary(summaries: dict[str, dict]) -> None:
    """In tóm tắt kết quả tiền xử lý từng split."""
    print(f"{'Split':<8} {'Gốc':>7} {'Rỗng':>5} {'Dup':>5} {'Nhãn lỗi':>9} {'Còn lại':>8}")
    for name, s in summaries.items():
        print(
            f"{name:<8} {s['so_dong_goc']:>7} {s['so_dong_rong']:>5} "
            f"{s['so_dong_duplicate']:>5} {s['so_dong_nhan_loi']:>9} {s['so_dong_con_lai']:>8}"
        )
    for name, s in summaries.items():
        dist = s["phan_bo_lop"]
        total = sum(dist.values())
        parts = ", ".join(f"{k}: {v} ({v / total * 100:.1f}%)" for k, v in dist.items())
        print(f"\n{name.upper()} phân bố lớp -> {parts}")
