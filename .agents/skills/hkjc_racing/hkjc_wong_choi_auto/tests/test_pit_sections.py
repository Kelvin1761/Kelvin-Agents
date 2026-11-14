"""段速 FT 組件（EXP-20261114-04）：計法同離線回放 arm 一致嘅關鍵規則。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import pit_sections as ps  # noqa: E402

TABLE = {
    "standards": {"2025": {f"ST|1200|C4|{i}": v for i, v in enumerate((24.0, 22.5, 23.0))}},
    "variant": {"2025-10-01|ST": {"first": 0.10, "l400": -0.20}},
    "nsec": {"ST|1200": 3},
    "z": {"first_v": [0.0, 0.4], "total_v": [0.0, 0.2]},
}


def run(date, secs, cls="C4"):
    return {"date": date, "track": "ST", "dist": 1200, "cls": cls, "secs": secs}


def test_needs_two_runs_and_uses_variant():
    runs = [run("2025-10-01", [23.9, 22.5, 23.0]), run("2025-09-20", [24.2, 22.6, 23.1])]
    first, total = ps.ft_values(runs, "2025-11-01", "第四班", TABLE)
    # 第一仗：first = −0.1 − 0.10 = −0.2；total = −0.1/3 − mean(0.10, −0.20) = −0.0333 + 0.05
    # 第二仗（冇當日快慢）：first = +0.2；total = +0.4/3
    w = (1.0, 0.5)
    exp_first = -((-0.2) * w[0] + 0.2 * w[1]) / sum(w)
    exp_total = -((-0.1 / 3 + 0.05) * w[0] + (0.4 / 3) * w[1]) / sum(w)
    assert abs(first - exp_first) < 1e-9 and abs(total - exp_total) < 1e-9
    assert ps.ft_values(runs[:1], "2025-11-01", "第四班", TABLE) == (None, None)


def test_incomplete_sections_and_future_runs_are_ignored():
    runs = [run("2025-11-02", [23.0, 22.0, 22.0]),           # 賽日之後：唔用
            run("2025-10-01", [23.9, 22.5]),                  # 冇跑完（段數唔齊）：唔用
            run("2025-09-20", [24.2, 22.6, 23.1])]
    assert ps.ft_values(runs, "2025-11-01", "第四班", TABLE) == (None, None)


def test_points_zero_when_any_missing_and_clipped():
    assert ps.ft_points(None, 0.1, TABLE) == 0.0
    big = ps.ft_points(10.0, 10.0, TABLE)                    # z clip 喺 +2.5
    assert abs(big - 0.5 * 9.45 * 2.5) < 1e-9
