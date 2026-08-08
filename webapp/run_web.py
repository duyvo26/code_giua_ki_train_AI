"""
File: run_web.py
Chức năng: Khởi động Flask web (thread nền) + tunnel Cloudflared, in link public
Vai trò: Entry point - chạy 1 lệnh duy nhất cho web demo trên Colab/locally
File liên quan: webapp/app.py, webapp/templates/index.html

Cách dùng:
    python webapp/run_web.py              # Flask + Cloudflared tunnel (link public)
    python webapp/run_web.py --no-tunnel  # chỉ Flask localhost (triển khai nội bộ)
    python webapp/run_web.py --port 9000  # đổi port (tự tìm port trống nếu bận)
"""

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
# Binary cloudflared chính thức cho Linux (Colab) - tải về khi pip không cài được
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/"
    "download/cloudflared-linux-amd64"
)
CLOUDFLARED_BIN = PROJECT_ROOT / "webapp" / "cloudflared"


def _find_free_port(start: int = 8080) -> int:
    """
    Tìm port trống bắt đầu từ start (tăng dần tối đa 20 port).

    Logic:
      - Thử bind socket vào từng port; thành công nghĩa là port trống
      - Tránh lỗi "Address already in use" khi Flask cũ còn giữ port
    """
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Khong tim duoc port trong tu {start} den {start + 20}")


def _start_flask(port: int) -> int:
    """
    Chạy Flask trong thread nền (daemon) để cell Colab không bị treo.

    Trả về port thực tế đang chạy (có thể khác port truyền vào nếu bị bận).
    """
    from webapp.app import app as flask_app

    actual_port = _find_free_port(port)
    if actual_port != port:
        print(f"[web][warn] Port {port} dang duoc dung - chuyen sang port {actual_port}")

    threading.Thread(
        target=flask_app.run,
        kwargs={"host": "0.0.0.0", "port": actual_port, "use_reloader": False},
        daemon=True,
    ).start()
    # Chờ Flask sẵn sàng trước khi mở tunnel
    for _ in range(20):
        try:
            urllib.request.urlopen(
                f"http://localhost:{actual_port}/health", timeout=2
            )
            break
        except Exception:  # noqa: BLE001 - server chưa up, chờ tiếp
            time.sleep(0.5)
    print(f"[web] Flask da san sang: http://localhost:{actual_port}")
    return actual_port


def _find_cloudflared() -> str:
    """
    Tìm binary cloudflared: ưu tiên PATH, nếu không có thì tải binary
    chính thức từ GitHub về webapp/cloudflared.

    Logic:
      - pip package 'cloudflared' đôi khi không đưa binary vào PATH trên Colab
      - Fallback tải file binary duy nhất (linux-amd64) rồi chmod +x
    """
    path = shutil.which("cloudflared")
    if path:
        return path

    if CLOUDFLARED_BIN.exists():
        return str(CLOUDFLARED_BIN)

    print("[web] Khong thay cloudflared tren PATH - tai binary tu GitHub...")
    urllib.request.urlretrieve(CLOUDFLARED_URL, CLOUDFLARED_BIN)
    os.chmod(CLOUDFLARED_BIN, 0o755)
    print(f"[web] Da tai: {CLOUDFLARED_BIN}")
    return str(CLOUDFLARED_BIN)


def _start_tunnel(port: int) -> str | None:
    """
    Mở Cloudflared tunnel tới Flask và parse link public từ stdout.

    Logic:
      - subprocess.Popen giữ tiến trình cloudflared sống
      - Duyệt từng dòng log, bắt URL dạng https://*.trycloudflare.com
    """
    binary = _find_cloudflared()
    proc = subprocess.Popen(
        [binary, "tunnel", "--url", f"http://localhost:{port}"],
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

    actual_port = _start_flask(args.port)

    if args.no_tunnel:
        print(f"Dang chay noi bo: http://localhost:{actual_port} (Ctrl+C de dung)")
    else:
        public_url = _start_tunnel(actual_port)
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
