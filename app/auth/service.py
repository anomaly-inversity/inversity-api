from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta, datetime, timezone
import jwt

from app.database.models import User, Workspace, WorkspaceUser, RoleEnum
from app.auth.schemas import UserCreate, UserLogin
from app.auth.utils import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.core.redis import redis_client
from app.core.config import settings


async def register_user(db: AsyncSession, user_in: UserCreate):
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
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

    return new_user


async def login_user(db: AsyncSession, user_in: UserLogin):
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_in.password, str(user.password_hash)):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    if redis_client.redis is not None:
        await redis_client.redis.setex(
            f"refresh_token:{user.id}:{refresh_token}",
            timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "valid",
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def refresh_user_token(refresh_token: str):
    try:
        payload = jwt.decode(
            refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if redis_client.redis is not None:
        is_valid = await redis_client.redis.get(
            f"refresh_token:{user_id}:{refresh_token}"
        )
        if not is_valid:
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

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


async def logout_user(user: User, token: str, refresh_token: str | None = None):
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
    except jwt.PyJWTError:
        pass

    if refresh_token and redis_client.redis is not None:
        await redis_client.redis.delete(f"refresh_token:{user.id}:{refresh_token}")
    else:
        if redis_client.redis is not None:
            keys = await redis_client.redis.keys(f"refresh_token:{user.id}:*")
            if keys:
                await redis_client.redis.delete(*keys)
