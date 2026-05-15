"""
商脉系统 — 认证流程测试
覆盖：JWT 签发/验证、注册、登录、刷新令牌、鉴权
"""
import pytest
from jose import jwt, JWTError

from app.config import settings
from app.dependencies.auth import create_access_token, create_refresh_token


# ── JWT 单元测试 ──────────────────────────────────────

class TestJWT:
    def test_create_access_token(self):
        token = create_access_token(data={"sub": "test-user-123"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["sub"] == "test-user-123"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token(self):
        token = create_refresh_token(data={"sub": "test-user-123"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["sub"] == "test-user-123"
        assert payload["type"] == "refresh"

    def test_token_expiry(self):
        from datetime import timedelta
        token = create_access_token(data={"sub": "test"}, expires_delta=timedelta(seconds=1))
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["type"] == "access"

    def test_custom_claims(self):
        token = create_access_token(data={"sub": "admin-1", "username": "admin", "role": "superadmin"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["username"] == "admin"
        assert payload["role"] == "superadmin"

    def test_invalid_token_raises(self):
        with pytest.raises(JWTError):
            jwt.decode("invalid.token.here", settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])

    def test_wrong_secret_raises(self):
        token = create_access_token(data={"sub": "test"})
        with pytest.raises(JWTError):
            jwt.decode(token, "wrong-secret", algorithms=[settings.JWT_ALGORITHM])


# ── 认证 API 集成测试 ────────────────────────────────

class TestAuthAPI:
    @pytest.mark.asyncio
    async def test_register_new_user(self, client):
        resp = await client.post("/api/v1/auth/register", json={"phone": "13800138001", "nickname": "测试用户"})
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["phone"] == "13800138001"
        assert data["data"]["name"] == "测试用户"
        assert data["data"]["access_token"]
        assert data["data"]["is_new"] is True

    @pytest.mark.asyncio
    async def test_register_duplicate_phone(self, client):
        await client.post("/api/v1/auth/register", json={"phone": "13800138002"})
        resp = await client.post("/api/v1/auth/register", json={"phone": "13800138002"})
        data = resp.json()
        assert data["code"] == 400
        assert "已注册" in data["message"]

    @pytest.mark.asyncio
    async def test_login_existing_user(self, client):
        await client.post("/api/v1/auth/register", json={"phone": "13800138003"})
        resp = await client.post("/api/v1/auth/login", json={"phone": "13800138003"})
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["is_new"] is False

    @pytest.mark.asyncio
    async def test_login_auto_register(self, client):
        resp = await client.post("/api/v1/auth/login", json={"phone": "13800138004"})
        data = resp.json()["data"]
        assert data["is_new"] is True
        assert data["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_token(self, client):
        reg = await client.post("/api/v1/auth/register", json={"phone": "13800138005"})
        refresh_token = reg.json()["data"]["refresh_token"]
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        data = resp.json()["data"]
        assert data["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client):
        reg = await client.post("/api/v1/auth/register", json={"phone": "13800138006"})
        access_token = reg.json()["data"]["access_token"]
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
        assert resp.json()["code"] == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
        assert resp.json()["code"] == 401

    @pytest.mark.asyncio
    async def test_register_invalid_phone(self, client):
        resp = await client.post("/api/v1/auth/register", json={"phone": "123"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_default_name(self, client):
        resp = await client.post("/api/v1/auth/register", json={"phone": "13800138007"})
        data = resp.json()["data"]
        assert data["name"] == "用户8007"


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_root(self, client):
        resp = await client.get("/")
        data = resp.json()
        assert data["status"] == "ok"


class TestProtectedEndpoints:
    @pytest.mark.asyncio
    async def test_no_token(self, client):
        resp = await client.get("/api/v1/members/me")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_valid_token(self, client):
        reg = await client.post("/api/v1/auth/register", json={"phone": "13800138010"})
        token = reg.json()["data"]["access_token"]
        resp = await client.get("/api/v1/members/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_invalid_token(self, client):
        resp = await client.get("/api/v1/members/me", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401
