"""核心领域模型。

设计原则：
- 与持久化解耦（不依赖 SQLAlchemy）
- 与 LLM 解耦（不依赖 LiteLLM）
- Pydantic v2 强类型校验
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ============================================================
# 枚举
# ============================================================


class Severity(str, Enum):
    """严重程度。"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def icon(self) -> str:
        return {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
            "info": "⚪",
        }[self.value]

    @property
    def rank(self) -> int:
        """用于排序，数字越小越严重。"""
        return ["critical", "high", "medium", "low", "info"].index(self.value)


class Category(str, Enum):
    """问题类别。"""

    SECURITY = "security"
    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    TEST = "test"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"


class ChangeStatus(str, Enum):
    """文件变更类型。"""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


# ============================================================
# Diff 相关
# ============================================================


class Hunk(BaseModel):
    """Diff 中的连续变更块。"""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    content: str
    symbol: str | None = None  # AST 识别后填充：所属函数/类


class FileChange(BaseModel):
    """单个文件的变更。"""

    path: str
    old_path: str | None = None
    status: ChangeStatus
    additions: int = 0
    deletions: int = 0
    hunks: list[Hunk] = Field(default_factory=list)
    language: str | None = None
    full_content: str | None = None  # 完整文件内容（审查时加载）


class Diff(BaseModel):
    """代码变更集合。"""

    repo_path: Path | None = None
    base_ref: str
    head_ref: str
    files: list[FileChange] = Field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0

    @property
    def changed_files_count(self) -> int:
        return len(self.files)

    @property
    def is_noise(self) -> bool:
        """是否噪音 PR（仅文档/锁文件等）。"""
        if not self.files:
            return True
        return all(_is_noise_file(f.path) for f in self.files)


def _is_noise_file(path: str) -> bool:
    """判断是否噪音文件。"""
    noise_suffixes = {".md", ".txt", ".rst", ".lock"}
    noise_dirs = {"docs/", "doc/", "vendor/", "node_modules/"}
    noise_names = {
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "Cargo.lock",
        "go.sum",
        "Pipfile.lock",
    }
    path_str = path.replace("\\", "/")
    if path_str.lower() in noise_names:
        return True
    if any(path_str.endswith(suf) for suf in noise_suffixes):
        return True
    if any(d in path_str for d in noise_dirs):
        return True
    return False


# ============================================================
# Finding（核心输出）
# ============================================================


class Finding(BaseModel):
    """单条审查发现。"""

    id: UUID = Field(default_factory=uuid4)
    agent: str
    severity: Severity
    category: Category
    file_path: str
    start_line: int
    end_line: int
    title: str = Field(..., max_length=200)
    description: str
    suggestion: str | None = None
    evidence: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    verified_by_tool: str | None = None


class ReviewStats(BaseModel):
    """审查统计。"""

    files_reviewed: int = 0
    lines_reviewed: int = 0
    agents_run: int = 0
    duration_sec: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    findings_by_category: dict[str, int] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    """审查最终输出。"""

    base_ref: str
    head_ref: str
    findings: list[Finding] = Field(default_factory=list)
    stats: ReviewStats = Field(default_factory=ReviewStats)
    created_at: datetime = Field(default_factory=datetime.now)
    errors: list[str] = Field(default_factory=list)

    @property
    def overall_risk(self) -> Severity:
        """整体风险等级（取最严重的 finding）。"""
        if not self.findings:
            return Severity.INFO
        return min(self.findings, key=lambda f: f.severity.rank).severity

    @property
    def blockers(self) -> list[Finding]:
        """阻断性问题（critical/high）。"""
        return [f for f in self.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]


# ============================================================
# Agent 上下文
# ============================================================


class SymbolInfo(BaseModel):
    """代码符号信息。"""

    name: str
    type: str  # function / class / method
    file_path: str
    start_line: int
    end_line: int
    code: str  # 符号对应的源码片段
    signature: str | None = None
    docstring: str | None = None


class AgentContext(BaseModel):
    """单个 Agent 执行所需的上下文。"""

    file_path: str
    file_content: str
    # 原始文件中的行号范围（1-based，闭区间）
    # LLM 返回的行号应基于这个范围
    original_start_line: int = 1
    original_end_line: int = 1
    changed_symbols: list[SymbolInfo] = Field(default_factory=list)
    related_symbols: list[SymbolInfo] = Field(default_factory=list)
    diff_hunks: list[Hunk] = Field(default_factory=list)
