#!/usr/bin/env python3
"""NBA_All_SGM_Report.txt + NBA_Banker_Report.txt: the day's formal combos, from the sidecars.

Each game's data comes from ``Game_<tag>_Full_Analysis.md.market_legs.json``, and only when
its ``report_sha256`` binds it to that report; the Markdown itself is never parsed.
Nothing machine-reads these two files: people read them, the scheduler snapshot copies them.

  1. NBA_All_SGM_Report.txt — every game: combo 1 (or NO BET and why) + the steady research record
  2. NBA_Banker_Report.txt  — Top Banker leg per game (highest-EV leg of combo 1) + combo 1 per game

usage: python generate_nba_sgm_reports.py --dir "2026-11-05 NBA Analysis" [--games AAA_BBB ...]
exit 1 when a selected game has no sidecar bound to its report.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SIDECAR_SUFFIX = ".market_legs.json"
LABELS = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM"}


def load_game(report: Path):
    """The report's sidecar, or None when it is missing or not bound to this report."""
    try:
        payload = json.loads(Path(str(report) + SIDECAR_SUFFIX).read_text(encoding="utf-8"))
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) and payload.get("report_sha256") == digest else None


def _pct(value):
    return "—" if value is None else f"{100 * value:.1f}%"


def _desc(leg):
    return leg.get("desc") or leg.get("selection") or (
        f"{leg.get('player')} {LABELS.get(leg.get('market'), leg.get('market'))} {leg.get('line'):g}+")


def formal_combo(sidecar):
    return next((c for c in sidecar.get("combos") or [] if str(c.get("combo_id")) == "1"), None)


def banker_leg(sidecar):
    """Highest-EV leg of combo 1 — the same leg the dashboard calls the banker."""
    combo = formal_combo(sidecar)
    legs = [l for l in (combo or {}).get("legs") or [] if l.get("p_final") is not None and l.get("price")]
    if not legs:
        return None
    best = max(legs, key=lambda l: l["p_final"] * l["price"] - 1)
    return f"{_desc(best)} @{best['price']:g} (EV {100 * (best['p_final'] * best['price'] - 1):+.1f}%)"


def combo_lines(sidecar):
    combo = formal_combo(sidecar)
    if not combo:
        reason = (sidecar.get("selection_diagnostics") or {}).get("no_bet_reason", "no_combo")
        return [f"🛡️ 組合 1: NO BET — {reason}"]
    price = combo.get("sportsbet_sgm_price") or combo.get("product_of_leg_prices")
    joint = combo.get("adjusted_joint_prob")
    out = [combo.get("heading") or f"🛡️ 組合 1 — 組合賠率 @{price}",
           f"   模型組合命中率 {_pct(joint)} | 真實 SGM 報價 @{price} | 模型 EV "
           + ("—" if joint is None or not price else f"{100 * (joint * price - 1):+.1f}%")]
    reference = {(l.get("player"), l.get("market"), l.get("line")): l for l in sidecar.get("legs") or []}
    for i, leg in enumerate(combo.get("legs") or [], 1):
        l10 = reference.get((leg.get("player"), leg.get("market"), leg.get("line")), {}).get("p_l10_base_rate")
        out.append(f"   🧩 {i} {_desc(leg)} @{leg.get('price'):g} | 模型 {_pct(leg.get('p_final'))} | L10 {_pct(l10)}")
    return out


def research_lines(sidecar):
    out = []
    for item in sidecar.get("review_candidates") or []:
        if not isinstance(item, dict) or item.get("candidate_id") != "steady":
            continue
        price = "未報價" if item.get("odds") is None else f"@{item['odds']:g}"
        out.append(f"   📎 {item.get('label', '研究記錄')}（OBSERVE，唔係投注）{price} | "
                   f"模型 {_pct(item.get('model_probability'))} | "
                   + "、".join(_desc(leg) for leg in item.get("legs") or []))
    return out


def display(tag):
    return tag.replace("_", " @ ")


def all_sgm_report(games, analysis_date):
    lines = ["# 🏀 NBA Wong Choi 全日 SGM 報告", f"# 📅 日期: {analysis_date} | 總場次: {len(games)}"]
    if any(g["sidecar"].get("season_phase") == "PRESEASON" for g in games):
        lines.append("# ⛔ NO BET — PRESEASON SHADOW ONLY：歷史參考組合，禁止投注。")
    lines.append("")
    for game in games:
        lines += ["=" * 60, f"## {display(game['tag'])}", "=" * 60]
        lines += combo_lines(game["sidecar"]) + research_lines(game["sidecar"]) + [""]
    quoted = sum(bool(formal_combo(g["sidecar"])) for g in games)
    lines += ["=" * 60, "# 📊 全日統計", "=" * 60, f"總場次: {len(games)}", f"已報價 SGM 組合數: {quoted}", ""]
    return "\n".join(lines)


def banker_report(games, analysis_date):
    lines = ["# 🛡️ NBA Wong Choi 全日穩膽 Banker 報告", f"# 📅 日期: {analysis_date} | 總場次: {len(games)}"]
    if any(g["sidecar"].get("season_phase") == "PRESEASON" for g in games):
        lines.append("# ⛔ NO BET — PRESEASON SHADOW ONLY：歷史參考組合，禁止投注。")
    lines += ["", "=" * 60, "## 📋 全日 Top Banker Legs 速覽", "=" * 60, "",
              "| # | 場次 | Banker Leg | 來源 |", "|---|------|-----------|------|"]
    for i, game in enumerate(games, 1):
        lines.append(f"| {i} | {game['tag'].replace('_', '@')} | {banker_leg(game['sidecar']) or 'N/A'} | 組合 1 |")
    lines += ["", "=" * 60, "## 🏆 逐場穩膽 SGM", "=" * 60, ""]
    for game in games:
        lines += ["-" * 50, f"### {display(game['tag'])}", "-" * 50] + combo_lines(game["sidecar"]) + [""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="NBA Wong Choi SGM summary reports (from sidecars)")
    parser.add_argument("--dir", required=True, help="Path to the NBA Analysis directory")
    parser.add_argument("--date", default=None, help="Analysis date (default: from the directory name)")
    parser.add_argument("--games", nargs="+", help="Only compile these validated game tags")
    args = parser.parse_args()

    target = Path(args.dir)
    if not target.is_dir():
        print(f"❌ 目錄不存在: {target}")
        return 1
    match = re.match(r"(\d{4}-\d{2}-\d{2})", target.resolve().name)
    analysis_date = args.date or (match.group(1) if match else "Unknown")

    if args.games:
        if any(not re.fullmatch(r"[A-Z]{2,4}_[A-Z]{2,4}", tag) for tag in args.games):
            parser.error("Invalid game tag")
        reports = [target / f"Game_{tag}_Full_Analysis.md" for tag in dict.fromkeys(args.games)]
        if any(not path.is_file() for path in reports):
            parser.error("Selected game report is missing")
    else:
        reports = sorted(target.glob("Game_*_Full_Analysis.md"))
    if not reports:
        print(f"⚠️ 搵唔到任何 Game_*_Full_Analysis.md 喺 {target}")
        return 1

    games, unbound = [], []
    for report in reports:
        tag = re.match(r"Game_(.+?)_Full_Analysis\.md$", report.name).group(1)
        sidecar = load_game(report)
        if sidecar is None:
            unbound.append(tag)
            continue
        games.append({"tag": tag, "sidecar": sidecar})
        print(f"  📖 {tag}: {'組合 1 已報價' if formal_combo(sidecar) else 'NO BET'} | Banker: {banker_leg(sidecar) or 'N/A'}")
    if unbound:
        print(f"⛔ sidecar 缺失或者對唔上報告: {', '.join(unbound)}；唔生成匯總報告。")
        return 1

    for name, text in (("NBA_All_SGM_Report.txt", all_sgm_report(games, analysis_date)),
                       ("NBA_Banker_Report.txt", banker_report(games, analysis_date))):
        path = target / name
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        print(f"  ✅ {name} ({len(text.encode())} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
