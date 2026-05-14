from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, JSON, Numeric, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, mapper_registry


class NodeType(str, Enum):
    COMPANY = "COMPANY"
    INDUSTRY = "INDUSTRY"
    TECHNOLOGY = "TECHNOLOGY"


class KnowledgeGraphNode(UUIDMixin, Base):
    __tablename__ = "knowledge_graph_nodes"

    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    outgoing_edges: Mapped[list["KnowledgeGraphEdge"]] = relationship(
        "KnowledgeGraphEdge", back_populates="source_node", foreign_keys="KnowledgeGraphEdge.source_id"
    )
    incoming_edges: Mapped[list["KnowledgeGraphEdge"]] = relationship(
        "KnowledgeGraphEdge", back_populates="target_node", foreign_keys="KnowledgeGraphEdge.target_id"
    )

    __table_args__ = (
        CheckConstraint("node_type IN ('COMPANY','INDUSTRY','TECHNOLOGY')", name="chk_node_type"),
    )


class KnowledgeGraphEdge(UUIDMixin, Base):
    __tablename__ = "knowledge_graph_edges"

    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_graph_nodes.id"), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_graph_nodes.id"), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(30), nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0.5"))
    properties: Mapped[dict | None] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    source_node: Mapped["KnowledgeGraphNode"] = relationship(
        "KnowledgeGraphNode", foreign_keys=[source_id], back_populates="outgoing_edges"
    )
    target_node: Mapped["KnowledgeGraphNode"] = relationship(
        "KnowledgeGraphNode", foreign_keys=[target_id], back_populates="incoming_edges"
    )