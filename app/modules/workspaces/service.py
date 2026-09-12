import secrets

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import RoleEnum, Workspace, WorkspaceUser
from app.modules.workspaces.schemas import (
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)

logger = structlog.get_logger()


def _to_response(
    workspace: Workspace, membership: WorkspaceUser, member_count: int
) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        invite_code=workspace.invite_code,
        created_by=workspace.created_by,
        created_at=workspace.created_at,
        role=membership.role,
        member_count=member_count,
    )


async def _count_members(db: AsyncSession, workspace_id: int) -> int:
    count_stmt = (
        select(func.count())
        .select_from(WorkspaceUser)
        .where(WorkspaceUser.workspace_id == workspace_id)
    )
    return (await db.execute(count_stmt)).scalar_one()


async def _generate_unique_invite_code(db: AsyncSession) -> str:
    """Generate invite_code unik, retry jika collision."""
    for _ in range(5):
        code = secrets.token_urlsafe(8)
        stmt = select(Workspace.id).where(Workspace.invite_code == code)
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            return code
    # Fallback: kode lebih panjang agar collision praktis mustahil.
    return secrets.token_urlsafe(16)


async def list_user_workspaces(
    db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100
) -> tuple[list[WorkspaceResponse], int]:
    """List semua workspace di mana user adalah member."""
    count_stmt = (
        select(func.count())
        .select_from(WorkspaceUser)
        .where(WorkspaceUser.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Workspace, WorkspaceUser)
        .join(WorkspaceUser, WorkspaceUser.workspace_id == Workspace.id)
        .where(WorkspaceUser.user_id == user_id)
        .order_by(Workspace.id.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    if not rows:
        return [], total

    workspace_ids = [workspace.id for workspace, _ in rows]
    count_rows = (
        await db.execute(
            select(WorkspaceUser.workspace_id, func.count())
            .where(WorkspaceUser.workspace_id.in_(workspace_ids))
            .group_by(WorkspaceUser.workspace_id)
        )
    ).all()
    counts = {workspace_id: count for workspace_id, count in count_rows}

    return [
        _to_response(workspace, membership, counts.get(workspace.id, 0))
        for workspace, membership in rows
    ], total


async def get_workspace_detail(
    db: AsyncSession, workspace_id: int, user_id: int
) -> WorkspaceResponse:
    """Detail satu workspace. 404 jika workspace tidak ada atau user bukan member."""
    stmt = (
        select(Workspace, WorkspaceUser)
        .join(
            WorkspaceUser,
            WorkspaceUser.workspace_id == Workspace.id,
        )
        .where(
            Workspace.id == workspace_id,
            WorkspaceUser.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    workspace, membership = row
    member_count = await _count_members(db, workspace_id)
    return _to_response(workspace, membership, member_count)


async def create_workspace(
    db: AsyncSession, user_id: int, payload: WorkspaceCreate
) -> WorkspaceResponse:
    """Buat workspace baru. Creator otomatis jadi ADMIN."""
    logger.info("create_workspace_attempt", user_id=user_id, name=payload.name)
    invite_code = await _generate_unique_invite_code(db)

    workspace = Workspace(
        name=payload.name,
        invite_code=invite_code,
        created_by=user_id,
    )
    db.add(workspace)
    await db.flush()

    membership = WorkspaceUser(
        workspace_id=workspace.id, user_id=user_id, role=RoleEnum.ADMIN
    )
    db.add(membership)
    await db.commit()
    await db.refresh(workspace)
    await db.refresh(membership)

    logger.info("create_workspace_success", user_id=user_id, workspace_id=workspace.id)
    return _to_response(workspace, membership, 1)


async def update_workspace(
    db: AsyncSession, workspace_id: int, user_id: int, payload: WorkspaceUpdate
) -> WorkspaceResponse:
    """Update nama workspace. Caller (router) sudah memastikan ADMIN."""
    stmt = select(Workspace).where(Workspace.id == workspace_id)
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    workspace.name = payload.name
    await db.commit()
    await db.refresh(workspace)

    stmt = select(WorkspaceUser).where(
        WorkspaceUser.workspace_id == workspace_id,
        WorkspaceUser.user_id == user_id,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()
    # Seharusnya tidak terjadi karena router sudah cek admin, tapi tetap aman.
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    member_count = await _count_members(db, workspace_id)
    logger.info("update_workspace_success", workspace_id=workspace_id)
    return _to_response(workspace, membership, member_count)


async def delete_workspace(db: AsyncSession, workspace_id: int) -> None:
    """Hard delete: hapus semua membership lalu workspace-nya."""
    stmt = select(Workspace).where(Workspace.id == workspace_id)
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    await db.execute(
        delete(WorkspaceUser).where(WorkspaceUser.workspace_id == workspace_id)
    )
    await db.delete(workspace)
    await db.commit()
    logger.info("delete_workspace_success", workspace_id=workspace_id)
