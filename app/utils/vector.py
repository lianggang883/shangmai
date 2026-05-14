"""
商脉系统 — 向量数据库客户端

支持: Milvus / Qdrant
用途: 768维会员角色向量/兴趣向量/企业描述向量
操作: insert / search / delete
"""
from abc import ABC, abstractmethod
from typing import Optional


class VectorClient(ABC):
    """向量数据库客户端抽象"""

    @abstractmethod
    async def insert(self, collection: str, id: str, embedding: list[float], metadata: dict = None):
        """插入向量"""
        ...

    @abstractmethod
    async def search(self, collection: str, query_embedding: list[float], top_k: int = 10, filter: dict = None) -> list[dict]:
        """ANN检索"""
        ...

    @abstractmethod
    async def delete(self, collection: str, ids: list[str]):
        """删除向量"""
        ...


class MilvusClient(VectorClient):
    """Milvus向量数据库客户端"""

    def __init__(self, host: str = "localhost", port: int = 19530, dim: int = 768):
        self.host = host
        self.port = port
        self.dim = dim
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from pymilvus import MilvusClient
                self._client = MilvusClient(uri=f"http://{self.host}:{self.port}")
            except ImportError:
                raise RuntimeError("pymilvus未安装: pip install pymilvus")
        return self._client

    async def insert(self, collection: str, id: str, embedding: list[float], metadata: dict = None):
        client = self._get_client()
        data = {"id": id, "vector": embedding}
        if metadata:
            data.update(metadata)
        client.insert(collection_name=collection, data=[data])

    async def search(self, collection: str, query_embedding: list[float], top_k: int = 10, filter: dict = None) -> list[dict]:
        client = self._get_client()
        results = client.search(
            collection_name=collection,
            data=[query_embedding],
            limit=top_k,
            output_fields=["*"],
            filter=filter or ""
        )
        if results and results[0]:
            return [{"id": r["id"], "score": r["distance"], **r.get("entity", {})} for r in results[0]]
        return []

    async def delete(self, collection: str, ids: list[str]):
        client = self._get_client()
        client.delete(collection_name=collection, ids=ids)


class InMemoryVectorClient(VectorClient):
    """内存向量数据库（开发/测试用）"""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self._collections: dict[str, dict[str, dict]] = {}

    async def insert(self, collection: str, id: str, embedding: list[float], metadata: dict = None):
        if collection not in self._collections:
            self._collections[collection] = {}
        self._collections[collection][id] = {
            "id": id, "vector": embedding, "metadata": metadata or {}
        }

    async def search(self, collection: str, query_embedding: list[float], top_k: int = 10, filter: dict = None) -> list[dict]:
        import math
        if collection not in self._collections:
            return []

        results = []
        for id_, data in self._collections[collection].items():
            vec = data["vector"]
            # 余弦相似度
            dot = sum(a * b for a, b in zip(query_embedding, vec))
            norm_q = math.sqrt(sum(x*x for x in query_embedding))
            norm_v = math.sqrt(sum(x*x for x in vec))
            score = dot / (norm_q * norm_v) if norm_q > 0 and norm_v > 0 else 0
            results.append({"id": id_, "score": score, **data.get("metadata", {})})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, collection: str, ids: list[str]):
        if collection in self._collections:
            for id_ in ids:
                self._collections[collection].pop(id_, None)


def create_vector_client(
    backend: str = "memory",
    host: str = "localhost",
    port: int = 19530,
    dim: int = 768
) -> VectorClient:
    """工厂函数"""
    if backend == "milvus":
        return MilvusClient(host=host, port=port, dim=dim)
    return InMemoryVectorClient(dim=dim)
