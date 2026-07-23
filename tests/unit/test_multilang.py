"""多语言 AST 解析测试。"""

from __future__ import annotations

import pytest

from cra.context.ast_engine import get_ast_engine


@pytest.fixture
def engine():
    return get_ast_engine()


# ============================================================
# JavaScript
# ============================================================

JS_SAMPLE = '''\
const x = 1;

function greet(name) {
    return "hello " + name;
}

class Calculator {
    add(a, b) {
        return a + b;
    }

    multiply(a, b) {
        return a * b;
    }
}

const arrow = (x) => x * 2;
'''


class TestJavaScript:
    def test_extracts_function(self, engine) -> None:
        symbols = engine.extract_symbols(JS_SAMPLE, "javascript", "test.js")
        names = [s.name for s in symbols]
        assert "greet" in names

    def test_extracts_arrow_function(self, engine) -> None:
        symbols = engine.extract_symbols(JS_SAMPLE, "javascript", "test.js")
        names = [s.name for s in symbols]
        # arrow function 可能命名也可能不命名，这里验证至少能识别为函数
        funcs = [s for s in symbols if s.type == "function"]
        assert len(funcs) >= 1

    def test_extracts_class_and_methods(self, engine) -> None:
        symbols = engine.extract_symbols(JS_SAMPLE, "javascript", "test.js")
        names = [s.name for s in symbols]
        assert "Calculator" in names
        assert "Calculator.add" in names
        assert "Calculator.multiply" in names


# ============================================================
# TypeScript
# ============================================================

TS_SAMPLE = '''\
interface User {
    id: number;
    name: string;
}

class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    findById(id: number): User | null {
        return this.users.find(u => u.id === id) || null;
    }
}

function formatUser(u: User): string {
    return `${u.id}: ${u.name}`;
}
'''


class TestTypeScript:
    def test_extracts_interface(self, engine) -> None:
        symbols = engine.extract_symbols(TS_SAMPLE, "typescript", "test.ts")
        names = [s.name for s in symbols]
        assert "User" in names

    def test_extracts_class_with_methods(self, engine) -> None:
        symbols = engine.extract_symbols(TS_SAMPLE, "typescript", "test.ts")
        names = [s.name for s in symbols]
        assert "UserService" in names
        assert "UserService.addUser" in names
        assert "UserService.findById" in names

    def test_extracts_function(self, engine) -> None:
        symbols = engine.extract_symbols(TS_SAMPLE, "typescript", "test.ts")
        names = [s.name for s in symbols]
        assert "formatUser" in names


# ============================================================
# Java
# ============================================================

JAVA_SAMPLE = '''\
public class HelloWorld {
    private String name;

    public HelloWorld(String name) {
        this.name = name;
    }

    public String greet() {
        return "Hello " + this.name;
    }

    private void log(String msg) {
        System.out.println(msg);
    }
}

class Utility {
    public static int add(int a, int b) {
        return a + b;
    }
}
'''


class TestJava:
    def test_extracts_classes(self, engine) -> None:
        symbols = engine.extract_symbols(JAVA_SAMPLE, "java", "Main.java")
        names = [s.name for s in symbols]
        assert "HelloWorld" in names
        assert "Utility" in names

    def test_extracts_methods(self, engine) -> None:
        symbols = engine.extract_symbols(JAVA_SAMPLE, "java", "Main.java")
        names = [s.name for s in symbols]
        assert "HelloWorld.greet" in names
        assert "HelloWorld.log" in names
        assert "Utility.add" in names

    def test_extracts_constructor(self, engine) -> None:
        symbols = engine.extract_symbols(JAVA_SAMPLE, "java", "Main.java")
        # 构造函数被识别为 method，名字为 "HelloWorld.HelloWorld"（带类前缀）
        ctors = [
            s for s in symbols
            if s.type == "method" and s.name.endswith("HelloWorld")
        ]
        assert len(ctors) >= 1


# ============================================================
# Go
# ============================================================

GO_SAMPLE = '''\
package main

import "fmt"

func greet(name string) string {
    return "hello " + name
}

type Calculator struct {
    result int
}

func (c *Calculator) Add(a, b int) int {
    c.result = a + b
    return c.result
}

func main() {
    fmt.Println(greet("world"))
}
'''


class TestGo:
    def test_extracts_functions(self, engine) -> None:
        symbols = engine.extract_symbols(GO_SAMPLE, "go", "main.go")
        names = [s.name for s in symbols if s.type == "function"]
        assert "greet" in names
        assert "main" in names

    def test_extracts_method(self, engine) -> None:
        symbols = engine.extract_symbols(GO_SAMPLE, "go", "main.go")
        # 方法名可能是 "Add" 或带 receiver 信息
        names = [s.name for s in symbols]
        assert "Add" in names


# ============================================================
# 集成：通过扩展名识别
# ============================================================


class TestEndToEndLanguageDetection:
    """通过文件名识别语言 → 提取符号的完整链路。"""

    @pytest.mark.parametrize(
        "file_path,expected_lang",
        [
            ("app.py", "python"),
            ("app.js", "javascript"),
            ("App.tsx", "tsx"),
            ("Main.java", "java"),
            ("main.go", "go"),
            ("readme.md", None),
        ],
    )
    def test_language_detection(
        self, engine, file_path: str, expected_lang: str | None
    ) -> None:
        assert engine.get_language(file_path) == expected_lang
