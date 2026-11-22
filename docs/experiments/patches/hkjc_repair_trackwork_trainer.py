#!/usr/bin/env python3
"""一次性資料修正（Kelvin 2026-11-21）：舊晨操檔練馬師欄寫咗「詳情」。

成因：冇排位表時用晨操頁後備馬匹列表，`parse_horse_list` 攞咗最後一格（「詳情」連結）做練馬師
（2026-05→07 約 1,900 匹）。parser 已修（`extract_trackwork.page_trainer`）；呢個腳本修返已存嘅檔：

  * 練馬師由同場次排位表攞（烙號配對，配唔到就用馬名）；排位表都冇就留空，唔估。
  * 用正確練馬師重新分類每行騎手角色（`classify_rider_role`）；有變就連摘要入面嘅角色計數一齊更新。
  * 原值全部記入 `<HK root>/_repairs/<日期>_trackwork_trainer.json`，可以還原。

    python3 docs/experiments/patches/hkjc_repair_trackwork_trainer.py            # dry-run
    python3 docs/experiments/patches/hkjc_repair_trackwork_trainer.py --apply
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"))
import extract_trackwork as xt  # noqa: E402

ROOT = Path((REPO / ".wongchoi_hk_data_root").read_text(encoding="utf-8").strip())
BAD = {"詳情"}


def card_trainers(meeting: Path, race_no) -> tuple[dict, dict]:
    by_brand, by_name = {}, {}
    for card in meeting.glob(f"* Race {race_no} 排位表.md"):
        for block in re.split(r"\n(?=馬號:\s*\d+)", card.read_text(encoding="utf-8", errors="replace")):
            tr = re.search(r"練馬師:\s*(.+)", block)
            if not tr:
                continue
            br = re.search(r"烙號:\s*([A-Z]\d{3})", block)
            nm = re.search(r"馬名:\s*(.+)", block)
            if br:
                by_brand[br.group(1)] = xt.clean_text(tr.group(1))
            if nm:
                by_name[xt.clean_text(nm.group(1))] = xt.clean_text(tr.group(1))
        break
    # 後備：同場次賽果（練馬師係靜態事實，唔係賽果資訊）—— 排位表缺場次或者退出馬先用到
    for res in meeting.glob("*全日賽果.json"):
        try:
            race = json.loads(res.read_text(encoding="utf-8")).get(str(race_no)) or {}
        except (OSError, ValueError):
            continue
        for row in race.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name", "")))
            tr = xt.clean_text(row.get("trainer", ""))
            if m and tr:
                by_brand.setdefault(m.group(1), tr)
            nm = xt.clean_text(re.sub(r"\([A-Z]\d{3}\)", "", str(row.get("horse_name", ""))))
            if nm and tr:
                by_name.setdefault(nm, tr)
    return by_brand, by_name


def main(apply: bool) -> int:
    log, fixed, unknown, role_changes = [], 0, 0, 0
    for f in sorted(ROOT.glob("20*_*/*晨操.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        horses = data.get("horses") or {}
        if not any(h.get("trainer") in BAD for h in horses.values()):
            continue
        by_brand, by_name = card_trainers(f.parent, data.get("race_no"))
        changed = False
        for key, h in horses.items():
            if h.get("trainer") not in BAD:
                continue
            new = by_brand.get(str(h.get("horseid", ""))[-4:]) or by_name.get(xt.clean_text(h.get("horse_name", ""))) or ""
            if new in ("-",):
                new = ""
            unknown += not new
            old_roles = [e.get("rider_role") for e in h.get("entries") or []]
            for e in h.get("entries") or []:
                e["rider_role"] = xt.classify_rider_role(e.get("rider", ""), e.get("details", ""), new)
            moved = sum(a != e.get("rider_role") for a, e in zip(old_roles, h.get("entries") or []))
            if moved and isinstance(h.get("summary"), dict):
                entries = [e for e in h["entries"] if not xt.is_race_row(e)]
                h["summary"]["rider_role_counts"] = {r: sum(1 for e in entries if e.get("rider_role") == r)
                                                     for r in sorted({e.get("rider_role", "未標明") for e in entries})}
                h["summary"]["trainer_self_count"] = sum(1 for e in entries if e.get("rider_role") == "練馬師")
            log.append({"file": str(f.relative_to(ROOT)), "horse": key, "old": h.get("trainer"), "new": new, "role_changes": moved})
            role_changes += moved
            h["trainer"] = new
            fixed += 1
            changed = True
        if changed and apply:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'修正' if apply else 'dry-run'}：{fixed} 匹（其中排位表都冇練馬師、留空 {unknown}），騎手角色改變 {role_changes} 行")
    if apply and log:
        out = ROOT / "_repairs" / f"{date.today().isoformat()}_trackwork_trainer.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"原值記錄：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--apply" in sys.argv[1:]))
