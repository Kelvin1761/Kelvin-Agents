import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hkjc_racing_engine.features.form import FormScorer
from hkjc_racing_engine.engine_core import RacingEngine


def test_zero_form_never_receives_place_credit():
    clean = FormScorer({'last_6_finishes': '6-7-3-1-8'}, {}).compute()
    invalid = FormScorer({'last_6_finishes': '0-6-7-3-1-8'}, {}).compute()
    assert invalid == clean
    assert '2次前三' in invalid[1]


def test_surface_sample_is_from_target_not_first_surface():
    engine = RacingEngine({'surface_performance_shadow':
        '今場=跑馬地草地 62.7分 | 沙田草地 60.0分(有效樣本0.0/原始0) | '
        '跑馬地草地 62.7分(有效樣本4.3/原始7) | 採用來源=local_history'}, {})
    result = engine._surface_performance_shadow_component()
    assert result['effective_n'] == 4.3
    assert result['score'] == 62.7


def test_zero_does_not_prove_recovery():
    engine = RacingEngine({'last_6_finishes': '0-6-7-8'}, {})
    assert not engine._has_recovery_evidence()


def test_consistency_ignores_status_rows_before_weighting_and_trend():
    valid = "第1仗: 6名 2 | 第2仗: 7名 4 | 第3仗: 3名 1 | 第4仗: 1名 0 | 第5仗: 8名 6"
    with_status = "第0仗: 0名 N/A | " + valid
    clean = RacingEngine({"_data": {"recent_6_detail": valid}}, {})
    invalid = RacingEngine({"_data": {"recent_6_detail": with_status}}, {})
    assert invalid._consistency_shadow_detail() == clean._consistency_shadow_detail()


def test_consistency_fallback_ignores_zero_before_sample_count():
    clean = RacingEngine({"last_6_finishes": "1-1"}, {})
    invalid = RacingEngine({"last_6_finishes": "0-1-1"}, {})
    assert invalid._consistency_score({"form_score": 100}) == clean._consistency_score({"form_score": 100})


def test_only_status_rows_have_no_consistency_detail():
    engine = RacingEngine({"_data": {"recent_6_detail": "第1仗: 0名 N/A"}}, {})
    assert engine._consistency_shadow_detail() is None
