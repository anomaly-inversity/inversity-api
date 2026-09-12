from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import Document, User, Workspace, WorkspaceUser
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.workspaces.dependencies import require_workspace_member

logger = structlog.get_logger()


async def require_document(
    workspace_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Document, Workspace, WorkspaceUser]:
    """Pastikan workspace ada, user member, dan document milik workspace itu."""
    workspace, membership = await require_workspace_member(
        workspace_id, current_user, db
    )

    stmt = select(Document).where(
        Document.id == document_id,
        Document.workspace_id == workspace_id,
    )
    document = (await db.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document, workspace, membership


async def require_document_owner(
    payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
    current_user: User = Depends(get_current_user),
) -> Document:
    """Pastikan current_user adalah owner/uploader document."""
    document, _, _ = payload
    if str(document.user_id) != str(current_user.id):
        logger.warning(
            "document_owner_denied",
            user_id=current_user.id,
            document_id=document.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only document owner can perform this action",
        )
    return document
