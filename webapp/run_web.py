"""
File: run_web.py
Chức năng: Khởi động Flask web (thread nền) + tunnel Cloudflared, in link public
Vai trò: Entry point - chạy 1 lệnh duy nhất cho web demo trên Colab/locally
File liên quan: webapp/app.py, webapp/templates/index.html

Cách dùng:
    python webapp/run_web.py              # Flask + Cloudflared tunnel (link public)
    python webapp/run_web.py --no-tunnel  # chỉ Flask localhost (triển khai nội bộ)
    python webapp/run_web.py --port 9000  # đổi port
"""

import argparse
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _start_flask(port: int) -> None:
    """
    Chạy Flask trong thread nền (daemon) để cell Colab không bị treo
    và tiến trình tunnel có thể giữ ở foreground.
    """
    from webapp.app import app as flask_app

    threading.Thread(
        target=flask_app.run,
        kwargs={"host": "0.0.0.0", "port": port, "use_reloader": False},
        daemon=True,
    ).start()
    # Chờ Flask sẵn sàng trước khi mở tunnel
    for _ in range(20):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
            break
        except Exception:  # noqa: BLE001 - server chưa up, chờ tiếp
            time.sleep(0.5)
    print(f"[web] Flask da san sang: http://localhost:{port}")


def _start_tunnel(port: int) -> str | None:
    """
    Mở Cloudflared tunnel tới Flask và parse link public từ stdout.

    Logic:
      - subprocess.Popen giữ tiến trình cloudflared sống
      - Duyệt từng dòng log, bắt URL dạng https://*.trycloudflare.com
    """
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 90
    for line in proc.stdout:
        print(line, end="")
        match = TUNNEL_URL_RE.search(line)
        if match:
            return match.group(0)
        if time.time() > deadline:
            print("[web][warn] Khong lay duoc link tunnel sau 90s")
            return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Chay Flask web + Cloudflared tunnel")
    parser.add_argument("--port", type=int, default=8080, help="Port Flask (mac dinh 8080)")
    parser.add_argument("--no-tunnel", action="store_true", help="Chi chay Flask localhost")
    args = parser.parse_args()

    _start_flask(args.port)

    if args.no_tunnel:
        print("Dang chay noi bo: http://localhost:{} (Ctrl+C de dung)".format(args.port))
    else:
        public_url = _start_tunnel(args.port)
        print("=" * 60)
        print("LINK PUBLIC - mo trong trinh duyet:", public_url)
        print("=" * 60)

    # Giữ tiến trình sống (tunnel + Flask) - nhấn Ctrl+C / dừng cell khi xong
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[web] Da dung web demo")


if __name__ == "__main__":
    main()
