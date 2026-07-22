"""Weekly validation review — one decision page across every shadow-tracked line.

The daily report tells you what to (maybe) bet TODAY. This tells you, across
the whole validation history, WHICH structures are actually earning their keep
and how close each derived market is to graduating from shadow-tracking to
bettable. It is read-only reporting over the existing trackers — it composes
the same summary functions the daily report and settlement use, so the numbers
always agree.

Decision rule surfaced at the bottom (matches _market_upgrade_gate):
  - a derived market graduates at >= 20 settled + ROI >= 0 + avg_clv >= 0;
  - props/chalk are judged on the model-vs-market scorecard + realised ROI,
    but stakes stay flat until ~150-200 settled legs (small-sample caution).
"""
from __future__ import annotations

from pathlib import Path

from tennis_wc.betting.ledger import combo_tracker_summary, tier_roi_summary
from tennis_wc.database.db import get_connection
from tennis_wc.props.settlement import model_vs_market_scorecard, prop_roi_report
from tennis_wc.reports.daily_report import (
    _market_validation_history,
    _market_upgrade_gate,
    _settlement_supported_market_keys,
    analysis_output_dir,
)

# Enough settled legs before we would trust a prop/chalk ROI enough to move off
# flat stakes (pro-practice small-sample guard; see the formula-review memo).
_STAKE_CONFIDENCE_MIN_SETTLED = 150


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


def weekly_review_data(as_of_date: str) -> dict:
    conn = get_connection()
    scorecard = model_vs_market_scorecard(conn)
    prop_roi = prop_roi_report(conn, value_only=True)
    return {
        "as_of": as_of_date,
        "scorecard": scorecard,
        "prop_roi": prop_roi,
        "derived_markets": _derived_market_rows(),
        "chalk": _chalk_chain_stats(),
        "tier_roi": tier_roi_summary(),
    }


def render_weekly_review(as_of_date: str) -> str:
    data = weekly_review_data(as_of_date)
    sc = data["scorecard"]
    prop = data["prop_roi"]["overall"]
    chalk = data["chalk"]

    lines = [
        "🎾 Tennis Wong Choi 每週檢討（驗證進度）",
        f"截至：{as_of_date}",
        "",
        "睇呢頁決定：邊條線儲夠證據好加注／開真注，邊條要繼續平注驗證。全部係影子追蹤嘅真結算數字。",
        "",
        "## 📊 一眼睇晒：邊條線贏緊",
        "",
    ]

    # Prop value line
    if prop.get("settled"):
        lines.append(
            f"- 🎾 Prop value（aces／總局數）：{prop['settled']} 結算｜命中 {_pct(prop.get('hit_rate'))}"
            f"｜ROI {_pct(prop.get('roi'), signed=True)}"
        )
    else:
        lines.append("- 🎾 Prop value：未有有注碼結算（多數 value 邊未賽完）")
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

    # Derived-market graduation
    lines += ["", "## 🎓 衍生市場畢業進度（≥20 結算 ＋ ROI≥0 ＋ CLV≥0 先可落）", ""]
    for r in data["derived_markets"]:
        badge = "✅ 已畢業" if r["tier"] == "VALIDATED_DERIVED_MARKET" else (
            f"⏳ 仲差 {r['to_graduate']} 條" if r["to_graduate"] > 0 else "🔍 夠數據但未達正 ROI/CLV"
        )
        lines.append(
            f"- {r['market']}：{r['settled']} 結算｜ROI {_pct(r['roi'], signed=True)}"
            f"｜CLV {_pct(r['avg_clv'], signed=True)}｜{badge}"
        )

    # Decision hints
    lines += ["", "## ⚙️ 決策提示", ""]
    hints: list[str] = []
    if prop.get("settled", 0) >= _STAKE_CONFIDENCE_MIN_SETTLED and (prop.get("roi") or 0) > 0 \
            and sc.get("settled") and sc["model"]["brier"] < sc["market"]["brier"]:
        hints.append(
            f"✅ Prop value 已儲夠 {prop['settled']} 條結算、ROI 正、模型贏記分卡 —— 可以考慮由平注升做小注 Kelly。"
        )
    else:
        need = max(0, _STAKE_CONFIDENCE_MIN_SETTLED - prop.get("settled", 0))
        hints.append(
            f"⏳ Prop 繼續平注驗證：距離「考慮加注」門檻仲差約 {need} 條結算"
            f"（同時要模型贏返記分卡）。"
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
