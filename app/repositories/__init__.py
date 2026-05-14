"""
Repositories — 数据访问层统一入口
"""

from app.repositories.member_repo import MemberRepo
from app.repositories.relationship_repo import RelationshipRepo
from app.repositories.cooperation_repo import CooperationRepo
from app.repositories.game_repo import GameRepo

# Alias for backward compatibility
GameProfileRepo = GameRepo

__all__ = [
    "MemberRepo",
    "RelationshipRepo",
    "CooperationRepo",
    "GameRepo",
    "GameProfileRepo",
]
