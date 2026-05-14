"""Generic base repository for all data access."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.core.exceptions import NotFoundError

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Async generic data access layer using SQLAlchemy 2.0 style."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get_by_id(self, id: str) -> ModelType | None:
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, id: str) -> ModelType:
        obj = await self.get_by_id(id)
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} with id={id} not found")
        return obj

    async def get_by_field(self, field: str, value: Any) -> ModelType | None:
        column = getattr(self.model, field, None)
        if column is None:
            raise AttributeError(f"Model {self.model.__name__} has no column '{field}'")
        stmt = select(self.model).where(column == value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: dict | None = None,
        order_by: str = "created_at",
        desc: bool = True,
    ) -> list[ModelType]:
        stmt = select(self.model)
        if filters:
            for col_name, value in filters.items():
                col = getattr(self.model, col_name, None)
                if col is not None:
                    stmt = stmt.where(col == value)
        order_col = getattr(self.model, order_by, None)
        if order_col is not None:
            stmt = stmt.order_by(order_col.desc() if desc else order_col.asc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: dict) -> ModelType:
        obj = self.model(**obj_in)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: str, obj_in: dict) -> ModelType | None:
        obj = await self.get_by_id(id)
        if obj is None:
            return None
        for key, value in obj_in.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id: str) -> bool:
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def count(self, filters: dict | None = None) -> int:
        stmt = select(func.count()).select_from(self.model)
        if filters:
            for col_name, value in filters.items():
                col = getattr(self.model, col_name, None)
                if col is not None:
                    stmt = stmt.where(col == value)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: str) -> bool:
        stmt = select(func.count()).select_from(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def save(self, obj: ModelType) -> ModelType:
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def expire(self, obj: ModelType) -> None:
        self.session.expire(obj)