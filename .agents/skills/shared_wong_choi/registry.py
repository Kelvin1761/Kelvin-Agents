"""Capability registry for the four production Wong Choi domains."""

from __future__ import annotations

from .contracts import (
    AdapterSpec,
    CapabilityReadiness,
    Domain,
    Operation,
    OperationBinding,
)


def _binding(
    operation: Operation,
    entrypoint: str,
    *modes: str,
    readiness: CapabilityReadiness = CapabilityReadiness.IMPLEMENTED,
    note: str = "",
) -> OperationBinding:
    return OperationBinding(operation, entrypoint, tuple(modes), readiness, note)


AU_SCHEDULER = ".agents/skills/au_racing/au_daily_auto/au_daily_schedule.py"
AU_HEALTH = ".agents/skills/au_racing/au_daily_auto/au_healthcheck.py"
HKJC_SCHEDULER = ".agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py"
TENNIS_SCHEDULER = "tennis-wong-choi/scripts/tennis_daily_schedule.py"
TENNIS_RECOVERY = "tennis-wong-choi/scripts/tennis_card_recovery.py"
NBA_SCHEDULER = ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py"


ADAPTER_SPECS: dict[Domain, AdapterSpec] = {
    Domain.AU: AdapterSpec(
        domain=Domain.AU,
        display_name="AU Wong Choi",
        owner="au_daily_auto",
        orchestrator=".agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py",
        bindings=(
            _binding(Operation.DISCOVER, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.PREDICT, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.VALIDATE, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.PUBLISH, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.SETTLE, AU_SCHEDULER, "evening"),
            _binding(Operation.HEALTH, AU_HEALTH, "healthcheck"),
            _binding(Operation.NOTIFY, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.CALENDAR_STATE, AU_SCHEDULER, "evening"),
            _binding(Operation.RECOVER, AU_HEALTH, "healthcheck"),
        ),
        # ⚠️ AU 晚更係**通宵** job，唔係一個兩個鐘嘅 batch。佢 22:00 開工，逐個
        # 場次抽（實測每個 ~26 分鐘，`warm_people_pages` 食晒），中間仲要等
        # Sportsbet 嘅冷卻窗；`au_daily_schedule.py` 自己個註解寫住「由 22:00 到
        # 早更 10:00 有十二個鐘，等一陣再續係免費嘅」。
        #
        # 2026-08-26 至 08-28 三晚全部喺 7200 秒正中被 adapter 斬死（08-28 discover
        # 到 8 個場次，做完 Cairns / Caulfield / Eagle Farm 就死，Rosehill 排字母
        # 第七，由頭到尾冇機會）。場次係按 slug 字母順序做，所以呢個 timeout 唔係
        # 「偶爾切走一個」，而係**穩定咁永遠切走排後面嗰批**。
        #
        # 11 個鐘 = 22:00 → 09:00，喺 10:00 早更之前留返一個鐘 headroom。歷史最長
        # 一個成功晚更係 18,061 秒（08-21，10 個場次），所以 39,600 有足夠餘裕。
        run_timeouts=(
            ("evening", 11 * 3600),
            # 早更平時得三十幾秒（淨係覆核＋合併），但佢同時係**晚更執唔晒之後
            # 唯一會再出網補抽嘅地方**，而 `au_healthcheck` 嘅自動補跑亦都係借
            # 呢個 mode 跑。一個大禮拜六追五個場次 = 5 × ~26 分鐘 ＋ 冷卻窗，
            # 兩三個鐘唔夠用。6 個鐘由 10:00 計都喺 16:00 前收工，離 22:00 晚更
            # 仲有大把距離。
            ("morning", 6 * 3600),
            ("healthcheck", 3600),
        ),
    ),
    Domain.HKJC: AdapterSpec(
        domain=Domain.HKJC,
        display_name="HKJC Wong Choi",
        owner="hkjc_daily_auto",
        orchestrator=".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py",
        bindings=(
            _binding(Operation.DISCOVER, HKJC_SCHEDULER, "watch", "prerace"),
            _binding(Operation.PREDICT, HKJC_SCHEDULER, "prerace"),
            _binding(Operation.VALIDATE, HKJC_SCHEDULER, "prerace"),
            _binding(Operation.PUBLISH, HKJC_SCHEDULER, "prerace", "postrace"),
            _binding(Operation.SETTLE, HKJC_SCHEDULER, "postrace"),
            _binding(
                Operation.HEALTH,
                HKJC_SCHEDULER,
                "prerace",
                "recovery",
                readiness=CapabilityReadiness.PARTIAL,
                note="Health gates exist, but there is no canonical standalone run manifest yet.",
            ),
            _binding(Operation.NOTIFY, HKJC_SCHEDULER, "watch", "prerace", "postrace"),
            _binding(Operation.CALENDAR_STATE, HKJC_SCHEDULER, "watch"),
            _binding(Operation.RECOVER, HKJC_SCHEDULER, "recovery", "startup"),
        ),
    ),
    Domain.TENNIS: AdapterSpec(
        domain=Domain.TENNIS,
        display_name="Tennis Wong Choi",
        owner="tennis_daily_schedule",
        orchestrator="tennis-wong-choi/src/tennis_wc/cli.py",
        bindings=(
            _binding(Operation.DISCOVER, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.PREDICT, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.VALIDATE, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.PUBLISH, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.SETTLE, TENNIS_SCHEDULER, "daily"),
            _binding(
                Operation.HEALTH,
                TENNIS_SCHEDULER,
                "daily",
                "card",
                readiness=CapabilityReadiness.PARTIAL,
                note="Structured HEALTH_JSON exists in a text log, not a canonical run manifest.",
            ),
            _binding(Operation.NOTIFY, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.CALENDAR_STATE, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.RECOVER, TENNIS_RECOVERY, "recovery"),
        ),
    ),
    Domain.NBA: AdapterSpec(
        domain=Domain.NBA,
        display_name="NBA Wong Choi",
        owner="nba_daily_auto",
        orchestrator=".agents/skills/nba/nba_orchestrator.py",
        bindings=(
            _binding(Operation.DISCOVER, NBA_SCHEDULER, "pregame", "health"),
            _binding(
                Operation.PREDICT,
                NBA_SCHEDULER,
                "pregame",
                readiness=CapabilityReadiness.DEFERRED_LIVE_GATE,
                note="Engineering complete; 2026-27 live coverage acceptance remains open.",
            ),
            _binding(Operation.VALIDATE, NBA_SCHEDULER, "pregame", "health"),
            _binding(Operation.PUBLISH, NBA_SCHEDULER, "pregame", "postgame"),
            _binding(
                Operation.SETTLE,
                NBA_SCHEDULER,
                "postgame",
                readiness=CapabilityReadiness.DEFERRED_LIVE_GATE,
                note="First completed-day reflector smoke remains open.",
            ),
            _binding(Operation.HEALTH, NBA_SCHEDULER, "health"),
            _binding(Operation.NOTIFY, NBA_SCHEDULER, "pregame", "postgame", "health"),
            _binding(Operation.CALENDAR_STATE, NBA_SCHEDULER, "pregame", "health"),
            _binding(
                Operation.RECOVER,
                NBA_SCHEDULER,
                "startup",
                readiness=CapabilityReadiness.PARTIAL,
                note="Single-day startup catch-up exists; multi-day backlog policy is not authorised.",
            ),
        ),
    ),
}


def adapter_spec(domain: Domain | str) -> AdapterSpec:
    return ADAPTER_SPECS[Domain(domain)]
