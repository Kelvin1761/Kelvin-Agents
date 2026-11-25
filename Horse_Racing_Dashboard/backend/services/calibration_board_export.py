"""校準板（`<WongChoiControl>/calibration_board.json`，EXP-20261125-07）→ dashboard snapshot（Portfolio 頁）。

只抄數，唔重計（同 roi_board_export 一樣）：「我哋講 X% 機會，實際係咪 X%」逐 domain、10pp 分桶、Wilson CI，
同埋同一批馬／注上嘅去水市場 log-loss 對照。冇數嘅 domain 照列，標 `available=false`，唔扮有。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
NAME = "calibration_board.json"
# (key, 標籤, 讀邊一段)
SECTIONS = (
    ("au_top3", "AU 賽馬 · 入頭三", ("au", "top3")),
    ("au_win", "AU 賽馬 · 獨贏", ("au", "win")),
    ("hkjc_top3", "香港賽馬 · 入頭三", ("hkjc", "top3")),
    ("nba", "NBA 腿（p_final）", ("nba", None)),
    ("tennis_all", "網球 · 全部定價 prop", ("tennis", "all")),
    ("tennis_featured", "網球 · 精選", ("tennis", "featured")),
)
BUCKET_KEYS = ("bucket", "n", "mean_p", "hit_rate", "ci", "low_n")


def board_path() -> Path:
    root = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(root) / NAME


def _section(raw: dict | None) -> dict:
    if not isinstance(raw, dict) or not raw.get("n"):
        return {"available": False}
    market = raw.get("market") if isinstance(raw.get("market"), dict) else {}
    return {
        "available": True,
        "n": raw.get("n"), "mean_p": raw.get("mean_p"), "hit_rate": raw.get("hit_rate"), "ci": raw.get("ci"),
        "logloss": raw.get("logloss"),
        "market_logloss": market.get("logloss_market"), "model_logloss_same_rows": market.get("logloss_model"),
        "market_method": market.get("method"),
        "buckets": [{k: b.get(k) for k in BUCKET_KEYS} for b in raw.get("buckets") or [] if b.get("n")],
    }


def export_calibration_board(path: Path | None = None) -> dict:
    path = Path(path or board_path())
    data = json.loads(path.read_text(encoding="utf-8"))
    domains = data.get("domains") if isinstance(data, dict) else None
    if not isinstance(domains, dict):
        raise ValueError(f"{path} has no domains")
    sections = []
    for key, label, (dom, part) in SECTIONS:
        d = domains.get(dom) or {}
        if dom == "nba":
            raw = dict(d.get("overall") or {}, buckets=d.get("buckets") or [])
            raw["market"] = {"method": "收市原價（未去水）gap", "logloss_market": None}
            sec = _section(raw)
            if sec["available"]:
                sec["market_gap"] = (d.get("market_raw_close") or {}).get("gap")
                sec["note"] = d.get("note")
        else:
            sec = _section(d.get(part))
        sec.update(key=key, label=label, first_day=d.get("first_day") or d.get("since"),
                   last_day=d.get("last_day") or d.get("until"))
        sections.append(sec)
    return {"schema_version": SCHEMA_VERSION, "status": "valid", "experiment": data.get("experiment"),
            "built_at": data.get("built_at"), "low_n": data.get("low_n"),
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sections": sections}
