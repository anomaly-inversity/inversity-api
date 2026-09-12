from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta, datetime, timezone
import jwt
import structlog

from app.database.models import User, Workspace, WorkspaceUser, RoleEnum
from app.modules.auth.schemas import UserCreate, UserLogin
from app.modules.auth.utils import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.core.redis import redis_client
from app.core.config import settings

logger = structlog.get_logger()


async def register_user(db: AsyncSession, user_in: UserCreate):
    logger.info("register_user_attempt", email=user_in.email)
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        logger.warning(
            "register_user_failed",
            reason="email_already_registered",
            email=user_in.email,
        )
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=user_in.email,
        name=user_in.name,
        password_hash=get_password_hash(user_in.password),
    )
    db.add(new_user)
    await db.flush()

    new_workspace = Workspace(name=user_in.workspace_name, created_by=new_user.id)
    db.add(new_workspace)
    await db.flush()

    new_workspace_user = WorkspaceUser(
        workspace_id=new_workspace.id, user_id=new_user.id, role=RoleEnum.ADMIN
    )
    db.add(new_workspace_user)
    await db.commit()

    logger.info("register_user_success", user_id=new_user.id)
    return new_user


async def login_user(db: AsyncSession, user_in: UserLogin):
    logger.info("login_user_attempt", email=user_in.email)
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_in.password, str(user.password_hash)):
        logger.warning(
            "login_user_failed", reason="incorrect_credentials", email=user_in.email
        )
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    if redis_client.redis is not None:
        await redis_client.redis.setex(
            f"refresh_token:{user.id}:{refresh_token}",
            timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "valid",
        )

    logger.info("login_user_success", user_id=user.id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def refresh_user_token(refresh_token: str):
    logger.info("refresh_token_attempt")
    try:
        payload = jwt.decode(
            refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            logger.warning("refresh_token_failed", reason="missing_sub")
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except jwt.PyJWTError as e:
        logger.warning("refresh_token_failed", reason="jwt_decode_error", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if redis_client.redis is not None:
        is_valid = await redis_client.redis.get(
            f"refresh_token:{user_id}:{refresh_token}"
        )
        if not is_valid:
            logger.warning(
                "refresh_token_failed", reason="revoked_or_expired", user_id=user_id
            )
            raise HTTPException(
                status_code=401, detail="Refresh token revoked or expired"
            )

    access_token = create_access_token(data={"sub": user_id})
    new_refresh_token = create_refresh_token(data={"sub": user_id})

    if redis_client.redis is not None:
        await redis_client.redis.delete(f"refresh_token:{user_id}:{refresh_token}")
        await redis_client.redis.setex(
            f"refresh_token:{user_id}:{new_refresh_token}",
            timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "valid",
        )

    logger.info("refresh_token_success", user_id=user_id)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


async def logout_user(user: User, token: str, refresh_token: str | None = None):
    logger.info("logout_user_attempt", user_id=user.id)
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        exp = payload.get("exp")
        if exp:
            now = datetime.now(timezone.utc).timestamp()
            ttl = int(exp - now)
            if ttl > 0 and redis_client.redis is not None:
                await redis_client.redis.setex(f"bl_{token}", ttl, "blacklisted")
    except jwt.PyJWTError as e:
        logger.warning("logout_user_jwt_error", reason="jwt_decode_error", error=str(e))

    if refresh_token and redis_client.redis is not None:
        await redis_client.redis.delete(f"refresh_token:{user.id}:{refresh_token}")
    else:
        if redis_client.redis is not None:
            keys = await redis_client.redis.keys(f"refresh_token:{user.id}:*")
            if keys:
                await redis_client.redis.delete(*keys)

    logger.info("logout_user_success", user_id=user.id)
