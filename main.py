from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.core.redis import redis_client
from app.auth.router import router as auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    yield
    await redis_client.disconnect()

app = FastAPI(lifespan=lifespan)

app.include_router(auth_router)

@app.get("/")
def hello_world():
    return {
        "Hello": "World",
    }
