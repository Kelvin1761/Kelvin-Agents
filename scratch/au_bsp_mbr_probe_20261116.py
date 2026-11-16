#!/usr/bin/env python3
"""EXP-20261116-25：Betfair AU 賽馬 Market Base Rate（佣金率）逐場地讀取 —— 只讀 listMarketCatalogue，唔落注。

    set -a; source ~/.wongchoi_betfair.env; set +a
    python3 scratch/au_bsp_mbr_probe_20261116.py OUT.json   # 讀未來 7 日全部 AU 贏／位市場
"""
import json, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/au_racing/au_betfair"))
import betfair_client as bf  # noqa: E402

now = datetime.now(timezone.utc)
out = defaultdict(lambda: defaultdict(set))
raw = []
for mtype in ("WIN", "PLACE"):
    res = bf.rpc("listMarketCatalogue", {
        "filter": {"eventTypeIds": ["7"], "marketCountries": ["AU"], "marketTypeCodes": [mtype],
                   "marketStartTime": {"from": now.isoformat(), "to": (now + timedelta(days=7)).isoformat()}},
        "maxResults": 1000, "marketProjection": ["EVENT", "MARKET_DESCRIPTION", "MARKET_START_TIME"]})
    for m in res:
        ev, d = m.get("event") or {}, m.get("description") or {}
        venue, rate = ev.get("venue") or ev.get("name"), d.get("marketBaseRate")
        out[venue][mtype].add(rate)
        raw.append({"venue": venue, "type": mtype, "start": m.get("marketStartTime"), "mbr": rate,
                    "market_id": m.get("marketId"), "discount_allowed": d.get("discountAllowed")})
summary = {v: {t: sorted(r) for t, r in d.items()} for v, d in sorted(out.items())}
for v, d in summary.items():
    print(f"{v:28s} {d}")
Path(sys.argv[1]).write_text(json.dumps({"queried_at": now.isoformat(), "summary": summary, "markets": raw}, indent=1))
