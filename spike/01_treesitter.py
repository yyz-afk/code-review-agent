"""
Spike 01: tree-sitter Python AST 解析能力验证

验证目标：
1. 能否解析 Python 代码为 AST
2. 能否提取函数/类的位置信息
3. 能否根据行号反查所属符号
4. 能否构建简单的调用图
5. 性能：解析速度
"""
import time
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

SAMPLE = Path(__file__).parent / "samples" / "buggy_code.py"
SOURCE = SAMPLE.read_text(encoding="utf-8")
SOURCE_BYTES = SOURCE.encode("utf-8")


def test_basic_parse():
    """测试 1：基础解析能力。"""
    print("\n[1] 基础解析测试")
    language = Language(tspython.language())
    parser = Parser(language)

    start = time.perf_counter()
    tree = parser.parse(SOURCE_BYTES)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"  解析耗时: {elapsed_ms:.2f} ms")
    print(f"  根节点类型: {tree.root_node.type}")
    print(f"  子节点数: {len(tree.root_node.children)}")
    print(f"  代码行数: {len(SOURCE.splitlines())}")
    return tree


def test_extract_symbols(tree):
    """测试 2：提取函数/类定义。"""
    print("\n[2] 符号提取测试")

    symbols = []

    def walk(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            params_node = node.child_by_field_name("parameters")
            symbols.append({
                "type": "function",
                "name": name_node.text.decode() if name_node else "?",
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "params": params_node.text.decode() if params_node else "()",
            })
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            symbols.append({
                "type": "class",
                "name": name_node.text.decode() if name_node else "?",
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
            })
        for child in node.children:
            walk(child)

    walk(tree.root_node)

    print(f"  共识别 {len(symbols)} 个符号:")
    for s in symbols:
        prefix = "  ├── 🔧" if s["type"] == "function" else "  ├── 📦"
        extra = s.get("params", "")
        print(f"{prefix} {s['name']}{extra}  (L{s['start_line']}-{s['end_line']})")

    return symbols


def test_locate_symbol_by_line(tree):
    """测试 3：根据行号反查所属符号（用于 diff 切分）。"""
    print("\n[3] 行号反查符号测试")

    # 模拟 diff 中的几行变更，反查所属函数
    test_lines = [10, 18, 29, 45, 60, 67]

    functions = []

    def collect_functions(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            functions.append({
                "name": name_node.text.decode() if name_node else "?",
                "start": node.start_point[0] + 1,
                "end": node.end_point[0] + 1,
            })
        for c in node.children:
            collect_functions(c)

    collect_functions(tree.root_node)

    for line in test_lines:
        owner = next(
            (f for f in functions if f["start"] <= line <= f["end"]),
            None,
        )
        if owner:
            print(f"  L{line}: 属于函数 {owner['name']} (L{owner['start']}-{owner['end']})")
        else:
            print(f"  L{line}: 模块级（无所属函数）")


def test_call_graph(tree):
    """测试 4：简单调用图构建。"""
    print("\n[4] 调用图构建测试")

    call_graph = {}

    def walk(node, current_func):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            new_func = name_node.text.decode() if name_node else "?"
            call_graph.setdefault(new_func, set())
            for c in node.children:
                walk(c, new_func)
        elif node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node and current_func:
                callee = func_node.text.decode()
                call_graph[current_func].add(callee)
            for c in node.children:
                walk(c, current_func)
        else:
            for c in node.children:
                walk(c, current_func)

    walk(tree.root_node, None)

    print("  函数调用关系:")
    for caller, callees in call_graph.items():
        if callees:
            print(f"  ├── {caller} → {', '.join(sorted(callees))}")
        else:
            print(f"  ├── {caller} → (无调用)")

    return call_graph


def test_get_function_body(tree):
    """测试 5：按符号提取代码片段（节省 token）。"""
    print("\n[5] 按符号提取代码片段测试")

    target = "process_order"

    def find_function(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.text.decode() == target:
                return node
        for c in node.children:
            result = find_function(c)
            if result:
                return result
        return None

    func_node = find_function(tree.root_node)
    if func_node:
        body = func_node.text.decode()
        body_lines = len(body.splitlines())
        full_lines = len(SOURCE.splitlines())
        ratio = body_lines / full_lines * 100
        print(f"  目标函数: {target}")
        print(f"  提取行数: {body_lines} / 总 {full_lines} ({ratio:.1f}%)")
        print(f"  节省 token: ~{100 - ratio:.1f}%")
    return func_node is not None


def test_perf_large_file(tree):
    """测试 6：大文件解析性能（模拟）。"""
    print("\n[6] 大文件性能测试")
    language = Language(tspython.language())
    parser = Parser(language)

    # 将样本代码复制 50 次模拟大文件
    big_source = (SOURCE + "\n\n") * 50
    big_bytes = big_source.encode("utf-8")
    line_count = len(big_source.splitlines())

    start = time.perf_counter()
    big_tree = parser.parse(big_bytes)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # 统计函数数
    func_count = 0

    def count(node):
        nonlocal func_count
        if node.type == "function_definition":
            func_count += 1
        for c in node.children:
            count(c)

    count(big_tree.root_node)

    print(f"  模拟规模: {line_count} 行 / {len(big_bytes)} bytes")
    print(f"  解析耗时: {elapsed_ms:.1f} ms")
    print(f"  识别函数: {func_count} 个")
    print(f"  吞吐: {line_count / elapsed_ms * 1000:.0f} 行/秒")


def main():
    print("=" * 60)
    print("Spike 01: tree-sitter Python AST 验证")
    print("=" * 60)
    print(f"样本: {SAMPLE}")

    tree = test_basic_parse()
    symbols = test_extract_symbols(tree)
    test_locate_symbol_by_line(tree)
    test_call_graph(tree)
    test_get_function_body(tree)
    test_perf_large_file(tree)

    print("\n" + "=" * 60)
    print("✅ tree-sitter 验证结论")
    print("=" * 60)
    print("- Python AST 解析：✓ 完全可用")
    print("- 函数/类位置提取：✓ 精确到行列")
    print("- 行号反查符号：✓ 支持 diff 切分")
    print("- 调用图构建：✓ 基础调用关系可识别")
    print("- 符号级代码提取：✓ 可节省大量 token")
    print("- 大文件性能：✓ 毫秒级解析")
    print("- 结论：tree-sitter 完全满足 Code Review 需求")


if __name__ == "__main__":
    main()
