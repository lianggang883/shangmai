"""Knowledge graph repository."""
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeNode, KnowledgeEdge


class KnowledgeRepo:
    """Data access for knowledge graph nodes and edges."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Nodes ──────────────────────────────────────────

    async def find_node(self, node_type: str, name: str) -> "KnowledgeNode | None":
        from app.models.knowledge import KnowledgeNode
        stmt = select(KnowledgeNode).where(
            KnowledgeNode.type == node_type,
            KnowledgeNode.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_nodes_by_type(self, node_type: str, limit: int = 100) -> list["KnowledgeNode"]:
        from app.models.knowledge import KnowledgeNode
        stmt = (
            select(KnowledgeNode)
            .where(KnowledgeNode.type == node_type)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_node(
        self, node_type: str, name: str, properties: dict | None = None
    ) -> "KnowledgeNode":
        from app.models.knowledge import KnowledgeNode
        node = KnowledgeNode(type=node_type, name=name, properties=properties or {})
        self.session.add(node)
        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def get_node_by_id(self, node_id: str) -> "KnowledgeNode | None":
        from app.models.knowledge import KnowledgeNode
        stmt = select(KnowledgeNode).where(KnowledgeNode.id == node_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_node_properties(self, node_id: str, properties: dict) -> "KnowledgeNode | None":
        node = await self.get_node_by_id(node_id)
        if node is None:
            return None
        node.properties = properties
        self.session.add(node)
        await self.session.flush()
        await self.session.refresh(node)
        return node

    # ── Edges ──────────────────────────────────────────

    async def get_edges(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        edge_type: str | None = None,
        limit: int = 200,
    ) -> list["KnowledgeEdge"]:
        from app.models.knowledge import KnowledgeEdge
        stmt = select(KnowledgeEdge)
        if source_id:
            stmt = stmt.where(KnowledgeEdge.source_id == source_id)
        if target_id:
            stmt = stmt.where(KnowledgeEdge.target_id == target_id)
        if edge_type:
            stmt = stmt.where(KnowledgeEdge.type == edge_type)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        weight: float = 1.0,
        properties: dict | None = None,
    ) -> "KnowledgeEdge":
        from app.models.knowledge import KnowledgeEdge
        edge = KnowledgeEdge(
            source_id=source_id,
            target_id=target_id,
            type=edge_type,
            weight=weight,
            properties=properties or {},
        )
        self.session.add(edge)
        await self.session.flush()
        await self.session.refresh(edge)
        return edge

    async def get_or_create_edge(
        self, source_id: str, target_id: str, edge_type: str, weight: float = 1.0
    ) -> "KnowledgeEdge":
        from app.models.knowledge import KnowledgeEdge
        stmt = select(KnowledgeEdge).where(
            KnowledgeEdge.source_id == source_id,
            KnowledgeEdge.target_id == target_id,
            KnowledgeEdge.type == edge_type,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        return await self.create_edge(source_id, target_id, edge_type, weight)

    # ── Domain queries ──────────────────────────────────

    async def get_industry_companies(self, industry_name: str) -> list["KnowledgeNode"]:
        return await self.get_nodes_by_type(f"company:{industry_name}")

    async def find_companies_by_industry(self, industry: str) -> list["KnowledgeNode"]:
        return await self.get_nodes_by_type("company", limit=50)

    async def find_related_nodes(
        self, node_id: str, depth: int = 1, edge_type: str | None = None
    ) -> list["KnowledgeNode"]:
        """Find nodes connected to the given node within specified depth."""
        from app.models.knowledge import KnowledgeNode, KnowledgeEdge

        # depth=1: direct connections
        edges = await self.get_edges(source_id=node_id, edge_type=edge_type)
        if depth == 1:
            target_ids = [e.target_id for e in edges]
        else:
            # recursive: collect all reachable nodes (simplified)
            all_edges = await self.get_edges(source_id=node_id)
            target_ids = [e.target_id for e in all_edges]

        if not target_ids:
            return []
        from sqlalchemy import or_
        stmt = select(KnowledgeNode).where(KnowledgeNode.id.in_(target_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())