"""Telegram: 精選 cards, the unified ROI board row, forward-test milestones, alerts.

Audience (Kelvin 2026-11-05): 精選 and ROI go to ``content`` (Kelvin + Heison);
errors and system notices go to ``primary`` (Kelvin only). Credentials live in
``~/.wongchoi_notify.env``. 精選 messages are sent only when TENNIS_NOTIFY_BETS=1.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger("tennis_wc")
NOTIFY_ENV_PATH = Path.home() / ".wongchoi_notify.env"
FORWARD_STATE = "featured-forward-state.json"


def _env(path: Path | None = None) -> dict[str, str]:
    try:
        text = (path or NOTIFY_ENV_PATH).read_text()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.removeprefix("export ").partition("=")
        if sep:
            values[key.strip()] = value.strip().strip("'\"")
    return values


def targets(path: Path | None = None, *, audience: str = "primary") -> list[str]:
    values = _env(path)
    primary = values.get("WC_NOTIFY_TELEGRAM_CHAT")
    if not primary:
        return []
    out = [primary]
    if audience == "content":
        out += [x.strip() for x in re.split(r"[,;]", values.get("WC_NOTIFY_TELEGRAM_EXTRA", "")) if x.strip()]
    return list(dict.fromkeys(out))


def chunks(text: str, *, limit: int = 3800) -> list[str]:
    out: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            out.append(current)
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        out.append(current)
    return out or [""]


def notify(text: str, *, audience: str = "primary", path: Path | None = None) -> bool:
    token = _env(path).get("WC_NOTIFY_TELEGRAM_TOKEN")
    chats = targets(path, audience=audience)
    if not token or not chats:
        _LOG.info("Notify skipped: no Telegram credentials")
        return False
    sent = 0
    for chat in chats:
        ok = True
        for part in chunks(text):
            try:
                body = urllib.parse.urlencode({"chat_id": chat, "text": part}).encode()
                request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
                with urllib.request.urlopen(request, timeout=15) as response:
                    ok = ok and 200 <= response.status < 300
            except Exception as exc:  # noqa: BLE001 - one recipient failing is logged
                ok = False
                _LOG.warning("Notify failed for one %s recipient: %s", audience, exc)
                break
        sent += int(ok)
    _LOG.info("Notify %s: %d/%d recipients", audience, sent, len(chats))
    return sent == len(chats)


def publish_featured(match_date: str, run_label: str, *, main: bool) -> list[dict]:
    """Record 精選 for the date, then send the main card or a top-up of new picks."""
    from tennis_wc.database.db import get_connection
    from tennis_wc.select import featured

    with get_connection() as conn:
        added = featured.record(conn, match_date, run_label)
        today = featured.picks_with_results(conn, since=match_date, until=match_date)
        perf = featured.performance(featured.picks_with_results(conn))
    _LOG.info("精選 %s @ %s: +%d (total %d)", match_date, run_label, len(added), len(today))
    if main:
        message = featured.telegram_message(match_date, today, kind="main", perf=perf)
    elif added:
        new_ids = {row["prop_id"] for row in added}
        message = featured.telegram_message(match_date, [r for r in today if r["prop_id"] in new_ids],
                                            kind="topup", perf=perf)
    else:
        return added
    if os.environ.get("TENNIS_NOTIFY_BETS") == "1":
        notify(message, audience="content")
    return added


def _roi_board():
    shared = Path(__file__).resolve().parents[4] / ".agents" / "skills" / "shared_racing" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import wongchoi_roi
    return wongchoi_roi


def _roi_row(profile: dict) -> dict:
    settled = int(profile.get("settled") or 0)
    return {"bets": settled, "hits": int(profile.get("wins") or 0),
            "stake": float(profile.get("staked") or settled), "pnl": float(profile.get("pnl") or 0.0)}


def featured_performance(match_date: str) -> dict:
    from tennis_wc.database.db import get_connection
    from tennis_wc.select import featured

    with get_connection() as conn:
        day = featured.picks_with_results(conn, since=match_date, until=match_date)
        overall = featured.picks_with_results(conn, until=match_date)
    return {"daily": featured.performance(day), "overall": featured.performance(overall)}


def send_roi_board(match_date: str, today: str) -> bool:
    """Yesterday's settled 精選 onto the unified Wong Choi ROI board (only if any settled)."""
    perf = featured_performance(match_date)
    board = _roi_board()
    entry = board.record("tennis", day=match_date, latest=_roi_row(perf["daily"]),
                         cumulative=_roi_row(perf["overall"]))
    if not (entry.get("latest") or {}).get("bets"):
        return False
    return notify(board.render(updated="tennis", today=today), audience="content")


def forward_milestone(log_dir: Path) -> str | None:
    """Telegram once when the 精選 forward test first reaches 250, and again at 600."""
    from tennis_wc.database.db import get_connection
    from tennis_wc.select import featured

    with get_connection() as conn:
        perf = featured.performance(featured.picks_with_results(conn))
    state_path = log_dir / FORWARD_STATE
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    settled = perf["settled"]
    milestone = (featured.FORWARD_FINAL_VERDICT if settled >= featured.FORWARD_FINAL_VERDICT
                 else featured.FORWARD_FIRST_VERDICT if settled >= featured.FORWARD_FIRST_VERDICT else None)
    if milestone is None or str(milestone) in state:
        return None
    verdict = featured.forward_verdict(perf)
    roi = f"{perf['roi']:+.1%}" if perf["roi"] is not None else "—"
    ci = f"[{perf['ci_low']:+.1%}, {perf['ci_high']:+.1%}]" if perf["ci_low"] is not None else "—"
    message = (f"🎾 Tennis 精選前向測試夠數（{milestone} 注）\n"
               f"已結算 {settled} 注｜中 {perf['wins']}｜ROI {roi}｜95% CI {ci}\n"
               f"預先登記判決：{verdict}\n"
               "EXP-20261105-10。系統唔會自動改模型或者開真錢，由 Kelvin 決定。")
    if notify(message, audience="primary"):
        state[str(milestone)] = {"verdict": verdict, "settled": settled,
                                 "sent_at": datetime.now().isoformat()}
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    return verdict
