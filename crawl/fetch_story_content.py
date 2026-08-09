"""
Lấy nội dung bài viết và bình luận từ link m.facebook.com/story.php

Cách dùng (chạy trong thư mục crawl/):

    .venv/bin/python fetch_story_content.py \
        --url "https://m.facebook.com/story.php?story_fbid=...&id=..."
    .venv/bin/python fetch_story_content.py --input post_urls.txt
    .venv/bin/python fetch_story_content.py --input post_urls.txt --cookies cookies.txt
    .venv/bin/python fetch_story_content.py --input post_urls.txt --dump-html

Ghi chú:
  - KHÔNG có cookies: chỉ lấy được nội dung bài viết (từ meta og:description).
  - CÓ cookies.txt (định dạng Netscape, export từ Chrome đang đăng nhập FB
    bằng extension "Get cookies.txt LOCALLY"): lấy thêm bình luận,
    tự bấm theo link "Xem thêm bình luận" tối đa MAX_EXPAND lần.
"""

import argparse
import html as html_mod
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import certifi
import requests

CRAWL_DIR = Path(__file__).resolve().parent
COOKIES_TXT = CRAWL_DIR / "cookies.txt"

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
HEADERS = {
    "User-Agent": MOBILE_USER_AGENT,
    "Accept-Language": "vi-VN,vi;q=0.9",
}

TIMEOUT = 30
MAX_EXPAND = 8           # so lan toi da theo link "Xem thêm bình luận"
MAX_COMMENTS = 200       # so binh luan toi da mo bai
COMMENT_BLOCK_RE = re.compile(r'data-testid="post-comment"')
EXPAND_LINK_RE = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*>[^<]*(?:Xem th|View (?:more|all))[^<]*</a>',
    re.IGNORECASE,
)
DIR_AUTO_RE = re.compile(r'<div dir="auto"[^>]*>(.*?)</div>', re.DOTALL)


def clean_text(raw: str) -> str:
    """Bỏ thẻ HTML, giải mã entity, dồn khoảng trắng."""
    text = re.sub(r"<br\s*/?>", "\n", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text


def build_session(cookies_path: Path | None) -> requests.Session:
    """Tạo session; nạp cookies.txt (Netscape) nếu có."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.verify = certifi.where()

    if cookies_path and cookies_path.exists():
        loaded = 0
        for line in cookies_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, path, secure, expiry, name, value = parts[:7]
            session.cookies.set(
                name,
                value,
                domain=domain,
                path=path,
                secure=secure.upper() == "TRUE",
                expires=int(expiry) if expiry.isdigit() else None,
            )
            loaded += 1
        print(f"[cookie] Da nap {loaded} cookie tu {cookies_path.name}")
        return session

    if cookies_path:
        print(f"[cookie] Khong thay {cookies_path.name} - chi lay duoc noi dung bai viet.")
    return session


def fetch_page(session: requests.Session, url: str) -> tuple[str, str]:
    """GET trang, retry 3 lan; tra ve (noi dung HTML, url cuoi cung)."""
    last_exc = None
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text, resp.url
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
        except requests.RequestException as exc:
            last_exc = exc
        time.sleep(2 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def parse_post_text(raw_html: str) -> str:
    """Trich noi dung bai viet tu meta og:description/og:title."""
    desc = re.search(r'og:description" content="([^"]*)"', raw_html)
    if desc and desc.group(1).strip():
        return html_mod.unescape(desc.group(1)).strip()
    title = re.search(r'og:title" content="([^"]*)"', raw_html)
    if title:
        return html_mod.unescape(title.group(1)).strip().removesuffix(" | Facebook")
    return ""


def parse_comments(raw_html: str) -> list[str]:
    """Tach tung block binh luan va lay text (kem ten nguoi dung)."""
    comments: list[str] = []
    parts = COMMENT_BLOCK_RE.split(raw_html)
    if len(parts) > 1:
        for block in parts[1:]:
            text = clean_text(block)
            if text:
                comments.append(text[:2000])
        return comments

    marker = re.search(r"(?:Xem th|View (?:more|all) comment)", raw_html, re.IGNORECASE)
    tail = raw_html[marker.start():] if marker else raw_html
    for match in DIR_AUTO_RE.finditer(tail):
        text = clean_text(match.group(1))
        if text:
            comments.append(text[:2000])
    return comments


def find_expand_link(raw_html: str, page_url: str) -> str | None:
    """Tim link 'Xem thêm bình luận' / 'View more comments'."""
    match = EXPAND_LINK_RE.search(raw_html)
    if not match:
        return None
    href = html_mod.unescape(match.group(1))
    return urljoin(page_url, href)


def fetch_comments(session: requests.Session, story_url: str, raw_html: str) -> list[str]:
    """Lay binh luan + theo link 'Xem thêm bình luận' toi khi het."""
    comments: list[str] = []
    seen: set[str] = set()
    current_url = story_url
    current_html = raw_html

    for _ in range(MAX_EXPAND):
        for comment in parse_comments(current_html):
            if comment not in seen:
                seen.add(comment)
                comments.append(comment)
        if len(comments) >= MAX_COMMENTS:
            break
        link = find_expand_link(current_html, current_url)
        if not link:
            break
        page_url = current_url
        current_html, current_url = fetch_page(session, link)
        if "login" in current_url and current_url != page_url:
            break
        time.sleep(1)

    return comments[:MAX_COMMENTS]


def process_one(session: requests.Session, url: str, has_cookies: bool) -> dict:
    """Xu ly 1 bai viet: noi dung + binh luan."""
    raw_html, final_url = fetch_page(session, url)
    if "login" in final_url and "login" not in url:
        return {"url": url, "error": "bi Facebook chan - can cookies dang nhap", "text": "", "comments": []}

    text = parse_post_text(raw_html)
    comments: list[str] = []
    if has_cookies:
        comments = fetch_comments(session, final_url, raw_html)
    else:
        print(f"  [warn] Khong co cookies - bo qua binh luan cua {url}")
    return {"url": url, "text": text, "comments": comments}


def write_output(posts: list[dict], out_path: Path) -> None:
    """Ghi file txt: URL + noi dung + binh luan."""
    lines: list[str] = []
    for index, post in enumerate(posts, start=1):
        lines.append("==============================")
        lines.append(f"Bai {index} - {post['url']}")
        lines.append("==============================")
        if post.get("error"):
            lines.append("KET QUA: LOI - " + post["error"])
        else:
            lines.append("NOI DUNG BAI:")
            lines.append(post["text"] or "(khong lay duoc noi dung bai)")
            comments = post.get("comments", [])
            lines.append("")
            lines.append(f"BINH LUAN ({len(comments)}):")
            for cindex, comment in enumerate(comments, start=1):
                lines.append(f"{cindex}. {comment}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[save] Da ghi {len(posts)} bai vao {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lay noi dung + binh luan tu link story.php")
    parser.add_argument("--url", help="Mot URL bai viet")
    parser.add_argument("--input", help="File chua danh sach URL (1 URL/dong)")
    parser.add_argument("--cookies", help=f"Duong dan cookies.txt (mac dinh: {COOKIES_TXT.name} neu co)")
    parser.add_argument("--out", default=str(CRAWL_DIR / "posts_content.txt"), help="File xuat ra")
    parser.add_argument("--json", action="store_true", help="Xuat them file .json")
    parser.add_argument("--dump-html", action="store_true", help="Luu HTML trang dau tien de debug")
    args = parser.parse_args()

    if args.url:
        urls = [args.url]
    elif args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[loi] Khong thay file {input_path}")
            return
        urls = [line.strip() for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        parser.print_help()
        return

    cookies_path = Path(args.cookies) if args.cookies else (COOKIES_TXT if COOKIES_TXT.exists() else None)
    session = build_session(cookies_path)
    has_cookies = cookies_path is not None and cookies_path.exists()

    posts: list[dict] = []
    for index, url in enumerate(urls, start=1):
        print(f"[{index}/{len(urls)}] Dang xu ly: {url}")
        try:
            post = process_one(session, url, has_cookies)
            if args.dump_html and index == 1:
                raw_html, _final = fetch_page(session, url)
                (CRAWL_DIR / "debug_page.html").write_text(raw_html, encoding="utf-8")
                print("  [dump] Da luu HTML vao debug_page.html")
            posts.append(post)
            print(f"  -> Text: {len(post.get('text', ''))} ky tu | Comments: {len(post.get('comments', []))}")
        except Exception as exc:  # noqa: BLE001 - loi 1 bai khong chan cac bai khac
            print(f"  [loi] {exc}")
            posts.append({"url": url, "error": str(exc), "text": "", "comments": []})

    write_output(posts, Path(args.out))
    if args.json:
        json_path = Path(args.out).with_suffix(".json")
        json_path.write_text(
            json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[save] Da ghi {json_path}")


if __name__ == "__main__":
    main()
