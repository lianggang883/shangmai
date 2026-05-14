"""LLM 配置层 - 多Provider统一接口"""
import os
from typing import Optional, Literal
from dataclasses import dataclass
from functools import lru_cache

PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()

LLMConfig = Literal["openai", "tencent", "deepseek", "anthropic", "zhipu", "mock"]


@dataclass
class LLMConfigData:
    provider: LLMConfig
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30
    mock_mode: bool = False


def _load_openai_config() -> LLMConfigData:
    return LLMConfigData(
        provider="openai",
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "30")),
        mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true",
    )


def _load_tencent_config() -> LLMConfigData:
    return LLMConfigData(
        provider="tencent",
        model=os.getenv("HUNYUAN_MODEL", "hunyuan-pro"),
        api_key=os.getenv("HUNYUAN_SECRET_KEY"),
        base_url="https://hunyuan.cloud.tencent.com",
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "30")),
        mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true",
    )


def _load_deepseek_config() -> LLMConfigData:
    return LLMConfigData(
        provider="deepseek",
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "30")),
        mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true",
    )


def _load_zhipu_config() -> LLMConfigData:
    return LLMConfigData(
        provider="zhipu",
        model=os.getenv("ZHIPU_MODEL", "glm-4"),
        api_key=os.getenv("ZHIPU_API_KEY"),
        base_url="https://open.bigmodel.cn/api/paas/v4",
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "30")),
        mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true",
    )


def _load_mock_config() -> LLMConfigData:
    return LLMConfigData(
        provider="mock",
        model="mock-gpt",
        temperature=0.7,
        max_tokens=2048,
        mock_mode=True,
    )


_PROVIDER_LOADERS = {
    "openai": _load_openai_config,
    "tencent": _load_tencent_config,
    "deepseek": _load_deepseek_config,
    "anthropic": _load_openai_config,  # Anthropic 兼容 OpenAI API格式
    "zhipu": _load_zhipu_config,
    "mock": _load_mock_config,
}


@lru_cache(maxsize=1)
def get_llm_config() -> LLMConfigData:
    """获取当前激活的LLM配置（单例）"""
    loader = _PROVIDER_LOADERS.get(PROVIDER, _load_mock_config)
    return loader()


# ============================================================
# 统一LLM调用接口
# ============================================================

async def llm_complete(prompt: str, system: str = "", **kwargs) -> str:
    """统一LLM补全接口"""
    cfg = get_llm_config()

    if cfg.mock_mode or cfg.provider == "mock":
        return _mock_response(prompt)

    if cfg.provider == "openai" or cfg.provider == "anthropic":
        return await _openai_complete(prompt, system, cfg, **kwargs)
    elif cfg.provider == "tencent":
        return await _tencent_complete(prompt, system, cfg, **kwargs)
    elif cfg.provider == "deepseek":
        return await _deepseek_complete(prompt, system, cfg, **kwargs)
    elif cfg.provider == "zhipu":
        return await _zhipu_complete(prompt, system, cfg, **kwargs)
    return _mock_response(prompt)


# ------------------------------------------------------------
# 各Provider实现
# ------------------------------------------------------------

async def _openai_complete(prompt: str, system: str, cfg: LLMConfigData, **kwargs) -> str:
    try:
        import openai
    except ImportError:
        return _mock_response(prompt)

    client = openai.OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        temperature=kwargs.get("temperature", cfg.temperature),
        max_tokens=kwargs.get("max_tokens", cfg.max_tokens),
    )
    return resp.choices[0].message.content or ""


async def _deepseek_complete(prompt: str, system: str, cfg: LLMConfigData, **kwargs) -> str:
    return await _openai_complete(prompt, system, cfg, **kwargs)


async def _tencent_complete(prompt: str, system: str, cfg: LLMConfigData, **kwargs) -> str:
    # 腾讯混元使用 HTTP API
    import aiohttp

    url = f"https://hunyuan.cloud.tencent.com/hyllm/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=cfg.timeout)) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]


async def _zhipu_complete(prompt: str, system: str, cfg: LLMConfigData, **kwargs) -> str:
    import aiohttp

    url = f"{cfg.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=cfg.timeout)) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]


def _mock_response(prompt: str) -> str:
    """Mock模式返回示例（开发/演示用）"""
    if not prompt:
        return "请输入内容"

    prompt_preview = prompt[:60]
    return (
        f"【Mock LLM响应】\n\n"
        f"收到您的问题：{prompt_preview}...\n\n"
        f"这是一个模拟响应。在生产环境中，"
        f"请在 .env.llm 中配置真实的API密钥。"
    )
