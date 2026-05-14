"""
商脉系统 · LLM客户端封装
支持: OpenAI / SiliconFlow / DeepSeek / Zhipu / Tencent / Mock
"""
import os

# HARDCODED SiliconFlow Config (auto-set by deploy script)
import os
os.environ.setdefault('LLM_PROVIDER', 'siliconflow')
os.environ.setdefault('LLM_API_KEY', 'sk-zdvgaqyxlsqjamgbndyinhyuefekqmnehoznafkbyjgrapol')
os.environ.setdefault('LLM_BASE_URL', 'https://api.siliconflow.cn/v1')
os.environ.setdefault('LLM_MODEL', 'deepseek-ai/DeepSeek-V3')
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)
PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str: ...
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class OpenAIClient(LLMClient):
    """OpenAI兼容客户端 (OpenAI / SiliconFlow / DeepSeek / Zhipu)"""
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o",
                 embed_model: str = "text-embedding-3-large", timeout: int = 60):
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = model
        self.embed_model = embed_model
        self.timeout = timeout

    async def chat(self, messages: list[dict], **kwargs) -> str:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
            response = await client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
            )
            return response.choices[0].message.content or ""
        except ImportError:
            return "[LLM未安装: pip install openai]"
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return f"[LLM调用失败: {str(e)}]"

    async def embed(self, text: str) -> list[float]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
            response = await client.embeddings.create(model=self.embed_model, input=text)
            return response.data[0].embedding
        except Exception as e:
            logger.warning(f"Embedding失败: {e}")
            return [0.0] * 768


class MockLLMClient(LLMClient):
    async def chat(self, messages: list[dict], **kwargs) -> str:
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[Mock响应] 收到: {user_msg[:60]}... 请配置LLM_PROVIDER和API_KEY"
    async def embed(self, text: str) -> list[float]:
        import hashlib, random
        h = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        random.seed(h)
        vec = [random.uniform(-1, 1) for _ in range(768)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


_llm_client: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is not None:
        return _llm_client

    if PROVIDER in ("openai", "siliconflow"):
        _llm_client = OpenAIClient(
            api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
            model=os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o")),
            embed_model=os.getenv("LLM_EMBED_MODEL", "text-embedding-3-large"),
            timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "60")),
        )
    elif PROVIDER == "deepseek":
        _llm_client = OpenAIClient(
            api_key=os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
        )
    elif PROVIDER == "zhipu":
        _llm_client = OpenAIClient(
            api_key=os.getenv("ZHIPU_API_KEY", ""),
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model=os.getenv("ZHIPU_MODEL", "glm-4"),
        )
    else:
        _llm_client = MockLLMClient()

    logger.info(f"LLM初始化: provider={PROVIDER}, model={getattr(_llm_client, 'model', 'mock')}")
    return _llm_client

def reset_llm_client():
    global _llm_client
    _llm_client = None
