"""读取 .cra.toml 配置文件。

支持团队自定义规则，让仓库根目录放一个 .cra.toml 即可定制审查行为。

Example .cra.toml:
    [review]
    enabled_agents = ["correctness", "security"]
    confidence_threshold = 0.6
    max_findings_per_file = 3

    [review.excluded_paths]
    patterns = ["vendor/**", "**/*.generated.*", "tests/fixtures/**"]

    [[review.custom_rules]]
    id = "no-print-in-prod"
    severity = "low"
    pattern = "^\\s*print\\("
    message = "生产代码不应包含 print 语句"

    [llm]
    model = "anthropic/glm-5.2"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cra.agents.orchestrator import ReviewConfig

logger = logging.getLogger(__name__)

try:
    import tomllib  # Python 3.11+ 内置
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]  # 3.10 fallback
    except ImportError:
        tomllib = None  # type: ignore[assignment]


class ProjectConfig:
    """项目级配置（从 .cra.toml 加载）。"""

    def __init__(self) -> None:
        self.enabled_agents: list[str] | None = None
        self.confidence_threshold: float | None = None
        self.max_findings_per_file: int | None = None
        self.excluded_paths: list[str] = []
        self.custom_rules: list[dict] = []
        self.model: str | None = None
        self.llm_profile: str | None = None
        self._loaded = False
        self._source: Path | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def source_path(self) -> Path | None:
        return self._source

    def apply_to_review_config(self, config: ReviewConfig) -> None:
        """把项目配置应用到 ReviewConfig（仅覆盖已设置的字段）。

        优先级规范：CLI 参数 > .cra.toml > 默认值
        因此本方法只在 CLI 没显式设置时才覆盖（由调用方保证）。
        """
        if self.enabled_agents is not None:
            config.enabled_agents = self.enabled_agents
        if self.confidence_threshold is not None:
            config.confidence_threshold = self.confidence_threshold
        if self.max_findings_per_file is not None:
            config.max_findings_per_file = self.max_findings_per_file

    def matches_excluded(self, file_path: str) -> bool:
        """检查文件是否匹配排除路径。"""
        if not self.excluded_paths:
            return False
        from fnmatch import fnmatch  # noqa: PLC0415

        normalized = file_path.replace("\\", "/")
        for pattern in self.excluded_paths:
            # 支持 ** glob
            simple_pattern = pattern.replace("**/", "").replace("/**", "")
            if fnmatch(normalized, pattern) or fnmatch(normalized, simple_pattern):
                return True
        return False


# ============================================================
# 加载逻辑
# ============================================================


def find_config_file(start_dir: Path | None = None) -> Path | None:
    """从 start_dir 向上查找 .cra.toml。"""
    if tomllib is None:
        return None
    if start_dir is None:
        start_dir = Path.cwd()

    for path in [start_dir, *start_dir.parents]:
        candidate = path / ".cra.toml"
        if candidate.is_file():
            return candidate
        # 防止越界（最多向上 10 层）
        if path == path.parent:
            break
    return None


def load_project_config(start_dir: Path | None = None) -> ProjectConfig:
    """加载 .cra.toml 配置。

    找不到则返回空配置（is_loaded=False）。
    """
    config = ProjectConfig()
    if tomllib is None:
        logger.debug("tomllib/tomli not available, .cra.toml disabled")
        return config

    config_file = find_config_file(start_dir)
    if config_file is None:
        return config

    try:
        with open(config_file, "rb") as f:
            data: dict[str, Any] = tomllib.load(f)
    except (OSError, ValueError) as e:
        logger.warning("Failed to parse %s: %s", config_file, e)
        return config

    review = data.get("review", {})
    config.enabled_agents = review.get("enabled_agents")
    config.confidence_threshold = review.get("confidence_threshold")
    config.max_findings_per_file = review.get("max_findings_per_file")

    excluded = review.get("excluded_paths", {})
    if isinstance(excluded, dict):
        config.excluded_paths = excluded.get("patterns", [])
    elif isinstance(excluded, list):
        config.excluded_paths = excluded

    config.custom_rules = review.get("custom_rules", [])

    llm = data.get("llm", {})
    config.model = llm.get("model")
    config.llm_profile = llm.get("profile")

    config._loaded = True
    config._source = config_file
    logger.info("Loaded project config from %s", config_file)
    return config
