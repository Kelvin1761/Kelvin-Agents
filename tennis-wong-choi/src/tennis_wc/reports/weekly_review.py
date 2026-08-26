"""Tennis Reflector — one weekly decision page across every tracked line.

The daily report tells you what to (maybe) bet TODAY. This tells you, across
the whole validation history, WHICH structures are actually earning their keep
and how close each derived market is to graduating from shadow-tracking to
bettable. It is read-only reporting over the existing trackers — it composes
the same summary functions the daily report and settlement use, so the numbers
always agree.

Decision rules surfaced at the bottom:
  - a derived market graduates at >= 20 settled + ROI >= 0 (CLV is NOT a gate:
    stored closing odds are contaminated with in-play prices -- see
    daily_report._market_upgrade_gate);
  - player props need positive formal-profile ROI plus probability skill or a
    credible bootstrap, and both the expanding recent window and fixed last-100
    circuit breaker must hold;
  - any family whose fixed short window turns negative returns to research,
    however profitable its lifetime still looks.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from tennis_wc.betting.ledger import combo_tracker_summary, tier_roi_summary
from tennis_wc.database.db import get_connection
from tennis_wc.props import strategy
from tennis_wc.evaluation.corpus import corpus_summary
from tennis_wc.props.settlement import model_vs_market_scorecard, prop_roi_report
from tennis_wc.reports.daily_report import (
    _market_validation_history,
    _market_upgrade_gate,
    _settlement_supported_market_keys,
    analysis_output_dir,
)

def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    pct = value * 100
    return f"{pct:+.1f}%" if signed else f"{pct:.1f}%"


def _prop_family_lines(roi: dict) -> list[str]:
    lines: list[str] = []
    for family, agg in sorted((roi.get("by_family") or {}).items()):
        if not agg.get("settled"):
            continue
        lines.append(
            f"  - {family}: {agg['settled']} 結算｜命中 {_pct(agg.get('hit_rate'))}"
            f"｜ROI {_pct(agg.get('roi'), signed=True)}（注 {agg.get('staked')}u）"
        )
    return lines


def _strategy_family_lines(strategy_state: dict) -> list[str]:
    """Render the exact evidence state used by the daily recommendation gate."""
    lines: list[str] = []
    for family, state in sorted((strategy_state.get("family_states") or {}).items()):
        if not state.get("recommendable_player_prop"):
            continue
        if not state.get("scorecard_settled") and not state.get("settled"):
            continue
        badge = {
            "VALIDATED": "✅",
            "EARLY_MAIN": "🟠",
            "RESEARCH_ONLY": "🧪",
        }.get(state.get("tier"), "🧪")
        lines.append(
            f"- {badge} {family}: {state.get('tier')}｜scorecard "
            f"{state.get('scorecard_settled', 0)}｜eligible paper "
            f"{state.get('settled', 0)}｜Brier "
            f"{state.get('model_brier', '—')} vs market "
            f"{state.get('market_brier', '—')}｜ROI "
            f"{_pct(state.get('roi'), signed=True)}｜近"
            f"{state.get('short_term_settled') or 0}注 "
            f"{_pct(state.get('short_term_roi'), signed=True)}"
        )
    return lines


def _derived_market_rows() -> list[dict]:
    """Per-market validation status for every settlement-supported derived
    market, sorted by how close it is to graduating."""
    rows: list[dict] = []
    for market_key in sorted(_settlement_supported_market_keys()):
        history = _market_validation_history(market_key)
        gate = _market_upgrade_gate(market_key, "DERIVED_MODEL")
        rows.append(
            {
                "market": market_key,
                "settled": history["settled"],
                "roi": history["roi"],
                "avg_clv": history["avg_clv"],
                "tier": gate["tier"],
                "to_graduate": max(0, 20 - history["settled"]),
            }
        )
    # Validated first, then nearest to the 20-settled bar.
    rows.sort(key=lambda r: (r["tier"] != "VALIDATED_DERIVED_MARKET", r["to_graduate"], -r["settled"]))
    return rows


def _chalk_chain_stats() -> dict:
    summary = combo_tracker_summary()
    settled = won = 0
    pnl = 0.0
    for row in summary.get("by_tier_status") or []:
        if "大熱串" not in str(row.get("tier") or ""):
            continue
        status = row.get("result_status")
        if status in ("WON", "LOST"):
            settled += int(row["combos"])
            pnl += float(row.get("profit") or 0)
        if status == "WON":
            won += int(row["combos"])
    return {"settled": settled, "won": won, "pnl": round(pnl, 2),
            "roi": (pnl / settled) if settled else None}


def _short_favourite_progress() -> dict | None:
    """The one cohort where the model is not behind the market, and how far it
    still is from being answerable.

    Reported every week on purpose. It is the only open lead left -- the match
    model is behind by Delta log-loss +0.0571 overall (CI [+0.0416, +0.0730]),
    cross-market coherence is a structural dead end (the book agrees with itself
    to a fifth of its own margin), and adding data did not help (Elo coverage
    went 27% -> 79% and the deficit stayed). A lead that is only checked when
    somebody remembers to check it is a lead that quietly dies, so the number
    that decides it goes on the page that gets read.
    """
    script = Path(__file__).resolve().parents[3] / "scripts" / "measure_short_favourites.py"
    if not script.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_short_fav", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        conn = get_connection()
        rows = module._load(conn)
        cohort = [r for r in rows if r["odds"] <= 1.6]
        pooled = module._paired_gap(cohort)
        return {
            "n": pooled.get("n", 0),
            "need": module.MIN_SAMPLE,
            "delta": pooled.get("delta_logloss"),
            "probability": pooled.get("probability_model_better"),
            "verdict": module._verdict(pooled),
        }
    except Exception:
        # A research harness must never take the weekly page down with it.
        return None


def _safe_short_favourite_progress() -> dict | None:
    try:
        return _short_favourite_progress()
    except Exception:
        return None


def weekly_review_data(as_of_date: str) -> dict:
    conn = get_connection()
    scorecard = model_vs_market_scorecard(conn, as_of_date=as_of_date)
    prop_roi = prop_roi_report(conn, value_only=True, as_of_date=as_of_date)
    prop_strategy = strategy.recommendation_gate(scorecard, prop_roi)
    return {
        "as_of": as_of_date,
        "scorecard": scorecard,
        "prop_roi": prop_roi,
        "prop_strategy": prop_strategy,
        "derived_markets": _derived_market_rows(),
        "chalk": _chalk_chain_stats(),
        "tier_roi": tier_roi_summary(),
        # Printed on the page, not just used to filter it. Every number above
        # now comes from provably pre-match rows only, and the corpus that
        # supplies them is small -- 291 staked of 2,304. Stating the
        # denominator is what stops the next reader from treating a
        # 291-observation ROI as a track record, and what would have exposed
        # the 2026-08-10 backfill on the day it landed.
        "corpus": corpus_summary(conn),
        # Guarded at the CALL SITE as well as inside: the harness has its own
        # try/except, and that only covers the work it does -- not the function
        # itself failing. Research code must never be load-bearing for the
        # operational page.
        "short_favourites": _safe_short_favourite_progress(),
    }


def render_weekly_review(as_of_date: str) -> str:
    data = weekly_review_data(as_of_date)
    sc = data["scorecard"]
    prop = data["prop_roi"]["overall"]
    prop_strategy = data["prop_strategy"]
    chalk = data["chalk"]
    corpus = data["corpus"]

    lines = [
        "🎾 Tennis Wong Choi 每週檢討（驗證進度）",
        f"截至：{as_of_date}",
        "",
        "睇呢頁決定：邊個 player-prop family 可以提早升做主線、邊個要自動降級；player-prop 升降級只用截至日期之前嘅結算。",
        "",
        "## 📊 一眼睇晒：邊條線贏緊",
        "",
    ]

    # The denominator, before any of the numbers that rest on it.
    admissible = corpus["point_in_time_staked"]
    excluded = corpus["post_start_staked"] + corpus["unverifiable_staked"]
    lines.append(
        f"- 📐 判決語料：{admissible} 注證實賽前"
        f"（另有 {excluded} 注開賽後寫或者量唔到幾時寫，唔入判決）"
    )
    if excluded > admissible:
        lines.append(
            "  - ⚠️ 唔入判決嗰批多過入判決嗰批。呢頁所有數字只講證實賽前嗰批；"
            "2026-08-10 一個回填 run 曾經令帳面 ROI 由 −23.38% 變 +2.86%。"
        )

    # Prop value line
    if prop.get("settled"):
        lines.append(
            f"- 🎾 Prop value（aces／總局數）：{prop['settled']} 結算｜命中 {_pct(prop.get('hit_rate'))}"
            f"｜ROI {_pct(prop.get('roi'), signed=True)}"
        )
    else:
        lines.append("- 🎾 Prop value：未有有注碼結算（多數 value 邊未賽完）")
    if prop_strategy.get("status") == "EARLY_MAIN":
        names = "、".join(prop_strategy.get("early_main_families") or [])
        lines.append(f"- 🟠 主線狀態：EARLY_MAIN（{names}；每注上限 0.5u）")
    elif prop_strategy.get("status") == "VALIDATED_SINGLE":
        names = "、".join(prop_strategy.get("validated_families") or [])
        lines.append(f"- ✅ 主線狀態：VALIDATED（{names}）")
    else:
        lines.append("- 🧪 主線狀態：RESEARCH_ONLY（未有 player-prop family 過早期門檻）")
    # Chalk chains
    if chalk["settled"]:
        lines.append(
            f"- 🔒 大熱串：{chalk['settled']} 結算｜命中 {chalk['won']}/{chalk['settled']}"
            f"｜損益 {chalk['pnl']:+g}u｜ROI {_pct(chalk.get('roi'), signed=True)}"
        )
    else:
        lines.append("- 🔒 大熱串：未有已結算組合")
    # Validated derived markets count
    validated = [r for r in data["derived_markets"] if r["tier"] == "VALIDATED_DERIVED_MARKET"]
    lines.append(f"- 🎯 衍生市場：{len(validated)}/{len(data['derived_markets'])} 個已通過畢業門檻（可入組合腳）")
    lines.append("- ❌ Match-winner：參考區、唔落（回測長期蝕，見每日報告）")
    fav = data.get("short_favourites")
    if fav and fav.get("n"):
        arrow = "落後" if (fav.get("delta") or 0) > 0 else "領先"
        lines.append(
            f"- 🔍 短賠熱門（賠率 ≤1.6，唯一未死嘅線索）：{fav['n']}/{fav['need']} 場"
            f"｜模型{arrow}市場 {abs(fav.get('delta') or 0):.5f} logloss"
            f"｜P={fav.get('probability')}"
        )
        lines.append(f"  - {fav['verdict']}")

    # Scorecard
    lines += ["", "## 🎾 Prop 記分卡（模型 vs 市場，越低越準）", ""]
    if sc.get("settled"):
        m, k = sc["model"], sc["market"]
        lines.append(f"- 已結算 {sc['settled']} 條｜模型 Brier {m['brier']} vs 市場 Brier {k['brier']}")
        lines.append(f"- 判定：{sc['verdict']}")
    else:
        lines.append("- 未有已結算 prop（等賽果）")
    fam_lines = _prop_family_lines(data["prop_roi"])
    if fam_lines:
        lines += ["", "分家庭 ROI（有注碼 value 注）："] + fam_lines

    lines += ["", "## 🚦 Player Prop 主線升降級（Reflector）", ""]
    strategy_lines = _strategy_family_lines(prop_strategy)
    if strategy_lines:
        lines += strategy_lines
    else:
        lines.append("- 未有 player-prop family 累積到可評估樣本。")
    lines.append("- EARLY_MAIN：至少 50 scorecard + 3 eligible paper bets + 正 ROI；模型 Brier／bootstrap 證據過關，上限 0.5u。")
    lines.append("- VALIDATED：至少 120 scorecard + 50 eligible paper bets，近期盈利亦要可信。")
    lines.append("- 自動降級：eligible ROI、時間近期窗或固定近100注任何一項轉負，立即回到 RESEARCH_ONLY。")

    # Derived-market graduation
    lines += ["", "## 🎓 衍生市場畢業進度（≥20 結算 ＋ ROI≥0 先可落）", ""]
    lines.append("⚠️ CLV 已停用做門檻：儲存嘅「收盤價」有部分係開賽後（in-play）抓到，")
    lines.append("   例如 4.65 → 「收」1.17，嗰啲唔係走盤而係場中價。下面 CLV 只作參考，唔可信。")
    lines.append("")
    for r in data["derived_markets"]:
        badge = "✅ 已畢業" if r["tier"] == "VALIDATED_DERIVED_MARKET" else (
            f"⏳ 仲差 {r['to_graduate']} 條" if r["to_graduate"] > 0 else "🔍 夠數據但 ROI 未轉正"
        )
        lines.append(
            f"- {r['market']}：{r['settled']} 結算｜ROI {_pct(r['roi'], signed=True)}"
            f"｜CLV {_pct(r['avg_clv'], signed=True)}（不可信）｜{badge}"
        )

    # Decision hints
    lines += ["", "## ⚙️ 決策提示", ""]
    hints: list[str] = []
    if prop_strategy.get("status") == "VALIDATED_SINGLE":
        hints.append(
            "✅ 有 player-prop family 已完整 VALIDATED；按可信度折扣 tenth-Kelly，單注最多 2u、兩腳最多 1u。"
        )
    elif prop_strategy.get("status") == "EARLY_MAIN":
        names = "、".join(prop_strategy.get("early_main_families") or [])
        hints.append(
            f"🟠 {names} 呈現可盈利早期趨勢，升做主線小注；每注固定最多 0.5u，逐週重跑升降級。"
        )
    else:
        hints.append(
            "⏳ 未有 player-prop family 過 EARLY_MAIN 門檻；繼續 paper settle，唔輸出正式主線注。"
        )
    for r in validated:
        hints.append(f"✅ {r['market']} 已畢業，可以做組合腳；但單獨落注前睇埋 ROI 樣本大細。")
    if not validated:
        hints.append("⏳ 未有衍生市場畢業 —— 全部仲喺影子追蹤，唔好落真注。")
    lines += hints

    lines += ["", "（此報告唯讀，唔會改動任何追蹤紀錄；數字同每日報告 / 結算一致。）"]
    return "\n".join(lines) + "\n"


def generate_weekly_review(as_of_date: str, output_dir: str | Path | None = None) -> Path:
    output_dir = Path(output_dir) if output_dir is not None else analysis_output_dir(as_of_date)
    output_path = output_dir / "Tennis_Weekly_Review.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_weekly_review(as_of_date), encoding="utf-8")
    return output_path
