"""CriticAgent 单元测试。"""

from __future__ import annotations

from uuid import uuid4

from cra.agents.critic import CriticAgent
from cra.core.models import Category, Finding, Severity


def _f(
    file: str = "a.py",
    line: int = 10,
    title: str = "test issue",
    confidence: float = 0.8,
    agent: str = "correctness",
    severity: Severity = Severity.MEDIUM,
) -> Finding:
    return Finding(
        id=uuid4(),
        agent=agent,
        severity=severity,
        category=Category.CORRECTNESS,
        file_path=file,
        start_line=line,
        end_line=line,
        title=title,
        description="d",
        confidence=confidence,
    )


class TestCriticBasics:
    def test_empty_input(self) -> None:
        critic = CriticAgent()
        result = critic.verify([])
        assert result.verified == []
        assert result.total_input == 0
        assert result.drop_rate == 0.0

    def test_single_finding_passes(self) -> None:
        critic = CriticAgent()
        f = _f(confidence=0.9)
        result = critic.verify([f])
        assert len(result.verified) == 1
        assert result.dropped_duplicates == []
        assert result.dropped_low_confidence == []


class TestConfidenceFilter:
    def test_filters_low_confidence(self) -> None:
        critic = CriticAgent(confidence_threshold=0.5)
        low = _f(confidence=0.3)
        high = _f(confidence=0.9, line=20, title="other")
        result = critic.verify([low, high])
        assert len(result.verified) == 1
        assert result.dropped_low_confidence == [low]
        assert result.verified[0] == high

    def test_boundary_at_threshold(self) -> None:
        critic = CriticAgent(confidence_threshold=0.5)
        f = _f(confidence=0.5)
        result = critic.verify([f])
        assert len(result.verified) == 1

    def test_custom_threshold(self) -> None:
        critic = CriticAgent(confidence_threshold=0.8)
        f1 = _f(confidence=0.6, line=1, title="a")
        f2 = _f(confidence=0.9, line=2, title="b")
        result = critic.verify([f1, f2])
        assert result.dropped_low_confidence == [f1]
        assert result.verified == [f2]


class TestDeduplication:
    def test_dedup_same_file_line_title(self) -> None:
        critic = CriticAgent()
        f1 = _f(line=10, confidence=0.7)
        f2 = _f(line=10, confidence=0.9)
        result = critic.verify([f1, f2])
        assert len(result.verified) == 1
        # 应保留置信度高的
        assert result.verified[0].confidence == 0.9
        assert len(result.dropped_duplicates) == 1

    def test_dedup_nearby_lines(self) -> None:
        """默认 line_bucket=5，L10 和 L11 应去重（同 bucket）。"""
        critic = CriticAgent(line_bucket_size=5)
        f1 = _f(line=10, title="a", confidence=0.7)
        f2 = _f(line=11, title="a", confidence=0.8)
        result = critic.verify([f1, f2])
        assert len(result.verified) == 1

    def test_keep_different_lines_far_apart(self) -> None:
        critic = CriticAgent(line_bucket_size=5)
        f1 = _f(line=10, title="a")
        f2 = _f(line=100, title="a")
        result = critic.verify([f1, f2])
        assert len(result.verified) == 2

    def test_different_files_kept(self) -> None:
        critic = CriticAgent()
        f1 = _f(file="a.py", line=10, title="a")
        f2 = _f(file="b.py", line=10, title="a")
        result = critic.verify([f1, f2])
        assert len(result.verified) == 2

    def test_different_titles_kept(self) -> None:
        critic = CriticAgent()
        f1 = _f(line=10, title="SQL injection")
        f2 = _f(line=10, title="resource leak")
        result = critic.verify([f1, f2])
        assert len(result.verified) == 2

    def test_title_case_insensitive(self) -> None:
        critic = CriticAgent()
        f1 = _f(line=10, title="SQL Injection")
        f2 = _f(line=10, title="sql injection")
        result = critic.verify([f1, f2])
        assert len(result.verified) == 1

    def test_title_punctuation_normalized(self) -> None:
        critic = CriticAgent()
        f1 = _f(line=10, title="SQL: Injection!")
        f2 = _f(line=10, title="sql injection")
        result = critic.verify([f1, f2])
        assert len(result.verified) == 1


class TestSorting:
    def test_sorts_by_severity_then_confidence(self) -> None:
        critic = CriticAgent()
        critical_low = _f(line=1, title="a", confidence=0.6, severity=Severity.CRITICAL)
        high_high = _f(line=2, title="b", confidence=0.95, severity=Severity.HIGH)
        critical_high = _f(line=3, title="c", confidence=0.95, severity=Severity.CRITICAL)
        result = critic.verify([critical_low, high_high, critical_high])
        # 期望顺序：critical_high → critical_low → high_high
        assert result.verified[0] == critical_high
        assert result.verified[1] == critical_low
        assert result.verified[2] == high_high


class TestResultStats:
    def test_drop_rate_calculation(self) -> None:
        critic = CriticAgent(confidence_threshold=0.5)
        f1 = _f(line=1, title="a", confidence=0.3)  # 会被过滤
        f2 = _f(line=2, title="b", confidence=0.9)
        result = critic.verify([f1, f2])
        assert result.total_input == 2
        assert result.drop_rate == 0.5

    def test_total_dropped(self) -> None:
        critic = CriticAgent(confidence_threshold=0.5)
        low = _f(line=1, title="a", confidence=0.3)
        dup1 = _f(line=2, title="b", confidence=0.7)
        dup2 = _f(line=2, title="b", confidence=0.8)
        result = critic.verify([low, dup1, dup2])
        assert result.total_dropped == 2  # 1 low + 1 dup
