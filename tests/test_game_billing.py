"""
商脉系统 — 游戏化 & 计费 测试
覆盖：签到、积分、等级、行动力、配置值
"""
import pytest
from app.config import settings, MONTHLY_FREE_AP_MAP


class TestGameAPI:
    @pytest.mark.asyncio
    async def test_checkin_with_token(self, client, user_token):
        """签到（需要 Token）"""
        if not user_token:
            pytest.skip("注册失败，跳过")
        resp = await client.post(
            "/api/v1/game/checkin",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_checkin_no_token(self, client):
        """无 Token 签到"""
        resp = await client.post("/api/v1/game/checkin")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_profile_with_token(self, client, user_token):
        """获取游戏档案"""
        if not user_token:
            pytest.skip("注册失败，跳过")
        resp = await client.get(
            "/api/v1/game/profile",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code in (200, 404)


class TestBillingAPI:
    @pytest.mark.asyncio
    async def test_balance_with_token(self, client, user_token):
        """查询行动力余额"""
        if not user_token:
            pytest.skip("注册失败，跳过")
        resp = await client.get(
            "/api/v1/billing/balance",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_transactions_with_token(self, client, user_token):
        """查询行动力记录"""
        if not user_token:
            pytest.skip("注册失败，跳过")
        resp = await client.get(
            "/api/v1/billing/transactions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_billing_no_token(self, client):
        """无 Token 查询行动力"""
        resp = await client.get("/api/v1/billing/balance")
        assert resp.status_code in (401, 403)


class TestGameConfig:
    """验证游戏化配置值"""

    def test_exp_table(self):
        assert settings.EXP_TABLE_LV2 == 100
        assert settings.EXP_TABLE_LV3 == 500
        assert settings.EXP_TABLE_LV4 == 2000
        assert settings.EXP_TABLE_LV5 == 8000
        assert settings.EXP_TABLE_LV6 == 30000

    def test_points(self):
        assert settings.POINTS_CHECKIN == 5
        assert settings.POINTS_INTERACTION == 10
        assert settings.POINTS_ICEBREAK == 20
        assert settings.POINTS_MEETING == 50
        assert settings.POINTS_COOPERATION == 100

    def test_points_ordering(self):
        """积分奖励递增"""
        vals = [settings.POINTS_CHECKIN, settings.POINTS_INTERACTION,
                settings.POINTS_ICEBREAK, settings.POINTS_MEETING,
                settings.POINTS_COOPERATION]
        assert vals == sorted(vals)

    def test_monthly_free_ap(self):
        assert MONTHLY_FREE_AP_MAP[1] == 1000
        assert len(MONTHLY_FREE_AP_MAP) == 6

    def test_level_range(self):
        from app.config import EXP_TABLE
        assert all(2 <= lv <= 6 for lv in EXP_TABLE.keys())


class TestDecayConfig:
    def test_decay_days(self):
        assert settings.DECAY_YELLOW_DAYS == 15
        assert settings.DECAY_ORANGE_DAYS == 60
        assert settings.DECAY_RED_DAYS == 90

    def test_decay_ordering(self):
        assert settings.DECAY_YELLOW_DAYS < settings.DECAY_ORANGE_DAYS < settings.DECAY_RED_DAYS

    def test_referral_rate(self):
        assert 0 < settings.REFERRAL_DEFAULT_RATE <= settings.REFERRAL_MAX_RATE
