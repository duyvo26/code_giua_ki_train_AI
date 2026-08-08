"""
File: config.py
Chức năng: Quản lý cấu hình ứng dụng, nạp biến môi trường từ .env bằng Pydantic Settings
Vai trò: Config - định nghĩa DIR_ROOT (thư mục gốc tuyệt đối) và các cài đặt chạy API
File liên quan: app/main.py, app/logger.py, app/services/sentiment_service.py, .env
"""

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str | None:
    """
    Tìm file .env từ thư mục hiện tại ngược lên các cấp cha.
    Thư mục chứa .env được định nghĩa là DIR_ROOT - mọi đường dẫn trong
    dự án đều dựa trên DIR_ROOT để tránh lỗi khi chạy từ nơi khác.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            return str(candidate)
    return None


# DIR_ROOT: thư mục gốc tuyệt đối của dự án (nơi chứa .env)
ENV_FILE = _find_env_file()
DIR_ROOT = Path(ENV_FILE).parent if ENV_FILE else Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Cấu hình toàn cục, nạp từ file .env (nếu có) với giá trị mặc định phù hợp.

    Logic:
      - Pydantic Settings tự đọc biến môi trường + file .env
      - ENV=development bật DEBUG log, production tắt DEBUG
      - MODEL_PATH có thể để tương đối (tính từ DIR_ROOT) hoặc tuyệt đối
    """

    ENV: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    ALLOW_ORIGINS: str = '["http://localhost:5173"]'
    MODEL_PATH: str = "models/best_model"
    MAX_SEQ_LEN: int = 256

    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE else f"{DIR_ROOT}/.env",
        extra="ignore",
    )

    @property
    def allow_origins_list(self) -> list[str]:
        """
        Chuyển chuỗi JSON ALLOW_ORIGINS từ .env thành list cho CORS.
        Nếu chuỗi không hợp lệ, fallback về localhost mặc định.
        """
        try:
            return json.loads(self.ALLOW_ORIGINS)
        except json.JSONDecodeError:
            return ["http://localhost:5173"]

    @property
    def model_path_resolved(self) -> Path:
        """
        Đường dẫn tuyệt đối tới thư mục mô hình fine-tuned.
        Hỗ trợ cả đường dẫn tương đối (tính từ DIR_ROOT) lẫn tuyệt đối.
        """
        path = Path(self.MODEL_PATH)
        if not path.is_absolute():
            path = DIR_ROOT / path
        return path


settings = Settings()
