"""市場參考層 —— **純顯示，永遠唔入評分**（Decision D1，Kelvin 2026-10-14）。

點解有呢層
----------
R1 / EXP-20261014 Benter combiner：模型對最早賽前市場**冇增量資訊**
（α −0.112，CI 上限 +0.011）。所以市場價唔混入排名；但讀者想睇「市場點睇」，
就要一個**分開、標明**嘅顯示層。呢個 module 就係嗰層。

紅線（同 `AGENTS.md`「賠率／市場價唔准做隱藏 proxy」一致）
---------------------------------------------------------------
* 只由 `renderer.py` 叫；`engine_core` / `scoring` / `matrix_mapper` 唔准
  import 呢度（`test_market_reference.py` 有 AST 守衛）。
* 只讀、唔寫：唔改 `python_auto`、唔改 `_data`、唔入 `Race_X_Auto_Scoring.csv`。
* 去水一律經共用 `shared_racing/scripts/devig.py`，唔准喺顯示層自己寫 1/odds。

方法（全部係量出嚟揀嘅，唔係順手）
---------------------------------
* 勝率：``power`` 去水。X1：AU 贏盤 power 最好（Δlogloss −0.0075，CI 唔包 0）；
  proportional 低估 <$2.0 大熱 11.4pp。
* 位盤：``odds_ratio`` 去水，target = 派彩位數（8+ 匹 3 位、5–7 匹 2 位）。
  X1：power 喺位盤過度修正。
* 推算前三／前四：discounted Harville，用 power 勝率，λ2 0.754、λ3 0.649、
  λ4 0.549（EXP-20261014-16 起步馬擬合）。係**市場推算**，唔係模型。
* 用**最早**一個賽前快照（`odds_history.json` 最早時間標籤）—— 早更重建會用
  當朝價覆寫 Formguide，所以 `_data.win_odds` 只係冇歷史檔時嘅後備。
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

_DEVIG_REL = Path("shared_racing") / "scripts" / "devig.py"
_DEVIG_MODULE = "_wc_shared_racing_devig"


def _devig_path() -> Path:
    """repo 入面嗰份共用 devig.py。

    正常係 `<skills>/shared_racing/scripts/devig.py`（相對呢個檔）。引擎 package
    有時會被成個抄去 tmp 做隔離測試，所以再由 cwd 向上搵 `.agents/skills/`。
    搵唔到就炸 —— 唔可以靜靜咁退返自己寫 1/odds。
    """
    here = Path(__file__).resolve()
    candidates = [here.parents[4] / _DEVIG_REL] if len(here.parents) > 4 else []
    for base in (Path.cwd().resolve(), *Path.cwd().resolve().parents):
        candidates.append(base / ".agents" / "skills" / _DEVIG_REL)
    for path in candidates:
        if path.is_file():
            return path
    raise ImportError(f"搵唔到共用去水 module（{_DEVIG_REL}）；試過：{candidates[:2]}")


def _load_devig():
    # 用檔案路徑載入，唔郁 sys.path（AGENTS.md 第 3 條：唔好將目錄插上 sys.path
    # 令 module 撞名）。dataclass 要求 module 已經喺 sys.modules。
    if _DEVIG_MODULE in sys.modules:
        return sys.modules[_DEVIG_MODULE]
    spec = importlib.util.spec_from_file_location(_DEVIG_MODULE, _devig_path())
    if spec is None or spec.loader is None:  # pragma: no cover - 路徑錯就要炸
        raise ImportError("共用去水 module 載入唔到")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_DEVIG_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_DEVIG_MODULE, None)
        raise
    return module


class _LazyDevig:
    """第一次用先載入（冇賠率嘅場次唔使碰 shared_racing）。"""

    def __getattr__(self, name):
        return getattr(_load_devig(), name)


devig = _LazyDevig()

WIN_METHOD = "power"
PLACE_METHOD = "odds_ratio"
# EXP-20261014-16：discounted Harville 起步馬擬合（第 2、3、4 名嘅折扣指數）。
HARVILLE_LAMBDAS = (0.754, 0.649, 0.549)
ODDS_HISTORY = "odds_history.json"


def places_paid(field_size: int) -> int:
    """AU 固定位盤派彩位數：8+ 匹 3 位、5–7 匹 2 位、≤4 匹冇位盤。"""
    if field_size >= 8:
        return 3
    if field_size >= 5:
        return 2
    return 0


def _valid_odds(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and 1.0 < x < 1000.0 else None


def earliest_snapshot(meeting_dir: Path | None, race_number) -> tuple[str, dict] | None:
    """`odds_history.json` 最早嘅 `{馬號: [贏, 位]}`，連時間標籤。

    同 `au_daily_schedule.earliest_odds` 同一個定義（sorted 第一個 key）。
    """
    if meeting_dir is None or race_number in (None, ""):
        return None
    try:
        hist = json.loads((Path(meeting_dir) / ODDS_HISTORY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    snaps = hist.get(str(race_number)) if isinstance(hist, dict) else None
    if not isinstance(snaps, dict) or not snaps:
        return None
    stamp = sorted(snaps)[0]
    prices = snaps[stamp]
    return (stamp, prices) if isinstance(prices, dict) and prices else None


def _stamp_label(stamp: str) -> str:
    when = str(stamp).partition("|")[0]
    # "2026-10-14T00:43:38" → "10-14 00:43"
    if len(when) >= 16 and when[4] == "-" and "T" in when:
        return f"{when[5:10]} {when[11:16]}"
    return when or "?"


def harville_top_k(probs: list[float], lambdas=HARVILLE_LAMBDAS) -> tuple[list[float], list[float]]:
    """Discounted Harville：回傳每匹 (P(前三), P(前四))。

    第 m 名（m ≥ 2）嘅條件機率 = p_j^λ / Σ_{未出} p^λ。逐個序列列舉，n ≤ 24
    最多 ~1.2 萬個三元組，每個再掃一次 n —— 一場唔使 0.2 秒。
    """
    n = len(probs)
    w2 = [p ** lambdas[0] for p in probs]
    w3 = [p ** lambdas[1] for p in probs]
    w4 = [p ** lambdas[2] for p in probs]
    tot2, tot3, tot4 = sum(w2), sum(w3), sum(w4)
    pos = [[0.0] * n for _ in range(4)]
    for i in range(n):
        p1 = probs[i]
        if p1 <= 0:
            continue
        pos[0][i] += p1
        d2 = tot2 - w2[i]
        if d2 <= 0:
            continue
        for j in range(n):
            if j == i:
                continue
            p12 = p1 * w2[j] / d2
            pos[1][j] += p12
            d3 = tot3 - w3[i] - w3[j]
            if d3 <= 0:
                continue
            for k in range(n):
                if k == i or k == j:
                    continue
                p123 = p12 * w3[k] / d3
                pos[2][k] += p123
                d4 = tot4 - w4[i] - w4[j] - w4[k]
                if d4 <= 0:
                    continue
                scale = p123 / d4
                for m in range(n):
                    if m != i and m != j and m != k:
                        pos[3][m] += scale * w4[m]
    top3 = [min(1.0, pos[0][x] + pos[1][x] + pos[2][x]) for x in range(n)]
    top4 = [min(1.0, top3[x] + pos[3][x]) for x in range(n)]
    return top3, top4


def build_market_reference(horses: dict, meeting_dir: Path | None = None,
                           race_number=None) -> dict:
    """計一場嘅市場參考。**唔改 `horses`**。

    回傳 ``{"source": str, "field": int, "priced": int, "places": int,
    "note": str|None, "runners": {馬號: {...}}}``；計唔到就 ``runners`` 係空、
    ``note`` 寫原因（唔靜靜咁消失）。
    """
    field = [str(num) for num, h in horses.items() if isinstance(h, dict)]
    snap = earliest_snapshot(meeting_dir, race_number)
    # `book` = 嗰個時間點個市場**成個**盤（包括之後退出嘅馬）。去水一定要喺成個
    # 盤上做：退出馬嘅 1/o 一剷走，剩低嘅 Σ(1/o) 會跌穿 1，假扮成套利盤
    # （2026-10-14 Rosehill R3／R8 實測 0.946／0.982）。
    book: dict[str, tuple[float | None, float | None]] = {}
    if snap:
        stamp, prices = snap
        source = f"最早賽前盤 {_stamp_label(stamp)}"
        for num, entry in prices.items():
            if isinstance(entry, (list, tuple)) and entry:
                book[str(num)] = (_valid_odds(entry[0]),
                                  _valid_odds(entry[1]) if len(entry) > 1 else None)
    else:
        source = "分析時盤"
        for num in field:
            data = horses[num].get("_data") if isinstance(horses[num].get("_data"), dict) else {}
            book[num] = (_valid_odds(data.get("win_odds")), _valid_odds(data.get("place_odds")))

    out = {"source": source, "field": len(field), "priced": 0, "places": 0,
           "note": None, "runners": {}}
    book_priced = [num for num, (w, _) in book.items() if w is not None]
    priced = [num for num in field if num in book_priced]
    out["priced"] = len(priced)
    if len(priced) < 2:
        # 完全冇價（例如未開盤）就乜都唔出 —— 同 💰 市場盤嗰行一樣；有價但唔夠先講原因。
        if priced:
            out["note"] = "有贏盤價嘅馬少過 2 匹，計唔到"
        return out
    try:
        win = devig.devig([book[num][0] for num in book_priced], WIN_METHOD)
    except ValueError as exc:  # UnderroundError / InvalidOddsError 都係 ValueError
        out["note"] = f"贏盤去水失敗：{exc}"
        return out
    book_p = dict(zip(book_priced, (float(p) for p in win.probabilities)))
    # 退出馬：條件於今日出賽名單，按比例歸一（Harville 下移除一匹馬嘅正確做法）。
    remaining = sum(book_p[num] for num in priced)
    win_p = [book_p[num] / remaining for num in priced]
    order = sorted(range(len(priced)), key=lambda i: -win_p[i])
    rank: dict[int, int] = {}
    for pos_i, idx in enumerate(order):
        prev = order[pos_i - 1] if pos_i else None
        rank[idx] = rank[prev] if prev is not None and abs(win_p[prev] - win_p[idx]) < 1e-12 else pos_i + 1
    top3, top4 = harville_top_k(win_p)

    # 位盤：只喺個盤同今日名單一致先計 —— 退出馬會改派彩位數同其他馬嘅位率，
    # 冇乾淨嘅條件化方法，寧願唔出都唔出錯數。
    places = places_paid(len(field))
    place_p: dict[str, float] = {}
    same_field = set(book_priced) == set(priced)
    if (places and same_field and len(priced) > places
            and all(book[num][1] is not None for num in priced)):
        try:
            pl = devig.devig([book[num][1] for num in priced], PLACE_METHOD, target_sum=places)
            place_p = {num: float(p) for num, p in zip(priced, pl.probabilities)}
        except ValueError:
            place_p = {}
    out["places"] = places if place_p else 0

    for i, num in enumerate(priced):
        out["runners"][num] = {
            "win_odds": book[num][0],
            "win_prob": win_p[i],
            "market_rank": rank[i],
            "place_prob": place_p.get(num),
            "top3_prob": top3[i],
            "top4_prob": top4[i],
        }
    notes = []
    scratched = [num for num in book_priced if num not in priced]
    if scratched:
        notes.append(f"盤內 {len(scratched)} 匹已退出：勝率按今日名單重新歸一，位率唔計")
    if len(priced) < len(field):
        notes.append(f"{len(field) - len(priced)} 匹冇贏盤價，未計入")
    out["note"] = "；".join(notes) or None
    return out


def horse_line(ref: dict, horse_num) -> str | None:
    """每匹馬一行；dashboard `parser_au` 靠呢個格式讀，改格式要改 parser。"""
    r = (ref or {}).get("runners", {}).get(str(horse_num))
    if not r:
        return None
    bits = [f"市場第 {r['market_rank']}/{ref['priced']}",
            f"勝 {r['win_prob'] * 100:.1f}%"]
    if r.get("place_prob") is not None and ref.get("places"):
        bits.append(f"位 {r['place_prob'] * 100:.1f}%（{ref['places']} 位）")
    bits.append(f"推算前三 {r['top3_prob'] * 100:.1f}%")
    bits.append(f"前四 {r['top4_prob'] * 100:.1f}%")
    return (f"📊 市場參考（{ref['source']} · 去水 · 非模型、唔入評分）: "
            + " · ".join(bits))


def method_note(ref: dict) -> str:
    """場次級一句方法說明（放喺第二部分開頭）。"""
    base = ("> 📊 **市場參考層**：純顯示，同模型分開、唔入任何評分或排名（D1）。"
            "勝率用 power 去水；位率用 odds-ratio 去水（按派彩位數）；"
            "推算前三／前四係由市場勝率經 discounted Harville（λ 0.754／0.649／0.549）推出，"
            "係市場推算，唔係模型預測。")
    if ref and ref.get("note"):
        base += f"（{ref['note']}）"
    return base
