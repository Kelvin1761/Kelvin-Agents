"""Plain-language reasons for one 精選 (featured) tennis pick (Kelvin 2026-11-11).

The card's old "來源紀錄" fold showed only an id and a timestamp. These sentences
explain why the model chose the bet, using only what was frozen when the pick
was priced: the prop row (model vs de-vigged market, projected margin/total),
the pricing evidence (both players' serve/return form, data quality) and the
latest match-winner prediction made no later than the pick. Nothing here is
recomputed, so the text cannot drift from the pick it describes.

Every helper returns ``[]``/``None`` on missing or malformed input; the export
must never fail because one explanation could not be written.
"""

from __future__ import annotations

import json
import re

_SPREAD_UNIT = {
    "player_game_handicap": ("全場", "局"),
    "player_first_set_game_handicap": ("首盤", "局"),
    "player_set_handicap": ("全場", "盤"),
}
_HANDICAP_IN_SELECTION = re.compile(r"\(([+-]?\d+(?:\.\d+)?)\)\s*$")


def _num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN -> None


def _pct(p: float) -> str:
    return f"{p * 100:.0f}%"


def _family(market_key: str) -> str | None:
    key = str(market_key or "")
    # Longest first: player_first_set_game_handicap before first_set_*.
    for name in sorted(
        (*_SPREAD_UNIT, "player_total_games", "player_win_a_set",
         "player_first_set_match", "first_set_winner"), key=len, reverse=True):
        if key == name or key.startswith(name + "_"):
            return name
    return None


def _evidence(prop: dict) -> dict:
    raw = prop.get("pricing_evidence_json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _selected_player(prop: dict, match: dict, family: str | None):
    """(selected_id, opponent_id); spreads pick A on the 'over' row, B on 'under'."""
    a, b = match.get("player_a_id"), match.get("player_b_id")
    if a is None or b is None:
        return None, None
    if family in _SPREAD_UNIT:
        sel = a if prop.get("side") == "over" else b if prop.get("side") == "under" else None
    else:
        sel = prop.get("subject_player_id")
    if sel not in (a, b):
        return None, None
    return sel, (b if sel == a else a)


def _price_reason(featured: dict) -> str | None:
    p, edge, odds = _num(featured.get("model_prob")), _num(featured.get("edge")), _num(featured.get("odds"))
    if p is None or edge is None or odds is None or odds <= 1:
        return None
    fair = p - edge
    text = (f"模型估呢注入嘅機會係 {_pct(p)}；Sportsbet 開 @{odds:.2f}，扣走莊家抽水之後，"
            f"市場只估 {_pct(fair)}。模型比市場高 {edge * 100:.1f} 個百分點，"
            "係呢場合資格盤口入面差距最大嗰注（每場最多揀一注）。")
    ev = _num(featured.get("ev"))
    if ev is not None and ev > 0:
        text += f"如果模型估得啱，長遠每落 $1 平均賺 {ev * 100:.0f} 仙。"
    return text


def _projection_reason(prop: dict, family: str | None, sel_name: str, opp_name: str,
                       selection: str) -> str | None:
    mean = _num(prop.get("predicted_mean"))
    if mean is None or family is None:
        return None
    if family in _SPREAD_UNIT:
        scope, unit = _SPREAD_UNIT[family]
        match = _HANDICAP_IN_SELECTION.search(str(selection or ""))
        handicap = _num(match.group(1)) if match else None
        if handicap is None:
            return None
        # predicted_mean is player A's margin; flip it when B is the pick.
        margin = mean if prop.get("side") == "over" else -mean
        lead = (f"模型預計 {sel_name} {scope}平均贏多 {margin:.1f} {unit}" if margin >= 0
                else f"模型預計 {sel_name} {scope}平均輸 {-margin:.1f} {unit}")
        if handicap < 0:
            need = f"呢注要佢{scope}贏多 {abs(handicap):g} {unit}以上先中。"
        else:
            need = f"呢注佢{scope}就算輸，輸少過 {handicap:g} {unit}都中。"
        return f"{lead}；{need}"
    if family == "player_win_a_set":
        return f"呢注唔使 {sel_name} 贏成場波，只要佢贏到一盤就中。"
    if family == "first_set_winner":
        return f"呢注只睇首盤，{sel_name} 贏咗第一盤就中，之後點打都唔影響。"
    if family == "player_total_games":
        line = _num(prop.get("line"))
        if line is None:
            return None
        pick = "大" if prop.get("side") == "over" else "細"
        return f"模型預計 {sel_name} 全場攞到 {mean:.1f} 局，盤口線係 {line:g} 局，所以揀{pick}。"
    return None


def _match_reason(match_pred: dict | None, sel_id, sel_name: str) -> str | None:
    if not match_pred:
        return None
    p = _num(match_pred.get("model_probability"))
    mk = _num(match_pred.get("no_vig_market_probability"))
    who = match_pred.get("selection_player_id")
    if p is None or who is None:
        return None
    if who != sel_id:
        p = 1 - p
        mk = None if mk is None else 1 - mk
    text = f"成場波嚟講，模型估 {sel_name} 贏嘅機會係 {_pct(p)}"
    return text + (f"（市場估 {_pct(mk)}）。" if mk is not None else "。")


def _form_reasons(evidence: dict, sel_id, opp_id, sel_name: str, opp_name: str) -> list[str]:
    profiles = (evidence.get("profiles") or {}).get("serve_return") or {}
    mine, theirs = profiles.get(str(sel_id)) or {}, profiles.get(str(opp_id)) or {}

    def stats(p):
        hold = _num((p.get("serve") or {}).get("hold_rate"))
        brk = _num((p.get("returning") or {}).get("break_rate"))
        return hold, brk, _num(p.get("opponent_elo_mean")), int(_num(p.get("matches")) or 0)

    h1, b1, e1, n1 = stats(mine)
    h2, b2, e2, n2 = stats(theirs)
    if None in (h1, b1, h2, b2):
        return []
    out = [f"近期狀態（{sel_name} 近 {n1} 場、{opp_name} 近 {n2} 場）："
           f"{sel_name} 發球局保發 {_pct(h1)}、接發破發 {_pct(b1)}；"
           f"{opp_name} 保發 {_pct(h2)}、破發 {_pct(b2)}。"]
    verdict = _compare(h1 - h2, b1 - b2, sel_name, opp_name)
    if e1 is not None and e2 is not None and abs(e1 - e2) >= 50:
        stronger = sel_name if e1 > e2 else opp_name
        verdict += (f"另外 {stronger} 嘅數字係對住較強對手打出嚟"
                    f"（對手平均 Elo {max(e1, e2):.0f} 對 {min(e1, e2):.0f}），含金量較高。")
    out.append(verdict)
    return out


# Gaps in hold/break rate: under 3 points reads as level, 8+ as a big gap.
_LEVEL, _BIG = 0.03, 0.08


def _edge_word(gap: float) -> str:
    return "強好多" if abs(gap) >= _BIG else "較強"


def _compare(hold_gap: float, break_gap: float, sel_name: str, opp_name: str) -> str:
    """One sentence on who serves/returns better; gaps are selected minus opponent."""
    if abs(hold_gap) >= _LEVEL and abs(break_gap) >= _LEVEL and (hold_gap > 0) == (break_gap > 0):
        who = sel_name if hold_gap > 0 else opp_name
        word = "強好多" if min(abs(hold_gap), abs(break_gap)) >= _BIG else "較強"
        text = f"{who} 發球同破發都{word}。"
        if hold_gap < 0:
            text += f"模型揀 {sel_name} 主要係覺得價錢開得太闊。"
        return text
    parts = []
    for gap, skill in ((hold_gap, "發球"), (break_gap, "破發")):
        if abs(gap) < _LEVEL:
            parts.append(f"{skill}兩個差唔多")
        else:
            parts.append(f"{sel_name if gap > 0 else opp_name} {skill}{_edge_word(gap)}")
    return "，".join(parts) + "。"


def _caveats(evidence: dict, sel_id, opp_id, court: str | None = None) -> str | None:
    # No "數據完整度 N/100" line: warning deductions are capped at 35, so every
    # match without a hard error scored exactly 65, the entry bar itself
    # (2,216 of 2,364 rows priced 2026-11-01..13). It said nothing. Name the
    # input that is actually missing instead.
    notes = []
    if court == "":
        notes.append("場地未知，場地 Elo 用緊整體 Elo 代替")
    profiles = (evidence.get("profiles") or {}).get("serve_return") or {}
    counts = [int(_num((profiles.get(str(pid)) or {}).get("matches")) or 0) for pid in (sel_id, opp_id)]
    if profiles and min(counts) < 10:
        notes.append(f"其中一位球員得 {min(counts)} 場紀錄，樣本少")
    if profiles and all((profiles.get(str(pid)) or {}).get("surface") is None for pid in (sel_id, opp_id)):
        notes.append("未有分場地數據，用緊全部場地合計")
    return ("要留意：" + "；".join(notes) + "。") if notes else None


def pick_reasons(featured: dict, prop: dict, match: dict, players: dict,
                 match_pred: dict | None = None, court: str | None = None) -> list[str]:
    """``court``: the tournament surface, "" when unknown, None when not looked up."""
    try:
        family = _family(featured.get("market_key") or prop.get("market_key"))
        sel_id, opp_id = _selected_player(prop, match, family)
        sel_name = players.get(sel_id) or "模型揀嘅球員"
        opp_name = players.get(opp_id) or "對手"
        evidence = _evidence(prop)
        selection = featured.get("selection") or prop.get("selection") or ""
        reasons = [
            _price_reason(featured),
            _projection_reason(prop, family, sel_name, opp_name, selection),
            _match_reason(match_pred, sel_id, sel_name) if sel_id is not None else None,
        ]
        if sel_id is not None:
            reasons += _form_reasons(evidence, sel_id, opp_id, sel_name, opp_name)
            reasons.append(_caveats(evidence, sel_id, opp_id, court))
        return [r for r in reasons if r]
    except Exception:  # noqa: BLE001 - an explanation must never break the export
        return []
