from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import (
    Document,
    DocumentStatusEnum,
    DocumentVersion,
    Revision,
    RevisionStatusEnum,
)
from app.modules.revisions.schemas import (
    RevisionCreate,
    RevisionResponse,
    RevisionUpdate,
)

logger = structlog.get_logger()


def _to_response(revision: Revision) -> RevisionResponse:
    return RevisionResponse(
        id=str(revision.id),
        document_version_id=str(revision.document_version_id),
        reviewer_id=str(revision.reviewer_id),
        note=revision.note,
        status=revision.status,
        created_at=revision.created_at,
    )


def _active_filter(version_id: str):
    return (Revision.document_version_id == version_id) & (
        Revision.deleted_at.is_(None)
    )


async def create_revision(
    db: AsyncSession,
    document: Document,
    version: DocumentVersion,
    reviewer_id: str,
    payload: RevisionCreate,
) -> RevisionResponse:
    """Buat revisi. Efek samping: document + version menjadi REVISE. Status lain tetap."""
    revision = Revision(
        document_version_id=version.id,
        reviewer_id=reviewer_id,
        note=payload.note,
        status=RevisionStatusEnum.PENDING,
    )
    db.add(revision)
    document.status = DocumentStatusEnum.REVISE
    version.status = DocumentStatusEnum.REVISE
    await db.commit()
    await db.refresh(revision)
    logger.info(
        "create_revision_success",
        revision_id=revision.id,
        version_id=version.id,
    )
    return _to_response(revision)


async def list_revisions(
    db: AsyncSession, version_id: str, skip: int = 0, limit: int = 100
) -> tuple[list[RevisionResponse], int]:
    count_stmt = (
        select(func.count()).select_from(Revision).where(_active_filter(version_id))
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Revision)
        .where(_active_filter(version_id))
        .order_by(Revision.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows], total


async def list_document_revisions(
    db: AsyncSession, document_id: str, skip: int = 0, limit: int = 100
) -> tuple[list[RevisionResponse], int]:
    """List menyeluruh revisions sebuah document dari semua versions.

    Join Revision -> DocumentVersion by document_id.
    Revisions tetap ditampilkan walau version sudah di-soft-delete.
    Hanya revision aktif (deleted_at IS NULL), newest first.
    """
    base_filter = (DocumentVersion.document_id == document_id) & (
        Revision.deleted_at.is_(None)
    )
    join_cond = Revision.document_version_id == DocumentVersion.id

    count_stmt = (
        select(func.count())
        .select_from(Revision)
        .join(DocumentVersion, join_cond)
        .where(base_filter)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Revision)
        .join(DocumentVersion, join_cond)
        .where(base_filter)
        .order_by(Revision.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows], total


async def get_revision(db: AsyncSession, version_id: str, revision_id: str) -> Revision:
    stmt = select(Revision).where(
        Revision.id == revision_id,
        _active_filter(version_id),
    )
    revision = (await db.execute(stmt)).scalar_one_or_none()
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found"
        )
    return revision


async def update_revision(
    db: AsyncSession, revision: Revision, payload: RevisionUpdate
) -> RevisionResponse:
    revision.note = payload.note
    await db.commit()
    await db.refresh(revision)
    logger.info("update_revision_success", revision_id=revision.id)
    return _to_response(revision)


async def delete_revision(db: AsyncSession, revision: Revision) -> None:
    revision.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("delete_revision_success", revision_id=revision.id)


async def resolve_revision(
    db: AsyncSession, revision: Revision, actor_id: str, is_admin: bool
) -> RevisionResponse:
    """Resolve revisi. Hanya pembuat revisi atau admin workspace."""
    if str(revision.reviewer_id) != str(actor_id) and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the reviewer who created this revision or workspace admin can resolve it",
        )
    if revision.status != RevisionStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending revisions can be resolved",
        )
    revision.status = RevisionStatusEnum.RESOLVED
    await db.commit()
    await db.refresh(revision)
    logger.info("resolve_revision_success", revision_id=revision.id)
    return _to_response(revision)
