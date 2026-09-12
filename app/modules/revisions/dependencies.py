import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import (
    Document,
    DocumentReviewer,
    DocumentVersion,
    RoleEnum,
    User,
    Workspace,
    WorkspaceUser,
)
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.documents.dependencies import require_document

logger = structlog.get_logger()


async def require_version(
    workspace_id: str,
    document_id: str,
    version_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Document, DocumentVersion, Workspace, WorkspaceUser]:
    """Pastikan document milik workspace + version aktif milik document itu."""
    document, workspace, membership = await require_document(
        workspace_id, document_id, current_user, db
    )
    stmt = select(DocumentVersion).where(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document.id,
        DocumentVersion.deleted_at.is_(None),
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found"
        )
    return document, version, workspace, membership


async def _is_assigned_reviewer(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    stmt = select(DocumentReviewer.id).where(
        DocumentReviewer.document_id == document_id,
        DocumentReviewer.reviewer_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def require_interested(
    payload: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_version
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Document, DocumentVersion, Workspace, WorkspaceUser]:
    """Read guard: owner document, reviewer document, atau admin workspace."""
    document, version, workspace, membership = payload
    if str(document.user_id) == str(current_user.id):
        return payload
    if membership.role == RoleEnum.ADMIN:
        return payload
    if await _is_assigned_reviewer(db, document.id, current_user.id):
        return payload
    logger.warning(
        "revision_read_denied",
        user_id=current_user.id,
        document_id=document.id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only document owner, assigned reviewer, or workspace admin can view revisions",
    )


async def require_document_revision_viewer(
    workspace_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Document, Workspace, WorkspaceUser]:
    """Read guard level document: owner, reviewer manapun, atau admin workspace.

    Dipakai endpoint menyeluruh /documents/{document_id}/revisions.
    Tidak memandang siapa pembuat revisi.
    """
    document, workspace, membership = await require_document(
        workspace_id, document_id, current_user, db
    )
    if str(document.user_id) == str(current_user.id):
        return document, workspace, membership
    if membership.role == RoleEnum.ADMIN:
        return document, workspace, membership
    if await _is_assigned_reviewer(db, document.id, current_user.id):
        return document, workspace, membership
    logger.warning(
        "revision_document_read_denied",
        user_id=current_user.id,
        document_id=document.id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only document owner, assigned reviewer, or workspace admin can view revisions",
    )


async def require_reviewer_or_admin(
    payload: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_version
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[Document, DocumentVersion, Workspace, WorkspaceUser]:
    """Write guard: reviewer document atau admin workspace."""
    document, version, workspace, membership = payload
    if membership.role == RoleEnum.ADMIN:
        return payload
    if await _is_assigned_reviewer(db, document.id, current_user.id):
        return payload
    logger.warning(
        "revision_write_denied",
        user_id=current_user.id,
        document_id=document.id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only assigned reviewer or workspace admin can manage revisions",
    )
