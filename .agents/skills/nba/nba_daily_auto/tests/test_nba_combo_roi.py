"""Synthetic ledger rows only; nothing touches the production ledger."""
from __future__ import annotations

import sys
from pathlib import Path

AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_combo_roi as roi  # noqa: E402

D = "2026-10-22"


def leg(player, price=1.5, line=10.0, market="pts"):
    return {"player": player, "market": market, "line": line, "side": "over", "price": price}


def sgm(cid, legs, product, *, late=False, snap="s1"):
    return {"row_type": "sgm_obs", "target_date": D, "game_tag": "AAA_BBB", "combo_id": cid,
            "legs": legs, "product_of_leg_prices": product, "snapshot_id": snap,
            "snapshot_role": "production", "snapshot_created_at": "2026-10-22T10:00:00+11:00",
            "late_write": late, "post_tip": False}


def quote(cid, price, snap="s1"):
    return {"row_type": "sgm_price_obs", "target_date": D, "game_tag": "AAA_BBB", "combo_id": cid,
            "snapshot_id": snap, "status": "ok", "sportsbet_sgm_price": price,
            "captured_at": "2026-10-22T10:01:00+00:00", "late_write": False, "post_tip": False}


def settle(player, outcome, line=10.0, market="pts"):
    return {"row_type": "settlement", "target_date": D, "game_tag": "AAA_BBB", "player": player,
            "market": market, "line": line, "side": "over", "outcome": outcome}


def test_win_loss_pending_void_and_roi():
    rows = [
        sgm("1", [leg("A"), leg("B")], 2.25), quote("1", 2.0),     # win @2.0
        sgm("2", [leg("A"), leg("C")], 3.0),                       # loss (C misses), no SGM quote
        sgm("3", [leg("A"), leg("D")], 4.0),                       # pending (D unsettled)
        sgm("X", [leg("A"), leg("E")], 5.0),                       # void (E DNP)
        settle("A", "hit"), settle("B", "hit"), settle("C", "miss"), settle("E", "void"),
    ]
    out = {c["combo_id"]: c for c in roi.settle_combos(rows)}
    assert [out[k]["state"] for k in "123X"] == ["win", "loss", "pending", "void"]
    s = roi.summarise(list(out.values()))
    assert s["total"]["settled"] == 2 and s["total"]["wins"] == 1
    assert s["total"]["sgm"] == {"n": 1, "wins": 1, "profit_units": 1.0, "roi": 1.0}  # only combo 1 had a quote
    assert s["total"]["product"]["profit_units"] == round(1.25 - 1.0, 3) and s["total"]["product"]["n"] == 2
    assert s["total"]["pending"] == 1 and s["total"]["void"] == 1


def test_late_snapshot_is_flagged_not_clean_and_split():
    rows = [sgm("1", [leg("A")], 2.0, late=True), settle("A", "hit")]
    combos = roi.settle_combos(rows)
    assert combos[0]["clean"] is False
    s = roi.summarise(combos)
    assert s["total"]["settled"] == 1 and s["total_clean"]["settled"] == 0


def test_clean_snapshot_preferred_over_late_one():
    rows = [sgm("1", [leg("A")], 2.0, late=True, snap="late"), sgm("1", [leg("B")], 3.0, snap="ok"),
            settle("B", "hit")]
    combos = roi.settle_combos(rows)
    assert len(combos) == 1 and combos[0]["clean"] and combos[0]["product_price"] == 3.0


def test_message_lines_handle_empty_and_label_types():
    empty = {"daily": roi.summarise([]), "cumulative": roi.summarise([])}
    assert any("未有已結算" in line for line in roi.message_lines(empty))
    rows = [sgm("1", [leg("A")], 2.0), settle("A", "hit")]
    both = roi.summarise(roi.settle_combos(rows))
    text = "\n".join(roi.message_lines({"daily": both, "cumulative": both}))
    assert "穩膽" in text and "樣本細" in text


def test_frozen_publication_quote_wins_over_later_reference_observation():
    from nba_sgm_quote import legs_identity
    chosen = sgm('1', [leg('A'), leg('B')], 2.25)
    chosen.update(sportsbet_sgm_status='ok', sportsbet_sgm_price=2.0,
                  sgm_quote={'status': 'ok', 'decimal_odds': 2.0, 'legs_sha256': legs_identity(chosen['legs'])})
    out = roi.settle_combos([chosen, quote('1', 3.0), settle('A', 'hit'), settle('B', 'hit')])
    assert out[0]['sgm_price'] == 2.0


def test_standalone_cli_reads_frozen_quotes_without_parent_pythonpath(tmp_path):
    import json
    import os
    import subprocess
    sys.path.insert(0, str(AUTO_DIR.parent))
    from nba_sgm_quote import legs_identity
    from nba_reliability import current_model_id
    chosen = sgm('1', [leg('A'), leg('B')], 2.25)
    chosen.update(sportsbet_sgm_status='ok', sportsbet_sgm_price=2.1,
                  sgm_quote={'status':'ok','decimal_odds':2.1,'legs_sha256':legs_identity(chosen['legs'])})
    base = dict(chosen, probability_model_id=current_model_id(), season_phase='EARLY_REGULAR', tip_unknown=False)
    rows = [chosen, dict(base,row_type='model_obs',player='A',market='pts',line=10),settle('A','hit'),settle('B','hit')]
    for arm in ('B0','B1','B2'):
        rows.append(dict(base,row_type='banker_shadow_obs',version='banker-ev-shadow-v1',arm=arm,eligible=arm=='B2'))
    path=tmp_path/'ledger'/f'{D}.jsonl';path.parent.mkdir()
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows));before=path.read_bytes()
    env=dict(os.environ,WONGCHOI_NBA_MARKET_LEDGER_ROOT=str(tmp_path),PYTHONDONTWRITEBYTECODE='1',NBA_WC_PROB_LAYER='1')
    env.pop('PYTHONPATH',None)
    command=[sys.executable,str(AUTO_DIR/'nba_combo_roi.py'),'--date',D]
    normal=subprocess.run(command,cwd=tmp_path,env=env,text=True,capture_output=True)
    assert normal.returncode==0,normal.stderr
    assert '1/1 中' in normal.stdout
    shadow=subprocess.run(command+['--shadow'],cwd=tmp_path,env=env,text=True,capture_output=True)
    assert shadow.returncode==0,shadow.stderr
    result=json.loads(shadow.stdout)
    assert result['arms']['B2']['sgm']['n']==1 and result['arms']['B2']['sgm']['profit_units']==1.1
    assert not result['promotion_allowed']
    assert path.read_bytes()==before and not (tmp_path/'reports').exists()


def test_known_miss_beats_void_and_pending():
    rows = [
        sgm("1", [leg("A"), leg("E")], 3.0),             # miss + void -> loss, not void
        sgm("2", [leg("A"), leg("D")], 3.0),             # miss + unsettled -> already lost
        sgm("3", [leg("B"), leg("E")], 3.0),             # hit + void -> void
        settle("A", "miss"), settle("B", "hit"), settle("E", "void"),
    ]
    out = {c["combo_id"]: c["state"] for c in roi.settle_combos(rows)}
    assert out == {"1": "loss", "2": "loss", "3": "void"}
