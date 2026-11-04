"""EXP-20261105-03 arm A1：近績分改直線名次（12 名封頂）＋剷穩定性分。

每仗名次分 s = 100 − (min(名次, 12) − 1) × 60 / 11；近 6 仗權重 1/(i+1)（同現行一樣）；
海外往績照現行併入。尺度凍結：leaf = clip(−9.3736 + 0.944123 × F1, 0, 100)
（2025-01-01 → 2026-03-31 共 12,902 匹嘅分佈，冇用賽果）。冇名次 → 60（同現行）。
非初出馬 `consistency_score` = 新 `form_score`（同 A2 一樣剷穩定性分）；初出馬照舊。
"""
import importlib.util
from pathlib import Path

ARM_NAME = "form_linear"
SCALE_A, SCALE_B = -9.3736, 0.944123


def _rank_points(rank):
    return 100.0 - (min(int(rank), 12) - 1) * 60.0 / 11.0


def _ranks(horse_data):
    """同 FormScorer 一樣嘅解析：本地近 6 仗，再加日期唔重複嘅海外往績。"""
    data = horse_data.get("_data", {}) if isinstance(horse_data.get("_data"), dict) else {}
    form = horse_data.get("last_6_finishes", "N/A")
    ranks = []
    if form != "N/A" and form != "" and str(form).replace("-", "").replace("N/A", "").strip():
        for p in str(form).replace("-", " ").replace(",", " ").split():
            try:
                rank = int(p.split("/")[0]) if "/" in p else int(p)
            except ValueError:
                continue
            if rank > 0:
                ranks.append(rank)
    local_dates = str(data.get("recent_6_detail", "") or "")
    for r in data.get("pdf_overseas_races", []) or []:
        race_date = str(r.get("date", "")).strip()
        if race_date and race_date not in ("-", "N/A") and race_date in local_dates:
            continue
        rank_str = str(r.get("rank", ""))
        try:
            rank = int(rank_str.split("/")[0]) if "/" in rank_str else int(rank_str)
        except ValueError:
            continue
        if rank > 0:
            ranks.append(rank)
    return ranks


def apply():
    # ⚠️ engine_core 用 `from form import FormScorer`（features/ 喺 sys.path 上），即係同
    # `hkjc_racing_engine.features.form.FormScorer` 唔係同一個 class；一定要 patch 引擎用緊嗰個。
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score

    form_class = engine_core.FormScorer
    original_compute = form_class.compute

    def compute(self):
        score, reason = original_compute(self)        # 保留原本說明文字
        ranks = _ranks(self.horse_data)[:6]
        if not ranks:
            return score, reason                      # 冇名次 → 60，同現行一樣
        weights = [1.0 / (i + 1) for i in range(len(ranks))]
        f1 = sum(_rank_points(r) * w for r, w in zip(ranks, weights)) / sum(weights)
        self.score = clip_score(SCALE_A + SCALE_B * f1)
        return self.score, reason

    form_class.compute = compute
    # 剷穩定性分：同 A2 一樣
    spec = importlib.util.spec_from_file_location("hkjc_arm_form_only", Path(__file__).with_name("hkjc_arm_form_only.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply()
