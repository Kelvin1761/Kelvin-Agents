#!/usr/bin/env python3
"""HKJC 覆盤第二步：逐維度歸因 + 跨賽日假設佇列（2026-10-10）。

舊覆盤只會講「大文豪排第 10，建議加強段速／試閘／速度訊號」—— 冇講係**邊個維度**
將佢壓低。呢度對每匹「模型漏咗嘅實際前三」同每匹「模型揀咗但跑唔入前三」，
逐維度計加權貢獻差：

    Δ_d = w_d × (m_d(馬) − 平均 m_d(對照組))

漏咗嘅馬對照模型頭三；揀錯嘅馬對照實際前三。最負（漏咗）／最正（揀錯）嘅
維度就係主因。權重同維度清單一律由 `hkjc_racing_engine.dimensions` 登記表讀，
centred 維度（同程表現）用 w × (m − 60)，所以加維度唔使改呢度。

舊 7D 年代嘅 CSV 冇 `matrix_trackwork`：嗰陣晨操仲喺 stability 入面，
所以 stability 用返兩個維度權重之和，晨操當冇貢獻。

歸因結果寫入 HK_Racing 根目錄嘅 `HKJC_Attribution_Ledger.jsonl`（每個賽日重寫自己嗰幾行，
重跑唔會重複）。`queue_summary()` 將全部賽日累積：同一個維度同一個方向夠
`QUEUE_THRESHOLD` 匹，先列做「值得開實驗」—— 單日結果冇功效，唔准即日調參。
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[5]
ENGINE_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"
if str(ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ENGINE_SCRIPTS))

LEDGER_NAME = "HKJC_Attribution_Ledger.jsonl"
QUEUE_THRESHOLD = 20


def _registry() -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    from hkjc_racing_engine import dimensions

    return dimensions.weights(), dimensions.centred_weights(), dimensions.labels()


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_matrix_rows(analysis_dir: Path) -> dict[int, dict[int, dict[str, Any]]]:
    """→ {race: {horse_no: {"name", "rank", "m": {dimension: raw score}}}} from Race_*_Auto_Scoring.csv."""
    out: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for path in sorted(analysis_dir.glob("Race_*_Auto_Scoring.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                race, horse = _num(row.get("race_number")), _num(row.get("horse_number"))
                if race is None or horse is None:
                    continue
                m = {key[len("matrix_"):]: v for key, raw in row.items()
                     if key.startswith("matrix_") and (v := _num(raw)) is not None}
                out[int(race)][int(horse)] = {"name": str(row.get("horse_name") or "").strip(),
                                              "rank": int(_num(row.get("rank")) or 999), "m": m}
    return dict(out)


def _effective_weights(m: dict[str, float], weights: dict[str, float]) -> dict[str, float]:
    w = dict(weights)
    if "trackwork" in w and "trackwork" not in m and "stability" in w:
        w["stability"] += w.pop("trackwork")   # 7D-era row: trackwork lived inside stability
    return w


def contributions(horse: dict[str, Any], reference: list[dict[str, Any]],
                  weights: dict[str, float], centred: dict[str, float]) -> dict[str, float]:
    """Weighted contribution gap of one horse vs the mean of a reference group, per dimension."""
    w = _effective_weights(horse["m"], weights)
    out = {}
    for key, wk in {**w, **centred}.items():
        mine = horse["m"].get(key, 60.0)
        ref = [r["m"].get(key, 60.0) for r in reference] or [60.0]
        out[key] = round(wk * (mine - sum(ref) / len(ref)), 3)
    return out


def attribute_race(race: int, horses: dict[int, dict[str, Any]], placings: dict[int, int],
                   registry=None) -> list[dict[str, Any]]:
    weights, centred, labels = registry or _registry()
    ranked = sorted(horses.items(), key=lambda kv: kv[1]["rank"])
    model_top3 = [h for n, h in ranked[:3]]
    actual_top3 = [horses[n] for n, p in placings.items() if p <= 3 and n in horses]
    rows = []
    for n, h in ranked:
        placed = placings.get(n, 99) <= 3
        picked = h["rank"] <= 3
        if placed and not picked:
            kind, ref = "missed", model_top3
        elif picked and not placed and placings.get(n) is not None:
            kind, ref = "overrated", actual_top3
        else:
            continue
        gap = contributions(h, ref, weights, centred)
        # missed: the dimension that held it back most (most negative); overrated: most positive
        order = sorted(gap.items(), key=lambda kv: kv[1], reverse=(kind == "overrated"))
        main = [k for k, v in order[:2] if (v < 0 if kind == "missed" else v > 0)]
        rows.append({"race": race, "horse_no": n, "horse_name": h["name"], "kind": kind,
                     "model_rank": h["rank"], "placing": placings.get(n), "gap": gap,
                     "total_gap": round(sum(gap.values()), 3), "main": main,
                     "main_labels": [labels.get(k, k) for k in main]})
    return rows


def attribute_meeting(analysis_dir: Path, placings_by_race: dict[int, dict[int, int]]) -> list[dict[str, Any]]:
    registry = _registry()
    matrix = load_matrix_rows(analysis_dir)
    rows = []
    for race, horses in sorted(matrix.items()):
        if race in placings_by_race and any("m" in h and h["m"] for h in horses.values()):
            rows.extend(attribute_race(race, horses, placings_by_race[race], registry))
    return rows


def write_ledger(ledger: Path, meeting: str, rows: list[dict[str, Any]]) -> None:
    kept = []
    if ledger.exists():
        kept = [line for line in ledger.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("meeting") != meeting]
    kept.extend(json.dumps({"meeting": meeting, **r}, ensure_ascii=False) for r in rows)
    ledger.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def queue_summary(ledger: Path, threshold: int = QUEUE_THRESHOLD) -> list[dict[str, Any]]:
    """Accumulate main causes across meetings → hypothesis queue, largest first."""
    if not ledger.exists():
        return []
    counts: Counter = Counter()
    meetings: dict[tuple[str, str], set] = defaultdict(set)
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("main"):
            key = (r["kind"], r["main"][0])
            counts[key] += 1
            meetings[key].add(r["meeting"])
    _w, _c, labels = _registry()
    return [{"kind": kind, "dimension": dim, "label": labels.get(dim, dim), "horses": n,
             "meetings": len(meetings[(kind, dim)]), "ready": n >= threshold}
            for (kind, dim), n in counts.most_common()]


def render_markdown(rows: list[dict[str, Any]], queue: list[dict[str, Any]]) -> list[str]:
    _w, _c, labels = _registry()
    lines = ["", "## 逐維度歸因（邊個維度令模型錯）",
             "- 計法：`權重 × (呢匹馬嘅維度分 − 對照組平均)`。漏咗嘅實際前三對照模型頭三；"
             "揀咗但跑唔入前三嘅對照實際前三。只係描述今日，唔係改動建議。"]
    if not rows:
        lines.append("- 今日冇可歸因嘅馬（或者 CSV 冇維度分）。")
    for r in rows:
        top = ", ".join(f"{labels.get(k, k)} {v:+.2f}" for k, v in
                        sorted(r["gap"].items(), key=lambda kv: kv[1], reverse=(r["kind"] == "overrated"))[:3])
        what = "漏咗（實際第 %s，模型排 %s）" % (r["placing"], r["model_rank"]) if r["kind"] == "missed" \
            else "揀錯（模型排 %s，實際第 %s）" % (r["model_rank"], r["placing"])
        cause = "／".join(r["main_labels"]) or "冇單一維度主因（差距分散）"
        lines.append(f"- R{r['race']} #{r['horse_no']} {r['horse_name']}：{what}；主因 **{cause}**；"
                     f"合計 {r['total_gap']:+.2f}（{top}）")
    lines.extend(["", "## 假設佇列（全部賽日累積）",
                  f"- 同一維度同一方向累積到 {QUEUE_THRESHOLD} 匹先值得開實驗；之前只係觀察。",
                  "- ⚠️ 權重大、分數散嘅維度（檔位與走位）天然最常做「主因」—— 次數多唔等於佢錯；"
                  "開實驗前要對比佢喺全部馬嘅影響力份額，並先睇已判死嘅記錄（EXP-20261010-09）。"])
    for q in queue[:8]:
        kind = "漏馬主因" if q["kind"] == "missed" else "高估主因"
        flag = "✅ 夠樣本，可以預先登記實驗" if q["ready"] else "累積中"
        lines.append(f"- {kind}：{q['label']} —— {q['horses']} 匹／{q['meetings']} 個賽日（{flag}）")
    if not queue:
        lines.append("- 佇列仲係空。")
    return lines
