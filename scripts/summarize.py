"""简洁展示真实 Git 项目审查结果。"""
import json
from pathlib import Path

data = json.loads(Path("C:/Users/许夏轩/AppData/Local/Temp/hello_agent.json").read_text(encoding="utf-8"))

print("=" * 60)
print(f"  hello-agent 真实 Git 项目审查结果")
print("=" * 60)
print(f"Base: {data['base_ref'][:8]}")
print(f"Head: {data['head_ref'][:8]}")
print(f"Files reviewed: {data['stats']['files_reviewed']}")
print(f"Duration: {data['stats']['duration_sec']}s")
print(f"Cost: ${data['stats']['cost_usd']}")
print(f"Tokens used: {data['stats']['tokens_used']}")
print(f"Total findings: {len(data['findings'])}")
print(f"By severity: {data['stats']['findings_by_severity']}")
print()

errors = data.get("errors", [])
if errors:
    print(f"⚠️  Errors ({len(errors)}):")
    for e in errors[:5]:
        print(f"  - {e}")
    print()

print("=" * 60)
print("  Findings (按严重度排序)")
print("=" * 60)
severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
findings = sorted(data["findings"], key=lambda x: severity_order.get(x["severity"], 99))
for i, f in enumerate(findings, 1):
    title = f["title"].encode("ascii", "replace").decode()
    print(f"{i:2d}. [{f['severity']:8s}] {f['file_path']}")
    print(f"    L{f['start_line']}-{f['end_line']} | conf={f['confidence']:.2f} | {title}")
    desc = f.get("description", "").encode("ascii", "replace").decode()
    if desc:
        first_line = desc.split("\n")[0][:100]
        print(f"    → {first_line}")
    print()
