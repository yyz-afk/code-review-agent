"""AST 引擎：基于 tree-sitter 的多语言代码解析。

Spike 验证：Python 解析速度 38 万行/秒，符号级提取可节省 93% token。
v0.3：扩展 TS / Java / JS / Go 支持。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from cra.core.models import SymbolInfo

logger = logging.getLogger(__name__)


# ============================================================
# 语言映射：文件扩展名 → tree-sitter 语言标识符
# ============================================================

_LANGUAGE_REGISTRY: dict[str, str] = {
    # Python
    ".py": "python",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    # Java
    ".java": "java",
    # Go
    ".go": "go",
}


@lru_cache(maxsize=16)
def _get_parser(language: str):
    """获取指定语言的 parser（缓存）。

    动态 import 避免未安装语言的 grammar 时启动报错。
    """
    from tree_sitter import Language, Parser  # noqa: PLC0415

    lang_capsule = _load_language_capsule(language)
    lang = Language(lang_capsule)
    return Parser(lang), lang


def _load_language_capsule(language: str):
    """加载语言的 grammar capsule。"""
    if language == "python":
        import tree_sitter_python as tspython  # noqa: PLC0415
        return tspython.language()
    if language == "javascript":
        import tree_sitter_javascript as tsjs  # noqa: PLC0415
        return tsjs.language()
    if language == "typescript":
        import tree_sitter_typescript as tsts  # noqa: PLC0415
        return tsts.language_typescript()
    if language == "tsx":
        import tree_sitter_typescript as tsts  # noqa: PLC0415
        return tsts.language_tsx()
    if language == "java":
        import tree_sitter_java as tsjava  # noqa: PLC0415
        return tsjava.language()
    if language == "go":
        import tree_sitter_go as tsgo  # noqa: PLC0415
        return tsgo.language()
    raise ValueError(f"Unsupported language: {language}")


# ============================================================
# 各语言的 AST 节点类型映射
# ============================================================

# 节点类型 → 符号类型
_FUNCTION_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    },
    "typescript": {
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    },
    "tsx": {
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    },
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
}

_CLASS_NODE_TYPES: dict[str, set[str]] = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration", "interface_declaration", "abstract_class_declaration"},
    "tsx": {"class_declaration", "interface_declaration"},
    "java": {"class_declaration", "interface_declaration", "enum_declaration"},
    "go": {"type_declaration"},  # Go 的 type 比较特殊
}


class AstEngine:
    """AST 解析引擎（多语言）。"""

    def get_language(self, file_path: str) -> str | None:
        """根据文件扩展名识别语言。"""
        ext = Path(file_path).suffix.lower()
        return _LANGUAGE_REGISTRY.get(ext)

    def extract_symbols(
        self, code: str, language: str, file_path: str = "<unknown>"
    ) -> list[SymbolInfo]:
        """提取代码中的符号（函数/类/方法）。"""
        try:
            parser, _ = _get_parser(language)
        except (ValueError, ImportError) as e:
            logger.debug("Language %s not available: %s", language, e)
            return []

        from tree_sitter import Node  # noqa: PLC0415

        tree = parser.parse(code.encode("utf-8"))
        symbols: list[SymbolInfo] = []

        func_types = _FUNCTION_NODE_TYPES.get(language, set())
        class_types = _CLASS_NODE_TYPES.get(language, set())

        def walk(node: Node, class_name: str | None = None) -> None:
            # 类
            if node.type in class_types:
                cn = self._extract_name(node, language)
                if cn:
                    symbols.append(SymbolInfo(
                        name=cn,
                        type="class",
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        code=node.text.decode("utf-8", errors="replace"),
                    ))
                    for child in node.children:
                        walk(child, cn)
                return

            # 函数/方法
            if node.type in func_types:
                fname = self._extract_name(node, language)
                if fname:
                    full_name = f"{class_name}.{fname}" if class_name else fname
                    symbols.append(SymbolInfo(
                        name=full_name,
                        type="method" if class_name else "function",
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        code=node.text.decode("utf-8", errors="replace"),
                    ))
                # 嵌套函数也递归
                for child in node.children:
                    walk(child, class_name)
                return

            for child in node.children:
                walk(child, class_name)

        walk(tree.root_node)
        return symbols

    @staticmethod
    def _extract_name(node, language: str) -> str | None:
        """从函数/类节点提取名称。

        不同语言的 AST 结构不同：
        - Python：name 字段直接
        - JS/TS：name 子节点
        - Java：name 子节点
        - Go：name 子节点（receiver 处理）
        """
        # 方式 1：tree-sitter 字段（Python 风格）
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8", errors="replace")

        # 方式 2：遍历找 identifier
        from tree_sitter import Node  # noqa: PLC0415
        for child in node.children:
            if child.type in ("identifier", "property_identifier", "type_identifier"):
                return child.text.decode("utf-8", errors="replace")

        return None

    def find_symbol_at_line(
        self, symbols: list[SymbolInfo], line: int
    ) -> SymbolInfo | None:
        """根据行号反查所属符号。"""
        candidates = [
            s for s in symbols
            if s.type in ("function", "method")
            and s.start_line <= line <= s.end_line
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda s: s.end_line - s.start_line)

    def get_changed_symbols(
        self,
        code: str,
        language: str,
        changed_lines: list[int],
        file_path: str = "<unknown>",
    ) -> list[SymbolInfo]:
        """获取受变更影响的符号（去重）。"""
        all_symbols = self.extract_symbols(code, language, file_path)
        changed: list[SymbolInfo] = []
        seen: set[str] = set()
        for line in changed_lines:
            sym = self.find_symbol_at_line(all_symbols, line)
            if sym and sym.name not in seen:
                changed.append(sym)
                seen.add(sym.name)
        return changed


@lru_cache
def get_ast_engine() -> AstEngine:
    """单例获取 AST 引擎。"""
    return AstEngine()
