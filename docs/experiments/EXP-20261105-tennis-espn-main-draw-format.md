# Tennis ESPN 大滿貫男單正賽 format

2026-11-05 Sydney。自正式 draw 修正 `3bc39eee` 開獨立 worktree。ESPN 男單正賽只有在來源明示 men's singles、已知大滿貫名稱同已辨識正賽 round 都吻合時，才沿用現有 BO5 規則。原未知、其他賽制路徑維持；忽略不可靠嘅 regulation.periods。依據 [2026 Grand Slam 規則](https://www.itftennis.com/media/5986/grand-slam-rulebook-2026-f2.pdf)。

用固定 ESPN ATP／WTA 澳網原文重播 1 月 12 日至 2 月 1 日歷史入口。254 條男單正賽履歷由 BO3 改成 BO5。208 條男單外圍、466 條女單正賽及外圍，維持 BO3。馬德里決賽兩條維持 BO3。另以 2026-06-07、07-12、09-13 公開 ATP scoreboard 做逐屆驗證，法網、溫布頓、美網每屆 127 場完成男單正賽均為 BO5。除 format 以外嘅完整有序輸出，澳網同馬德里兩個 arm SHA256 各自一致。呢啲係已封存原文重播，唔代表歷史 production 逐日成功抓取或回填。

Wimbledon 嘅 qualifying final 仍屬獨立格式例外。今次原文 16 場中有 11 場記四至五盤，現有 qualifying 值未改，唔應以今次主賽修復代替該例外或改其他分析入口。舊履歷與 frozen prediction 評估不在本次資料修復範圍。沒有新的準確度證據。
