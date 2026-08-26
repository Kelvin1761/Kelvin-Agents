# NBA Wong Choi Automation Alignment

## Goal

保留 `nba_orchestrator.py` 做唯一分析入口，為 NBA 補齊同其他 Wong Choi 一致嘅 unattended-safe production shell。

## Tasks

- [x] 盤點 orchestrator、reflector、dashboard exporter、archive path 同現有 launchd 模式。
- [x] 加 season-aware scheduler；冇賽事係 dormant，source outage 係 temporary failure。
- [x] 完整分析後先寫 immutable prediction snapshot；任何 game/validator/FILL/summary 缺口都禁止 deploy。
- [x] 接 post-game reflector、results-backed archive、dashboard settlement proposal／deploy。
- [x] 加 local-primary NBA archive path、structured run logs、Telegram operational alerts、已驗證 BET／NO BET 投注卡、賽後表現摘要同防重複發送。
- [x] 加 pregame/postgame/health/startup launchd jobs，同 `健康.sh` NBA 狀態。
- [x] 加單元／整合測試並跑 `./檢查.sh --quick`、`./檢查.sh`、`./健康.sh`。
- [x] 2026-08-26 full readiness scan：修正 Sydney 賽事日、官方賽程覆蓋、2026-27 season、live Sportsbet schema、ML import／X+、WAS tag、DNP／同姓球員結算、未完整 reflector archive、compile-only bypass。
- [x] 建立六階段 lifecycle classifier；POSTSEASON subtype 分開 PLAY_IN／PLAYOFFS；preseason automation 強制 shadow／NO BET。

## Done When

- [x] Off-season dry run exit 0 並寫 `dormant`，唔建立假分析。
- [x] Fixture simulation 只喺完整且 validator 通過時建立 snapshot／允許 deploy。
- [x] Post-game 冇完整賽果時保留 live folder；有結果先 archive。
- [x] launchd 已安裝、載入，並由全系統健康檢查顯示。

## Pre-season production gate

- [ ] 2026-27 第一個有盤比賽日完成 live pregame smoke：ESPN tags = Sportsbet tags = reports = snapshot manifest。
- [ ] 第一個完場日完成 live reflector smoke：所有 legs 只可以係 hit／miss／void，`unverified=0` 先歸檔。
- [ ] 收集最少 30 個 settled forward recommendations，建立 NBA bootstrap baseline；之前只可講「pipeline ready」，唔可以講模型已證明盈利。
- [x] Odds freshness policy 已實作：21:00 warm-up append-only snapshot但唔 publish／唔發content card；00:30 production；06:30只刷新未開賽game，有material source change先加 final-refresh snapshot，已開賽 artifacts不可改寫。
- [ ] 決定係咪授權 scheduler 自動清理多日 postgame backlog；今次 scan 只記錄風險，未擴大 unattended archive／Telegram side effects。
