"""Git Diff 解析器。

基于 GitPython 获取 diff，解析为结构化的 FileChange / Hunk。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from cra.core.models import ChangeStatus, Diff, FileChange, Hunk


class DiffParser:
    """解析 git diff 输出。"""

    # Hunk 头部：@@ -old_start,old_lines +new_start,new_lines @@
    HUNK_HEADER = re.compile(
        r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? "
        r"\+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@"
    )

    def parse_unified_diff(self, diff_text: str) -> list[FileChange]:
        """解析 unified diff 格式文本。"""
        files: list[FileChange] = []
        current_file: FileChange | None = None
        current_hunk_lines: list[str] = []
        # 暂存 --- 与 +++ 行，待两者齐全时再创建 FileChange
        pending_old_path: str | None = None
        pending_new_path: str | None = None
        # 标记是否已经基于 ---/+++ 创建了 FileChange（避免重复创建）
        file_created_from_header = False

        def flush_file() -> None:
            """收尾当前文件。"""
            nonlocal current_file, current_hunk_lines
            if current_file is not None:
                if current_hunk_lines:
                    self._finalize_hunk(current_file, current_hunk_lines)
                    current_hunk_lines = []
                files.append(current_file)
            current_file = None

        def try_create_from_header() -> None:
            """根据 --- 与 +++ 创建 FileChange（处理 add/delete/modify/rename）。"""
            nonlocal current_file, file_created_from_header
            if file_created_from_header:
                return
            if pending_old_path is None and pending_new_path is None:
                return

            old = pending_old_path
            new = pending_new_path

            if old == "/dev/null" and new and new != "/dev/null":
                # 新增文件
                current_file = FileChange(
                    path=_strip_prefix(new),
                    status=ChangeStatus.ADDED,
                )
            elif new == "/dev/null" and old and old != "/dev/null":
                # 删除文件
                current_file = FileChange(
                    path=_strip_prefix(old),
                    status=ChangeStatus.DELETED,
                )
            elif old and new and old != "/dev/null" and new != "/dev/null":
                old_clean = _strip_prefix(old)
                new_clean = _strip_prefix(new)
                if old_clean != new_clean:
                    current_file = FileChange(
                        path=new_clean,
                        old_path=old_clean,
                        status=ChangeStatus.RENAMED,
                    )
                else:
                    current_file = FileChange(
                        path=new_clean,
                        status=ChangeStatus.MODIFIED,
                    )
            file_created_from_header = True

        for line in diff_text.splitlines(keepends=False):
            # 新文件头：开始一个新文件块
            if line.startswith("diff --git"):
                flush_file()
                pending_old_path = None
                pending_new_path = None
                file_created_from_header = False
                continue

            # 暂存 ---/+++ 直到两者齐全
            if line.startswith("--- "):
                pending_old_path = line[4:].strip()
                continue
            if line.startswith("+++ "):
                pending_new_path = line[4:].strip()
                try_create_from_header()
                continue

            # 显式变更类型标记（在 ---/+++ 之前出现）
            if current_file is None and (
                line.startswith("new file mode")
                or line.startswith("deleted file mode")
                or line.startswith("rename from")
                or line.startswith("rename to")
                or line.startswith("old mode")
                or line.startswith("new mode")
                or line.startswith("similarity index")
                or line.startswith("dissimilarity index")
                or line.startswith("index ")
                or line.startswith("copy from")
                or line.startswith("copy to")
            ):
                # 这些标记在 ---/+++ 之前，先跳过；
                # 实际 add/delete/modify 状态会从 ---/+++ 推断
                # rename 信息也会从 ---/+++ 不一致推断
                if line.startswith("rename from"):
                    pending_old_path = line[len("rename from ") :]
                elif line.startswith("rename to"):
                    pending_new_path = line[len("rename to ") :]
                    try_create_from_header()
                continue

            # 在已经有 current_file 的场景下，遇到 rename 等标记更新
            if current_file is not None:
                if line.startswith("rename from"):
                    current_file.old_path = line[len("rename from ") :]
                elif line.startswith("rename to"):
                    current_file.status = ChangeStatus.RENAMED

            # Hunk 头
            if current_file is not None and line.startswith("@@"):
                if current_hunk_lines:
                    self._finalize_hunk(current_file, current_hunk_lines)
                    current_hunk_lines = []
                match = self.HUNK_HEADER.match(line)
                if match:
                    current_hunk_lines.append(line)
                continue

            # Hunk 内容
            if current_file is not None and current_hunk_lines:
                current_hunk_lines.append(line)
                if line.startswith("+") and not line.startswith("+++"):
                    current_file.additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    current_file.deletions += 1

        flush_file()
        return files

    def _finalize_hunk(self, file: FileChange, lines: list[str]) -> None:
        """把累积的行解析为 Hunk。"""
        if not lines:
            return
        header = lines[0]
        match = self.HUNK_HEADER.match(header)
        if not match:
            return
        file.hunks.append(
            Hunk(
                old_start=int(match.group("old_start")),
                old_lines=int(match.group("old_lines") or 1),
                new_start=int(match.group("new_start")),
                new_lines=int(match.group("new_lines") or 1),
                content="\n".join(lines),
            )
        )

    def get_diff_from_git(self, repo_path: Path, base: str, head: str) -> Diff:
        """从 Git 仓库获取 diff。"""
        diff_text = self._run_git_diff(repo_path, base, head)
        files = self.parse_unified_diff(diff_text)
        # 过滤掉无法解析的文件
        files = [f for f in files if f.hunks or f.status != ChangeStatus.MODIFIED]

        total_add = sum(f.additions for f in files)
        total_del = sum(f.deletions for f in files)

        return Diff(
            repo_path=repo_path,
            base_ref=base,
            head_ref=head,
            files=files,
            total_additions=total_add,
            total_deletions=total_del,
        )

    @staticmethod
    def _run_git_diff(repo_path: Path, base: str, head: str) -> str:
        """执行 git diff 命令。"""
        try:
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--no-color",
                    f"{base}...{head}",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"git diff failed: {e.stderr or e.stdout}") from e
        except FileNotFoundError as e:
            raise RuntimeError("git command not found") from e


def parse_git_diff(diff_text: str) -> list[FileChange]:
    """便捷函数：解析 diff 文本。"""
    return DiffParser().parse_unified_diff(diff_text)


def _strip_prefix(path: str) -> str:
    """去掉 git diff 路径前缀（a/ 或 b/）。

    Examples:
        "b/src/main.py" → "src/main.py"
        "a/old.py" → "old.py"
        "src/main.py" → "src/main.py"（无前缀时原样返回）
    """
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
