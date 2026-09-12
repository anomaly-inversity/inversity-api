from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import (
    Document,
    DocumentReviewer,
    ReviewRequest,
    ReviewStatusEnum,
    WorkspaceUser,
)
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentResponse,
    DocumentReviewerCreate,
    DocumentReviewerResponse,
    DocumentUpdate,
    NeedReviewItem,
)

logger = structlog.get_logger()


def _to_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(document.id),
        workspace_id=str(document.workspace_id),
        user_id=str(document.user_id),
        title=document.title,
        status=document.status,
        created_at=document.created_at,
    )


def _to_reviewer_response(reviewer: DocumentReviewer) -> DocumentReviewerResponse:
    return DocumentReviewerResponse(
        id=reviewer.id,
        document_id=str(reviewer.document_id),
        reviewer_id=str(reviewer.reviewer_id),
        is_mentor=reviewer.is_mentor,
    )


async def create_document(
    db: AsyncSession, workspace_id: str, user_id: str, payload: DocumentCreate
) -> DocumentResponse:
    """Buat document baru. Owner = current_user, status awal draft."""
    logger.info("create_document_attempt", user_id=user_id, workspace_id=workspace_id)
    document = Document(
        workspace_id=workspace_id,
        user_id=user_id,
        title=payload.title,
        status="draft",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    logger.info("create_document_success", document_id=document.id)
    return _to_response(document)


async def list_documents(
    db: AsyncSession, workspace_id: str, skip: int = 0, limit: int = 100
) -> tuple[list[DocumentResponse], int]:
    """List document dalam satu workspace (member only)."""
    count_stmt = (
        select(func.count())
        .select_from(Document)
        .where(Document.workspace_id == workspace_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    documents = (await db.execute(stmt)).scalars().all()
    return [_to_response(d) for d in documents], total


async def get_document(db: AsyncSession, document: Document) -> DocumentResponse:
    """Detail satu document (dependency sudah validasi kepemilikan workspace)."""
    return _to_response(document)


async def list_need_reviews(
    db: AsyncSession,
    workspace_id: str,
    reviewer_id: str,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[NeedReviewItem], int]:
    """List document yang perlu current_user approve/reject.

    Kriteria: ada ReviewRequest pending di mana reviewer_id = current_user
    dan document belum punya mentor (masih actionable, accept tidak kena 409).
    """
    base = (
        select(Document, ReviewRequest)
        .join(ReviewRequest, ReviewRequest.document_id == Document.id)
        .where(
            Document.workspace_id == workspace_id,
            ReviewRequest.reviewer_id == reviewer_id,
            ReviewRequest.status == ReviewStatusEnum.PENDING,
        )
        .where(
            ~select(DocumentReviewer.id)
            .where(
                DocumentReviewer.document_id == Document.id,
                DocumentReviewer.is_mentor.is_(True),
            )
            .exists()
        )
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = base.order_by(ReviewRequest.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()

    items = [
        NeedReviewItem(
            id=str(doc.id),
            workspace_id=str(doc.workspace_id),
            user_id=str(doc.user_id),
            title=doc.title,
            status=doc.status,
            created_at=doc.created_at,
            review_request_id=str(req.id),
            review_requested_at=req.created_at,
        )
        for doc, req in rows
    ]
    return items, total


async def update_document(
    db: AsyncSession, document: Document, payload: DocumentUpdate
) -> DocumentResponse:
    """Update title/status. Caller (router) sudah memastikan owner."""
    if payload.title is not None:
        document.title = payload.title
    if payload.status is not None:
        document.status = payload.status
    await db.commit()
    await db.refresh(document)
    logger.info("update_document_success", document_id=document.id)
    return _to_response(document)


async def delete_document(db: AsyncSession, document: Document) -> None:
    """Hapus document (owner only). Review request terkait ikut terhapus via cascade manual."""
    from datetime import datetime, timezone

    from app.database.models import DocumentVersion, ReviewRequest

    await db.execute(
        delete(ReviewRequest).where(ReviewRequest.document_id == document.id)
    )
    await db.execute(
        delete(DocumentReviewer).where(DocumentReviewer.document_id == document.id)
    )
    # Soft-delete versions agar revisions tetap ada di database (tidak orphan FK).
    versions_stmt = select(DocumentVersion).where(
        DocumentVersion.document_id == document.id,
        DocumentVersion.deleted_at.is_(None),
    )
    versions = (await db.execute(versions_stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    for version in versions:
        version.deleted_at = now
    await db.delete(document)
    await db.commit()
    logger.info("delete_document_success", document_id=document.id)


async def list_reviewers(
    db: AsyncSession, document_id: str
) -> tuple[list[DocumentReviewerResponse], int]:
    """List reviewer/pembimbing sebuah document."""
    count_stmt = (
        select(func.count())
        .select_from(DocumentReviewer)
        .where(DocumentReviewer.document_id == document_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(DocumentReviewer).where(DocumentReviewer.document_id == document_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_reviewer_response(r) for r in rows], total


async def add_reviewer_manual(
    db: AsyncSession,
    workspace_id: str,
    document: Document,
    payload: DocumentReviewerCreate,
) -> DocumentReviewerResponse:
    """Admin input manual reviewer. Reviewer wajib member workspace."""
    stmt = select(WorkspaceUser).where(
        WorkspaceUser.workspace_id == workspace_id,
        WorkspaceUser.user_id == payload.reviewer_id,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reviewer not found in this workspace",
        )

    stmt = select(DocumentReviewer).where(
        DocumentReviewer.document_id == document.id,
        DocumentReviewer.reviewer_id == payload.reviewer_id,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reviewer already assigned to this document",
        )

    if payload.is_mentor:
        stmt = select(DocumentReviewer).where(
            DocumentReviewer.document_id == document.id,
            DocumentReviewer.is_mentor.is_(True),
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document already has a mentor",
            )

    reviewer = DocumentReviewer(
        document_id=document.id,
        reviewer_id=payload.reviewer_id,
        is_mentor=payload.is_mentor,
    )
    db.add(reviewer)
    await db.commit()
    await db.refresh(reviewer)
    logger.info(
        "add_reviewer_manual_success",
        document_id=document.id,
        reviewer_id=payload.reviewer_id,
    )
    return _to_reviewer_response(reviewer)


async def remove_reviewer(
    db: AsyncSession, document_id: str, reviewer_row_id: int
) -> None:
    """Admin hapus reviewer dari document."""
    stmt = select(DocumentReviewer).where(
        DocumentReviewer.id == reviewer_row_id,
        DocumentReviewer.document_id == document_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer not found"
        )
    await db.delete(row)
    await db.commit()
    logger.info("remove_reviewer_success", reviewer_row_id=reviewer_row_id)
