"""LLM 调用封装：基于 LiteLLM 的统一接口。

设计要点：
- 多 Provider 统一接口（Claude/GPT/DeepSeek）
- mock 模式（无 API Key 时自动降级，便于开发测试）
- 结构化 JSON 输出
- 重试与超时
- 成本统计

Spike 验证：litellm 1.59.12 可用，需 legacy-cgi 兼容 Python 3.13。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from cra.core.errors import LlmError

logger = logging.getLogger(__name__)


@dataclass
class LlmResponse:
    """LLM 响应。"""

    content: str
    model: str
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    mock: bool = False
    raw: Any = None

    def parse_json(self) -> Any:
        """解析内容为 JSON，兼容 markdown 代码块包裹。"""
        content = self.content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            # 去掉首尾的 ``` 行
            lines = [ln for ln in lines[1:] if not ln.strip().startswith("```")]
            content = "\n".join(lines)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON from LLM response: %s", e)
            return None


@dataclass
class LlmCallStats:
    """累计调用统计。"""

    total_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    mock_calls: int = 0
    errors: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    def add(self, response: LlmResponse) -> None:
        self.total_calls += 1
        self.total_tokens += response.tokens_input + response.tokens_output
        self.total_cost += response.cost_usd
        if response.mock:
            self.mock_calls += 1
        self.by_model[response.model] = self.by_model.get(response.model, 0) + 1


def _has_any_api_key() -> bool:
    """检查是否配置了任一 API Key。"""
    return any(
        os.environ.get(k)
        for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    )


# ============================================================
# 自定义模型定价表
# ============================================================

# litellm 内置价格表不包含国产模型，这里显式补充
# 价格单位：USD per token
# 数据来源：各厂商 2026-07 公布价格（按 1 USD ≈ 7.2 CNY 折算）
_CUSTOM_MODEL_PRICES: dict[str, dict[str, float]] = {
    # 智谱 GLM 系列（BigModel.cn）
    "glm-5.2": {
        "input_cost_per_token": 0.00000028,   # ¥0.002/1k → ~$0.28/1M
        "output_cost_per_token": 0.00000028,
    },
    "glm-4.7": {
        "input_cost_per_token": 0.00000007,   # ¥0.5/1M → ~$0.07/1M
        "output_cost_per_token": 0.00000007,
    },
    "glm-4-plus": {
        "input_cost_per_token": 0.00000694,   # ¥50/1M → ~$6.94/1M
        "output_cost_per_token": 0.00000694,
    },
    "glm-4-flash": {
        "input_cost_per_token": 0.0,           # 免费
        "output_cost_per_token": 0.0,
    },
    # DeepSeek
    "deepseek-chat": {
        "input_cost_per_token": 0.00000014,   # ¥1/1M → ~$0.14/1M
        "output_cost_per_token": 0.00000028,
    },
}


def _register_custom_prices() -> None:
    """向 litellm 注册自定义模型价格。"""
    try:
        import litellm  # noqa: PLC0415
    except ImportError:
        return

    for model, prices in _CUSTOM_MODEL_PRICES.items():
        try:
            litellm.register_model({model: prices})
        except Exception:  # noqa: BLE001
            logger.debug("Failed to register price for %s", model)


# 模块加载时注册一次
_register_custom_prices()


class LlmClient:
    """LLM 客户端：统一封装 litellm。"""

    def __init__(
        self,
        default_model: str = "deepseek/deepseek-chat",
        timeout: int = 30,
        enable_mock: bool | None = None,
    ) -> None:
        self.default_model = default_model
        self.timeout = timeout
        # 显式开启 mock 或无 API Key 时启用
        self.mock_mode = enable_mock if enable_mock is not None else not _has_any_api_key()
        self.stats = LlmCallStats()

        if self.mock_mode:
            logger.info("LLM client running in MOCK mode (no API key configured)")
        else:
            logger.info("LLM client ready, default model: %s", default_model)

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.1,
        response_format: dict | None = None,
    ) -> LlmResponse:
        """同步风格的消息补全（实际是 async）。"""
        target_model = model or self.default_model

        if self.mock_mode:
            return self._mock_response(target_model, messages)

        return await self._real_call(
            target_model, messages, temperature, response_format
        )

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> tuple[Any, LlmResponse]:
        """便捷方法：调用并解析为 JSON。返回 (parsed, response)。"""
        response = await self.complete(messages, model=model, temperature=0.1)
        return response.parse_json(), response

    async def _real_call(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict | None,
    ) -> LlmResponse:
        """真实 LLM 调用（带重试）。"""
        import litellm  # noqa: PLC0415
        from tenacity import (  # noqa: PLC0415
            AsyncRetrying,
            RetryError,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        # 兼容 Python 3.13（litellm 依赖 cgi）
        try:
            import cgi  # noqa: F401
        except ImportError:
            pass

        # 可重试的异常类型：超时、限流、连接错误（不含逻辑错误）
        retryable = (
            TimeoutError,
            ConnectionError,
        )
        # litellm 的 timeout/api 错误也视为可重试
        for exc_name in ("litellm.Timeout", "litellm.RateLimitError",
                         "litellm.APIConnectionError", "httpx.ReadTimeout"):
            try:
                cls = _resolve_class(exc_name)
                if cls:
                    retryable = (*retryable, cls)
            except (ImportError, AttributeError):
                pass

        start = asyncio.get_event_loop().time()
        try:
            # 重试策略：最多 3 次，指数退避（4s/8s/16s）
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=2, min=4, max=16),
                retry=retry_if_exception_type(retryable),
                reraise=True,
            ):
                with attempt:
                    return await self._do_single_call(
                        model, messages, temperature, response_format,
                        litellm, start,
                    )
            # 不可达
            raise LlmError("Retry loop exited unexpectedly")
        except RetryError as e:
            self.stats.errors += 1
            logger.exception("LLM call failed after retries: %s", e)
            raise LlmError(f"LLM call failed after retries: {e}") from e
        except Exception as e:
            # 非可重试异常直接抛出（如认证错误）
            self.stats.errors += 1
            logger.exception("LLM call failed (non-retryable): %s", e)
            raise LlmError(f"LLM call failed: {e}") from e

    async def _do_single_call(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict | None,
        litellm_module: Any,
        start_time: float,
    ) -> LlmResponse:
        """执行单次 LLM 调用（不含重试逻辑）。"""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "timeout": self.timeout,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await litellm_module.acompletion(**kwargs)
        elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        content = response.choices[0].message.content or ""
        tokens_input = response.usage.prompt_tokens if response.usage else 0
        tokens_output = response.usage.completion_tokens if response.usage else 0

        cost = self._compute_cost(model, tokens_input, tokens_output)

        result = LlmResponse(
            content=content,
            model=response.model or model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=float(cost),
            duration_ms=elapsed_ms,
            raw=response,
        )
        self.stats.add(result)
        return result

    def _mock_response(
        self, model: str, messages: list[dict[str, str]]
    ) -> LlmResponse:
        """Mock 模式：返回空内容（由 Agent 自行处理）。"""
        result = LlmResponse(
            content="[]",  # 默认空 findings
            model=f"{model} (mock)",
            tokens_input=10,
            tokens_output=2,
            cost_usd=0.0,
            duration_ms=1.0,
            mock=True,
        )
        self.stats.add(result)
        return result

    @staticmethod
    def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
        """计算单次调用成本（USD）。

        优先用 litellm 内置价格表；不认识时降级到 _CUSTOM_MODEL_PRICES。
        """
        # 去掉 provider 前缀（"anthropic/glm-5.2" → "glm-5.2"）
        bare_model = model.split("/", 1)[-1]

        # 1. 自定义价格表（最快，无需网络）
        if bare_model in _CUSTOM_MODEL_PRICES:
            prices = _CUSTOM_MODEL_PRICES[bare_model]
            return (
                tokens_in * prices["input_cost_per_token"]
                + tokens_out * prices["output_cost_per_token"]
            )

        # 2. 兜底：litellm 内置价格
        try:
            import litellm  # noqa: PLC0415
            return float(litellm.completion_cost(
                model=model,
                prompt=" ",  # litellm 会用 token count 推算
                completion=" ",
            ) or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0


@lru_cache
def get_llm_client() -> LlmClient:
    """单例获取 LLM 客户端。"""
    from cra.core import get_settings  # noqa: PLC0415

    settings = get_settings()
    return LlmClient(
        default_model=settings.default_model,
        timeout=settings.llm_timeout,
    )


def _resolve_class(dotted_path: str):
    """按 'module.Class' 形式动态解析类。

    Args:
        dotted_path: 例如 'litellm.Timeout' 或 'httpx.ReadTimeout'

    Returns:
        类对象，解析失败返回 None。
    """
    try:
        module_path, _, class_name = dotted_path.rpartition(".")
        if not module_path:
            return None
        import importlib  # noqa: PLC0415

        module = importlib.import_module(module_path)
        return getattr(module, class_name, None)
    except ImportError:
        return None
