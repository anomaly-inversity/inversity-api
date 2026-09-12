from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import RoleEnum, User, WorkspaceUser
from app.modules.auth.utils import get_password_hash
from app.modules.users.schemas import (
    UserCreateByAdmin,
    UserUpdateByAdmin,
    UserWorkspaceResponse,
)

logger = structlog.get_logger()


def _to_response(user: User, membership: WorkspaceUser) -> UserWorkspaceResponse:
    return UserWorkspaceResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=membership.role,
        joined_at=membership.joined_at,
    )


async def list_workspace_users(
    db: AsyncSession, workspace_id: int, skip: int = 0, limit: int = 100
) -> tuple[list[UserWorkspaceResponse], int]:
    """List semua user yang terdaftar pada satu workspace."""
    count_stmt = (
        select(func.count())
        .select_from(WorkspaceUser)
        .where(WorkspaceUser.workspace_id == workspace_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(User, WorkspaceUser)
        .join(WorkspaceUser, WorkspaceUser.user_id == User.id)
        .where(WorkspaceUser.workspace_id == workspace_id)
        .order_by(WorkspaceUser.joined_at.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [_to_response(user, membership) for user, membership in rows], total


async def get_workspace_user_detail(
    db: AsyncSession, workspace_id: int, user_id: int
) -> UserWorkspaceResponse:
    """Detail satu user dalam workspace. 404 jika bukan member workspace itu."""
    stmt = (
        select(User, WorkspaceUser)
        .join(WorkspaceUser, WorkspaceUser.user_id == User.id)
        .where(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this workspace",
        )
    user, membership = row
    return _to_response(user, membership)


async def create_workspace_user(
    db: AsyncSession, workspace_id: int, payload: UserCreateByAdmin
) -> UserWorkspaceResponse:
    """Admin mendaftarkan user baru langsung ke workspace-nya."""
    logger.info(
        "admin_create_user_attempt", email=payload.email, workspace_id=workspace_id
    )
    stmt = select(User).where(User.email == payload.email)
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    new_user = User(
        email=payload.email,
        name=payload.name,
        password_hash=get_password_hash(payload.password),
    )
    db.add(new_user)
    await db.flush()

    membership = WorkspaceUser(
        workspace_id=workspace_id, user_id=new_user.id, role=payload.role
    )
    db.add(membership)
    await db.commit()
    await db.refresh(new_user)
    await db.refresh(membership)

    logger.info(
        "admin_create_user_success",
        user_id=new_user.id,
        workspace_id=workspace_id,
    )
    return _to_response(new_user, membership)


async def update_workspace_user(
    db: AsyncSession, workspace_id: int, user_id: int, payload: UserUpdateByAdmin
) -> UserWorkspaceResponse:
    """Admin update name/email/password (tabel users) dan role (tabel workspace_users)."""
    stmt = (
        select(User, WorkspaceUser)
        .join(WorkspaceUser, WorkspaceUser.user_id == User.id)
        .where(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this workspace",
        )
    user, membership = row

    if payload.email is not None and payload.email != user.email:
        stmt = select(User).where(User.email == payload.email)
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already in use"
            )
        user.email = payload.email

    if payload.name is not None:
        user.name = payload.name

    if payload.password is not None:
        user.password_hash = get_password_hash(payload.password)

    if payload.role is not None and payload.role != membership.role:
        if membership.role == RoleEnum.ADMIN and payload.role != RoleEnum.ADMIN:
            await _ensure_not_last_admin(db, workspace_id)
        membership.role = payload.role

    await db.commit()
    await db.refresh(user)
    await db.refresh(membership)

    logger.info("admin_update_user_success", user_id=user.id, workspace_id=workspace_id)
    return _to_response(user, membership)


async def delete_workspace_user(
    db: AsyncSession, workspace_id: int, user_id: int, current_user_id: int
) -> None:
    """Remove membership: hapus baris workspace_users, data users tetap ada."""
    if user_id == current_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself from the workspace",
        )

    stmt = select(WorkspaceUser).where(
        WorkspaceUser.workspace_id == workspace_id,
        WorkspaceUser.user_id == user_id,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this workspace",
        )

    if membership.role == RoleEnum.ADMIN:
        await _ensure_not_last_admin(db, workspace_id)

    await db.delete(membership)
    await db.commit()
    logger.info("admin_delete_user_success", user_id=user_id, workspace_id=workspace_id)


async def _ensure_not_last_admin(db: AsyncSession, workspace_id: int) -> None:
    count_stmt = (
        select(func.count())
        .select_from(WorkspaceUser)
        .where(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.role == RoleEnum.ADMIN,
        )
    )
    admin_count = (await db.execute(count_stmt)).scalar_one()
    if admin_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote or remove the last admin in workspace",
        )
