# ADR-002: Declarative Schedule/Freshness Policy and Manifest-backed Cutover

## Status

Accepted — Stage 3B implementation, 2026-08-26.

## Context

四個 Wong Choi domain 都已經有成熟程度不同嘅 scheduler。問題唔係「有冇 cron」，而係原定 slot、timezone、target date、refresh scope、publish permission 同 sleep/wake catch-up 冇一份共用可測政策。NBA 尤其明顯：21:00、00:30、06:30 原本共用一個 launchd label，遲醒後無法知道原本係 warmup、production 定 final refresh。

同時，AU／HKJC／Tennis 已有 production wrapper，當中包含 local data root、TCC、Node、dashboard snapshot 同 self-update 保護。一次過重寫 wrapper 會增加營運風險。

## Decision

1. `.agents/skills/shared_wong_choi/schedule_policy.py` 成為 timezone、job slot、freshness role、refresh scope、snapshot mode 同 content/publish permission 嘅宣告式政策。
2. `.agents/skills/shared_wong_choi/control_plane.py` 成為 prediction lifecycle 嘅 manifest-backed dispatch 入口，負責 canonical identity、single-run lock、immutable attempts、temporary retry 同 status normalization。
3. Domain wrapper 保留所有現有環境準備，最後一步先交畀 control plane；domain adapter 再用 subprocess 執行原 scheduler。共用層唔 import scoring、features 或 ruler。
4. NBA 三個 pregame slot 拆成三個 launchd labels，明確傳入 `warmup`、`production`、`final_refresh`。21:00 禁止 publish/content card；00:30 正式 production；06:30 只刷新未開賽場次，已開賽 artifacts 不可改寫。
5. HKJC weekly promotion review、AU Telegram bot 同獨立 auto-heal healthcheck 唔屬 prediction dispatch，維持專用入口。

## Security and Data Boundaries

- Telegram credentials、data-root paths 同 provider secrets繼續由 repo 外 env file／現有 wrapper提供；control manifest不可記錄 secret value。
- State root預設為 `~/WongChoiData/WongChoiControl`，同分析 artifacts分開；manifest只保存 command、exit、status同有限 stderr tail。
- 未知 status、缺 status、hard non-zero exit一律 fail closed。

## Observability

- 每個 attempt有 immutable JSON manifest：domain、mode、target date、scheduled slot、operation、state、timestamps、exit code同 source envelope。
- 同一 attempt重跑只讀既有 manifest；exit 75／124先可按 bounded retry policy開新 attempt。
- Fixture clock覆蓋 Sydney DST、missed slots、shadow publish suppression同 NBA unstarted-only refresh。

## Rollback

- Wrapper最後一行可改回直接執行 domain scheduler；domain engine同 artifacts schema冇改。
- NBA installer會先 bootout舊 `com.antigravity.nba-wong-choi.pregame`，舊 plist改名 `.disabled`；要 rollback可停用三個新 labels並還原舊 plist。
- Control state係旁路紀錄；移除佢唔會改寫 domain prediction data。

## Consequences

- Stage 2B contract由測試層進入實際 daily dispatch路徑。
- Scheduled slot唔再等同 process真正醒來時間；NBA catch-up仍保持正確 freshness role。
- 過渡期 publish gate同 Telegram內容仍由 domain scheduler執行；共用層先統一 run result／政策，Stage 3B operational matrix會驗證各 domain既有 fail-closed行為。

## Revisit Trigger

當 scheduler搬到多 worker、需要跨機 lease，或者共用層正式接管 publish／notification side effects時，再評估 durable queue、central release gate同 notification outbox。未有量化需要前唔引入 microservices。
