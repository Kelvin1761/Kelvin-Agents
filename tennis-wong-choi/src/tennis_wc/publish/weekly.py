"""Sunday Telegram: is 21:00 the right time to bet? (plan 2026-11-05, stage 1 monitoring)

For the last 7 days of 精選:
  * how many came at 21:00 vs the 23:00 / 09:00 top-ups;
  * how the price moved between the pick and the last pre-start quote
    (the 15-75 min preclose capture, else the latest ordinary capture);
  * the forward test's progress.
If 21:00 keeps supplying under half the picks, Kelvin decides whether to move it.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from tennis_wc.store.db import get_connection


def _close(conn, pick) -> float | None:
    for table in ("preclose_market_odds_snapshots", "market_odds_snapshots"):
        row = conn.execute(f"""
            SELECT odds FROM {table}
            WHERE match_id = ? AND market_name = ? AND selection_name = ?
              AND fetched_at < ? ORDER BY fetched_at DESC, id DESC LIMIT 1""",
            (pick["match_id"], pick["feed_market_name"], pick["feed_selection_name"],
             pick["start_time_utc"])).fetchone()
        if row:
            return float(row[0])
    return None


def weekly_text(today: str) -> str:
    from tennis_wc.select import featured

    start = (date.fromisoformat(today) - timedelta(days=7)).isoformat()
    with get_connection() as conn:
        picks = [dict(r) for r in conn.execute(
            "SELECT * FROM featured_picks WHERE match_date >= ? AND match_date < ? ORDER BY match_date, rank",
            (start, today))]
        moves = []
        for pick in picks:
            close = _close(conn, pick)
            if close:
                moves.append(close / float(pick["odds"]) - 1.0)
        perf = featured.performance(featured.picks_with_results(conn))
    by_label = Counter(p["run_label"] for p in picks)
    lines = [f"🎾 Tennis 精選｜每週時間檢查（{start} 至 {today}）",
             f"精選 {len(picks)} 注：21:00 {by_label.get('21:00', 0)}｜23:00 {by_label.get('23:00', 0)}"
             f"｜09:00 {by_label.get('09:00', 0)}"]
    if picks:
        share = by_label.get("21:00", 0) / len(picks)
        lines.append(f"21:00 佔 {share:.0%}" + ("（少過一半，要諗吓改時間）" if share < 0.5 else ""))
    if moves:
        shorter = sum(1 for m in moves if m < -0.005)
        longer = sum(1 for m in moves if m > 0.005)
        lines.append(f"出 card 價 → 開賽前價：平均 {sum(moves) / len(moves):+.1%}"
                     f"（{len(moves)} 注；縮水 {shorter}、變長 {longer}）")
    else:
        lines.append("出 card 價 → 開賽前價：未有可比較嘅報價")
    roi = f"{perf['roi']:+.1%}" if perf["roi"] is not None else "—"
    lines.append(f"前向測試：已結算 {perf['settled']}／{featured.FORWARD_FIRST_VERDICT} 注｜ROI {roi}")
    return "\n".join(lines)


def send_weekly(today: str) -> bool:
    from tennis_wc.publish.telegram import notify

    return notify(weekly_text(today), audience="primary")
