from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, registry

# Shared registry with forward-ref resolution (needed for cross-model refs in same file)
mapper_registry = registry()

class Base(DeclarativeBase):
    registry = mapper_registry


class UUIDMixin:
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
    )