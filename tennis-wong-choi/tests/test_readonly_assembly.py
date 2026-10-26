"""A read-only assembly must calculate the same features without storing stats."""
from __future__ import annotations

import sqlite3
import sys

from conftest import configure_test_db


def test_readonly_assembly_has_identical_features_and_no_side_effects(tmp_path,monkeypatch):
    path=configure_test_db(tmp_path,monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.ingest_matches import ingest_upcoming_matches,ingest_default_history
    from tennis_wc.ingestion.ingest_tournaments import ingest_tournaments
    import tennis_wc.features.feature_builder as builder
    init_db();ingest_tournaments('2026-05-08','2026-05-08')
    ingest_upcoming_matches('2026-05-08');ingest_default_history('2026-05-08')
    for name,module in list(sys.modules.items()):
        if name.startswith('tennis_wc.features.') and hasattr(module,'utc_now'):
            monkeypatch.setattr(module,'utc_now',lambda:'2026-05-08T00:00:00Z')
    writable,_=builder.assemble_match_feature_snapshot(1,persist_derived=True)
    tables=('player_opponent_rank_bucket_stats','player_big_match_stats','player_round_stats',
            'player_tournament_level_stats','player_bo_format_stats')
    with sqlite3.connect(path) as c:
        before={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
    def readonly():
        c=sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)
        c.row_factory=sqlite3.Row
        return c
    for name,module in list(sys.modules.items()):
        if name.startswith('tennis_wc.features.') and hasattr(module,'get_connection'):
            monkeypatch.setattr(module,'get_connection',readonly)
    assembled,_=builder.assemble_match_feature_snapshot(1)
    assert assembled==writable
    with sqlite3.connect(path) as c:
        assert {t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}==before
        assert c.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0]==0
