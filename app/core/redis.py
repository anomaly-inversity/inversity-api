import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logger import logger

class RedisClient:
    def __init__(self):
        self.redis = None

    async def connect(self):
        self.redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("redis_connected", url=settings.REDIS_URL)

    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            logger.info("redis_disconnected")

redis_client = RedisClient()
