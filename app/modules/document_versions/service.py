from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import Document, DocumentVersion
from app.modules.document_versions.schemas import (
    DocumentVersionCreate,
    DocumentVersionResponse,
    DocumentVersionUpdate,
)

logger = structlog.get_logger()


def _to_response(version: DocumentVersion) -> DocumentVersionResponse:
    return DocumentVersionResponse(
        id=str(version.id),
        document_id=str(version.document_id),
        file_path=version.file_path,
        ai_summary=version.ai_summary,
        ai_detection_score=version.ai_detection_score,
        status=version.status,
        created_at=version.created_at,
    )


def _active_filter(document_id: str):
    """Filter versi aktif: milik document ini dan belum di-soft-delete."""
    return (DocumentVersion.document_id == document_id) & (
        DocumentVersion.deleted_at.is_(None)
    )


async def create_version(
    db: AsyncSession, document: Document, payload: DocumentVersionCreate
) -> DocumentVersionResponse:
    """Buat version baru. Caller (router) sudah memastikan owner via require_document_owner."""
    logger.info("create_version_attempt", document_id=document.id)
    version = DocumentVersion(
        document_id=document.id,
        file_path=payload.file_path,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    logger.info("create_version_success", version_id=version.id)
    return _to_response(version)


async def list_versions(
    db: AsyncSession, document_id: str, skip: int = 0, limit: int = 100
) -> tuple[list[DocumentVersionResponse], int]:
    """List versi aktif sebuah document (member workspace). Revisions tetap ada walau versi di-soft-delete."""
    count_stmt = (
        select(func.count())
        .select_from(DocumentVersion)
        .where(_active_filter(document_id))
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(DocumentVersion)
        .where(_active_filter(document_id))
        .order_by(DocumentVersion.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(v) for v in rows], total


async def get_version(
    db: AsyncSession, document_id: str, version_id: str
) -> DocumentVersion:
    """Detail satu versi aktif. 404 jika tidak milik document ini atau sudah di-soft-delete."""
    stmt = select(DocumentVersion).where(
        DocumentVersion.id == version_id,
        _active_filter(document_id),
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found"
        )
    return version


async def update_version(
    db: AsyncSession, version: DocumentVersion, payload: DocumentVersionUpdate
) -> DocumentVersionResponse:
    """Update file_path versi (owner only)."""
    version.file_path = payload.file_path
    await db.commit()
    await db.refresh(version)
    logger.info("update_version_success", version_id=version.id)
    return _to_response(version)


async def delete_version(db: AsyncSession, version: DocumentVersion) -> None:
    """Soft delete versi (owner only). Set deleted_at, row + revisions tetap ada di database."""
    version.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("delete_version_success", version_id=version.id)
