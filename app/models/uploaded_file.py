# -*- coding: utf-8 -*-
"""文件上传记录模型 - PKG-002"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from app.models import Base
import enum

class FileCategory(str, enum.Enum):
    AVATAR = "avatar"           # 会员头像
    IDENTITY = "identity"       # 身份证明
    BUSINESS_LICENSE = "business"  # 营业执照
    PRODUCT_IMAGE = "product"   # 产品图片
    DOCUMENT = "document"      # 文档资料
    MEDIA = "media"            # 音视频
    OTHER = "other"

class FileStatus(str, enum.Enum):
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 业务字段
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    stored_name = Column(String(255), nullable=False, unique=True, comment="COS存储名(唯一)")
    file_path = Column(String(512), nullable=False, comment="COS完整路径")
    file_url = Column(String(1024), nullable=False, comment="访问URL")
    file_size = Column(BigInteger, nullable=False, comment="文件大小(字节)")
    mime_type = Column(String(100), nullable=False, comment="MIME类型")
    file_ext = Column(String(20), nullable=True, comment="文件扩展名")
    category = Column(String(20), nullable=True, comment="文件分类")
    # 关联
    owner_id = Column(Integer, nullable=True, comment="上传者ID(member_id或admin_id)")
    owner_type = Column(String(20), nullable=True, comment="owner类型: member/admin")
    # 关联业务ID(如member_id, activity_id等)
    ref_id = Column(Integer, nullable=True, comment="关联业务ID")
    ref_type = Column(String(50), nullable=True, comment="关联业务类型")
    # 状态与审计
    status = Column(String(20), nullable=False, default="completed", comment="状态")
    download_count = Column(Integer, default=0, comment="下载次数")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    # 可选：缩略图/预览URL
    thumbnail_url = Column(String(1024), nullable=True, comment="缩略图URL")
    # 可选：元数据JSON
    extra_data = Column(Text, nullable=True, comment="额外元数据JSON")

    def to_dict(self):
        return {
            "id": self.id,
            "file_name": self.file_name,
            "file_url": self.file_url,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "file_ext": self.file_ext,
            "category": self.category,
            "owner_id": self.owner_id,
            "owner_type": self.owner_type,
            "ref_id": self.ref_id,
            "ref_type": self.ref_type,
            "status": self.status,
            "thumbnail_url": self.thumbnail_url,
            "download_count": self.download_count,
            "created_at": str(self.created_at) if self.created_at else None,
        }