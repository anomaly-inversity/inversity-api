from fastapi import FastAPI
from contextlib import asynccontextmanager
from scalar_fastapi import get_scalar_api_reference

from app.core.redis import redis_client
from app.auth.router import router as auth_router
from app.core.logger import setup_logging
from app.core.middleware import LoggingMiddleware

setup_logging(pretty=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    yield
    await redis_client.disconnect()


app = FastAPI(lifespan=lifespan, docs_url=None)
app.add_middleware(LoggingMiddleware)

app.include_router(auth_router)


@app.get("/docs", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


@app.get("/")
def hello_world():
    return {
        "message": "Hello World",
    }
