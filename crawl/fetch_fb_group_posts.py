"""
Crawl 5 URL bài viết mới nhất từ group Facebook (giả lập điện thoại).

Chạy bằng môi trường ảo riêng trong thư mục `crawl/`:

    cd crawl
    .venv/bin/python fetch_fb_group_posts.py
    .venv/bin/python fetch_fb_group_posts.py --login   # đăng nhập FB lần đầu

Facebook hiện bắt buộc đăng nhập để xem bài trong group. Có 2 cách nạp
phiên đăng nhập (chỉ cần làm 1 lần, lưu vào `cookies.json`):

  - Chạy `--login`: mở cửa sổ trình duyệt thật, bạn tự đăng nhập
    facebook.com bằng tài khoản cá nhân (nhập tay email/mật khẩu),
    script tự phát hiện đăng nhập xong và lưu phiên lại.
  - Dùng extension "Get cookies.txt LOCALLY" export facebook.com
    -> lưu thành `cookies.txt` trong thư mục này.

Kết quả: 5 URL bài viết mới nhất (dạng story.php?story_fbid=...)
được in ra và lưu vào `fb_post_urls.txt`.
"""

import argparse
import re
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

CRAWL_DIR = Path(__file__).resolve().parent
COOKIES_TXT = CRAWL_DIR / "cookies.txt"
STORAGE_STATE = CRAWL_DIR / "cookies.json"
OUTPUT_FILE = CRAWL_DIR / "fb_post_urls.txt"

GROUP_ID = "762609615053439"
GROUP_URL = f"https://m.facebook.com/groups/{GROUP_ID}/?locale=vi_VN"

# --- Cấu hình giả lập điện thoại iPhone -----------------------------------
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
VIEWPORT = {"width": 360, "height": 800}
POST_URL_RE = re.compile(
    r"(?:story_fbid|story\.php\?story_fbid)=(\d+)|/groups/{group}/(?:posts|permalink)/(\d+)".format(
        group=GROUP_ID
    )
)
FULL_POST_URL = "https://m.facebook.com/story.php?story_fbid={post_id}&id={group}"

# Cửa sổ thời gian chờ (ms) - Facebook m.facebook nạp chậm
NAV_TIMEOUT = 45_000
SCROLL_PAUSE_MS = 2_500
LOGIN_TIMEOUT_S = 300
NUMBER_OF_POSTS = 5


def _load_cookies(context: BrowserContext) -> None:
    """
    Nap cookie dang nhap (neu co) tu cookies.txt hoac cookies.json.

    Logic:
      - Uu tien cookies.txt (dinh dang Netscape: domain, flag, path, secure,
        expiry, name, value) - parse tung dong, bo dong comment/rng
      - Neu khong co cookies.txt, dung storage_state tu cookies.json
        (luu boi --login)

    Args:
        context (BrowserContext): Browser context cua Playwright de nap cookie vao
    """
    if COOKIES_TXT.exists():
        cookies = []
        for line in COOKIES_TXT.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, include_subdomains, path, secure, expiry, name, value = parts[:7]
            http_only = len(parts) > 7 and parts[7].upper() == "TRUE"
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "expires": int(expiry),
                    "secure": secure.upper() == "TRUE",
                    "httpOnly": http_only,
                    "sameSite": "Lax",
                }
            )
        if cookies:
            context.add_cookies(cookies)
            print(f"[cookie] Da nap {len(cookies)} cookie tu cookies.txt")
    elif STORAGE_STATE.exists():
        context.storage_state(path=str(STORAGE_STATE))
        print(f"[cookie] Da nap storage_state tu cookies.json")


def _is_login_page(page: Page) -> bool:
    """
    Nhan biet trang dang nhap/login wall cua Facebook.

    Logic:
      - URL chua "login" -> chac chan la trang login
      - Hoac trang co input[name="email"] (form dang nhap hien thi)

    Args:
        page (Page): Trang hien tai cua Playwright

    Returns:
        bool: True neu dang o trang dang nhap, nguoc lai False
    """
    if "login" in page.url:
        return True
    return page.locator('input[name="email"]').count() > 0


def _dismiss_consent(page: Page) -> None:
    """
    Dong thong bao dong y cookie/banner chan neu xuat hien.

    Logic:
      - Duyet danh sach selector ban phim cho moi ngon ngu (EN/VI)
      - Chi bam khi button/ link visible (timeout ngan de khong treo)
      - Dung sau lan bam dau tien thanh cong

    Args:
        page (Page): Trang hien tai cua Playwright
    """
    for selector in [
        'button:has-text("Cho phép tất cả cookie")',
        'button:has-text("Not Now")',
        'button:has-text("Không phải bây giờ")',
        'a:has-text("Continue")',
    ]:
        button = page.locator(selector).first
        try:
            if button.is_visible(timeout=1_000):
                button.click(timeout=3_000)
                print("[consent] Da dong banner consent")
                return
        except Exception:
            pass


def _scroll_to_load(page: Page, times: int = 4) -> None:
    """
    Cuon feed de cac bai viet moi duoc tai them (lazy load).

    Logic:
      - Cuon chuot xuong 1200px moi lan roi dung SCROLL_PAUSE_MS de
        Facebook tai them noi dung truoc khi cuon lan tiep

    Args:
        page (Page): Trang group dang mo
        times (int): So lan cuon (mac dinh 4)
    """
    for _ in range(times):
        page.mouse.wheel(0, 1_200)
        page.wait_for_timeout(SCROLL_PAUSE_MS)


def _collect_post_urls(page: Page) -> list[str]:
    """
    Trich toan bo URL bai viet trong DOM, bo trung, giu thu tu moi -> cu.

    Logic:
      - Quet toan bo the <a> co href chua "story" hoac duong dan group
      - Dung regex POST_URL_RE de lay post_id tu 2 dang URL:
        story_fbid=<id> hoac /groups/<id>/(posts|permalink)/<id>
      - Chuan hoa ve FULL_POST_URL, loai trung qua set

    Args:
        page (Page): Trang group da cuon xong

    Returns:
        list[str]: Danh sach URL bai viet (chua deduplicate, moi -> cu)
    """
    hrefs = page.eval_on_selector_all(
        'a[href*="story"], a[href*="groups/{}"]'.format(GROUP_ID),
        "els => els.map(e => e.href)",
    )
    seen: set[str] = set()
    urls: list[str] = []
    for href in hrefs:
        match = POST_URL_RE.search(href)
        if not match:
            continue
        post_id = match.group(1) or match.group(2)
        url = FULL_POST_URL.format(group=GROUP_ID, post_id=post_id)
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _login_and_save() -> None:
    """
    Mo cua so trinh duyet that de nguoi dung dang nhap Facebook bang tay.

    Logic:
      - Mo Chromium headless=False voi viewport desktop, locale vi_VN
      - Mo trang facebook.com/login, nguoi dung nhap tay email + mat khau
      - Poll moi 2s de phat hien dang nhap xong (thoat trang login va
        khong con input email)
      - Khi xong: cho 3s cho phien on dinh, luu storage_state vao
        cookies.json va dong cua so - chi can lam 1 lan
      - Het LOGIN_TIMEOUT_S (5 phut) ma chua xong thi dong cua so
    """
    print("[login] Mo cua so trinh duyet - vui long dang nhap facebook.com")
    print("[login] bang tai khoan ca nhan (nhap tay email + mat khau).")
    print(f"[login] Toi da {LOGIN_TIMEOUT_S // 60} phut - xong tu dong luu phien va dong cua so.")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 850},
            locale="vi_VN",
        )
        page = context.new_page()
        page.goto(
            "https://www.facebook.com/login/",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        deadline = time.monotonic() + LOGIN_TIMEOUT_S
        while time.monotonic() < deadline:
            time.sleep(2)
            logged_in = "login" not in page.url and page.locator('input[name="email"]').count() == 0
            if logged_in:
                page.wait_for_timeout(3_000)
                context.storage_state(path=str(STORAGE_STATE))
                print(f"[login] Da dang nhap va luu phien -> {STORAGE_STATE.name}")
                browser.close()
                return
        print("[login] Het thoi gian cho - chua phat hien dang nhap xong.")
        browser.close()


def main() -> None:
    """
    Chay crawl va in 5 URL bai viet moi nhat cua group.

    Logic:
      - --login: mo trinh duyet de dang nhap, luu phien roi thoat
      - Khong co flag: mo trang group giau lap iPhone (headless)
      - Nap cookie da luu, dong consent banner, cuon feed de tai bai
      - Gap login wall -> in huong dan xu ly (--login hoac cookies.txt)
      - Luu 5 URL moi nhat vao fb_post_urls.txt va in ra man hinh
    """
    parser = argparse.ArgumentParser(description="Crawl 5 URL bai viet moi nhat tu group Facebook")
    parser.add_argument(
        "--login",
        action="store_true",
        help="mo trinh duyet de dang nhap facebook.com, luu phien roi thoat (lam 1 lan)",
    )
    args = parser.parse_args()

    if args.login:
        _login_and_save()
        return

    print(f"[crawl] Mo {GROUP_URL}")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=MOBILE_USER_AGENT,
            viewport=VIEWPORT,
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            locale="vi_VN",
        )
        _load_cookies(context)

        page = context.new_page()
        try:
            page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - m.facebook hay timeout do chặn
            print(f"[warn] goto timeout/nap cham, tiep tuc: {exc}")

        page.wait_for_timeout(3_000)
        _dismiss_consent(page)

        if _is_login_page(page):
            print("\n[BLOCK] Facebook bat dang nhap (login wall).")
            print("  Cach xu ly (lam 1 trong 2):")
            print(f"  1. Chay: .venv/bin/python fetch_fb_group_posts.py --login")
            print(f"     -> dang nhap facebook.com bang tay trong cua so hien ra,")
            print(f"        phien tu dong luu vao {STORAGE_STATE.name}")
            print(f"  2. Dung extension 'Get cookies.txt LOCALLY' export cookie facebook.com")
            print(f"     -> luu thanh {COOKIES_TXT.name}")
            print("  Sau do chay lai script nay.")
            browser.close()
            return

        _scroll_to_load(page)
        urls = _collect_post_urls(page)
        browser.close()

    if not urls:
        print("[KET QUA] Khong tim thay bai viet nao. Thu nap cookie dang nhap va chay lai.")
        return

    top_urls = urls[:NUMBER_OF_POSTS]
    print(f"\n[KET QUA] {len(urls)} bai viet tim thay, lay {len(top_urls)} moi nhat:")
    for index, url in enumerate(top_urls, start=1):
        print(f"  {index}. {url}")

    OUTPUT_FILE.write_text("\n".join(top_urls) + "\n", encoding="utf-8")
    print(f"[save] Da luu {len(top_urls)} URL vao {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
