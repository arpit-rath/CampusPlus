"""CRUD router for `categories`.

Reference data mapping a category slug (wifi, electrical, sanitation, ...)
to its default department. `category.slug` is the value AGENTS.md's AI
schema (`app/ai/schemas.py`, Track B) is expected to emit for `category`
— this router just persists/serves the mapping, it doesn't classify
anything.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Category

router = APIRouter()


# --- Schemas -------------------------------------------------------------


class CategoryBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    default_department_id: uuid.UUID


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    default_department_id: uuid.UUID | None = None


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


# --- Routes ----------------------------------------------------------


@router.get("", response_model=list[CategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.slug))
    return list(result.scalars().all())


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate, db: AsyncSession = Depends(get_db)
) -> Category:
    category = Category(**payload.model_dump())
    db.add(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A category with that slug already exists, or default_department_id is invalid",
        ) from exc
    await db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A category with that slug already exists, or default_department_id is invalid",
        ) from exc
    await db.refresh(category)
    return category


@router.delete(
    "/{category_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_category(
    category_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    await db.delete(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Category is still referenced by complaints/clusters",
        ) from exc
