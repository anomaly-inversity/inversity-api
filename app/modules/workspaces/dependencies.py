from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import RoleEnum, User, Workspace, WorkspaceUser
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user

logger = structlog.get_logger()


async def require_workspace_member(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Workspace, WorkspaceUser]:
    """Pastikan workspace ada dan current_user adalah member. 404 jika bukan member."""
    stmt = select(Workspace).where(Workspace.id == workspace_id)
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    stmt = select(WorkspaceUser).where(
        WorkspaceUser.workspace_id == workspace_id,
        WorkspaceUser.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()
    if membership is None:
        logger.warning(
            "workspace_member_denied",
            user_id=current_user.id,
            workspace_id=workspace_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    return workspace, membership


async def require_workspace_admin(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Workspace, WorkspaceUser]:
    """Pastikan workspace ada dan current_user adalah ADMIN di workspace itu."""
    workspace, membership = await require_workspace_member(
        workspace_id, current_user, db
    )

    if membership.role != RoleEnum.ADMIN:
        logger.warning(
            "workspace_admin_denied",
            user_id=current_user.id,
            workspace_id=workspace_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this workspace",
        )

    return workspace, membership
