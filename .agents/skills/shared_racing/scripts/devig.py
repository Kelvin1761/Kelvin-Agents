"""De-vig（去水）：將莊家 decimal odds 轉做加埋等於 1（或 k）嘅機率。

純數學、零依賴（唔用 scipy），所以 racing 同 tennis 可以各自持有一份。
tennis 嗰份喺 ``tennis-wong-choi/src/tennis_wc/betting/devig.py`` —— 兩份
**刻意重複**：AU／HKJC／tennis 係獨立 package，唔互相 import（AGENTS.md）。
改一邊要記得改埋另一邊。

呢個 module 係基建（plan item X0）。唯一 caller：AU 顯示層
``au_racing_engine/market_reference.py``（D1，2026-10-14 —— 純顯示，唔入評分；
按 X1 結果用 power 計勝率、odds_ratio 計位率）。將其他 proportional caller 換成
其他方法係另一個要量度嘅改動，唔可以順手做。

方法
----
``implied``  π_i = 1 / o_i，``overround`` Π = Σπ_i。

* ``proportional``  p_i = T·π_i / Π（multiplicative；假設水平均分佈）。
* ``additive``      p_i = π_i − (Π − T)/n（每個 outcome 扣同一個絕對值）。
* ``power``         p_i = π_i^k，解 Σπ_i^k = T。回傳 ``param = k``。
* ``shin``          Shin (1993) / Jullien–Salanié：
                    p_i = [√(z² + 4(1−z)π_i²/Π) − z] / (2(1−z))，解 Σp_i = 1。
                    回傳 ``param = z``（insider share）。只支援 T = 1。
* ``odds_ratio``    Cheung (2015)：p_i = π_i / (c + π_i − c·π_i)，解 Σp_i = T。
                    回傳 ``param = c``。

``target_sum``（T）
    win market T = 1；place market 有 k 個位就 T = k（例如 8+ 匹 3 個位 → 3）。
    除 Shin 外全部方法都支援；T 必須喺 (0, n) 之內。

邊界處理（全部明確，冇靜靜 fallback）
------------------------------------
* **無效 odds**（None、NaN、inf、非數字、≤ 1.0）：預設 raise
  ``InvalidOddsError``。如果 caller 想剔走佢哋（例如退出馬），用
  ``devig(..., on_invalid="exclude")``：無效位置回傳 ``None``，其餘 outcome
  以 **剔走後** 嘅 overround 去水 —— 即係話剔走一匹馬會改變其他馬嘅機率，
  呢個係 caller 要知嘅語義，唔係 bug。
* **n < 2**（剔走後都計）：raise ``InvalidOddsError``。n = 2 全部方法都得。
* **overround < T（套利 / underround）**：預設 raise ``UnderroundError``。
  ``allow_underround=True`` 時 proportional／additive／power／odds_ratio 照計
  （power 嘅 k < 1、additive 會加返、odds_ratio 嘅 c < 1）；Shin 喺 underround
  冇定義（z 會係負數），一律 raise。overround == T 時全部方法回傳 π 本身
  （Shin z = 0、power k = 1、odds_ratio c = 1）。
* **additive 出負數**（長途冷門 + 高水好常見）：將負數嗰啲 outcome 設 0，
  margin 重新分畀其餘 outcome，重複到冇負數。``clipped`` 記低幾多個被設 0。
* **proportional／additive 出 > 1**（place market 嘅大熱）：設 1，多出嚟嘅
  重新分畀其餘 outcome。``clipped`` 一樣會計埋。power 同 odds_ratio 結構上
  保證喺 (0, 1)，唔使 clip。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = [
    "METHODS",
    "DevigResult",
    "InvalidOddsError",
    "UnderroundError",
    "additive",
    "devig",
    "implied_probabilities",
    "odds_ratio",
    "power",
    "proportional",
    "shin",
]

METHODS = ("proportional", "additive", "power", "shin", "odds_ratio")

_TOL = 1e-12
_MAX_ITER = 500


class InvalidOddsError(ValueError):
    """odds 唔係 > 1.0 嘅有限數字，或者有效 outcome 少過 2 個。"""


class UnderroundError(ValueError):
    """Σ(1/o) < target_sum —— 套利盤；預設唔去水。"""


@dataclass(frozen=True)
class DevigResult:
    method: str
    probabilities: tuple[float | None, ...]
    overround: float
    target_sum: float
    param: float | None = None
    param_name: str | None = None
    clipped: int = 0
    excluded: tuple[int, ...] = field(default_factory=tuple)

    @property
    def fair_odds(self) -> tuple[float | None, ...]:
        return tuple(
            None if p is None else (math.inf if p == 0 else 1.0 / p)
            for p in self.probabilities
        )


# --------------------------------------------------------------------- inputs

def _is_valid(o: object) -> bool:
    if o is None or isinstance(o, bool):
        return False
    try:
        x = float(o)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x > 1.0


def implied_probabilities(odds: Iterable[object]) -> list[float]:
    """1/o，任何一個無效就 raise ``InvalidOddsError``。"""
    values = list(odds)
    out: list[float] = []
    for i, o in enumerate(values):
        if not _is_valid(o):
            raise InvalidOddsError(f"odds[{i}]={o!r} 唔係 > 1.0 嘅有限數字")
        out.append(1.0 / float(o))  # type: ignore[arg-type]
    if len(out) < 2:
        raise InvalidOddsError(f"去水最少要 2 個 outcome，得 {len(out)} 個")
    return out


def _check_target(target_sum: float, n: int) -> float:
    t = float(target_sum)
    if not (math.isfinite(t) and 0.0 < t < n):
        raise ValueError(f"target_sum={target_sum!r} 要喺 (0, {n}) 之內")
    return t


def _check_overround(total: float, target: float, allow_underround: bool) -> None:
    if total < target - 1e-12 and not allow_underround:
        raise UnderroundError(
            f"overround Σ(1/o)={total:.6f} < target_sum={target:g}（套利盤）；"
            "要計就傳 allow_underround=True"
        )


def _bisect(fn, lo: float, hi: float) -> float:
    """fn 單調、fn(lo) 同 fn(hi) 異號。"""
    f_lo = fn(lo)
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        f_mid = fn(mid)
        if f_mid == 0.0 or (hi - lo) < _TOL * max(1.0, abs(mid)):
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _redistribute(raw: list[float], target: float) -> tuple[list[float], int]:
    """將 < 0 設 0、> 1 設 1，差額按「每個 outcome 同一個絕對值」分返畀其餘。

    additive 用；proportional 用 ``_rescale_capped``（按比例分返）。
    """
    probs = list(raw)
    fixed: dict[int, float] = {}
    for _ in range(len(probs) + 1):
        free = [i for i in range(len(probs)) if i not in fixed]
        bad = [i for i in free if probs[i] < 0.0 or probs[i] > 1.0]
        if not bad:
            break
        for i in bad:
            fixed[i] = 0.0 if probs[i] < 0.0 else 1.0
            probs[i] = fixed[i]
        free = [i for i in range(len(probs)) if i not in fixed]
        if not free:
            break
        gap = (target - sum(probs)) / len(free)
        for i in free:
            probs[i] += gap
    return probs, len(fixed)


def _rescale_capped(pi: list[float], target: float) -> tuple[list[float], int]:
    probs = [target * x / sum(pi) for x in pi]
    capped: set[int] = set()
    for _ in range(len(pi) + 1):
        over = [i for i, p in enumerate(probs) if p > 1.0 and i not in capped]
        if not over:
            break
        capped.update(over)
        free = [i for i in range(len(pi)) if i not in capped]
        remaining = target - len(capped)
        scale = remaining / sum(pi[i] for i in free)
        probs = [1.0 if i in capped else pi[i] * scale for i in range(len(pi))]
    return probs, len(capped)


# -------------------------------------------------------------------- methods

def proportional(odds: Sequence[object], *, target_sum: float = 1.0,
                 allow_underround: bool = False) -> DevigResult:
    pi = implied_probabilities(odds)
    t = _check_target(target_sum, len(pi))
    total = sum(pi)
    _check_overround(total, t, allow_underround)
    probs, clipped = _rescale_capped(pi, t)
    return DevigResult("proportional", tuple(probs), total, t, clipped=clipped)


def additive(odds: Sequence[object], *, target_sum: float = 1.0,
             allow_underround: bool = False) -> DevigResult:
    pi = implied_probabilities(odds)
    t = _check_target(target_sum, len(pi))
    total = sum(pi)
    _check_overround(total, t, allow_underround)
    margin = (total - t) / len(pi)
    probs, clipped = _redistribute([x - margin for x in pi], t)
    return DevigResult("additive", tuple(probs), total, t, clipped=clipped)


def power(odds: Sequence[object], *, target_sum: float = 1.0,
          allow_underround: bool = False) -> DevigResult:
    pi = implied_probabilities(odds)
    t = _check_target(target_sum, len(pi))
    total = sum(pi)
    _check_overround(total, t, allow_underround)

    def excess(k: float) -> float:
        return sum(x ** k for x in pi) - t  # 喺 k 上嚴格遞減

    if abs(total - t) <= 1e-15:
        k = 1.0
    else:
        lo, hi = 1e-6, 1.0
        while excess(hi) > 0:
            lo, hi = hi, hi * 2.0
            if hi > 1e6:
                raise ValueError("power：搵唔到 k（odds 太極端）")
        k = _bisect(excess, lo, hi)
    probs = [x ** k for x in pi]
    return DevigResult("power", tuple(probs), total, t, param=k, param_name="k")


def _shin_probs(pi: list[float], total: float, z: float) -> list[float]:
    if z == 0.0:
        return [x / math.sqrt(total) for x in pi]
    return [
        (math.sqrt(z * z + 4.0 * (1.0 - z) * x * x / total) - z) / (2.0 * (1.0 - z))
        for x in pi
    ]


def shin(odds: Sequence[object], *, target_sum: float = 1.0,
         allow_underround: bool = False) -> DevigResult:
    """Shin z 用 bisection 解 Σp(z) = 1。

    Σp(0) = √Π > 1、z→1 時 Σp → Σπ²/Π < 1，所以 Π > 1 時 (0, 1) 內必有根。
    數值上同 mberk/shin 嘅不動點迭代、同 n = 2 嘅解析解一致（見 tests）。
    """
    if float(target_sum) != 1.0:
        raise ValueError("shin 只係 win market 模型（target_sum 必須係 1）")
    pi = implied_probabilities(odds)
    total = sum(pi)
    if total < 1.0 - 1e-12:
        raise UnderroundError(
            f"shin 喺 underround（Σ(1/o)={total:.6f} < 1）冇定義"
            + ("；allow_underround 唔適用於 shin" if allow_underround else "")
        )
    if total <= 1.0 + 1e-15:
        z = 0.0
    else:
        z = _bisect(lambda zz: sum(_shin_probs(pi, total, zz)) - 1.0, 0.0, 1.0 - 1e-12)
    probs = _shin_probs(pi, total, z)
    s = sum(probs)  # 只係清走 bisection 尾數
    probs = [p / s for p in probs]
    return DevigResult("shin", tuple(probs), total, 1.0, param=z, param_name="z")


def odds_ratio(odds: Sequence[object], *, target_sum: float = 1.0,
               allow_underround: bool = False) -> DevigResult:
    pi = implied_probabilities(odds)
    t = _check_target(target_sum, len(pi))
    total = sum(pi)
    _check_overround(total, t, allow_underround)

    def excess(c: float) -> float:  # 喺 c 上嚴格遞減
        return sum(x / (c + x - c * x) for x in pi) - t

    if abs(total - t) <= 1e-15:
        c = 1.0
    else:
        lo, hi = 1.0, 1.0
        while excess(hi) > 0:
            hi *= 2.0
            if hi > 1e12:
                raise ValueError("odds_ratio：搵唔到 c")
        while excess(lo) < 0:
            lo /= 2.0
            if lo < 1e-12:
                raise ValueError("odds_ratio：搵唔到 c")
        c = _bisect(excess, lo, hi)
    probs = [x / (c + x - c * x) for x in pi]
    return DevigResult("odds_ratio", tuple(probs), total, t, param=c, param_name="c")


_DISPATCH = {
    "proportional": proportional,
    "additive": additive,
    "power": power,
    "shin": shin,
    "odds_ratio": odds_ratio,
}


def devig(odds: Sequence[object], method: str = "proportional", *,
          target_sum: float = 1.0, allow_underround: bool = False,
          on_invalid: str = "raise") -> DevigResult:
    """統一入口。``on_invalid``：``"raise"``（預設）或 ``"exclude"``。"""
    if method not in _DISPATCH:
        raise ValueError(f"method={method!r} 唔支援；可選 {METHODS}")
    if on_invalid not in ("raise", "exclude"):
        raise ValueError(f"on_invalid={on_invalid!r} 只可以係 'raise' 或 'exclude'")
    values = list(odds)
    fn = _DISPATCH[method]
    if on_invalid == "raise":
        return fn(values, target_sum=target_sum, allow_underround=allow_underround)

    keep = [i for i, o in enumerate(values) if _is_valid(o)]
    excluded = tuple(i for i in range(len(values)) if i not in set(keep))
    inner = fn([values[i] for i in keep], target_sum=target_sum,
               allow_underround=allow_underround)
    full: list[float | None] = [None] * len(values)
    for j, i in enumerate(keep):
        full[i] = inner.probabilities[j]
    return DevigResult(inner.method, tuple(full), inner.overround, inner.target_sum,
                       param=inner.param, param_name=inner.param_name,
                       clipped=inner.clipped, excluded=excluded)
