import re, json
from pathlib import Path

# Load skeleton
skel = Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Automated Skeleton.md").read_text()
data = Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Automated Data.md").read_text()

filled = skel

replacements = {
    r'\{\{LLM_FILL: 短途/中距離 班次賽/讓磅賽\}\}': '短途 讓磅賽',
    r'\{\{LLM_FILL(?:[^\}]*)\}\}': 'Test Fill',
}
for k, v in replacements.items():
    filled = re.sub(k, v, filled)

# Manually mock some grades for testing
filled = filled.replace("- **狀態與穩定性** [核心]: `[Test Fill]`", "- **狀態與穩定性** [核心]: `[✅]`")
filled = filled.replace("- **段速與引擎** [核心]: `[Test Fill]`", "- **段速與引擎** [核心]: `[✅]`")
filled = filled.replace("- **EEM與形勢** [半核心]: `[Test Fill]`", "- **EEM與形勢** [半核心]: `[✅]`")
filled = filled.replace("- **騎練訊號** [半核心]: `[Test Fill]`", "- **騎練訊號** [半核心]: `[✅]`")
filled = filled.replace("- **級數與負重** [輔助]: `[Test Fill]`", "- **級數與負重** [輔助]: `[✅]`")
filled = filled.replace("- **場地適性** [輔助]: `[Test Fill]`", "- **場地適性** [輔助]: `[✅]`")
filled = filled.replace("- **賽績線** [輔助]: `[Test Fill]`", "- **賽績線** [輔助]: `[✅]`")
filled = filled.replace("- **裝備與距離** [輔助]: `[Test Fill]`", "- **裝備與距離** [輔助]: `[➖]`")

Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Analysis.md").write_text(filled)
print("Dummy Analysis created")
