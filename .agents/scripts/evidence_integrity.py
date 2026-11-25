#!/usr/bin/env python3
"""研究證據完整性（系統升級第二輪第 2 項，2026-11-25）：證據記錄指住嘅 artifact 仲喺唔喺度。

點解：`evidence/records/prediction/*` 用絕對路徑＋sha256 封印每份預測快照。檔一搬（NBA 賽後歸檔用 `shutil.move`），
之後每次研究覆核都驗唔到 —— 2026-10-21 → 11-25 research-review 日日 failed，一個月冇人知（EXP-20261125-03）。
設計上「搬咗」本身就係證據改變（覆核會 fail-closed），所以唔可以靠「搵返 bytes 就當冇搬」去補；
正確做法係**唔准搬**（搬嘢嘅 step 要抄、原位留低），同埋**第二日就捉到**。呢個腳本做後者。

判斷（同覆核用嘅 resolver 一樣：`research_prediction_artifacts._offloaded_candidate`）：
  * 原路徑有 → ok；冇但官方 offload 位置有（AU／HKJC 舊快照搬去外置碟）→ ok（relocated）；兩個都冇 → missing。
  * sha256 抽查：每次隨機抽 `--sample` 個 ok 嘅 artifact 讀 bytes 核對（全部讀要幾 GB）。
狀態寫 `<WongChoiControl>/evidence_integrity_state.json`；**missing 比上次多 = ❌**（舊嘅已知 missing 只報數）。

    python3 evidence_integrity.py [--sample 200] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTROL = Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or Path.home() / "WongChoiData" / "WongChoiControl")
STATE = CONTROL / "evidence_integrity_state.json"


def _resolver():
    """覆核用嘅 offload resolver ＋ 已知嘅 AU 歸檔搬遷（`AU_Racing/<場次>` → `AU_Racing/Archive/<場次>`，再可能 offload 去外置碟）。

    AU 歸檔成個場次資料夾搬入 Archive/（AGENTS.md：Archive/ 係語料一部分），所以證據路徑全部唔再指住 bytes；
    bytes 冇冇（2026-11-25 抽查 2,875／2,875 搵到），只係搬咗。呢度當「已知搬遷」，但覆核本身睇唔到（冇 relocation root）。
    """
    sys.path.insert(0, str(REPO / ".agents" / "skills"))
    sys.path.insert(0, str(REPO / ".agents" / "scripts"))
    from shared_wong_choi.research_prediction_artifacts import _offloaded_candidate
    import wongchoi_paths

    def resolve(path: Path):
        alt = _offloaded_candidate(path)
        if alt is not None and Path(alt).is_file():
            return alt
        parts = path.parts
        if "_prediction_snapshots" in parts:
            i = parts.index("_prediction_snapshots")
            meeting = Path(*parts[:i])
            archived = meeting.parent / "Archive" / meeting.name
            if archived.is_dir():
                try:
                    folder = wongchoi_paths.prediction_snapshot_dir(archived, "_prediction_snapshots")
                except Exception:  # noqa: BLE001 — 外置碟冇插
                    return None
                cand = Path(folder) / Path(*parts[i + 1:])
                return cand if cand.is_file() else None
        return None
    return resolve


def scan(records_dir: Path | None = None, *, sample: int = 200, seed: int | None = None,
         offloaded=None) -> dict:
    records_dir = records_dir or CONTROL / "evidence" / "records" / "prediction"
    offloaded = offloaded or _resolver()
    counts: dict[str, Counter] = {}
    missing: list[str] = []
    ok_refs: list[tuple[str, str]] = []
    for f in sorted(records_dir.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counts.setdefault("unreadable", Counter())["records"] += 1
            continue
        domain = str(rec.get("domain") or (rec.get("body") or {}).get("domain") or f.name.split("%3A")[1:2] or "?")
        domain = domain.strip("[]'\"") or "?"
        c = counts.setdefault(domain, Counter())
        c["records"] += 1
        for a in rec.get("artifacts") or []:
            c["refs"] += 1
            p = Path(a.get("path") or "")
            if p.is_file():
                c["direct"] += 1
                ok_refs.append((str(p), a.get("sha256") or ""))
                continue
            alt = None
            try:
                alt = offloaded(p)
            except Exception:  # noqa: BLE001 — resolver 拋錯 = 搵唔到
                alt = None
            if alt is not None and Path(alt).is_file():
                c["relocated"] += 1
                ok_refs.append((str(alt), a.get("sha256") or ""))
            else:
                c["missing"] += 1
                missing.append(f"{domain}:{p}")
    rng = random.Random(seed)
    bad_sha = []
    for path, want in rng.sample(ok_refs, min(sample, len(ok_refs))):
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if want and h.hexdigest() != want:
            bad_sha.append(path)
    return {"at": datetime.now(timezone.utc).isoformat(),
            "domains": {d: dict(c) for d, c in sorted(counts.items())},
            "missing_total": len(missing), "missing": sorted(missing),
            "sha_checked": min(sample, len(ok_refs)), "sha_mismatch": bad_sha}


def compare(report: dict, previous: dict | None) -> dict:
    prev = set((previous or {}).get("missing") or [])
    new = [m for m in report["missing"] if m not in prev]
    level = "bad" if new or report["sha_mismatch"] else ("warn" if report["missing_total"] else "ok")
    return {"level": level, "new_missing": new, "known_missing": report["missing_total"] - len(new)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-state", action="store_true", help="唔寫狀態（試跑）")
    ap.add_argument("--accept-current", action="store_true",
                    help="將而家嘅 missing 記做已知（只喺人手核實過冇得還原之後用；例：指去系統 tmp 嘅舊測試殘留）")
    a = ap.parse_args(argv)
    try:
        previous = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    report = scan(sample=a.sample)
    verdict = compare(report, previous)
    if not a.no_state and (verdict["level"] != "bad" or a.accept_current):
        # 有新 missing 唔會寫入 —— 下次照樣報，直到有人處理（還原或者記錄原因）
        STATE.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.json:
        print(json.dumps(report | {"verdict": verdict}, ensure_ascii=False, indent=1))
    else:
        for d, c in report["domains"].items():
            print(f"{d}: {c.get('records', 0)} 記錄、{c.get('refs', 0)} artifact —— 原位 {c.get('direct', 0)}、"
                  f"offload {c.get('relocated', 0)}、冇咗 {c.get('missing', 0)}")
        print(f"sha256 抽查 {report['sha_checked']} 個，對唔上 {len(report['sha_mismatch'])}")
        print(f"判斷：{verdict['level']}（新冇咗 {len(verdict['new_missing'])}、已知 {verdict['known_missing']}）")
        for m in verdict["new_missing"][:10]:
            print("  新冇咗：" + m)
    return {"ok": 0, "warn": 0, "bad": 1}[verdict["level"]]


if __name__ == "__main__":
    sys.exit(main())
