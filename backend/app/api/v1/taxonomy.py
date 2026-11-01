from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import admin, database
from app.api.idempotency import IdempotentRoute
from app.api.pagination import page
from app.api.serialization import record
from app.core.errors import fail
from app.models.taxonomy import Issue, Outlet, PublicationType, Subject, Template
from app.services.notifications import audit

router = APIRouter(prefix="/admin", route_class=IdempotentRoute)


@router.get("/subjects")
def list_subjects(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, Subject, select(Subject), limit, cursor)


@router.get("/outlets")
def list_outlets(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, Outlet, select(Outlet), limit, cursor)


@router.get("/templates")
def list_templates(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, Template, select(Template), limit, cursor)


@router.get("/issues")
def list_issues(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, Issue, select(Issue), limit, cursor)


class SubjectInput(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    name: str = Field(min_length=1, max_length=200)


class TypeInput(BaseModel):
    code: str = Field(pattern=r"^[A-Z_]+$", max_length=50)
    name: str = Field(min_length=1, max_length=200)


class OutletInput(SubjectInput):
    type_id: UUID


class Rules(BaseModel):
    abstract_required: bool = True
    min_words: int = Field(default=100, ge=1)
    max_words: int = Field(default=20000, ge=1, le=100000)


class TemplateInput(BaseModel):
    outlet_id: UUID
    validation_schema: Rules
    instructions: str = Field(max_length=20000)


def save(db, user, item, action):
    db.add(item)
    db.flush()
    audit(db, user, action, item)
    return record(item)


@router.post("/subjects", status_code=201)
def subject(data: SubjectInput, user=Depends(admin), db=Depends(database)):
    return save(db, user, Subject(**data.model_dump()), "CREATE_SUBJECT")


@router.post("/publication-types", status_code=201)
def kind(data: TypeInput, user=Depends(admin), db=Depends(database)):
    return save(db, user, PublicationType(**data.model_dump()), "CREATE_TYPE")


@router.post("/outlets", status_code=201)
def outlet(data: OutletInput, user=Depends(admin), db=Depends(database)):
    if not db.get(PublicationType, data.type_id):
        fail("TYPE_NOT_FOUND", 422)
    return save(db, user, Outlet(**data.model_dump()), "CREATE_OUTLET")


@router.post("/templates", status_code=201)
def template(data: TemplateInput, user=Depends(admin), db=Depends(database)):
    if (
        not db.get(Outlet, data.outlet_id)
        or data.validation_schema.min_words > data.validation_schema.max_words
    ):
        fail("INVALID_TEMPLATE", 422)
    db.execute(select(func.pg_advisory_xact_lock(17005)))
    version = (
        db.scalar(select(func.max(Template.version)).where(Template.outlet_id == data.outlet_id))
        or 0
    ) + 1
    return save(
        db,
        user,
        Template(
            outlet_id=data.outlet_id,
            version=version,
            validation_schema=data.validation_schema.model_dump(),
            instructions=data.instructions,
        ),
        "CREATE_TEMPLATE_VERSION",
    )


class IssueInput(BaseModel):
    outlet_id: UUID
    volume: str = Field(min_length=1, max_length=100)
    issue_number: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)


@router.post("/issues", status_code=201)
def issue(data: IssueInput, user=Depends(admin), db=Depends(database)):
    if not db.get(Outlet, data.outlet_id):
        fail("OUTLET_NOT_FOUND", 422)
    return save(db, user, Issue(**data.model_dump()), "CREATE_ISSUE")
