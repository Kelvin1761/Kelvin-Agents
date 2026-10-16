# 獨立正確性實驗：0 名次

主家族完成後，2026-10-16 審查觀察到 23 匹 last6 有 0；其中多筆 recent_6_detail 亦含「0名」。
FormScorer 已明文排除 <=0，consistency 仍會將佢放入 denominator 同 recent_shift 平均，兩者處理唔一致。

此為新發現，獨立於原先五個固定候選；不利用結果揀參。
唯一 arm：consistency 詳情解析及後備名次解析都排除 <=0；其他不變。
baseline 同截至 2026-10-10 語料不變；重新走 production harness。
按評估合約 §7：無效名次不應當作已完成賽績，與績效方向無關。
即使模型指標無提升仍屬正確性問題；但未滿足零顯著退步與 PIT 要求前不 release model code。
