"""pytest 全局配置。"""

import sys
from pathlib import Path

# 让 src/ 目录可被 import
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 让 `from tests.fixtures.xxx` 可被 import（tests 作为 package）
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
