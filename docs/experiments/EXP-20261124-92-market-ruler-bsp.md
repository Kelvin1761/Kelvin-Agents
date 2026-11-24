# EXP-20261124-92 市場尺接駁 Betfair BSP（`--price bsp`）

- 日期：2026-11-25　平台：AU　類型：評估工具（唔郁模型、唔郁排名、唔郁注單）
- 起因：Kelvin「接駁 BSP 版」。EXP-20261124-91 修好記錄器之後，BSP 有兩個來源：記錄器（11-06 起，每晚自動）同公開 CSV（08-06 → 11-23，人手下載）。
- 新增：`au_wong_choi_auto/scripts/au_bsp.py`（載入＋配對，測試 `au_racing/tests/test_au_bsp.py`）；`market_ruler.py --price bsp`。

## 配對（現行 live BASE，2026-08-05 起）
- 40,938 匹：精確 39,775、後備（日期＋馬名＋場次唯一）997、配唔到 166 → 99.6%；4,243/4,260 場齊晒。
- 記錄器對 CSV（11-06 → 11-23 重疊）：獨贏 7,889 匹、位 7,769 匹，全部一樣（最大 log 差 6e−9）。即係記錄器配對可信。
- log(SP) 對 log(BSP) 相關 0.987。

## 結果

| | 獨贏 Δll（每場） | 入頭三 | 判 |
|---|---|---|---|
| 現行 live 喺 BSP（3,533 場／90 日） | −0.00037 [−0.00133, +0.00058] | −0.00042 [−0.00128, +0.00049] | 冇市場以外資訊 |
| 現行 live 喺 SP（EXP-90） | −0.00043 [−0.00159, +0.00078] | −0.00044 [−0.00126, +0.00042] | 冇 |
| F1 對 v2-rescreen BASE，BSP 配對 | −0.00001 [−0.00015, +0.00012] | +0.00012 [−0.00008, +0.00031] | FAIL |

市場本身：同一批 4,219 場，淨市場頭馬 nll SP 1.7590、BSP 1.7405，差 0.0185（SE 0.0022）。BSP 明顯準啲，同預期一樣（交易所、冇莊家利潤形狀）。

## 讀法
- 兩個收市價都話：現行模型冇市場以外嘅資訊。同 EXP-20261124-60（BSP CSV 版 Q1）一致。
- 合約：候選兩個價都報；真錢規則要過落注嗰個市場嘅價，喺 Sportsbet 落都要過 BSP。

## 可重現
```bash
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch"
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform au "$D/au-debut-trainer-20261124/BASE.json" --price bsp
```
（要外置碟：BSP 來源喺 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/`。）
