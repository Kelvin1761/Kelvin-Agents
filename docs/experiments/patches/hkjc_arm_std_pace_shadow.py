"""EXP-20261112-13 forward shadow（`std_pace_shadow`）：「步速修正等級」改用對馬會標準嘅新數值入分。

數值 = live 寫入 `_data.std_pace.p2`（hkjc_racing_engine.past_runs：近 6 仗逐段對馬會標準、扣步速、換算到今仗負磅，
EXP-20261112-09 定義）。四級門檻 = dev 半（< 2026-09-06，2,050 匹）現行四級比例（14.3／45.1／26.9／13.7%）喺 live 數值上嘅分位數，
冇用賽果，喺任何 forward 場次之前寫死：
  < −0.089 s → 仍具競爭力｜< 0.431 → 接近平均｜< 0.927 → 仍偏慢｜其餘 → 明顯落後
（EXP-09 用嘅表有 18% 場次用錯班次標準 —— Logic `race_class` 預設第四班；live 改用排位表班次，所以門檻重計，EXP-09 係 −0.155／0.416／0.926。）
加減分照現行（+6.52／+1.42／−4／−8），其餘段速訊號唔郁；冇新數值嘅馬保留原本等級。
Δ = 新數值 − live。Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。Fixed, nothing fitted.
"""
ARM_NAME = "std_pace_shadow"
CUTS = (-0.089, 0.431, 0.927)
LABELS = ("✅ 步速修正後仍具競爭力", "➖ 步速修正後接近平均", "⚠️ 步速修正後仍偏慢", "❌ 步速修正後明顯落後")


def apply():
    from hkjc_racing_engine.features.speed import SpeedScorer

    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        pace = data.get("std_pace")
        if not isinstance(pace, dict) or pace.get("p2") is None:
            return data
        v = float(pace["p2"])
        k = 0 if v < CUTS[0] else 1 if v < CUTS[1] else 2 if v < CUTS[2] else 3
        out = dict(data)
        out["finish_time_adj_level"] = f"{LABELS[k]} (近 {pace.get('n')} 仗對標準偏差 {v:+.2f}s)"
        return out

    SpeedScorer._data = _data
