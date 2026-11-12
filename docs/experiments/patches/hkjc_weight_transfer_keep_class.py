"""EXP-20261112-26：權重遷移（EXP-25）嘅「保留評分與經驗」版本 —— **事後候選**（睇完 EXP-25 結果先諗到）。

EXP-25 全搬版將評分與經驗（β −0.082）減到 0，Gold／Good 跌；推測主因係呢個。
規則（跑 A/B 之前寫死，數字全部由 EXP-25 嘅 transfer.json 計，冇再估）：
  評分與經驗維持現行權重；狀態與穩定性、騎練訊號、段速表現、檔位與走位
  按 β ÷ 引擎場內 SD 重新分配，四個加埋 = 佢哋現行權重總和。
  K100 = 新權重；K50 = 新舊各半。其餘維度唔郁。
  S100／S50（Kelvin：「段速好緊要」）：段速表現都維持現行權重 —— 賽果庫冇匹馬自己分段，段速只能用輸頭馬等級代表（對應度 0.67），
  β 好可能低估；只喺狀態、騎練、檔位三個之間按 β ÷ SD 重新分配。
用法：python3 docs/experiments/patches/hkjc_weight_transfer_keep_class.py <transfer.json> <out.json>
"""
import json
import sys

MOVE = ("stability", "trainer_signal", "sectional", "race_shape")
t = json.load(open(sys.argv[1]))
cur, beta, sd = t["current"], t["beta"], t["sd"]
raw = {d: max(beta[d], 0.0) / sd[d] for d in MOVE}
c = sum(cur[d] for d in MOVE) / sum(raw.values())
k100 = {d: c * raw[d] for d in MOVE}
k50 = {d: 0.5 * cur[d] + 0.5 * k100[d] for d in MOVE}
for d in MOVE:
    print(f"{d:<16} 現行 {cur[d]:.4f}  K100 {k100[d]:.4f}  K50 {k50[d]:.4f}")
print(f"class_advantage  維持 {cur['class_advantage']:.4f}")
MOVE3 = ("stability", "trainer_signal", "race_shape")
raw3 = {d: max(beta[d], 0.0) / sd[d] for d in MOVE3}
c3 = sum(cur[d] for d in MOVE3) / sum(raw3.values())
s100 = {d: c3 * raw3[d] for d in MOVE3}
s50 = {d: 0.5 * cur[d] + 0.5 * s100[d] for d in MOVE3}
for d in MOVE3:
    print(f"[S] {d:<16} 現行 {cur[d]:.4f}  S100 {s100[d]:.4f}  S50 {s50[d]:.4f}")
json.dump({"K100": k100, "K50": k50, "S100": s100, "S50": s50}, open(sys.argv[2], "w"), indent=1)
