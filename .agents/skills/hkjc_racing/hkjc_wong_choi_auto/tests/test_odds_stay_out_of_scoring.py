"""紅線：HKJC 賽前賠率快照**唔可以**入評分。

同 AU `test_odds_capture.py` 同一個決定（Kelvin 2026-08-04）：賠率係做將來
研究／dashboard 用，唔係評分輸入。市場排序一入分就會主導成個模型，嗰個係
產品定位決定，唔應該因為有人手快加咗個 leaf 就靜靜咁發生。呢個決定要靠
測試守住，唔可以靠記性。

掃描範圍 = 由 Facts 到排名嘅成條鏈：引擎 package、auto engine scripts、
Facts／Logic builder 同 orchestrator。有人喺呢度讀 `HKJC_Odds_History.json`
或者 GraphQL 嘅賠率欄位，呢度就要紅。
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
HKJC = REPO / ".agents" / "skills" / "hkjc_racing"
SCAN_DIRS = (
    HKJC / "hkjc_wong_choi_auto" / "scripts",          # 包括 hkjc_racing_engine/
    HKJC / "hkjc_wong_choi" / "scripts",
)
SCAN_FILES = (
    REPO / ".agents" / "scripts" / "run_prerace_pipeline.py",
)
FORBIDDEN = (
    "HKJC_Odds_History",
    "hkjc_odds_capture",
    "oddsNodes",
    "oddsValue",
    "pmPools",
)


def _sources():
    for root in SCAN_DIRS:
        yield from sorted(root.rglob("*.py"))
    for path in SCAN_FILES:
        if path.exists():
            yield path


def test_scan_actually_covers_the_engine():
    """防止路徑搬咗之後呢個測試靜靜變成「掃零個檔」永遠綠。"""
    names = {p.name for p in _sources()}
    assert "engine_core.py" in names
    assert "scoring.py" in names
    assert "hkjc_auto_orchestrator.py" in names


def test_no_scoring_path_reads_pre_race_odds():
    hits = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [f"{path.relative_to(REPO)}: {tok}" for tok in FORBIDDEN if tok in text]
    assert not hits, (
        "評分路徑唔准讀賽前賠率快照（市場一入分就主導模型）：\n" + "\n".join(hits))
