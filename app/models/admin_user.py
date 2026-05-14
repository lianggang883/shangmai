# -*- coding: utf-8 -*-
"""管理员用户模型 商脉平台 Phase 2 - PKG-001"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.sql import func
from app.models.base import Base
import enum

class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    CONTENT_ADMIN = "content_admin"
    USER_ADMIN = "user_admin"
    ANALYST = "analyst"
    OPERATOR = "operator"

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False, comment="登录用户名")
    password_hash = Column(String(255), nullable=False, comment="bcrypt密码哈希")
    nickname = Column(String(100), nullable=True, comment="显示名称")
    email = Column(String(100), unique=True, index=True, nullable=True, comment="邮箱")
    phone = Column(String(20), nullable=True, comment="手机号")
    role = Column(SQLEnum(AdminRole), default=AdminRole.OPERATOR, nullable=False, comment="角色")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    last_login_at = Column(DateTime(timezone=True), nullable=True, comment="最后登录时间")
    last_login_ip = Column(String(45), nullable=True, comment="最后登录IP")
    login_count = Column(Integer, default=0, nullable=False, comment="登录次数")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username={self.username})>"

    @property
    def is_super_admin(self): return self.role == AdminRole.SUPER_ADMIN

    def can_manage_members(self):
        return self.role in [AdminRole.SUPER_ADMIN, AdminRole.USER_ADMIN]

    def can_manage_activities(self):
        return self.role in [AdminRole.SUPER_ADMIN, AdminRole.CONTENT_ADMIN, AdminRole.OPERATOR]

    def can_view_dashboard(self): return True

    def can_send_notification(self):
        return self.role in [AdminRole.SUPER_ADMIN, AdminRole.OPERATOR]

    def to_dict(self, include_sensitive=False):
        role_names = {
            AdminRole.SUPER_ADMIN: "超级管理员",
            AdminRole.CONTENT_ADMIN: "内容管理员",
            AdminRole.USER_ADMIN: "会员管理员",
            AdminRole.ANALYST: "数据分析师",
            AdminRole.OPERATOR: "运营人员",
        }
        data = {
            "id": self.id, "username": self.username, "nickname": self.nickname,
            "email": self.email, "phone": self.phone, "role": self.role.value,
            "role_name": role_names.get(self.role, "未知角色"),
            "is_active": self.is_active,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "last_login_ip": self.last_login_ip,
            "login_count": self.login_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_sensitive: data["password_hash"] = self.password_hash
        return data