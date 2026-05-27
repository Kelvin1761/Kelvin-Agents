# Unified Race Reflector

一個入口同時處理 AU 同 HKJC 賽後覆盤，會：

- 擷取或讀取賽果
- 寫入對應 race analysis folder
- 比對原本 model selections vs 實際賽果
- 產生 `Gold / Good / Pass / 1 Hit / Miss`
- 做 incident / forgiveness 分析
- 分析實際 Top 3 但模型冇揀中的馬
- 跑 archive backtest，列出 improvement suggestions
- **唔會**自動實裝任何 improvement

## CLI

```bash
python3 .agents/skills/shared_racing/race_reflector/scripts/unified_race_reflector.py \
  --platform au \
  --meeting "2026-04-18 Randwick" \
  --results-url "https://www.racenet.com.au/results/horse-racing/randwick-20260418/all-races"
```

```bash
python3 .agents/skills/shared_racing/race_reflector/scripts/unified_race_reflector.py \
  --platform hkjc \
  --meeting "2026-05-20_HappyValley" \
  --results-url "https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate=2026/05/20&RaceNo=1" \
  --race 1 --race 2
```

## Natural Language CLI

而家都可以直接用 freeform request：

```bash
python3 .agents/skills/shared_racing/race_reflector/scripts/unified_race_reflector.py \
  "reflect HKJC Sha Tin 2026-05-20 race 3" \
  --results-url "https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate=2026/05/20&RaceNo=3"
```

```bash
python3 .agents/skills/shared_racing/race_reflector/scripts/unified_race_reflector.py \
  "reflect AU Randwick 2026-04-18 race 1" \
  --results-url "https://www.racenet.com.au/results/horse-racing/randwick-20260418/all-races"
```

## Notes

- `--meeting-dir` 可直接指向現成 meeting 資料夾。
- 如果 meeting folder 已經有 results file，可省略 `--results-url`。
- `--race` 可重複，多個指定 race 會集中反映；唔加就會反映整個 meeting。
- freeform request 最好包含 `賽區 + 場地 + YYYY-MM-DD + race number`。
- Backtest 只會輸出 evidence，同 approval gate 一樣，**唔會**改 live code / matrix。
