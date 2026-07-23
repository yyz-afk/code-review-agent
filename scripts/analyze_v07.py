"""展示 v0.7 的 4 Agent 审查结果。"""

import json
from pathlib import Path

data = json.loads(Path("C:/Users/许夏轩/AppData/Local/Temp/v07.json").read_text(encoding="utf-8"))

print("=" * 60)
print("  v0.7: 4 Agent 并行审查（comprehensive.diff）")
print("=" * 60)
print(f"耗时: {data['stats']['duration_sec']}s")
print(f"成本: ${data['stats']['cost_usd']}")
print(f"Files reviewed: {data['stats']['files_reviewed']}")
print(f"Findings: {len(data['findings'])}")
print(f"按严重度: {data['stats']['findings_by_severity']}")
print(f"按类别: {data['stats']['findings_by_category']}")
errors = data.get("errors", [])
print(f"错误: {len(errors)}")
for e in errors[:3]:
    print(f"  - {e}")

print()
print("Findings 按 Agent 分组:")
by_agent = {}
for f in data["findings"]:
    by_agent.setdefault(f["agent"], []).append(f)

for agent, fs in sorted(by_agent.items()):
    print(f"\n  [{agent}] {len(fs)} 个")
    for f in sorted(fs, key=lambda x: x["start_line"]):
        title = f["title"].encode("ascii", "replace").decode()[:60]
        print(f"    L{f['start_line']:3d} | [{f['severity']:8s}] "
              f"conf={f['confidence']:.2f} | {title}")
