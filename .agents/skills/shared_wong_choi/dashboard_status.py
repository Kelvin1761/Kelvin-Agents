"""Read-only ownership/configuration view for the Central Wong Choi Dashboard."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def collect_dashboard_status(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().resolve() / "Horse_Racing_Dashboard"
    config = _read(root / "wrangler.toml")
    local_tunnel_url = _read(root / "CURRENT_URL.txt")
    url = "https://wongchoi-dashboard.pages.dev"
    d1 = re.search(r'(?m)^binding\s*=\s*"WC_LEDGER"\s*$', config) is not None
    kv = re.search(r'(?m)^binding\s*=\s*"WC_STATE"\s*$', config) is not None
    functions = (root / "functions" / "api" / "sports-bets.js").is_file()
    audit = (root / "functions" / "api" / "audit.js").is_file()
    migration = (root / "migrations" / "0001_unified_bet_ledger.sql").is_file()
    configured = root.is_dir() and d1 and functions and audit and migration
    attention = []
    if not configured:
        attention.append("dashboard_ledger_not_fully_configured")
    return {
        "schema_version": "wong-choi-dashboard-status/v1",
        "status": "configured" if configured else "attention",
        "attention": attention,
        "ownership": "central_wong_choi_control_tower",
        "path": str(root),
        "url": url or None,
        "local_tunnel_url": local_tunnel_url or None,
        "analysis_authority": "four_domain_engines",
        "model_evidence_source": "central_append_only_evidence",
        "betting_ledger_source": "cloudflare_d1_wc_ledger" if d1 else "unavailable",
        "kv_shadow_configured": kv,
        "audit_api_configured": audit,
        "recommendation_calculation_allowed": False,
    }


def render_dashboard_telegram(payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"📊 中央旺財 Dashboard：{payload.get('status')}",
            f"網址：{payload.get('url') or '未設定'}",
            f"投注 ledger：{payload.get('betting_ledger_source')}",
            f"模型證據：{payload.get('model_evidence_source')}",
            "Dashboard 只顯示／記帳，唔會自行計 prediction 或改排名。",
        )
    )
