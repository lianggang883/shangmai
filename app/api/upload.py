# -*- coding: utf-8 -*-
"""
文件上传 API v2 — 腾讯云COS
商脉平台 Phase 2 - PKG-002
完全重写，使用 cos-python-sdk-v5 + 数据库元数据记录
"""
import os, time, uuid, hashlib, json
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.models.uploaded_file import UploadedFile

router = APIRouter()

# ========================
# COS 配置（从环境变量读取）
# ========================
COS_SECRET_ID = os.getenv("COS_SECRET_ID", "")
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
COS_BUCKET = os.getenv("COS_BUCKET", "shangmai-1301366473")
COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")
COS_CDN_DOMAIN = os.getenv("COS_CDN_DOMAIN", "")  # 若配置了CDN加速域名则优先用CDN

def get_cos_base_url() -> str:
    """返回COS访问基础URL，优先使用CDN域名"""
    if COS_CDN_DOMAIN:
        return f"https://{COS_CDN_DOMAIN}"
    return f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com"

# ========================
# COS 客户端单例
# ========================
_cos_client = None

def get_cos_client():
    """懒加载COS客户端"""
    global _cos_client
    if _cos_client is None:
        try:
            from qcloud_cos import CosConfig, CosS3Client
            config = CosConfig(
                Region=COS_REGION,
                SecretId=COS_SECRET_ID,
                SecretKey=COS_SECRET_KEY,
            )
            _cos_client = CosS3Client(config)
            print(f"[COS] 客户端初始化成功: {COS_BUCKET} in {COS_REGION}")
        except ImportError:
            from qcloud_cos import CosConfig, CosS3Client
            config = CosConfig(
                Region=COS_REGION,
                SecretId=COS_SECRET_ID,
                SecretKey=COS_SECRET_KEY,
            )
            _cos_client = CosS3Client(config)
            print(f"[COS] 客户端初始化成功(v1): {COS_BUCKET}")
        except Exception as e:
            print(f"[COS] 客户端初始化失败: {e}")
            _cos_client = None
    return _cos_client

# ========================
# 文件类型配置
# ========================
ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_DOC = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
ALLOWED_ARCHIVE = {".zip", ".rar", ".7z", ".tar", ".gz"}
ALLOWED_DATA = {".txt", ".csv", ".json", ".xml"}
ALLOWED_VIDEO = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"}
ALLOWED_AUDIO = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}

ALL_ALLOWED = (ALLOWED_IMAGE | ALLOWED_DOC | ALLOWED_ARCHIVE |
               ALLOWED_DATA | ALLOWED_VIDEO | ALLOWED_AUDIO)

FILE_CATEGORY_MAP = {
    "avatar": ALLOWED_IMAGE,
    "identity": ALLOWED_IMAGE | {".pdf"},
    "business": ALLOWED_IMAGE | {".pdf"},
    "product": ALLOWED_IMAGE,
    "document": ALLOWED_DOC | ALLOWED_DATA,
    "media": ALLOWED_VIDEO | ALLOWED_AUDIO,
    "other": ALL_ALLOWED,
}

# ========================
# 工具函数
# ========================
def gen_stored_name(ext: str) -> str:
    """生成唯一存储文件名: {category}/{date}/{uuid}.{ext}"""
    ts = datetime.now().strftime("%Y%m%d")
    uid = uuid.uuid4().hex[:12]
    return f"shangmai/{ts}/{uid}{ext}"

def get_mime_type(filename: str) -> str:
    """根据扩展名推断MIME类型"""
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        ".pdf": "application/pdf", ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".zip": "application/zip", ".rar": "application/x-rar-compressed",
        ".txt": "text/plain", ".csv": "text/csv", ".json": "application/json",
        ".xml": "application/xml",
        ".mp4": "video/mp4", ".avi": "video/x-msvideo",
        ".mov": "video/quicktime", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".flac": "audio/flac",
    }
    return mime_map.get(ext, "application/octet-stream")

def detect_category(filename: str, mime_type: str) -> str:
    """根据文件名/MIME自动推断分类"""
    name_lower = filename.lower()
    mime_lower = mime_type.lower()
    if any(k in name_lower for k in ["avatar", "photo", "头像", "照片"]):
        return "avatar"
    if any(k in name_lower for k in ["card", "namecard", "business", "名片", "执照"]):
        return "business"
    if any(k in name_lower for k in ["product", "产品", "商品"]):
        return "product"
    if any(k in name_lower for k in ["idcard", "identity", "身份证", "证件"]):
        return "identity"
    if mime_lower.startswith("image/"):
        return "product" if "preview" in name_lower else "other"
    if mime_lower.startswith("video/"):
        return "media"
    if mime_lower.startswith("audio/"):
        return "media"
    return "document"

# ========================
# Request/Response 模型
# ========================
class UploadResponse(BaseModel):
    success: bool = True
    file_id: int
    file_name: str
    stored_name: str
    file_url: str
    thumbnail_url: Optional[str] = None
    file_size: int
    mime_type: str
    file_ext: str
    category: str
    uploaded_at: str

class FileRecord(BaseModel):
    id: int
    file_name: str
    file_url: str
    file_size: int
    mime_type: str
    file_ext: str
    category: str
    owner_type: Optional[str]
    ref_type: Optional[str]
    status: str
    download_count: int
    thumbnail_url: Optional[str]
    created_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class FileListResponse(BaseModel):
    total: int
    files: List[FileRecord]

# ========================
# 核心上传函数
# ========================
async def upload_to_cos(content: bytes, cos_key: str, mime_type: str) -> str:
    """上传文件到COS，返回访问URL"""
    client = get_cos_client()
    base_url = get_cos_base_url()
    url = f"{base_url}/{cos_key}"
    
    if client is None:
        # COS SDK不可用，返回模拟URL（开发模式）
        print(f"[COS] ⚠️ SDK未就绪，返回模拟URL: {url}")
        return url

    try:
        from qcloud_cos import CosS3Client
        if isinstance(client, CosS3Client):
            client.put_object(
                Bucket=COS_BUCKET,
                Key=cos_key,
                Body=content,
                ContentLength=str(len(content)),
                ContentType=mime_type,
            )
        else:
            # 旧版SDK
            client.put_object(
                Bucket=COS_BUCKET,
                Key=cos_key,
                Body=content,
                ContentType=mime_type,
            )
        print(f"[COS] ✅ 上传成功: {cos_key}")
        return url
    except Exception as e:
        print(f"[COS] ❌ 上传失败: {cos_key} -> {e}")
        raise HTTPException(status_code=500, detail=f"COS上传失败: {str(e)[:100]}")

# ========================
# API 端点
# ========================

@router.post("/", response_model=UploadResponse)
async def upload_single(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None, description="文件分类: avatar/identity/business/product/document/media/other"),
    ref_id: Optional[int] = Form(None, description="关联业务ID"),
    ref_type: Optional[str] = Form(None, description="关联业务类型"),
    db: AsyncSession = Depends(get_db),
):
    """
    单文件上传
    POST /api/v1/upload/
    """
    # 1. 读取内容
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="没有上传文件内容")

    MAX_SIZE = 50 * 1024 * 1024  # 50MB
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail=f"文件超过50MB限制(当前{len(content)//1024}KB)")

    # 2. 检查扩展名
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext or ext not in ALL_ALLOWED:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，支持: {', '.join(sorted(ALL_ALLOWED))}")

    # 3. MIME类型
    mime_type = file.content_type or get_mime_type(file.filename or "")
    
    # 4. 自动分类或使用指定分类
    cat = category or detect_category(file.filename or "", mime_type)
    if cat not in FILE_CATEGORY_MAP:
        cat = "other"
    if ext not in FILE_CATEGORY_MAP.get(cat, ALL_ALLOWED):
        cat = "other"  # 强制归为other

    # 5. 生成存储名
    stored_name = gen_stored_name(ext)

    # 6. 上传到COS
    file_url = await upload_to_cos(content, stored_name, mime_type)

    # 7. 写入数据库记录
    uploaded_file = UploadedFile(
        file_name=file.filename or "unknown",
        stored_name=stored_name,
        file_path=stored_name,
        file_url=file_url,
        file_size=len(content),
        mime_type=mime_type,
        file_ext=ext,
        category=cat,
        owner_id=None,  # 认证后从token获取
        owner_type=None,
        ref_id=ref_id,
        ref_type=ref_type,
        status="completed",
    )
    db.add(uploaded_file)
    await db.commit()
    await db.refresh(uploaded_file)

    return UploadResponse(
        success=True,
        file_id=uploaded_file.id,
        file_name=uploaded_file.file_name,
        stored_name=uploaded_file.stored_name,
        file_url=uploaded_file.file_url,
        file_size=uploaded_file.file_size,
        mime_type=uploaded_file.mime_type,
        file_ext=uploaded_file.file_ext,
        category=uploaded_file.category,
        uploaded_at=str(uploaded_file.created_at),
    )


@router.post("/batch", response_model=List[UploadResponse])
async def upload_batch(
    files: List[UploadFile] = File(..., description="批量上传(最多9个)"),
    category: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    批量文件上传
    POST /api/v1/upload/batch
    """
    if len(files) > 9:
        raise HTTPException(status_code=400, detail="最多支持9个文件批量上传")

    results = []
    for file in files:
        try:
            content = await file.read()
            if not content or len(content) > 50 * 1024 * 1024:
                continue

            ext = os.path.splitext(file.filename or "")[1].lower()
            if not ext or ext not in ALL_ALLOWED:
                continue

            mime_type = file.content_type or get_mime_type(file.filename or "")
            cat = category or detect_category(file.filename or "", mime_type)
            stored_name = gen_stored_name(ext)
            file_url = await upload_to_cos(content, stored_name, mime_type)

            record = UploadedFile(
                file_name=file.filename or "unknown",
                stored_name=stored_name,
                file_path=stored_name,
                file_url=file_url,
                file_size=len(content),
                mime_type=mime_type,
                file_ext=ext,
                category=cat,
                status="completed",
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

            results.append(UploadResponse(
                success=True,
                file_id=record.id,
                file_name=record.file_name,
                stored_name=record.stored_name,
                file_url=record.file_url,
                file_size=record.file_size,
                mime_type=record.mime_type,
                file_ext=record.file_ext,
                category=record.category,
                uploaded_at=str(record.created_at),
            ))
        except Exception as e:
            print(f"[Upload] 批量中单个失败: {e}")
            continue

    return results


@router.get("/", response_model=FileListResponse)
async def list_files(
    category: Optional[str] = Query(None, description="按分类筛选"),
    owner_id: Optional[int] = Query(None, description="按上传者筛选"),
    ref_type: Optional[str] = Query(None, description="按业务类型筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    文件列表（分页）
    GET /api/v1/upload/?category=avatar&page=1&page_size=20
    """
    query = select(UploadedFile).where(UploadedFile.status == "completed")
    count_query = select(func.count(UploadedFile.id)).where(UploadedFile.status == "completed")

    if category:
        query = query.where(UploadedFile.category == category)
        count_query = count_query.where(UploadedFile.category == category)
    if owner_id:
        query = query.where(UploadedFile.owner_id == owner_id)
        count_query = count_query.where(UploadedFile.owner_id == owner_id)
    if ref_type:
        query = query.where(UploadedFile.ref_type == ref_type)
        count_query = count_query.where(UploadedFile.ref_type == ref_type)

    # 总数
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    query = query.order_by(desc(UploadedFile.created_at)).offset(offset).limit(page_size)
    result = await db.execute(query)
    records = result.scalars().all()

    return FileListResponse(
        total=total,
        files=[FileRecord(
            id=r.id, file_name=r.file_name, file_url=r.file_url,
            file_size=r.file_size, mime_type=r.mime_type, file_ext=r.file_ext,
            category=r.category, owner_type=r.owner_type, ref_type=r.ref_type,
            status=r.status, download_count=r.download_count,
            thumbnail_url=r.thumbnail_url, created_at=str(r.created_at) if r.created_at else None,
        ) for r in records]
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    删除文件（COS删除 + DB标记）
    DELETE /api/v1/upload/{file_id}
    """
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.id == file_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 软删除
    record.status = "deleted"
    await db.commit()

    # 尝试从COS删除（可选，保留历史）
    client = get_cos_client()
    if client:
        try:
            if "qcloud_cos" in str(type(client)):
                client.delete_object(Bucket=COS_BUCKET, Key=record.stored_name)
            else:
                client.delete_object(Bucket=COS_BUCKET, Key=record.stored_name)
            print(f"[COS] ✅ 已删除: {record.stored_name}")
        except Exception as e:
            print(f"[COS] ⚠️ 删除失败(继续软删除): {e}")

    return {"success": True, "message": "文件已删除", "file_id": file_id}


@router.get("/{file_id}")
async def get_file_info(
    file_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取单个文件信息
    GET /api/v1/upload/{file_id}
    """
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.id == file_id)
    )
    record = result.scalar_one_or_none()
    if not record or record.status == "deleted":
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return record.to_dict()


@router.get("/stats/summary")
async def get_upload_stats(db: AsyncSession = Depends(get_db)):
    """上传统计（管理员用）"""
    total = (await db.execute(
        select(func.count(UploadedFile.id)).where(UploadedFile.status == "completed")
    )).scalar() or 0
    
    total_size = (await db.execute(
        select(func.sum(UploadedFile.file_size)).where(UploadedFile.status == "completed")
    )).scalar() or 0

    # 按分类统计
    cat_result = await db.execute(
        select(UploadedFile.category, func.count(UploadedFile.id))
        .where(UploadedFile.status == "completed")
        .group_by(UploadedFile.category)
    )
    by_category = {r[0] or "other": r[1] for r in cat_result.all()}

    return {
        "total_files": total,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "by_category": by_category,
    }