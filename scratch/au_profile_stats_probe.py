#!/usr/bin/env python3
"""Racenet profile 摘要統計有冇真預測力？—— 落分之前必須先量。

抓到嘅新欄位（`scratch/au_profile_stats.json`）：
  winPercentage / placePercentage  —— 我哋由 jockey_ly 推導得到，但呢個係全庫口徑
  roi / lastYearRoi / seasonRoi    —— **真正新**（需要 SP，自己計唔到）
  totalRuns                        —— 生涯場數（經驗量），我哋冇
  ⚠️ currentSeasonRuns == lastYearRuns（實測 738=738），所以 season 嗰組冇新資訊

量度方法同之前所有 leaf 一致：場內 Spearman ρ vs 實際名次 + 場內五分位前三率，
只計覆蓋率足夠嘅場次。對照組 = 現行 jockey_score / trainer_score。

唯讀，本地 cache，零 Racenet 請求。
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"))

HERE = Path(__file__).resolve().parent
MIN_COVERED = 4     # 一場至少幾多匹有數據先計


def slugify(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2.0
        i = j + 1
    return out


def spearman(xs, ys):
    if len(xs) < 4:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    return num / (dx * dy) ** 0.5 if dx > 0 and dy > 0 else None


def main():
    prof_path = HERE / "au_profile_stats.json"
    if not prof_path.exists():
        sys.exit("未有 au_profile_stats.json —— 先跑 au_profile_fetch.py")
    profiles = json.loads(prof_path.read_text(encoding="utf-8"))
    by_kind = defaultdict(dict)
    for key, rec in profiles.items():
        kind, slug = key.split("|", 1)
        by_kind[kind][slug] = rec["stats"]
    print(f"profile: " + ", ".join(f"{k} {len(v)}" for k, v in by_kind.items()))

    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    # 由 leaf cache 攞 jockey/trainer 名 —— stability cache 冇存，改由 Logic 名對映
    # 用 archive 結果 CSV 嘅名（同 profile 抓取用同一來源）
    import csv
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, normalize_horse_name,
                                       normalize_track_name, parse_int)
    people = {}
    with HISTORICAL_RESULTS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race, pos = parse_int(row.get("Race")), parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            key = (str(row.get("Date") or "").strip(),
                   normalize_track_name(row.get("Track") or ""), race,
                   normalize_horse_name(row.get("Horse") or ""))
            people[key] = (slugify(row.get("Jockey")), slugify(row.get("Trainer")), pos)

    # 逐場評估
    FEATS = {
        "jockey winPercentage": ("jockey", "winPercentage"),
        "jockey placePercentage": ("jockey", "placePercentage"),
        "jockey roi (生涯)": ("jockey", "roi"),
        "jockey lastYearRoi": ("jockey", "lastYearRoi"),
        "jockey totalRuns (經驗)": ("jockey", "totalRuns"),
        "trainer winPercentage": ("trainer", "winPercentage"),
        "trainer placePercentage": ("trainer", "placePercentage"),
        "trainer roi (生涯)": ("trainer", "roi"),
        "trainer lastYearRoi": ("trainer", "lastYearRoi"),
        "trainer totalRuns (經驗)": ("trainer", "totalRuns"),
    }
    rho = defaultdict(list)
    quint = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    cover = defaultdict(list)

    races_by = defaultdict(list)
    for (date, track, race, horse), (jk, tr, pos) in people.items():
        races_by[(date, track, race)].append((jk, tr, pos))

    for key, field in races_by.items():
        if len(field) < 6:
            continue
        pos = [p for _, _, p in field]
        for label, (kind, stat) in FEATS.items():
            table = by_kind.get(kind, {})
            vals, keep = [], []
            for i, (jk, tr, _) in enumerate(field):
                slug = jk if kind == "jockey" else tr
                st = table.get(slug)
                if st is None or st.get(stat) is None:
                    continue
                vals.append(float(st[stat]))
                keep.append(i)
            cover[label].append(len(vals) / len(field))
            if len(vals) < MIN_COVERED:
                continue
            sub = [pos[i] for i in keep]
            r = spearman(vals, sub)
            if r is not None:
                rho[label].append(-r)
            order = sorted(range(len(vals)), key=lambda i: -vals[i])
            for slot, idx in enumerate(order):
                q = min(4, slot * 5 // len(order))
                quint[label][q][0] += 1
                quint[label][q][1] += 1 if sub[idx] <= 3 else 0

    print(f"\n{'特徵':28}{'可用場數':>9}{'場內覆蓋':>9}{'ρ':>8}{'Q1前三%':>9}{'Q5前三%':>9}{'差':>7}")
    out = []
    for label in FEATS:
        if len(rho[label]) < 30:
            continue
        q = quint[label]
        q1 = 100 * q[0][1] / q[0][0] if q[0][0] else 0
        q5 = 100 * q[4][1] / q[4][0] if q[4][0] else 0
        out.append((label, len(rho[label]), 100 * statistics.mean(cover[label]),
                    statistics.mean(rho[label]), q1, q5))
    for label, n, cov, r, q1, q5 in sorted(out, key=lambda x: -x[3]):
        print(f"{label:28}{n:>9}{cov:>8.0f}%{r:>8.3f}{q1:>9.1f}{q5:>9.1f}{q1-q5:>7.1f}")
    print("\n對照：jockey_score ρ 0.163 / trainer_score ρ 0.156 /"
          " jockey_horse_fit ρ 0.071 / form_score ρ 0.214")


if __name__ == "__main__":
    main()
