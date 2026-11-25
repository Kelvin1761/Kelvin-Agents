"""EXP-20261121-31：Sportsbet 價高過 Betfair 係咪訊號？（AU 頭兩選，紙上 forward，預先登記）

只睇模型頭兩選（Kelvin 2026-11-21：「only looking at top 2」）。每匹馬喺賽日**第一個早更**
Sportsbet 快照凍結一次，配 ±30 分鐘內最近嘅 Betfair 早更快照（兩樣都係賽前、落注嗰刻拎得到）。
凍結紀錄寫入 `work/au-sb-betfair-forward-picks.jsonl`，之後唔再改（快照之後被修正都唔換）。

* 高價組（overlay）：Sportsbet 位賠 ÷ Betfair 位賠（未扣佣金嘅 back 價）≥ `OVERLAY_RATIO`（1.10）。
  門檻喺睇任何賽果之前、由賽前價錢分佈定：11-18→11-21 434 匹頭兩選，比例中位 1.06、74% > 1，
  所以「高過」係常態唔係篩選；1.10 ≈ 最高四分一。
* 主判決：高價組夠 `TARGET` 注已結算位注之後判**一次**並凍結：
  P1 高價組 Sportsbet 位注 ROI 95% CI 下限 > 0；P2 高價組 − 其餘 ROI 差 95% CI 下限 > 0。
  兩樣都過 = PASS（訊號），否則 REJECT／INCONCLUSIVE。Bootstrap 按賽日抽，2,000 次，seed 固定。
* 未夠數只報數量（盲測），唔報 ROI。永遠唔會自動落注、唔會改模型。
* **落唔落到注（附加，唔改主判決；Astra 2026-11-25 提出）**：紙上價差唔等於真係落到。結算時用賽前資料加兩樣：
  - `sb_place_next`：凍結之後下一張 Sportsbet 早更快照嘅位賠；仲係 ≥ OVERLAY_RATIO 先算「價維持到」。
  - `bf_place_winners` vs `sb_places_paid`：Betfair 位置盤派幾多個位（記錄器 numberOfWinners）同 Sportsbet 一唔一樣。
  判決時另報「落得到子集」（高價組 ∩ 價維持 ∩ 位置規則一樣）ROI＋CI。冇數據嘅唔計入子集（唔當係落到）。
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))  # repo root：wongchoi_paths
import au_betting as B  # noqa: E402

try:  # 入錯場守衛（同落注單／dashboard 同一份）
    from odds_quality import field_numbers, outside_field  # noqa: E402
except ImportError:  # pragma: no cover - 守衛未發佈之前
    field_numbers = outside_field = None

EXPERIMENT = "EXP-20261121-31"
START = "2026-11-17"          # Betfair 早更價開始有記錄
TARGET = 1000                 # 高價組已結算位注
PAIR_MINUTES = 30
OVERLAY_RATIO = 1.10
PERSIST_MINUTES = 20          # 「價維持到」：凍結之後最少 20 分鐘嗰張早更快照
BOOT = 2000
SEED = 20261121
MORNING = B.MORNING_TAGS


def bf_name(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _ts(key: str):
    raw, _sep, tag = str(key).partition("|")
    try:
        return datetime.fromisoformat(raw), tag
    except ValueError:
        return None, tag


def _price(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 1.0 else None


def freeze_point(history: dict, race: int, day: str, field) -> tuple[str, dict] | None:
    """賽日第一個早更 Sportsbet 快照（過入錯場守衛）。"""
    snaps = history.get(str(race)) or {}
    for key in sorted(snaps):
        when, tag = _ts(key)
        if when is None or tag not in MORNING or when.date().isoformat() != day:
            continue
        if outside_field and outside_field(snaps[key], field):
            continue
        return key, snaps[key]
    return None


def betfair_pair(bf_history: dict, sb_key: str) -> tuple[str, dict] | None:
    sb_when, _ = _ts(sb_key)
    best = None
    for key, prices in (bf_history or {}).items():
        when, tag = _ts(key)
        if when is None or tag not in MORNING or not isinstance(prices, dict):
            continue
        gap = abs((when - sb_when).total_seconds()) / 60
        if gap <= PAIR_MINUTES and (best is None or gap < best[0]):
            best = (gap, key, prices)
    return (best[1], best[2]) if best else None


def picks_for_meeting(folder: Path, day: str) -> list[dict]:
    try:
        sb = json.loads((folder / "odds_history.json").read_text(encoding="utf-8"))
        bf = json.loads((folder / "betfair_odds_history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    races = sorted(int(m.group(1)) for m in
                   (re.search(r"Race_(\d+)_", f.name) for f in folder.glob("Race_*_Auto_Analysis.md")) if m)
    for race in races:
        field = field_numbers(folder, race) if field_numbers else None
        point = freeze_point(sb, race, day, field)
        if not point:
            continue
        sb_key, sb_prices = point
        pair = betfair_pair(bf, sb_key)
        for rank, (num, name) in enumerate(B.top_two(folder, race), 1):
            row = {"meeting": folder.name, "day": day, "race": race, "num": num, "name": name,
                   "rank": rank, "sb_key": sb_key, "bf_key": pair[0] if pair else None}
            p = sb_prices.get(str(num)) or []
            row["sb_win"], row["sb_place"] = (_price(p[0]), _price(p[1])) if len(p) == 2 else (None, None)
            q = (pair[1].get(bf_name(name)) if pair else None) or []
            bw, bp = (_price(q[0]), _price(q[1])) if len(q) == 2 else (None, None)
            # Betfair 位市場薄：位賠 > 獨贏 = 壞價，唔用（預先登記嘅數據質素規則）
            row["bf_bad"] = bool(bw and bp and bp > bw)
            row["bf_win"], row["bf_place"] = (bw, None if row["bf_bad"] else bp)
            rows.append(row)
    return rows


def freeze(picks_path: Path, *, until: str) -> int:
    """將未凍結嘅（賽日 ≤ until）頭兩選寫入 jsonl；已有嘅唔郁。"""
    seen = set()
    if picks_path.exists():
        for line in picks_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            seen.add((r["meeting"], r["race"], r["num"]))
    from wongchoi_paths import AU_RACING  # noqa: PLC0415
    root = Path(AU_RACING)
    added = []
    for base in (root, root / "Archive"):
        for folder in sorted(base.glob("2026-*")):
            day = folder.name[:10]
            if not folder.is_dir() or day < START or day > until:
                continue
            for r in picks_for_meeting(folder, day):
                k = (r["meeting"], r["race"], r["num"])
                if k not in seen:
                    seen.add(k)
                    added.append(r)
    if added:
        picks_path.parent.mkdir(parents=True, exist_ok=True)
        with picks_path.open("a", encoding="utf-8") as fh:
            for r in added:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(added)


def _results(folder: Path) -> dict:
    res = folder / "Race_Results_Reflector.md"
    if not res.exists():
        return {}
    parts = re.split(r"^## Race (\d+)\s*$", res.read_text(errors="replace"), flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        found = B.RE_FINISH.findall(parts[i + 1])   # 冇 SP 嘅完成馬都要計（唔係退出）
        if found:
            out[int(parts[i])] = {int(n): int(pos) for pos, n in found}
    return out


def _next_sb_place(folder: Path, r: dict) -> float | None:
    """凍結點之後同日下一張早更 Sportsbet 快照嘅位賠（賽前資料）。"""
    try:
        sb = json.loads((folder / "odds_history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    snaps = sb.get(str(r["race"])) or {}
    frozen, _ = _ts(r["sb_key"])
    after = sorted(k for k in snaps if k > r["sb_key"])
    for key in after:
        when, tag = _ts(key)
        if when is None or tag not in MORNING or when.date().isoformat() != r["day"]:
            continue
        # 幾十秒後嘅 morning-rebuild 係同一份價重寫，唔算「之後」—— 要隔最少 PERSIST_MINUTES
        if frozen is not None and (when - frozen).total_seconds() < PERSIST_MINUTES * 60:
            continue
        p = snaps[key].get(str(r["num"])) or []
        return _price(p[1]) if len(p) == 2 else None
    return None


_PLACE_TERMS = None


def _place_terms() -> dict:
    global _PLACE_TERMS
    if _PLACE_TERMS is None:
        try:
            sys.path.insert(0, str(HERE.parent / "au_wong_choi_auto" / "scripts"))
            import au_bsp  # noqa: PLC0415
            _PLACE_TERMS = au_bsp.place_terms()
        except Exception:  # noqa: BLE001 — 外置碟冇插 = 冇呢項資料，唔影響主判決
            _PLACE_TERMS = {}
    return _PLACE_TERMS


def execution_fields(folder: Path, r: dict, pays: int) -> dict:
    """附加「落唔落到注」欄位（全部用賽前資料）。"""
    nxt = _next_sb_place(folder, r)
    venue = re.sub(r"[^a-z0-9]", "", re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", r["meeting"]).split(" Race")[0]
                   .split("_Race")[0].lower())
    winners = _place_terms().get((r["day"], venue, r["race"]))
    return {"sb_place_next": nxt,
            "persisted": None if nxt is None or not r.get("bf_place") else nxt / r["bf_place"] >= OVERLAY_RATIO,
            "sb_places_paid": pays, "bf_place_winners": winners,
            "terms_match": None if winners is None else winners == pays}


def settle(rows: list[dict], folders: dict) -> list[dict]:
    """→ 已結算：加 overlay、placed、won、place_return、win_return。遲退出（退注）同未有賽果唔計。"""
    import au_reflect_notify as R  # noqa: PLC0415
    cache, out = {}, []
    for r in rows:
        if not (r.get("sb_place") and r.get("bf_place")):
            continue
        folder = folders.get(r["meeting"])
        if folder is None:
            continue
        if r["meeting"] not in cache:
            cache[r["meeting"]] = _results(folder)
        placings = cache[r["meeting"]].get(r["race"])
        if not placings or r["num"] not in placings:
            continue
        fin = placings[r["num"]]
        pays = R.places_paid(R.field_size(folder, r["race"]))
        s = dict(r, overlay=r["sb_place"] / r["bf_place"] >= OVERLAY_RATIO, placed=1 <= fin <= pays, won=fin == 1)
        s.update(execution_fields(folder, r, pays))
        s["place_return"] = s["sb_place"] if s["placed"] else 0.0
        s["win_return"] = (s["sb_win"] or 0.0) if s["won"] else 0.0
        out.append(s)
    return out


def _roi(rows, key="place_return"):
    return (sum(r[key] for r in rows) / len(rows) - 1.0) if rows else None


def _boot(rows, fn):
    days = sorted({r["day"] for r in rows})
    by = {d: [r for r in rows if r["day"] == d] for d in days}
    rng, vals = random.Random(SEED), []
    for _ in range(BOOT):
        sample = [r for d in (rng.choice(days) for _ in days) for r in by[d]]
        v = fn(sample)
        if v is not None:
            vals.append(v)
    vals.sort()
    return [vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]] if vals else [None, None]


def evaluate(settled: list[dict]) -> dict:
    over = [r for r in settled if r["overlay"]]
    rest = [r for r in settled if not r["overlay"]]

    def diff(s):
        a, b = _roi([r for r in s if r["overlay"]]), _roi([r for r in s if not r["overlay"]])
        return None if a is None or b is None else a - b

    p1 = _boot(over, _roi)
    p2 = _boot(settled, diff)
    ok = p1[0] is not None and p1[0] > 0 and p2[0] is not None and p2[0] > 0
    bins = {}
    for lo, hi in ((0, 0.9), (0.9, 1.0), (1.0, 1.1), (1.1, 99)):
        b = [r for r in settled if lo < r["sb_place"] / r["bf_place"] <= hi]
        bins[f"{lo}-{hi}"] = {"n": len(b), "place_roi": _roi(b)}
    exe = [r for r in over if r.get("persisted") is True and r.get("terms_match") is True]
    execution = {"n": len(exe), "place_roi": _roi(exe), "place_roi_ci": _boot(exe, _roi) if exe else [None, None],
                 "overlay_with_next_price": sum(r.get("persisted") is not None for r in over),
                 "overlay_persisted": sum(r.get("persisted") is True for r in over),
                 "overlay_terms_known": sum(r.get("terms_match") is not None for r in over),
                 "overlay_terms_mismatch": sum(r.get("terms_match") is False for r in over),
                 "note": "附加：唔改主判決；落得到子集 = 高價組 ∩ 價維持 ∩ 位置規則一樣"}
    return {"verdict": "PASS" if ok else "REJECT", "execution": execution,
            "overlay": {"n": len(over), "place_roi": _roi(over), "place_roi_ci": p1,
                        "win_roi": _roi([r for r in over if r["sb_win"]], "win_return")},
            "rest": {"n": len(rest), "place_roi": _roi(rest)},
            "diff_ci": p2, "ratio_bins": bins,
            "evaluated_at": datetime.now().isoformat(timespec="seconds")}


def status(picks_path: Path, status_path: Path) -> dict:
    from wongchoi_paths import AU_RACING  # noqa: PLC0415
    root = Path(AU_RACING)
    folders = {d.name: d for base in (root, root / "Archive") for d in base.glob("2026-*") if d.is_dir()}
    rows = [json.loads(x) for x in picks_path.read_text(encoding="utf-8").splitlines()] \
        if picks_path.exists() else []
    prev = {}
    try:
        prev = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    settled = settle(rows, folders)
    over = sum(1 for r in settled if r["overlay"])
    st = {"experiment": EXPERIMENT, "target_races": TARGET, "unit": "注",
          "races_collected": over,
          "interim": {"frozen_picks": len(rows),
                      "paired_with_betfair": sum(1 for r in rows if r.get("sb_place") and r.get("bf_place")),
                      "betfair_place_bad": sum(1 for r in rows if r.get("bf_bad")),
                      "settled": len(settled), "overlay_settled": over,
                      "rest_settled": len(settled) - over,
                      # 落唔落到注（只係數量，唔報 ROI —— 照樣盲測）
                      "overlay_persisted": sum(1 for r in settled if r["overlay"] and r.get("persisted") is True),
                      "overlay_terms_mismatch": sum(1 for r in settled if r["overlay"] and r.get("terms_match") is False),
                      "overlay_executable": sum(1 for r in settled if r["overlay"] and r.get("persisted") is True
                                                and r.get("terms_match") is True)},
          "updated_at": datetime.now().isoformat(timespec="seconds")}
    if prev.get("evaluation"):
        st["evaluation"] = prev["evaluation"]          # 判咗就凍結，唔再判
    elif over >= TARGET:
        st["evaluation"] = evaluate(settled)
    status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--work-dir", default=str(HERE / "work"))
    ap.add_argument("--until", default=datetime.now().date().isoformat())
    args = ap.parse_args(argv)
    work = Path(args.work_dir)
    added = freeze(work / "au-sb-betfair-forward-picks.jsonl", until=args.until)
    st = status(work / "au-sb-betfair-forward-picks.jsonl", work / "au-sb-betfair-forward-status.json")
    print(json.dumps({"added": added, **st["interim"], "done": bool(st.get("evaluation"))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
