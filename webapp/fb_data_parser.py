"""
File: fb_data_parser.py
Chức năng: Parse file dữ liệu Facebook (txt/JSON) xuất từ extension
           "FB Group URL Grabber" thành cấu trúc chuẩn cho web đọc.
Vai trò: Util - tách logic parse khỏi app.py, không phụ thuộc thư viện ngoài
File liên quan: webapp/app.py, crawl/chrome-extension/popup.js

Hai định dạng đầu vào:

1) JSON (tự detect nếu text bắt đầu bằng "["):
   [{"index": 1, "url": "...", "postText": "...", "comments": ["a", "b"], "commentCount": 2}]

2) TXT chuẩn của extension (phiên bản mới):
   === BAI 1 ===
   URL: https://www.facebook.com/groups/762609615053439/posts/1749329799714744
   NOI DUNG:
     Tuyển dụng nhân viên...
   --- BINH LUAN ---
   1. Cẩm Huỳnh: sao tui chưa có nữa tr
   2. InspiringReindeer7449: Mình gửi kb với bạn rồi á

   (cũng đọc được format cũ "Bai 1 - url" / dòng "======" nhờ fallback regex)
"""

import json
import re
from typing import Any

_POST_HEADER_RE = re.compile(r"^===\s*BAI\s+(\d+)\s*===\s*$")
_POST_HEADER_OLD_RE = re.compile(r"^Bai\s+(\d+)\s*[-–]\s*(\S+)\s*={0,}\s*$")
_URL_RE = re.compile(r"^URL\s*[:：]\s*(\S+)$")
_NOI_DUNG_RE = re.compile(r"^NOI\s*DUNG\s*[:：]\s*$")
_BINH_LUAN_RE = re.compile(r"^---\s*BINH\s*LUAN.*$")
_COMMENT_RE = re.compile(r"^\d+\s*[.\-)]\s*(.+)$")

# Chặn các dòng "header" cũ lọt vào nội dung khi parse fallback
_OLD_DIVIDER_RE = re.compile(r"^={4,}$")


def parse_fb_data(text: str) -> dict[str, Any]:
    """
    Parse text từ extension (JSON hoặc TXT) -> cấu trúc chuẩn.

    Trả về: {"posts": [{index, url, text, comments}], "warnings": [...]}
    Không raise - lỗi parse được đẩy vào warnings.
    """
    content = (text or "").strip()
    if not content:
        return {"posts": [], "warnings": ["File rỗng"]}
    if content.startswith("["):
        return _parse_fb_json(content)
    return _parse_fb_txt(content)


def _parse_fb_json(content: str) -> dict[str, Any]:
    """Parse định dạng JSON từ extension."""
    warnings: list[str] = []
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        return {"posts": [], "warnings": [f"JSON lỗi: {exc}"]}
    if not isinstance(raw, list):
        return {"posts": [], "warnings": ["JSON phải là mảng danh sách bài viết"]}

    posts: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Bài {index}: bỏ qua phần tử không phải object")
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            warnings.append(f"Bài {index}: thiếu url - bỏ qua")
            continue
        comments = item.get("comments")
        if not isinstance(comments, list):
            comments = [str(c) for c in (item.get("comments") or []) if str(c).strip()]
        posts.append(
            {
                "index": index,
                "url": url,
                "text": str(item.get("postText") or item.get("text") or "").strip(),
                "comments": [str(c).strip() for c in comments if str(c).strip()],
            }
        )
    return {"posts": posts, "warnings": warnings}


def _parse_fb_txt(content: str) -> dict[str, Any]:
    """Parse định dạng TXT (chuẩn mới + fallback format cũ)."""
    warnings: list[str] = []
    lines = content.splitlines()
    posts: list[dict[str, Any]] = []

    # --- Bước 1: tách bài bằng header "=== BAI N ===" (format mới) ----------
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _POST_HEADER_RE.match(stripped):
            if current:
                sections.append(current)
            current = [line]
        elif _POST_HEADER_OLD_RE.match(stripped):
            # format cũ: dòng "Bai N - url" bắt đầu bài mới
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    if not sections:
        warnings.append("Không tìm thấy mục 'BAI' nào - có thể file không đúng định dạng")

    # --- Bước 2: mỗi section -> 1 bài --------------------------------------
    for section in sections:
        post = _parse_post_section(section)
        if post is None:
            warnings.append(
                f"Đoạn bắt đầu '{section[0][:40]}...' không nhận ra URL - bỏ qua"
            )
            continue
        posts.append(post)

    # --- Bước 3: đánh số lại index theo thứ tự xuất hiện --------------------
    for index, post in enumerate(posts, start=1):
        post["index"] = index
    return {"posts": posts, "warnings": warnings}


def _parse_post_section(section: list[str]) -> dict[str, Any] | None:
    """Parse 1 đoạn text thành 1 bài: tách URL, nội dung, bình luận."""
    url = ""
    body_lines: list[str] = []
    comment_lines: list[str] = []
    in_comments = False
    seen_url = False

    for line in section:
        stripped = line.strip()

        # Format cũ: "Bai 1 - <url>"
        old_match = _POST_HEADER_OLD_RE.match(stripped)
        if old_match and not url:
            url = old_match.group(2)
            continue
        if _POST_HEADER_RE.match(stripped):
            continue
        if _OLD_DIVIDER_RE.match(stripped):
            continue

        url_match = _URL_RE.match(stripped)
        if url_match and not seen_url:
            url = url_match.group(1)
            seen_url = True
            continue
        if _NOI_DUNG_RE.match(stripped):
            in_comments = False
            continue
        if _BINH_LUAN_RE.match(stripped):
            in_comments = True
            continue

        if in_comments:
            comment_match = _COMMENT_RE.match(stripped)
            if comment_match:
                comment_lines.append(comment_match.group(1).strip())
            elif stripped:
                comment_lines.append(stripped)
        elif stripped:
            body_lines.append(stripped)

    if not url:
        return None

    return {
        "index": 0,  # đánh số lại ở hàm gọi
        "url": url,
        "text": "\n".join(body_lines).strip(),
        "comments": comment_lines,
    }
