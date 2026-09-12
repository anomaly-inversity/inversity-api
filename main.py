import asyncio
import logging
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from scalar_fastapi import get_scalar_api_reference

from app.core import logger
from app.core.redis import redis_client
from app.database.session import Base, engine
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.workspaces.router import router as workspaces_router
from app.core.logger import setup_logging
from app.core.middleware import LoggingMiddleware
from app.core.config import settings

setup_logging(pretty=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    yield
    await redis_client.disconnect()


app = FastAPI(lifespan=lifespan, docs_url=None)
app.add_middleware(LoggingMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(workspaces_router)


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


async def auto_migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    logger.info("database migrated successfully")


if __name__ == "__main__":
    asyncio.run(auto_migrate())
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        log_level=logging.ERROR,
    )
