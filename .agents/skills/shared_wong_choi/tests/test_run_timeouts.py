"""Regression cover for the 2026-08-26 AU evening truncation.

三晚嘅 AU 晚更喺 7200 秒正中俾 adapter 殺死，八個場次淨係做到三個，而所有
signal 都話冇事：run log 停喺 `status: running`、九個 suite 全綠、dashboard
驗證 0 problems、Cloudflare 發佈成功。捉到佢嘅唯一嘢係人手數場次。

呢批測試釘死三件事：
  1. timeout 跟 domain／mode 走，唔係一個全域常數；
  2. AU 晚更嗰個數字大到覆蓋佢設計上嘅通宵窗口；
  3. 俾 timeout 斬死嘅時候，個狀態要叫得出自己個名，唔好扮成一般 exception。
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.au_adapter import AUAdapter  # noqa: E402
from shared_wong_choi.contracts import (  # noqa: E402
    DEFAULT_RUN_TIMEOUT_SECONDS,
    AdapterSpec,
    CapabilityReadiness,
    Domain,
    Operation,
    OperationBinding,
    RunIdentity,
    RunRequest,
    RunState,
)
from shared_wong_choi.registry import adapter_spec  # noqa: E402


def _request(mode: str) -> RunRequest:
    slot = "22:00" if mode == "evening" else "10:00"
    return RunRequest(
        identity=RunIdentity(Domain.AU, mode, date(2026, 8, 29), slot),
        operation=Operation.PREDICT,
    )


def _spec(**overrides) -> AdapterSpec:
    base = dict(
        domain=Domain.AU,
        display_name="probe",
        owner="probe",
        orchestrator="probe.py",
        bindings=(
            OperationBinding(
                Operation.PREDICT,
                "probe.py",
                ("evening", "morning"),
                CapabilityReadiness.IMPLEMENTED,
                "",
            ),
        ),
    )
    base.update(overrides)
    return AdapterSpec(**base)


# ── 1. lookup 語義 ──────────────────────────────────────────────────────────

def test_declared_mode_wins_and_undeclared_mode_falls_back() -> None:
    spec = _spec(run_timeouts=(("evening", 39600),))
    assert spec.run_timeout_seconds("evening") == 39600
    assert spec.run_timeout_seconds("morning") == DEFAULT_RUN_TIMEOUT_SECONDS


def test_timeout_for_unknown_mode_is_rejected_at_construction() -> None:
    # 打錯 mode 名嘅 timeout 睇落已經修好咗，實際上個 run 仍然行緊 default ——
    # 即係同呢次事故一模一樣嘅失敗形狀。所以要即刻炸，唔好靜靜接受。
    with pytest.raises(ValueError, match="unknown mode"):
        _spec(run_timeouts=(("evenning", 39600),))


@pytest.mark.parametrize("bad", [0, -1])
def test_non_positive_timeout_is_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _spec(run_timeouts=(("evening", bad),))


# ── 2. AU 嘅實際數字 ────────────────────────────────────────────────────────

def test_au_evening_covers_its_overnight_window() -> None:
    """晚更 22:00 開工，設計上跑到早更 10:00。

    歷史最長一個**成功**晚更係 18,061 秒（2026-08-21，10 個場次）。任何細過
    佢嘅 timeout 都係喺穩定咁切走字母排後面嗰批場次 —— Rosehill 排第七。
    """
    spec = adapter_spec(Domain.AU)
    assert spec.run_timeout_seconds("evening") >= 11 * 3600
    assert spec.run_timeout_seconds("evening") > 18_061


def test_au_morning_covers_a_full_catch_up() -> None:
    """早更係晚更執唔晒之後唯一會再出網補抽嘅地方。

    一個大禮拜六追五個場次 ≈ 5 × 26 分鐘 ＋ 冷卻窗。
    """
    assert adapter_spec(Domain.AU).run_timeout_seconds("morning") >= 5 * 26 * 60


def test_every_declared_timeout_beats_the_shared_default() -> None:
    # 一個「明文寫低但其實仲短過 default」嘅 timeout 係純粹嘅負收益。
    for domain in Domain:
        spec = adapter_spec(domain)
        for mode, seconds in spec.run_timeouts:
            if mode == "healthcheck":
                continue  # 體檢本身就係要快，短係啱嘅。
            assert seconds >= spec.default_run_timeout_seconds, (domain, mode)


# ── 3. adapter 真係用到、而且死得夠大聲 ─────────────────────────────────────

def test_adapter_passes_the_per_mode_timeout_to_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout='{"status": "ok"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    AUAdapter(REPO_ROOT, tmp_path).execute(_request("evening"))
    assert seen["timeout"] == adapter_spec(Domain.AU).run_timeout_seconds("evening")


def test_morning_and_evening_do_not_share_one_timeout(tmp_path: Path) -> None:
    adapter = AUAdapter(REPO_ROOT, tmp_path)
    assert adapter.run_timeout_seconds(_request("evening")) != adapter.run_timeout_seconds(
        _request("morning")
    )


def test_timeout_is_recorded_as_adapter_timeout_not_a_bare_exception(
    tmp_path: Path,
) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 7200)

    result = AUAdapter(REPO_ROOT, tmp_path, runner=runner).execute(_request("evening"))

    assert result.state is RunState.FAILED
    # `adapter_exception:TimeoutExpired` 睇落似個網絡問題；呢個名叫得出係我哋
    # 自己斬佢，而 detail 要講埋斬喺邊個秒數，唔使再翻 log 反推。
    assert result.status == "adapter_timeout"
    assert result.detail["timeout_seconds"] == adapter_spec(Domain.AU).run_timeout_seconds(
        "evening"
    )
    assert "run_timeouts" in result.detail["hint"]
