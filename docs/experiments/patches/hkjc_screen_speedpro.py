#!/usr/bin/env python3
"""EXP-20261110-02 — HKJC SpeedPro 能量差篩選（唔係 A/B，唔郁任何評分）。

問題：馬會 SpeedPro 嘅 `speedproenergydifference`（預計能量 − 今場所需能量），
喺控制咗我哋模型排名之後，仲有冇上名資訊？

用法（兩步，全部唯讀）：

    H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
    PYTHONDONTWRITEBYTECODE=1 python3 $H run --since 2026-11-11 --out <scratch>/base.jsonl
    python3 docs/experiments/patches/hkjc_screen_speedpro.py <scratch>/base.jsonl --since 2026-11-11

凍結規則（2026-11-10 預先登記，夠數重跑嗰陣唔准改）：

* 快照：每個賽日攞賽日 03:00 UTC 之前最後一份（`hkjc_forward_tracker.speedpro_pre_race_snapshot`，
  同追蹤表數場次用同一條規則）。冇賽前快照嘅場次唔入。
* 判定欄位只有 `diff`。其餘欄位只報告，唔可以事後換做判定欄位。
* 統計量：每場按 `diff` 由高到低（同分按馬號）攞頭三；按模型排名每兩名一段（1–2、3–4…11+）分層，
  計「頭三 vs 其餘」上名率差，用 Mantel–Haenszel 權重合併。
* 推論：以賽日做單位 bootstrap 2000 次，seed 0。
* 判定：95% CI 下界 > 0 → PASS_SCREEN（可以預先登記排名 arm）；否則 REJECT。
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents" / "skills" / "hkjc_racing" / "hkjc_daily_auto"))
sys.path.insert(0, str(REPO / ".agents" / "scripts"))

from hkjc_forward_tracker import speedpro_pre_race_snapshot  # noqa: E402

JUDGED_FIELD = "diff"
FIELDS = {"diff": "speedproenergydifference", "energy": "speedproenergy", "fit": "fitnessrating"}
NESTED = ("lastrun", "bestlast12months", "bestatdistance")
BOOTSTRAP, SEED = 2000, 0


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def placed(horse) -> bool:
    return isinstance(horse.get("pos"), int) and 1 <= horse["pos"] <= 3


def load(base_path: Path, root: Path, since: str, until: str):
    races, skipped = [], collections.Counter()
    for line in base_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        race = json.loads(line)
        if "date" not in race or race["date"] < since or (until and race["date"] > until):
            continue
        snap = speedpro_pre_race_snapshot(root, race["meeting"])
        path = snap / f"sg_race_{race['race']}.json" if snap else None
        if not path or not path.exists():
            skipped["no_pre_race_snapshot"] += 1
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload = payload.get("zh-hk") or payload.get("en-us") or payload
        by_no = {int(x["runnernumber"]): x for x in payload.get("SpeedPRO", [])
                 if str(x.get("runnernumber", "")).isdigit()}
        rank = {no: i + 1 for i, no in enumerate(race["picks"])}
        horses = []
        for horse in sorted(race["horses"], key=lambda h: h["n"]):
            if not (isinstance(horse.get("pos"), int) and horse["pos"] > 0):
                continue
            row = {"n": horse["n"], "pos": horse["pos"], "raw": horse["raw"], "rank": rank.get(horse["n"], 99)}
            sp = by_no.get(horse["n"]) or {}
            for key, source in FIELDS.items():
                row[key] = _num(sp.get(source))
            for key in NESTED:
                row[key] = _num((sp.get(key) or {}).get("energy")) if isinstance(sp.get(key), dict) else None
            horses.append(row)
        races.append({"meeting": race["meeting"], "race": race["race"], "horses": horses})
    return races, skipped


def auc(races, key):
    wins = total = 0.0
    for race in races:
        vals = [(h[key], placed(h)) for h in race["horses"] if h.get(key) is not None]
        pos = [v for v, p in vals if p]
        neg = [v for v, p in vals if not p]
        wins += sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
        total += len(pos) * len(neg)
    return wins / total if total else float("nan")


def stratified_gap(races, key):
    """MH-weighted place-rate gap (pp): field top-3 in race vs the rest, within model-rank bands of two."""
    cells = collections.defaultdict(lambda: [0, 0, 0, 0])
    for race in races:
        horses = [h for h in race["horses"] if h.get(key) is not None]
        top = {h["n"] for h in sorted(horses, key=lambda h: (-h[key], h["n"]))[:3]}
        for h in horses:
            cell = cells[min((h["rank"] - 1) // 2, 5)]
            if h["n"] in top:
                cell[0] += placed(h); cell[1] += 1
            else:
                cell[2] += placed(h); cell[3] += 1
    num = den = 0.0
    for a, n1, b, n0 in cells.values():
        if n1 and n0:
            weight = n1 * n0 / (n1 + n0)
            num += weight * (a / n1 - b / n0)
            den += weight
    return 100 * num / den if den else float("nan")


def meeting_bootstrap(races, stat):
    rng = random.Random(SEED)
    by = collections.defaultdict(list)
    for race in races:
        by[race["meeting"]].append(race)
    keys = sorted(by)
    out = sorted(stat([r for k in rng.choices(keys, k=len(keys)) for r in by[k]]) for _ in range(BOOTSTRAP))
    out = [x for x in out if x == x]
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", type=Path, help="hkjc_eval_harness.py run 嘅輸出")
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    parser.add_argument("--root", type=Path, default=None, help="HK data root（預設讀 .wongchoi_hk_data_root）")
    args = parser.parse_args()
    root = args.root
    if root is None:
        from wongchoi_paths import hk_data_root  # type: ignore
        root = Path(hk_data_root())
    races, skipped = load(args.base, root, args.since, args.until)
    runners = sum(len(r["horses"]) for r in races)
    meetings = len({r["meeting"] for r in races})
    print(f"races {len(races)}  meetings {meetings}  runners {runners}  skipped {dict(skipped)}")
    if not races:
        print("冇場次。")
        return 1
    lo, hi = meeting_bootstrap(races, lambda s: auc(s, "raw"))
    print(f"model raw           AUC {auc(races, 'raw'):.4f} [{lo:.4f}, {hi:.4f}]")
    result = {}
    for key in (*FIELDS, *NESTED):
        cover = 100 * sum(h.get(key) is not None for r in races for h in r["horses"]) / max(1, runners)
        a_lo, a_hi = meeting_bootstrap(races, lambda s, k=key: auc(s, k))
        g_lo, g_hi = meeting_bootstrap(races, lambda s, k=key: stratified_gap(s, k))
        gap = stratified_gap(races, key)
        result[key] = (gap, g_lo, g_hi)
        tag = "  ← 判定欄位" if key == JUDGED_FIELD else ""
        print(f"{key:19s} AUC {auc(races, key):.4f} [{a_lo:.4f}, {a_hi:.4f}]  覆蓋 {cover:5.1f}%  "
              f"分層上名率差 {gap:+.1f}pp [{g_lo:+.1f}, {g_hi:+.1f}]{tag}")
    gap, lo, hi = result[JUDGED_FIELD]
    print(f"\nVERDICT {'PASS_SCREEN' if lo > 0 else 'REJECT'}  ({JUDGED_FIELD} {gap:+.1f}pp, CI 下界 {lo:+.1f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
