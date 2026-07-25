"""Code Review Agent CLI 入口。

使用 typer 实现，提供 review / version 命令。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Windows 控制台 UTF-8 支持（必须早于其他 import 之外的输出）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        # Python < 3.7 或无 tty 时跳过
        pass

import typer
from rich.console import Console
from rich.logging import RichHandler

from cra import __version__
from cra.agents.orchestrator import ReviewConfig, ReviewOrchestrator
from cra.cli.reporter import render, save_report
from cra.core import get_settings
from cra.core.errors import CodeReviewError

app = typer.Typer(
    name="code-review",
    help="AI Code Review Agent — 基于 LLM 的代码审查工具",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _setup_logging(level: str = "INFO") -> None:
    """配置 rich 日志。"""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(
            console=console,
            show_time=False,
            show_path=False,
            rich_tracebacks=True,
        )],
    )


def _print_banner() -> None:
    console.print(
        f"\n[bold blue]Code Review Agent[/bold blue] "
        f"[dim]v{__version__}[/dim]\n"
    )


@app.command()
def version() -> None:
    """显示版本号。"""
    console.print(f"code-review-agent v{__version__}")


@app.command()
def review(
    base: str = typer.Option(
        None,
        "--base", "-b",
        help="Base ref（分支/commit/tag），例如 main 或 HEAD~1",
    ),
    head: str = typer.Option(
        "HEAD",
        "--head",
        help="Head ref，默认 HEAD",
    ),
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo", "-r",
        help="Git 仓库路径（默认当前目录）",
        exists=True,
        file_okay=False,
    ),
    diff_file: Path = typer.Option(
        None,
        "--diff",
        help="从 diff 文件读取（替代 git diff）",
        exists=True,
        dir_okay=False,
    ),
    fmt: str = typer.Option(
        "text",
        "--format", "-f",
        help="输出格式：text / markdown / json / sarif",
    ),
    output: Path = typer.Option(
        None,
        "--output", "-o",
        help="输出到文件（默认 stdout）",
    ),
    confidence: float = typer.Option(
        None,
        "--confidence",
        help="置信度阈值（0.0-1.0，默认从配置读取）",
        min=0.0, max=1.0,  # v0.8.1：范围校验，typer 自动报错
    ),
    agents: str = typer.Option(
        None,
        "--agents",
        help="启用的 Agent（逗号分隔：correctness,security,performance,architecture）",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="静默模式（不输出 banner / 统计）",
    ),
) -> None:
    """审查代码变更。"""
    settings = get_settings()
    _setup_logging(settings.log_level)

    if not quiet:
        _print_banner()

    # 构建配置
    enabled_agents: list[str] | None = None
    if agents:
        enabled_agents = [a.strip() for a in agents.split(",") if a.strip()]

    config = ReviewConfig(
        confidence_threshold=confidence or settings.confidence_threshold,
        max_findings_per_file=settings.max_findings_per_file,
        enabled_agents=enabled_agents if enabled_agents else None,
    )

    # 加载项目级 .cra.toml（命令行参数优先级最高，不被覆盖）
    from cra.core.config_loader import load_project_config  # noqa: PLC0415

    project_cfg = load_project_config(Path.cwd())
    if project_cfg.is_loaded:
        # v0.8.1：CLI 优先，仅填充 CLI 未指定的字段
        if enabled_agents is None:
            project_cfg.apply_to_review_config(config)
        else:
            # agents 已被 CLI 指定，只覆盖其他字段
            if project_cfg.confidence_threshold is not None and confidence is None:
                config.confidence_threshold = project_cfg.confidence_threshold
            if project_cfg.max_findings_per_file is not None:
                config.max_findings_per_file = project_cfg.max_findings_per_file
        console.print(
            f"[dim]Loaded project config: {project_cfg.source_path}[/dim]"
        )

    # v0.8.1：把 project_config 传给 orchestrator 让其生效
    # （excluded_paths / custom_rules 在 orchestrator 中真正使用）
    orchestrator = ReviewOrchestrator(config=config, project_config=project_cfg)

    async def run():
        if diff_file:
            diff_text = diff_file.read_text(encoding="utf-8")
            return await orchestrator.review_diff(diff_text)
        if not base:
            console.print("[red]Error:[/red] 必须指定 --base 或 --diff")
            raise typer.Exit(2)
        return await orchestrator.review_git(repo, base, head)

    try:
        result = asyncio.run(run())
    except CodeReviewError as e:
        console.print(f"[red]Review failed:[/red] {e}")
        raise typer.Exit(5) from e
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        raise typer.Exit(130) from None

    # 渲染输出
    content = render(result, fmt)

    if output:
        save_report(result, output, fmt)
        console.print(f"[green]✓ Report saved to[/green] {output}")
    else:
        console.print(content)

    # 退出码：有 critical/high → 1，否则 0
    if result.blockers:
        if not quiet:
            console.print(
                f"\n[red]⚠️  {len(result.blockers)} blocker(s) found[/red]"
            )
        raise typer.Exit(1)


@app.command()
def info() -> None:
    """显示当前配置信息。"""
    settings = get_settings()
    _print_banner()
    console.print("[bold]Configuration:[/bold]")
    console.print(f"  env:                {settings.env}")
    console.print(f"  default_model:      {settings.default_model}")
    console.print(f"  deep_model:         {settings.deep_model}")
    console.print(f"  confidence_thresh:  {settings.confidence_threshold}")
    console.print(f"  max_findings/file:  {settings.max_findings_per_file}")
    console.print(f"  log_level:          {settings.log_level}")

    # API Key 状态
    import os
    console.print("\n[bold]LLM Providers:[/bold]")
    for name, key in [
        ("DEEPSEEK", "DEEPSEEK_API_KEY"),
        ("OPENAI", "OPENAI_API_KEY"),
        ("ANTHROPIC", "ANTHROPIC_API_KEY"),
    ]:
        status = "[green]✓[/green]" if os.environ.get(key) else "[red]✗[/red]"
        console.print(f"  {status} {name}")


def main() -> None:
    """入口点。"""
    app()


if __name__ == "__main__":
    main()
