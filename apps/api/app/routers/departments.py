"""CRUD router for `departments`.

Reference data — small, rarely-changing table. Full CRUD is exposed mainly
so an admin UI (or a seed script) can manage it without a raw DB
connection; nothing here calls the AI provider.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Department

router = APIRouter()


# --- Schemas -------------------------------------------------------------


class DepartmentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_email: EmailStr | None = None


class DepartmentRead(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


# --- Routes ----------------------------------------------------------


@router.get("", response_model=list[DepartmentRead])
async def list_departments(db: AsyncSession = Depends(get_db)) -> list[Department]:
    result = await db.execute(select(Department).order_by(Department.name))
    return list(result.scalars().all())


@router.get("/{department_id}", response_model=DepartmentRead)
async def get_department(
    department_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Department:
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    return department


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate, db: AsyncSession = Depends(get_db)
) -> Department:
    department = Department(**payload.model_dump())
    db.add(department)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A department with that name already exists"
        ) from exc
    await db.refresh(department)
    return department


@router.patch("/{department_id}", response_model=DepartmentRead)
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
) -> Department:
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(department, field, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A department with that name already exists"
        ) from exc
    await db.refresh(department)
    return department


@router.delete(
    "/{department_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_department(
    department_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    await db.delete(department)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Department is still referenced by categories/complaints",
        ) from exc
