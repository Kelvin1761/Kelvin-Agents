"""EXP-20261112-12 arm：段速維度「兩樣都放」—— 保留現行「步速修正等級」（輸頭馬秒數），另加一項表現數字＋負磅換算等級。

依據：EXP-20261112-11（賽果庫 5,206 場 walk-forward）入面「兩樣都放」capture@5 +0.39 [+0.02,+0.74]、NDCG +0.003、
Good 7/7 季 ≥0（非主 arm）。呢度喺真引擎 449 場確認。

預先登記（跑之前寫死）：
  數值   EXP-08 PIT 表現數字 W（`hkjc_fig_level_table.py` 生成，WC_EXP_FIG_TABLE；β 0.01123 只用 2026-05-03 之前估）
  門檻   dev 半（< 2026-09-06）有現行等級又有 W 嘅馬，按現行四級比例取 W 分位數（W 越大越好）—— 由 prep 寫入 WC_EXP_FIG_CUTS
  加減分 現行等級嘅一半：+3.26／+0.71／−2／−4（現行 +6.52／+1.42／−4／−8）
  加法   喺段速分所有返回路徑之後加再 clip（唔計入段速訊號數目，同 EXP-09 加入版一樣）；冇 W 嘅馬唔郁
  判決   hkjc_eval_harness compare --stage4 fixed_rule（全語料 389 場）＋ holdout 半；另同「同幅度隨機加項」null 比
"""
import json
import os
from pathlib import Path

ARM_NAME = "fig_added_half"
POINTS = (3.26, 0.71, -2.0, -4.0)


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import clip_score

    table = json.load(open(os.environ["WC_EXP_FIG_TABLE"]))["table"]
    cuts = json.load(open(os.environ["WC_EXP_FIG_CUTS"]))["cuts_W"]      # 由大到細：W ≥ cuts[0] → 第一級
    original = orch._align_runner_headers

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        row = table.get(f"{Path(logic_path).parent.name}|{int(race_context.get('race_number'))}") or {}
        for num, horse in horses.items():
            v = row.get(str(num)) if isinstance(horse, dict) else None
            if v:
                horse.setdefault("_data", {})["exp1112_figW"] = v[1]

    orch._align_runner_headers = patched
    base_compute = SpeedScorer.compute

    def compute(self):
        score, note = base_compute(self)
        v = self._data().get("exp1112_figW")
        if v is None:
            return score, note
        k = 0 if v >= cuts[0] else 1 if v >= cuts[1] else 2 if v >= cuts[2] else 3
        self.detail = list(getattr(self, "detail", []) or []) + [
            {"factor": "表現數字（負磅換算）", "value": f"{v:+.3f} s/km", "delta": POINTS[k], "why": "EXP-20261112-12"}]
        return clip_score(score + POINTS[k]), note

    SpeedScorer.compute = compute
