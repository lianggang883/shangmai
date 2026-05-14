# -*- coding: utf-8 -*-
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, Text, Integer, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models import Base, UUIDMixin, TimestampMixin

class Resource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'resources'
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey('members.id'), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    position: Mapped[str | None] = mapped_column(String(50))
    industry: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(String(50))
    intro: Mapped[str | None] = mapped_column(Text)
    needs: Mapped[str | None] = mapped_column(Text)
    analysis_tags: Mapped[dict | None] = mapped_column(JSON, default=list)
    estimated_value: Mapped[int] = mapped_column(Integer, default=0)
    is_starred: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    member: Mapped['Member'] = relationship('Member', foreign_keys=[member_id])
