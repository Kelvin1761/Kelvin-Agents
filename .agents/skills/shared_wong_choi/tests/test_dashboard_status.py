from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.dashboard_status import collect_dashboard_status


def test_dashboard_is_central_display_with_d1_but_not_prediction_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Horse_Racing_Dashboard"
    (root / "functions" / "api").mkdir(parents=True)
    (root / "migrations").mkdir()
    (root / "wrangler.toml").write_text(
        'binding = "WC_STATE"\nbinding = "WC_LEDGER"\n', encoding="utf-8"
    )
    (root / "CURRENT_URL.txt").write_text("https://example.test", encoding="utf-8")
    (root / "functions" / "api" / "sports-bets.js").write_text("", encoding="utf-8")
    (root / "functions" / "api" / "audit.js").write_text("", encoding="utf-8")
    (root / "migrations" / "0001_unified_bet_ledger.sql").write_text("", encoding="utf-8")

    result = collect_dashboard_status(tmp_path, tmp_path / "state")

    assert result["status"] == "configured"
    assert result["ownership"] == "central_wong_choi_control_tower"
    assert result["betting_ledger_source"] == "cloudflare_d1_wc_ledger"
    assert result["model_evidence_source"] == "central_append_only_evidence"
    assert result["recommendation_calculation_allowed"] is False
    assert result["backup"]["status"] == "no_data"
