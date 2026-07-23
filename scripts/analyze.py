"""分析审查结果。"""

import json
from pathlib import Path

# 预期 Bug 清单（基于 comprehensive.diff）
EXPECTED = [
    ("E1", "SQL 注入", 10, "get_order 的 f-string"),
    ("E2", "SQL 注入", 17, "list_user_orders 的 f-string"),
    ("E3", "SQL 注入", 22, "循环内 f-string"),
    ("E4", "N+1 查询", 21, "循环内 execute"),
    ("E5", "命令注入", 38, "subprocess shell=True"),
    ("E6", "异常吞没", 39, "except: pass"),
    ("E7", "finally return", 6, "utils.parse_int"),
    ("E8", "硬编码密钥", 7, "API_SECRET"),
    ("E9", "除零未检查", 44, "divide_refund"),
    ("E10", "空值未检查", 28, "order.user.email"),
]


KEYWORDS = {
    "SQL 注入": ["sql", "注入", "injection", "execute"],
    "N+1 查询": ["n+1", "循环", "loop"],
    "命令注入": ["命令", "command", "subprocess", "shell"],
    "异常吞没": ["except", "异常", "吞", "exception"],
    "finally return": ["finally", "return"],
    "硬编码密钥": ["密钥", "secret", "hardcoded"],
    "除零未检查": ["除", "zero", "division", "divid"],
    "空值未检查": ["none", "空值", "null"],
}


def analyze(report_path: str) -> None:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))

    print("=" * 60)
    print("  审查统计")
    print("=" * 60)
    print(f"总耗时: {data['stats']['duration_sec']}s")
    print(f"总成本: ${data['stats']['cost_usd']}")
    print(f"总 findings: {len(data['findings'])}")
    print(f"按严重度: {data['stats']['findings_by_severity']}")
    if data.get("errors"):
        print(f"⚠️  错误: {len(data['errors'])} 个")
        for e in data["errors"]:
            print(f"   - {e}")

    findings = data["findings"]
    print()
    print("=" * 60)
    print("  检出率分析")
    print("=" * 60)
    print(f"{'ID':<4} {'类型':<16} {'位置':<10} {'状态':<6}")
    print("-" * 50)

    hit = 0
    for eid, btype, line, _ in EXPECTED:
        # 找行号匹配（±3 行）或描述关键词匹配
        line_match = [
            f for f in findings
            if abs(f.get("start_line", 0) - line) <= 3
        ]
        desc_match = [
            f for f in findings
            if any(kw in (f.get("description", "") + f.get("title", "")).lower()
                  for kw in KEYWORDS.get(btype, []))
        ]
        is_hit = bool(line_match or desc_match)
        if is_hit:
            hit += 1
        print(f"{eid:<4} {btype:<16} L{line:<8} {'✅' if is_hit else '❌'}")

    rate = hit / len(EXPECTED) * 100
    print()
    print(f"检出率: {hit}/{len(EXPECTED)} = {rate:.0f}%")

    print()
    print("=" * 60)
    print("  全部 Findings")
    print("=" * 60)
    for i, f in enumerate(sorted(findings, key=lambda x: (x["file_path"], x["start_line"])), 1):
        title = f.get("title", "")
        # 转 ASCII 避免控制台编码问题
        title_ascii = title.encode("ascii", "replace").decode()
        print(f"{i:2d}. [{f['severity']:8s}] {f['file_path']:14s} "
              f"L{f['start_line']:3d}-{f['end_line']:3d} | {title_ascii}")


if __name__ == "__main__":
    import sys
    analyze(sys.argv[1] if len(sys.argv) > 1
            else "C:/Users/许夏轩/AppData/Local/Temp/comprehensive2.json")
