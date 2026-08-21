"""AU Wong Choi 對市場：目標做唔做得到，同我哋喺市場之上有冇加到嘢。

2026-08-04 實測（715 場，SP 100% 覆蓋）：

    純市場（按 SP 排序）  Gold 23.2 · Good位 34.4 · winT3 67.7 · AUC 0.7393
    純 AU Wong Choi     Gold 15.5 · Good位 21.3 · winT3 56.2 · AUC 0.6530
    混合（市場 0.6）      Gold 23.5 · Good位 32.3
    混合（市場 0.9）      Gold 23.2 · Good位 35.5

**目標做得到** —— 市場權重 ≥0.4 過 Gold 20，≥0.6 兩個都過。
**但冇一個混合顯著贏純市場**：權重 >20% 落我哋嘅分就開始變差，
<20% 就同純市場分唔開。即係我哋冇任何市場捉唔到嘅資訊。

分段睇（馬群大細／乾濕／熱門程度）**冇一個 niche 贏得到**，
差距一致喺 −0.069 至 −0.096。

⚠️ SP 係開跑價，早上攞唔到。早盤弱過 SP，所以上面係**上限**。

⚠️ 呢個唔代表個模型冇價值 —— AUC 量嘅係排序，而呢個產品出嘅係
**有證據嘅文字分析**。但如果目標係 Gold/Good 數字，就要老實面對：
嗰個數字要靠賠率先達到得到。

原本嘅問題：Gold 20% / Good 30% 做唔做得到？—— 用市場做參照系。

點解要參照系：完美排序 = Gold 100%，所以「理論上限」冇資訊。有資訊嘅問題係
「一個聚合晒全世界資訊嘅排序做到幾多」。賠率就係嗰個 —— 佢包含晒馬房意向、
騎師市場、內幕、我哋睇唔到嘅一切。

如果市場都做唔到 20/30，咁個目標唔係「我哋未夠好」，係呢個難度本身。
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

S = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts").resolve()
sys.path[:0] = [str(S), str(S.parents[2] / "shared_racing")]
from eval_metrics import race_metrics, summarize_races  # noqa: E402

SP = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/"
          "2409e80e-a448-4b75-8fbb-bc0671c170f2/scratchpad")

# 由賽果 CSV 砌市場排序（SP 由細到大 = 市場心目中由強到弱）
by_race = defaultdict(list)
with open(SP / "sb_results.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        try:
            by_race[(r["Date"], r["Track"], int(r["Race"]))].append(
                (r["Horse"], int(r["Pos"]), float(r["SP"]) if r["SP"] else None))
        except (TypeError, ValueError):
            pass


def grade(rows_by_race, order_key):
    out = []
    for key, runners in rows_by_race.items():
        usable = [x for x in runners if x[2] is not None]
        if len(usable) < 4:
            continue
        ranked = sorted(usable, key=order_key)
        picks = [x[0] for x in ranked]
        pos = {x[0]: x[1] for x in usable}
        t3 = {h for h, p in pos.items() if p <= 3}
        win = next((h for h, p in pos.items() if p == 1), None)
        if len(t3) < 3 or win is None:
            continue
        out.append(race_metrics(picks, t3, winner=win, actual_pos=pos,
                                field_size=max(pos.values())))
    c = summarize_races(out)["counts"]
    n = len(out)
    return n, {k: 100.0 * c[k] / n for k in
               ("gold", "gold_strict", "good_positional", "pass",
                "champion", "winner_in_top3")}


n, mkt = grade(by_race, lambda x: x[2])
print(f"── 市場（按 SP 排序）── {n} 場")
print(f"{'':16}{'Gold':>8}{'Good位':>9}{'Pass':>8}{'首選=頭馬':>11}{'winT3':>8}")
print(f"{'市場':16}" + "".join(f"{mkt[k]:>8.1f}" if k != "good_positional" else f"{mkt[k]:>9.1f}"
      for k in ("gold", "good_positional", "pass",
                "champion", "winner_in_top3")))

# 我哋（同一批場次入面能對上嘅）
leaves = json.loads((SP / "leaves_sb_v3.json").read_text())["races"]
from au_racing_engine import matrix_mapper  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
rows = []
for r in leaves:
    sc = []
    for row in r["rows"]:
        m = matrix_mapper.map_features_to_matrix_scores(row["features"])
        sc.append((sum(m.get(k, 60.0) * w for k, w in MATRIX_WEIGHTS.items()) + row["wet"],
                   row["name"], row["pos"]))
    sc.sort(key=lambda x: -x[0])
    pos = {s[1]: s[2] for s in sc}
    t3 = {h for h, p in pos.items() if p <= 3}
    win = next((h for h, p in pos.items() if p == 1), None)
    if not t3 or win is None:
        continue
    rows.append(race_metrics([s[1] for s in sc], t3, winner=win, actual_pos=pos,
                             field_size=max(pos.values())))
c = summarize_races(rows)["counts"]
nn = len(rows)
ours = {k: 100.0 * c[k] / nn for k in
        ("gold", "gold_strict", "good_positional", "pass",
         "champion", "winner_in_top3")}
print(f"{'AU Wong Choi':16}" + "".join(f"{ours[k]:>8.1f}" if k != "good_positional" else f"{ours[k]:>9.1f}"
      for k in ("gold", "good_positional", "pass",
                "champion", "winner_in_top3")) + f"   ({nn} 場)")
print(f"{'差距':16}" + "".join(f"{ours[k]-mkt[k]:>+8.1f}" if k != "good_positional" else f"{ours[k]-mkt[k]:>+9.1f}"
      for k in ("gold", "good_positional", "pass",
                "champion", "winner_in_top3")))
print(f"\n目標：Gold 20.0 · Good位 30.0")
print(f"我哋距離目標：Gold {20.0-ours['gold']:+.1f} · Good位 {30.0-ours['good_positional']:+.1f}")
print(f"市場距離目標：Gold {20.0-mkt['gold']:+.1f} · Good位 {30.0-mkt['good_positional']:+.1f}")
