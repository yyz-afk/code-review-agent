"""分析改进后的综合审查结果。"""
import json
from pathlib import Path

data = json.loads(Path("C:/Users/许夏轩/AppData/Local/Temp/improved.json").read_text(encoding="utf-8"))

print("=" * 60)
print("  v0.5 改进后的综合样本审查（comprehensive.diff）")
print("=" * 60)
print(f"耗时: {data['stats']['duration_sec']}s")
print(f"成本: ${data['stats']['cost_usd']}")
print(f"Token: {data['stats']['tokens_used']}")
print(f"Findings: {len(data['findings'])}")
print(f"按严重度: {data['stats']['findings_by_severity']}")
print(f"按类别: {data['stats']['findings_by_category']}")
print(f"错误: {len(data.get('errors', []))}")
print()

print("Findings 详情（按 agent 分组）:")
print()
by_agent = {}
for f in data['findings']:
    by_agent.setdefault(f['agent'], []).append(f)

for agent, findings in by_agent.items():
    print(f"  [{agent}] {len(findings)} 个")
    for f in sorted(findings, key=lambda x: x['start_line']):
        title = f['title'].encode('ascii', 'replace').decode()
        print(f"    - [{f['severity']:8s}] L{f['start_line']:3d}-{f['end_line']:3d} "
              f"conf={f['confidence']:.2f} | {title}")
    print()
