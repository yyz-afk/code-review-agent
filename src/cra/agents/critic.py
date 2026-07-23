"""Critic Agent：对其他 Agent 的 findings 做去重 + 置信度过滤。

v0.7 抽取为独立类，便于：
- 单元测试（不再混在 Orchestrator 里）
- Phase 2 升级为 LLM 驱动的验证层（当前是规则驱动）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from cra.core.models import Finding

logger = logging.getLogger(__name__)


@dataclass
class CriticResult:
    """Critic 处理结果。"""

    verified: list[Finding] = field(default_factory=list)
    dropped_duplicates: list[Finding] = field(default_factory=list)
    dropped_low_confidence: list[Finding] = field(default_factory=list)
    total_input: int = 0

    @property
    def total_dropped(self) -> int:
        return len(self.dropped_duplicates) + len(self.dropped_low_confidence)

    @property
    def drop_rate(self) -> float:
        if self.total_input == 0:
            return 0.0
        return self.total_dropped / self.total_input


class CriticAgent:
    """Critic 验证 Agent（规则驱动，Phase 2 可升级为 LLM 驱动）。

    职责：
    1. 跨 Agent / 跨 hunk 去重（同位置 + 相似标题）
    2. 按置信度阈值过滤
    3. 严重度排序
    """

    def __init__(
        self,
        line_bucket_size: int = 5,
        confidence_threshold: float = 0.5,
    ) -> None:
        self.line_bucket_size = line_bucket_size
        self.confidence_threshold = confidence_threshold

    def verify(
        self,
        findings: list[Finding],
    ) -> CriticResult:
        """对原始 findings 做去重 + 过滤。"""
        result = CriticResult(total_input=len(findings))

        if not findings:
            return result

        # Step 1: 置信度过滤
        passed_conf = []
        for f in findings:
            if f.confidence >= self.confidence_threshold:
                passed_conf.append(f)
            else:
                result.dropped_low_confidence.append(f)

        # Step 2: 去重（按 file + line_bucket + normalized_title）
        seen: dict[tuple, Finding] = {}
        for f in passed_conf:
            key = self._make_key(f)
            existing = seen.get(key)
            if existing is None:
                seen[key] = f
            else:
                # 保留置信度更高的
                if f.confidence > existing.confidence:
                    result.dropped_duplicates.append(existing)
                    seen[key] = f
                else:
                    result.dropped_duplicates.append(f)

        # Step 3: 排序（severity rank → confidence desc → line asc）
        verified = sorted(
            seen.values(),
            key=lambda f: (
                f.severity.rank,
                -f.confidence,
                f.start_line,
            ),
        )
        result.verified = verified

        if result.drop_rate > 0.5:
            logger.warning(
                "Critic dropped %.0f%% of findings (may indicate agent over-reporting)",
                result.drop_rate * 100,
            )

        return result

    def _make_key(self, f: Finding) -> tuple:
        """生成去重 key。"""
        line_bucket = f.start_line // max(self.line_bucket_size, 1)
        normalized_title = self._normalize_title(f.title)
        return (f.file_path, line_bucket, normalized_title)

    @staticmethod
    def _normalize_title(title: str) -> str:
        """归一化标题：小写 + 去多余空白 + 去标点 + 末尾 strip。"""
        import re  # noqa: PLC0415

        s = title.lower().strip()
        s = re.sub(r"[^\w\s]", " ", s)  # 标点 → 空格
        s = re.sub(r"\s+", " ", s)  # 多空格 → 单空格
        return s.strip()  # 最后再 strip 一次（标点转的末尾空格）
