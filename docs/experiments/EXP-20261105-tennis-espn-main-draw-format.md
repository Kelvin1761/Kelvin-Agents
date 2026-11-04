# Tennis ESPN 大滿貫男單正賽 format

2026-11-05 Sydney。自正式 draw 修正 `3bc39eee` 開獨立 worktree。ESPN 男單正賽只有在來源明示 men's singles、已知大滿貫名稱同已辨識正賽 round 都吻合時，才沿用現有 BO5 規則。原未知、其他賽制路徑維持；忽略不可靠嘅 regulation.periods。依據 [2026 Grand Slam 規則](https://www.itftennis.com/media/5986/grand-slam-rulebook-2026-f2.pdf)。

用固定 ESPN ATP／WTA 澳網原文重播 1 月 12 日至 2 月 1 日歷史入口。254 條男單正賽履歷由 BO3 改成 BO5。208 條男單外圍、466 條女單正賽及外圍，維持 BO3。馬德里決賽兩條維持 BO3。另以 2026-06-07、07-12、09-13 公開 ATP scoreboard 做逐屆驗證，法網、溫布頓、美網每屆 127 場完成男單正賽均為 BO5。除 format 以外嘅完整有序輸出，澳網同馬德里兩個 arm SHA256 各自一致。呢啲係已封存原文重播，唔代表歷史 production 逐日成功抓取或回填。

Wimbledon 男單 qualifying final 另按已核實規則標 BO5。2026 原文 16 場皆完成，11 場打四至五盤，其餘 5 場直落三盤。前兩輪及女單 qualifying final 維持 BO3。[ATP 官方規則實例](https://www.atptour.com/en/news/arnaldi-albot-wimbledon-qualifying-2023-thursday)。固定庫 8 場 Sportsbet Wimbledon fixtures 嘅 round 全部 UNKNOWN，今次只改有明示 ESPN 階段嘅歷史入庫，未改賽前估價。舊履歷與 frozen prediction 評估不在本次資料修復範圍。沒有新的準確度證據。
