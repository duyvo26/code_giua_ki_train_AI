"""
File: main.py
Chức năng: Điểm khởi đầu ứng dụng FastAPI - khởi tạo app, CORS, middleware, router
Vai trò: Entry point - chỉ lắp ráp các thành phần, không chứa business logic
File liên quan: app/routers/sentiment_router.py, app/utils/response.py, app/config.py
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import get_logger
from app.routers.sentiment_router import router as sentiment_router
from app.services.sentiment_service import ModelNotFoundError, sentiment_service
from app.utils.response import register_exception_handlers

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """
    Factory tạo FastAPI app: CORS, exception handlers, router.

    Logic:
      - CORS cho phép frontend (origin khai báo trong .env) gọi API
      - register_exception_handlers: mọi lỗi trả ApiError chuẩn
      - include_router: gắn endpoint /predict và /health
      - Startup: tải model; thiếu model chỉ log warning, không sập server
        (model có thể được nạp lại khi predict)
    """
    app = FastAPI(
        title="Sentiment Analysis API (PhoBERT fine-tuned)",
        description="Phan loai cam xuc binh luan tieng Viet - chay noi bo, khong gui du lieu ra ngoai",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(sentiment_router)

    @app.on_event("startup")
    async def on_startup() -> None:
        """Tải model khi khởi động; nếu thiếu thì ghi warning (chờ fine-tune)."""
        try:
            sentiment_service.load()
            logger.info("Startup hoan tat - mo hinh san sang")
        except ModelNotFoundError as exc:
            logger.warning(str(exc))

    return app


app = create_app()
