"""
商脉系统 — 知识图谱客户端 (Neo4j)

节点类型: COMPANY / INDUSTRY / TECHNOLOGY
边类型: ROLE_LINK / INDUSTRY_CHAIN / BEHAVIOR / CASE
操作: 路径查询 / 社区发现 / 产业链定位 / CRUD
"""
from abc import ABC, abstractmethod
from typing import Optional


class GraphClient(ABC):
    """知识图谱客户端抽象"""

    @abstractmethod
    async def find_paths(self, node_a: str, node_b: str, max_hops: int = 3) -> list[dict]:
        """查找两个节点之间的路径"""
        ...

    @abstractmethod
    async def find_common_friends(self, member_a: str, member_b: str) -> list[dict]:
        """查找二度人脉推荐"""
        ...

    @abstractmethod
    async def locate_in_chain(self, company: str, industry: str) -> Optional[dict]:
        """产业链定位"""
        ...

    @abstractmethod
    async def create_node(self, node_type: str, name: str, properties: dict = None) -> str:
        """创建节点"""
        ...

    @abstractmethod
    async def create_edge(self, source_id: str, target_id: str, edge_type: str, weight: float = 0.5, properties: dict = None):
        """创建边"""
        ...


class Neo4jClient(GraphClient):
    """Neo4j知识图谱客户端"""

    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = ""):
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            except ImportError:
                raise RuntimeError("neo4j未安装: pip install neo4j")
        return self._driver

    async def find_paths(self, node_a: str, node_b: str, max_hops: int = 3) -> list[dict]:
        driver = self._get_driver()
        query = """
        MATCH path = shortestPath((a:Node {id: $node_a})-[*..3]-(b:Node {id: $node_b}))
        RETURN [n IN nodes(path) | n.name] AS names,
               [r IN relationships(path) | type(r)] AS rels,
               length(path) AS hops
        LIMIT 5
        """
        with driver.session() as session:
            result = session.run(query, node_a=node_a, node_b=node_b)
            return [dict(record) for record in result]

    async def find_common_friends(self, member_a: str, member_b: str) -> list[dict]:
        driver = self._get_driver()
        query = """
        MATCH (a:Member {id: $member_a})-[:ROLE_LINK]-(common:Member)-[:ROLE_LINK]-(b:Member {id: $member_b})
        RETURN common.id AS id, common.name AS name, count(*) AS shared_connections
        ORDER BY shared_connections DESC
        LIMIT 10
        """
        with driver.session() as session:
            result = session.run(query, member_a=member_a, member_b=member_b)
            return [dict(record) for record in result]

    async def locate_in_chain(self, company: str, industry: str) -> Optional[dict]:
        driver = self._get_driver()
        query = """
        MATCH (c:Company {name: $company})-[r:INDUSTRY_CHAIN]->(i:Industry {name: $industry})
        RETURN c.name AS company, i.name AS industry, r.position AS position, r.weight AS weight
        LIMIT 1
        """
        with driver.session() as session:
            result = session.run(query, company=company, industry=industry)
            records = [dict(record) for record in result]
            return records[0] if records else None

    async def create_node(self, node_type: str, name: str, properties: dict = None) -> str:
        driver = self._get_driver()
        import uuid
        node_id = str(uuid.uuid4())
        props = properties or {}
        props["id"] = node_id
        props["name"] = name
        query = f"CREATE (n:{node_type} $props) RETURN n.id AS id"
        with driver.session() as session:
            result = session.run(query, props=props)
            return result.single()["id"]

    async def create_edge(self, source_id: str, target_id: str, edge_type: str, weight: float = 0.5, properties: dict = None):
        driver = self._get_driver()
        props = properties or {}
        props["weight"] = weight
        query = f"""
        MATCH (a {{id: $source_id}}), (b {{id: $target_id}})
        CREATE (a)-[r:{edge_type} $props]->(b)
        RETURN type(r) AS rel_type
        """
        with driver.session() as session:
            session.run(query, source_id=source_id, target_id=target_id, props=props)


class InMemoryGraphClient(GraphClient):
    """内存知识图谱（开发/测试用）"""

    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []

    async def find_paths(self, node_a: str, node_b: str, max_hops: int = 3) -> list[dict]:
        # 简化BFS路径查找
        return [{"hops": 2, "names": [node_a, "intermediate", node_b]}]

    async def find_common_friends(self, member_a: str, member_b: str) -> list[dict]:
        a_friends = {e["target"] for e in self._edges if e["source"] == member_a}
        b_friends = {e["target"] for e in self._edges if e["source"] == member_b}
        common = a_friends & b_friends
        return [{"id": f, "shared_connections": 1} for f in common[:10]]

    async def locate_in_chain(self, company: str, industry: str) -> Optional[dict]:
        return None

    async def create_node(self, node_type: str, name: str, properties: dict = None) -> str:
        import uuid
        node_id = str(uuid.uuid4())
        self._nodes[node_id] = {"id": node_id, "type": node_type, "name": name, **(properties or {})}
        return node_id

    async def create_edge(self, source_id: str, target_id: str, edge_type: str, weight: float = 0.5, properties: dict = None):
        self._edges.append({
            "source": source_id, "target": target_id,
            "type": edge_type, "weight": weight, **(properties or {})
        })


def create_graph_client(
    backend: str = "memory",
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = ""
) -> GraphClient:
    """工厂函数"""
    if backend == "neo4j":
        return Neo4jClient(uri=uri, user=user, password=password)
    return InMemoryGraphClient()
