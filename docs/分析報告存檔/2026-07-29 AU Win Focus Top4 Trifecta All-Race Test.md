# AU Wong Choi — Win Focus 對 Top 4 Trifecta 全歷史測試

## 測試口徑

- 歷史期間：2025-08-02 至 2026-07-08；WIN 可評估 709 場，完整頭三名可評估 706 場。
- Top 4 Box hit：模型頭四選包晒實際第1、2、3名，不理順序。
- 四馬 Box 有 24 個有序組合；archive 冇 AU Trifecta dividend，所以唔計虛假 ROI。
- Cross-fit：全709場都有 out-of-fold ranking，但訓練可包含較後日期。
- Strict walk-forward：只用過去訓練未來，覆蓋574場；呢層較接近實際部署。

## 全709場 grouped-date cross-fit

| 模型 | #1勝率 | 冠軍Top2 | 冠軍Top4 | Top4 Box中三甲 | 順序三重彩 | 打和所需平均$1派彩 |
|---|---:|---:|---:|---:|---:|---:|
| 現行 7D | 23.6% | 39.1% | 63.6% | 13.3% (94/706) | 1.4% | $180.26 |
| Win Logistic | 25.7% | 42.5% | 63.9% | 14.3% (101/706) | 1.4% | $167.76 |
| Win GBM | 26.1% | 42.6% | 63.3% | 13.3% (94/706) | 1.3% | $180.26 |

### 全歷史 Top 2 各 $1 WIN

| 模型 | ROI @ pre-play WAP proxy | ROI @ BSP（5%） |
|---|---:|---:|
| 現行 7D | -4.2% (708場) | +7.7% (707場) |
| Win Logistic | +2.6% (707場) | +15.3% (706場) |
| Win GBM | +4.1% (707場) | +17.0% (705場) |

## 嚴格時間順序 walk-forward

| 模型 | 場次 | #1勝率 | 冠軍Top2 | Top4 Box中三甲 | 95% CI | pre-play WAP ROI | BSP ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 現行 7D | 574 | 24.0% | 38.3% | 13.0% (74/571) | [10.4%, 16.0%] | -8.2% | +4.5% |
| Win Logistic | 574 | 25.4% | 40.2% | 14.0% (80/571) | [11.4%, 17.1%] | -9.1% | +2.0% |
| Win GBM | 574 | 23.5% | 39.7% | 14.2% (81/571) | [11.6%, 17.3%] | -5.3% | +6.6% |

## 配對泛化審計

| 候選 | Strict Top2 gains/losses | p | Strict Box gains/losses | p |
|---|---:|---:|---:|---:|
| Win Logistic | 24/13 (net +11) | 0.099 | 15/9 (net +6) | 0.307 |
| Win GBM | 48/40 (net +8) | 0.456 | 26/19 (net +7) | 0.371 |

## 五角度覆盤結論

1. **結果偏差：** Win Logistic／GBM 喺 Strict Box 分別只比現行多6／7場命中；改善幅度約1個百分點。
2. **過程偏差：** Winner-only objective 主要改善冠軍排序，冇直接學習亞軍、季軍，因此 Top2 改善唔會等比例傳到 Trifecta。
3. **Protocol 審計：** 同時使用全量 cross-fit及嚴格 walk-forward有效阻止只憑全歷史靚數升級模型。
4. **泛化性：** Box 改善配對 p-value 未達顯著；而 WIN fixed-price proxy 喺 strict forward 仍為負。
5. **Design Pattern Proposal：** Win-focus 只可作 shadow ranking；若目標包含 Trifecta，應另訓練 place／podium objective，唔應用 winner objective 取代整條排名。

## 決策

- 不升級正式 AU Wong Choi 模型。
- 可將 Win Logistic／GBM 加入100至200場 forward A/B paper test。
- Trifecta 只記錄 Top4 Box hit；未有實際 dividend archive 前，不宣稱正回報。
- 若下一輪專門改善 Trifecta，測試 multi-objective（Win + Top3/place）shadow model，而唔係再加強 winner-only 權重。
