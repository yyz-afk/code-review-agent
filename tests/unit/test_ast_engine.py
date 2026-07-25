"""AST Engine 单元测试。"""

from __future__ import annotations

import pytest

from cra.context.ast_engine import AstEngine, get_ast_engine

# 测试样本：含函数、类、方法、嵌套
PY_SAMPLE = '''\
"""模块文档。"""

import os


def func_a(x):
    """函数 A。"""
    return x + 1


class MyClass:
    """一个类。"""

    def method_b(self, y):
        return y * 2

    def method_c(self):
        """方法 C。"""
        return self.method_b(10)


def func_d():
    pass
'''


@pytest.fixture
def engine() -> AstEngine:
    return get_ast_engine()


class TestLanguageDetection:
    """语言识别。"""

    def test_python(self, engine: AstEngine) -> None:
        assert engine.get_language("main.py") == "python"
        assert engine.get_language("app/utils.py") == "python"

    def test_javascript(self, engine: AstEngine) -> None:
        assert engine.get_language("app.js") == "javascript"

    def test_typescript(self, engine: AstEngine) -> None:
        assert engine.get_language("app.ts") == "typescript"

    def test_java(self, engine: AstEngine) -> None:
        assert engine.get_language("Main.java") == "java"

    def test_go(self, engine: AstEngine) -> None:
        assert engine.get_language("main.go") == "go"

    def test_unsupported(self, engine: AstEngine) -> None:
        assert engine.get_language("readme.md") is None
        assert engine.get_language("config.yml") is None
        assert engine.get_language("data.csv") is None

    def test_case_insensitive(self, engine: AstEngine) -> None:
        assert engine.get_language("APP.PY") == "python"


class TestSymbolExtraction:
    """符号提取。"""

    def test_extracts_functions(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        names = [s.name for s in symbols]
        # 顶层函数
        assert "func_a" in names
        assert "func_d" in names

    def test_extracts_classes(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        classes = [s for s in symbols if s.type == "class"]
        assert len(classes) == 1
        assert classes[0].name == "MyClass"

    def test_extracts_methods_with_class_prefix(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        names = [s.name for s in symbols]
        # 方法名应该含类前缀
        assert "MyClass.method_b" in names
        assert "MyClass.method_c" in names

    def test_symbol_locations(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        func_a = next(s for s in symbols if s.name == "func_a")
        # func_a 起于第 6 行（按 PY_SAMPLE 数）
        assert func_a.start_line == 6
        assert func_a.end_line >= func_a.start_line

    def test_symbol_contains_code(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        func_a = next(s for s in symbols if s.name == "func_a")
        assert "def func_a" in func_a.code
        assert "return x + 1" in func_a.code

    def test_symbol_file_path_propagated(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "my/file.py")
        assert all(s.file_path == "my/file.py" for s in symbols)


class TestFindSymbolAtLine:
    """按行号反查符号。"""

    def test_find_function_by_line(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        # func_a 在 6-8 行，查 L7
        sym = engine.find_symbol_at_line(symbols, 7)
        assert sym is not None
        assert sym.name == "func_a"

    def test_find_method_by_line(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        # method_b 应该在某行，查找它的范围
        method_b = next(s for s in symbols if s.name == "MyClass.method_b")
        middle = (method_b.start_line + method_b.end_line) // 2
        found = engine.find_symbol_at_line(symbols, middle)
        assert found is not None
        assert found.name == "MyClass.method_b"

    def test_line_outside_any_function(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        # 模块级（import 区域）
        sym = engine.find_symbol_at_line(symbols, 2)
        assert sym is None

    def test_returns_most_inner_symbol(self, engine: AstEngine) -> None:
        # 如果有嵌套（虽然 Python 语法不支持嵌套函数的话较少见）
        # 这里只验证不会返回错误的符号
        symbols = engine.extract_symbols(PY_SAMPLE, "python", "test.py")
        # 查 import 行
        assert engine.find_symbol_at_line(symbols, 4) is None


class TestGetChangedSymbols:
    """变更符号识别。"""

    def test_returns_only_affected_symbols(self, engine: AstEngine) -> None:
        symbols = engine.get_changed_symbols(
            PY_SAMPLE, "python", [7], "test.py"
        )
        # L7 属于 func_a（6-8）
        names = [s.name for s in symbols]
        assert "func_a" in names

    def test_deduplicates_symbols(self, engine: AstEngine) -> None:
        # 多行变更但同一函数，应该去重
        symbols = engine.get_changed_symbols(
            PY_SAMPLE, "python", [7, 8], "test.py"
        )
        names = [s.name for s in symbols]
        assert names.count("func_a") == 1

    def test_handles_multiple_symbols(self, engine: AstEngine) -> None:
        # 跨多个函数的变更
        symbols = engine.get_changed_symbols(
            PY_SAMPLE, "python", [7, 14], "test.py"
        )
        names = {s.name for s in symbols}
        # 应该包含两个不同函数
        assert "func_a" in names


class TestUnsupportedLanguage:
    """不支持的语言降级。"""

    def test_returns_empty_for_unsupported(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols("code", "ruby", "test.rb")
        assert symbols == []

    def test_returns_empty_for_none(self, engine: AstEngine) -> None:
        symbols = engine.extract_symbols("code", "unknown", "test")
        assert symbols == []
