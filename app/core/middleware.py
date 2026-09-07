import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger()

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            process_time = time.perf_counter() - start_time
            response.headers["X-Request-ID"] = request_id

            logger.info(
                "request_completed",
                status_code=response.status_code,
                process_time_ms=round(process_time * 1000, 2),
            )

            return response
        except Exception as e:
            process_time = time.perf_counter() - start_time
            logger.error(
                "request_failed",
                error=str(e),
                process_time_ms=round(process_time * 1000, 2),
                exc_info=True
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
