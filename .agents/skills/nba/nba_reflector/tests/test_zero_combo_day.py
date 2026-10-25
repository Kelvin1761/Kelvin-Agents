"""Valid abstentions archive; missing predictions and unfinished games still block."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import nba_reflector_orchestrator as reflector
import nba_daily_review_archive as archive

DAY = '2026-10-25'


def report(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'Game_BKN_CLE_Full_Analysis.md'
    path.write_text('# NBA analysis\nNo eligible combinations.\n')
    data = {'schema_version': 'nba-market-eval-legs/v1',
            'report_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'combos': [], 'legs': [{'player': 'Player', 'picked': False, 'picked_in': []}]}
    sidecar = Path(str(path) + '.market_legs.json')
    sidecar.write_text(json.dumps(data))
    return path, sidecar


def test_zero_combo_reflector_writes_artifacts_without_db_or_ml(tmp_path, monkeypatch):
    report(tmp_path)
    (tmp_path / 'Results_Brief_2026-10-24.json').write_text('{}')
    (tmp_path / 'Props_Verification_2026-10-24.json').write_text('{"games":[]}')
    monkeypatch.setattr(reflector, 'open_reflector_db', lambda: pytest.fail('must not open DB for zero legs'))
    monkeypatch.setattr(sys, 'argv', ['reflector', '--date', DAY, '--dir', str(tmp_path), '--skip-fetch', '--skip-pbp'])
    reflector.main()
    summary = json.loads((tmp_path / f'Reflector_Run_Summary_{DAY}.json').read_text())
    assert summary['verified_no_combos'] is True
    assert summary['rows_recorded'] == 0
    assert summary['ml_summary'] is None
    assert Path(summary['training_snapshot']).is_file()


@pytest.mark.parametrize('failure', ['stale', 'missing', 'malformed', 'no_legs', 'picked', 'combo'])
def test_absent_or_broken_predictions_are_not_valid_abstentions(tmp_path, failure):
    path, sidecar = report(tmp_path)
    data = json.loads(sidecar.read_text())
    if failure == 'stale':
        path.write_text('changed')
    elif failure == 'missing':
        sidecar.unlink()
        assert not reflector.verified_no_combo_reports(str(tmp_path))
        return
    elif failure == 'malformed':
        data = []
    elif failure == 'no_legs':
        data['legs'] = []
    elif failure == 'picked':
        data['legs'][0]['picked'] = True
    else:
        data['combos'] = [{'combo_id': 1, 'legs': []}]
    sidecar.write_text(json.dumps(data))
    assert not reflector.verified_no_combo_reports(str(tmp_path))


@pytest.mark.parametrize('final', [False, True])
def test_zero_combo_archive_waits_for_final_results(tmp_path, monkeypatch, final):
    source = tmp_path / f'{DAY} NBA Analysis'
    report(source)
    results = source / 'results.json'
    results.write_text(json.dumps({'_version': 'RESULTS_BRIEF_V1',
                                  'games': [{'status': 'Final' if final else 'In Progress',
                                             'away': {'team': 'BKN'}, 'home': {'team': 'CLE'}}]}))
    verification = source / 'verification.json'
    verification.write_text(json.dumps({'summary': {'total_legs': 0}}))
    training = source / 'training.csv'
    training.write_text('header\n')
    (source / f'Reflector_Run_Summary_{DAY}.json').write_text(json.dumps({
        'training_snapshot': str(training), 'results_path': str(results),
        'verification_path': str(verification), 'rows_recorded': 0,
    }))
    monkeypatch.setattr(archive, 'WORKSPACE_ROOT', tmp_path)
    monkeypatch.setattr(archive, 'NBA_ANALYSIS', tmp_path / 'archive')
    monkeypatch.setattr(archive, 'is_valid_no_bet', lambda day: True)
    monkeypatch.setattr(archive.subprocess, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, 'argv', ['review', '--date', DAY])
    assert archive.main() == 0
    assert source.exists() is not final
    assert (tmp_path / 'archive' / source.name).exists() is final


def test_zero_combo_results_must_cover_every_report(tmp_path):
    path = tmp_path / 'results.json'
    path.write_text(json.dumps({'_version': 'RESULTS_BRIEF_V1', 'games': [
        {'status': 'Final', 'away': {'team': 'BKN'}, 'home': {'team': 'CLE'}}]}))
    ready, reason = archive.results_are_final(path, report_names=[
        'Game_BKN_CLE_Full_Analysis.md', 'Game_MIA_CHA_Full_Analysis.md'])
    assert not ready
    assert 'games_missing_results:Game_MIA_CHA_Full_Analysis.md' == reason
