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
    return "✅ PASS（訊號成立）" if result.get("pass") else "❌ 未過（冇證據）"


def _numbers(test: ForwardTest, result: dict) -> str:
    ci = result.get("ci95") or [None, None]
    fmt = lambda v: "N/A" if v is None else f"{v * 100:+.1f}pp"  # noqa: E731
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
        elif test.test == "M":
            parts.append(f"{test.experiment} {item.get('days')}/{item['checkpoint']['days']} 日、"
                         f"{item.get('flagged_legs')}/{item['checkpoint']['flagged_legs']} 腿"
                         + (" ✅" if item.get("ready") else ""))
        else:
            parts.append(f"{test.experiment} {item.get('events')}/{item['checkpoint']['events']} 宗、"
                         f"{item.get('event_legs')}/{item['checkpoint']['event_legs']} 腿"
                         + (" ✅" if item.get("ready") else ""))
    return "；".join(parts)
