"""DiffParser 单元测试。"""

from __future__ import annotations

import pytest

from cra.context.diff_parser import DiffParser, parse_git_diff
from cra.core.models import ChangeStatus

from tests.fixtures.sample_diffs import (
    DELETE_FILE_DIFF,
    MULTI_FILE_DIFF,
    MULTI_HUNK_DIFF,
    SIMPLE_DIFF,
    UTF8_DIFF,
)


class TestSimpleDiff:
    """单文件、单 hunk 的基础场景。"""

    def test_parses_single_file(self) -> None:
        files = parse_git_diff(SIMPLE_DIFF)
        assert len(files) == 1

    def test_new_file_status(self) -> None:
        files = parse_git_diff(SIMPLE_DIFF)
        assert files[0].status == ChangeStatus.ADDED
        assert files[0].path == "example.py"

    def test_records_additions(self) -> None:
        files = parse_git_diff(SIMPLE_DIFF)
        assert files[0].additions == 5
        assert files[0].deletions == 0

    def test_extracts_hunk(self) -> None:
        files = parse_git_diff(SIMPLE_DIFF)
        assert len(files[0].hunks) == 1
        hunk = files[0].hunks[0]
        assert hunk.new_start == 1
        assert hunk.new_lines == 5
        assert "import os" in hunk.content


class TestMultiHunkDiff:
    """同一文件多个 hunk。"""

    def test_parses_multiple_hunks(self) -> None:
        files = parse_git_diff(MULTI_HUNK_DIFF)
        assert len(files) == 1
        assert len(files[0].hunks) == 2

    def test_hunk_line_ranges(self) -> None:
        files = parse_git_diff(MULTI_HUNK_DIFF)
        h1, h2 = files[0].hunks
        # 第一个 hunk: @@ -5,4 +5,7 @@（new_start=5, new_lines=7）
        assert h1.new_start == 5
        assert h1.new_lines == 7
        # 第二个 hunk: @@ -20,3 +23,5 @@（new_start=23, new_lines=5）
        assert h2.new_start == 23
        assert h2.new_lines == 5

    def test_additions_count(self) -> None:
        files = parse_git_diff(MULTI_HUNK_DIFF)
        # 第一个 hunk: +3 行（def new_func / return 42 / 空行）
        # 第二个 hunk: +2 行（z=3 / return x+y+z）
        # 合计 5
        assert files[0].additions == 5


class TestMultiFileDiff:
    """多文件 diff。"""

    def test_parses_multiple_files(self) -> None:
        files = parse_git_diff(MULTI_FILE_DIFF)
        assert len(files) == 2
        assert files[0].path == "main.py"
        assert files[1].path == "utils.py"

    def test_modified_status(self) -> None:
        files = parse_git_diff(MULTI_FILE_DIFF)
        assert all(f.status == ChangeStatus.MODIFIED for f in files)


class TestDeleteFile:
    """删除文件场景。"""

    def test_deleted_status(self) -> None:
        files = parse_git_diff(DELETE_FILE_DIFF)
        assert files[0].status == ChangeStatus.DELETED

    def test_records_deletions(self) -> None:
        files = parse_git_diff(DELETE_FILE_DIFF)
        assert files[0].deletions == 5


class TestUtf8Diff:
    """中文内容（UTF-8）。"""

    def test_handles_chinese_content(self) -> None:
        files = parse_git_diff(UTF8_DIFF)
        assert len(files) == 1
        # 验证中文未乱码
        content = files[0].hunks[0].content
        assert "处理用户请求" in content

    def test_handles_chinese_path(self) -> None:
        # 假设路径含中文（虽然少见，但应能解析）
        diff = """\
diff --git a/工具.py b/工具.py
index 1111111..2222222 100644
--- a/工具.py
+++ b/工具.py
@@ -1,2 +1,3 @@
 def x():
     pass
+    return None
"""
        files = parse_git_diff(diff)
        assert files[0].path == "工具.py"


class TestEdgeCases:
    """边界情况。"""

    def test_empty_diff(self) -> None:
        assert parse_git_diff("") == []

    def test_binary_file_diff_skipped_gracefully(self) -> None:
        # 二进制文件的 diff 无 hunks，应能优雅处理
        diff = """\
diff --git a/logo.png b/logo.png
index 1111111..2222222 100644
Binary files a/logo.png and b/logo.png differ
"""
        # 应该不抛异常
        files = parse_git_diff(diff)
        # 二进制文件可能被记录但无 hunks
        assert isinstance(files, list)

    def test_double_parse_returns_same_result(self) -> None:
        """多次解析结果一致（幂等）。"""
        f1 = parse_git_diff(SIMPLE_DIFF)
        f2 = parse_git_diff(SIMPLE_DIFF)
        assert len(f1) == len(f2)
        assert f1[0].path == f2[0].path


class TestInstantiation:
    """实例化测试。"""

    def test_parser_instance(self) -> None:
        parser = DiffParser()
        assert parser is not None
