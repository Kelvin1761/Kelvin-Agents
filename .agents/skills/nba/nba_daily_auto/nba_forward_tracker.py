"""NBA forward-test tracker：進行中嘅 forward 測試一張表，夠數即刻 Telegram 一次。

AGENTS.md「Forward 測試一律登記入追蹤表」：每個 forward／shadow 測試第一次夠數就要推 Telegram。
NBA 嘅舊 `nba_experiment_readiness.py` 隨 EXP-20261103-16 刪咗，呢個係替代品。

規矩：每個測試嘅評估規則喺開測試前已經凍結（協議 + 凍結腳本）。夠數之後呢度會自動跑**一次**
凍結腳本、將結果寫入 reports/ 並推 Telegram；**永遠唔會改模型或者落注規則** —— 上唔上線係
Kelvin 決定。
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ForwardTest:
    key: str
    label: str
    experiment: str
    script: str          # repo-relative frozen evaluation script
    test: str            # test name inside that script
    action: str          # 夠數之後要做乜


FORWARD_TESTS: tuple[ForwardTest, ...] = (
    ForwardTest("minutes_risk", "上場時間風險（大比數／上場時間波動／傷患標籤／背靠背）有冇令 p_final 高估",
                "EXP-20261109-04 M", "docs/experiments/patches/nba_forward_mt/evaluate.py", "M",
                "結果已凍結；pass 只證明模型高估呢類腿，改揀腿規則要另外預先登記同過 model-regression-gate"),
    ForwardTest("late_receivers", "21:00 後主力臨場缺陣，接手出手／助攻嘅隊友係咪被低估",
                "EXP-20261109-04 T", "docs/experiments/patches/nba_forward_mt/evaluate.py", "T",
                "結果已凍結；pass 都只係研究訊號，唔會自動落注；點估 ≥+5pp 但 CI 跨零就按協議延長一次"),
    ForwardTest("featured_250", "大細盤精選紙上盤：中期檢查（250 注）",
                "EXP-20261110-01 F250", "docs/experiments/patches/nba_featured/evaluate.py", "F250",
                "中期唔會判 PASS；STOP（CI 上限 < 0）就建議停 card，否則繼續到 1,000 注"),
    ForwardTest("featured_1000", "大細盤精選紙上盤：終判（1,000 注）",
                "EXP-20261110-01 F1000", "docs/experiments/patches/nba_featured/evaluate.py", "F1000",
                "PASS（ROI CI 下限 > 0）先考慮落真錢，細注開始、由你決定；未過就停或者重新設計"),
    ForwardTest("under_avg", "大細盤 under：線高過近 10 場平均 5% 以上（紙上，1,200 注）",
                "EXP-20261110-03 FU_AVG", "docs/experiments/patches/nba_under/evaluate.py", "FU_AVG",
                "PASS（97.5% CI 下限 > 0）先考慮加入精選揀注規則（要新 RULE 同新協議）；未過就記低、唔再用呢批數據重試"),
    ForwardTest("under_edge", "大細盤 under：模型同去水價分歧 ≥8pp（紙上，300 注）",
                "EXP-20261110-03 FU_EDGE", "docs/experiments/patches/nba_under/evaluate.py", "FU_EDGE",
                "PASS（97.5% CI 下限 > 0）先考慮將精選門檻由 5pp 改 8pp（要新 RULE）；未過就記低"),
    ForwardTest("pick_penalty", "穩膽揀中嘅腿，命中率係咪低過模型自己估嘅（對照：合資格但冇揀嘅腿）",
                "EXP-20261111-01 P", "docs/experiments/patches/nba_pick_penalty/evaluate.py", "P",
                "PASS = 揀腿規則本身拖低命中，下一步係預先登記一個新揀腿規則再比；未過 = 冇證據，穩膽規則唔郁"),
    ForwardTest("s2_blend", "自己模型佔更大份額：市場＋S2（新上場時間預測）對現行發佈機率",
                "EXP-20261111-05 S2", "docs/experiments/patches/nba_s2_forward/evaluate.py", "S2",
                "PASS（log-loss 差 95% CI 上限 < 0）先可以申請將發佈機率換做 MS2，要過 model-regression-gate；未過就維持現行"),
)


def _load(script: str):
    path = REPO / script
    spec = importlib.util.spec_from_file_location(f"nba_forward_{path.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _verdict(result: dict) -> str:
    if result.get("status") == "not_ready":
        return "未夠數"
    if result.get("test") == "F250":
        return "⛔ STOP（明顯蝕緊）" if result.get("stop") else "➡️ 繼續（中期唔判 PASS）"
    return "✅ PASS（訊號成立）" if result.get("pass") else "❌ 未過（冇證據）"


def _numbers(test: ForwardTest, result: dict) -> str:
    ci = result.get("ci95") or [None, None]
    fmt = lambda v: "N/A" if v is None else f"{v * 100:+.1f}pp"  # noqa: E731
    if test.test.startswith("F"):
        pct = lambda v: "N/A" if v is None else f"{v * 100:+.1f}%"  # noqa: E731
        hit = result.get("hit_rate")
        return (f"{result.get('n_bets')} 注、{result.get('days')} 日；命中 {'N/A' if hit is None else f'{hit * 100:.1f}%'}；"
                f"平注 ROI {pct(result.get('roi'))} [{pct(ci[0])}, {pct(ci[1])}]")
    if test.test == "S2":
        loss = result.get("logloss") or {}
        num = lambda v: "N/A" if v is None else f"{v:+.4f}"  # noqa: E731
        return (f"{result.get('n_legs')} 腿、{result.get('days')} 日；log-loss 發佈 {loss.get('pub', float('nan')):.4f}、"
                f"MS2 {loss.get('ms2', float('nan')):.4f}；差 {num(result.get('primary_delta'))} [{num(ci[0])}, {num(ci[1])}]；"
                f"其中換新時間預測佔 {num((result.get('ms2_vs_msr') or {}).get('delta'))}")
    if test.test == "P":
        picked, control = result.get("picked") or {}, result.get("control") or {}
        rate = lambda side, key: "N/A" if side.get(key) is None else f"{side[key] * 100:.1f}%"  # noqa: E731
        return (f"揀中 {result.get('n_flagged')} 腿（中 {rate(picked, 'hit_rate')}、模型 {rate(picked, 'model')}、差一 {rate(picked, 'near_miss_rate')}）；"
                f"對照 {control.get('n')} 腿（中 {rate(control, 'hit_rate')}、模型 {rate(control, 'model')}）；"
                f"殘差差距 {fmt(result.get('primary_delta_resid'))} [{fmt(ci[0])}, {fmt(ci[1])}]")
    if test.test == "M":
        return (f"有旗標 {result.get('n_flagged')}／{result.get('n_legs')} 腿；"
                f"（實際−模型）差 {fmt(result.get('primary_delta_resid'))} [{fmt(ci[0])}, {fmt(ci[1])}]")
    roi = result.get("event_roi")
    return (f"{result.get('events')} 宗缺陣、{result.get('event_legs')} 腿；"
            f"校準差 {fmt(result.get('primary_delta_cal'))} [{fmt(ci[0])}, {fmt(ci[1])}]；"
            f"單注 ROI {'N/A' if roi is None else f'{roi * 100:+.1f}%'}")


def check(*, ledger: Path, analysis: Path, reports: Path,
          notify: Callable[[str, str], object],
          tests: tuple[ForwardTest, ...] = FORWARD_TESTS,
          loader: Callable = _load) -> dict:
    """→ {key: progress}。夠數就凍結評估一次並 notify（notify_once 保證唔會重覆推）。"""
    report: dict = {}
    for test in tests:
        try:
            module = loader(test.script)
            progress = module.status(ledger, analysis)[test.test]
        except Exception as exc:  # noqa: BLE001 — a tracker failure must never block postgame
            report[test.key] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        report[test.key] = progress
        if not progress.get("ready"):
            continue
        result = module.evaluate(ledger, analysis, reports, only=test.test)[test.test]
        notify(f"forward-ready:{test.key}",
               f"🧪 NBA forward 測試夠數：{test.label}（{test.experiment}）\n"
               f"判決：{_verdict(result)}\n{_numbers(test, result)}\n"
               f"下一步：{test.action}\n（live 唔會自動改，上唔上線係你決定）")
    return report


def summary_line(report: dict) -> str:
    parts = []
    for test in FORWARD_TESTS:
        item = report.get(test.key) or {}
        if item.get("error"):
            parts.append(f"{test.experiment} ⚠️")
        elif test.test.startswith("F"):
            parts.append(f"{test.experiment} {item.get('bets')}/{item['checkpoint']['bets']} 注"
                         + (" ✅" if item.get("ready") else ""))
        elif test.test in ("M", "P", "S2"):
            parts.append(f"{test.experiment} {item.get('days')}/{item['checkpoint']['days']} 日、"
                         f"{item.get('flagged_legs')}/{item['checkpoint']['flagged_legs']} 腿"
                         + (" ✅" if item.get("ready") else ""))
        else:
            parts.append(f"{test.experiment} {item.get('events')}/{item['checkpoint']['events']} 宗、"
                         f"{item.get('event_legs')}/{item['checkpoint']['event_legs']} 腿"
                         + (" ✅" if item.get("ready") else ""))
    return "；".join(parts)
