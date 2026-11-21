"""AU ranking metric 只有一份（EXP-20261121-32，Kelvin 2026-11-21）。"""
import ast
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))
import au_eval  # noqa: E402
from model_evaluation_decision import RANKING_KEYS  # noqa: E402

FROZEN = ("au_draw_forward", "au_debut_neutral_forward", "au_heavy_h2_forward",
          "au_l600_recency_forward", "au_lpos_forward", "au_overseas_proxy_forward")


def test_registry_has_kelvin_metrics_and_all_are_known():
    for key in ("top2_any_hit", "top2_place_rate", "top3_place_rate", "top3_capture_at5"):
        assert key in au_eval.RANKING_METRICS
    assert set(au_eval.RANKING_METRICS) <= RANKING_KEYS
    assert au_eval.RANKING_METRICS_PRE_20261121 == ("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc")


def test_metric_rows_carry_new_metrics():
    race = {"rows": [{"pos": p, "ability": a} for p, a in ((1, 80), (5, 70), (2, 60), (3, 50), (4, 40))]}
    row = au_eval._stage4_metric_rows([race], lambda r: r["ability"])[0]
    assert row["top2_any_hit"] is True
    assert row["top2_place_rate"] == 0.5          # 頭二選：80（第 1）中、70（第 5）唔中
    assert abs(row["top3_place_rate"] - 2 / 3) < 1e-9


def test_no_au_script_hardcodes_a_ranking_tuple():
    """production AU 判決器唔准自己抄一串 ranking metric（一樣嘢只准有一個標準）。"""
    for path in SCRIPTS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "ranking_metrics":
                assert not isinstance(node.value, (ast.Tuple, ast.List)), f"{path.name} 抄咗 ranking_metrics"


def test_pre_registered_forwards_stay_on_frozen_ruler():
    for name in FROZEN:
        text = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        assert "ranking_metrics=RANKING_METRICS_PRE_20261121" in text, name
