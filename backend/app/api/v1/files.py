import io
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi import File as Upload
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import current_user, database, roles
from app.api.idempotency import IdempotentRoute
from app.api.serialization import record
from app.core.config import get_settings
from app.core.errors import fail
from app.integrations.storage import storage
from app.models.articles import Article, ArticleVersion, File
from app.services.files import upload
from app.services.workflow import can_read, owner

router = APIRouter(route_class=IdempotentRoute)


@router.post("/files", status_code=201)
async def create(
    file: UploadFile = Upload(...),
    kind: str = Form(...),
    article_id: UUID | None = Form(None),
    user=Depends(current_user),
    db=Depends(database),
):
    if article_id:
        article = db.get(Article, article_id)
        if not article:
            fail("ARTICLE_NOT_FOUND", 404)
        owner(article, user)
    cfg = get_settings()
    maximum = cfg.payment_proof_max_bytes if kind == "PROOF" else cfg.manuscript_max_bytes
    data = await file.read(maximum + 1)
    if len(data) > maximum:
        fail("FILE_TOO_LARGE", 413)
    return record(
        upload(db, user, kind, article_id, file.filename, file.content_type, data), ("storage_key",)
    )


@router.get("/files/{file_id}/download")
def download(file_id: UUID, user=Depends(current_user), db=Depends(database)):
    file = db.get(File, file_id)
    if not file or file.scan_status != "CLEAN":
        fail("FILE_NOT_FOUND", 404)
    if file.owner_user_id != user.id and "ADMIN" not in roles(db, user):
        if file.kind != "MANUSCRIPT" or not file.article_id:
            fail("FILE_NOT_FOUND", 404)
        can_read(db, db.get(Article, file.article_id), user)
        submitted = db.scalar(
            select(ArticleVersion.id).where(
                ArticleVersion.manuscript_file_id == file.id,
                ArticleVersion.submitted_at.is_not(None),
            )
        )
        if not submitted:
            fail("FILE_NOT_FOUND", 404)
    return StreamingResponse(
        io.BytesIO(storage().get(file.storage_key)),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file.id}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
