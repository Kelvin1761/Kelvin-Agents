#!/usr/bin/env python3
"""每晚重建嘅表：版本化＋有效版本指針＋回退（EXP-20261125-08，Tier-1 自我學習試點，先做練馬師剩餘表現表）。

檔案（全部同 live 表同一個資料夾）：
  * `AU_Trainer_Residual.json`                       live 檔 —— 重建照舊寫（bytes 同以前一模一樣）；
  * `AU_Trainer_Residual.versions/AU_Trainer_Residual.<as_of>-<sha10>.json`   每份重建另存，內容 = live 檔 bytes；
  * `AU_Trainer_Residual.active.json`                指針 {version, file, sha256, as_of, previous, pinned, history}；
  * `AU_Trainer_Residual.events.jsonl`               啟用／回退／解除鎖定事件（只加唔刪）。

引擎（`people_overlays.default_table_path`）讀指針指住、sha256 驗過嘅版本檔；冇指針／指針壞 = 照讀 live 檔。

規矩：
  * 新重建 sha 同有效版本一樣 → 乜都唔做（重跑唔會開新版本）。
  * 指針 `pinned`（自動回退之後）→ 新重建照存版本檔，但**唔會自動啟用**；`unpin` 先會（Kelvin 決定）。
  * 每次啟用都記低「有冇改寫舊歷史」：將新表截到上一版 `as_of`，同上一版比較。純追加（只多咗新一日）
    = `shadow: not_needed`；改寫咗 = `shadow: pending`，交 `au_residual_shadow.py` 喺之後 7 個賽日判。
  * 只保留最近 14 份版本檔；有效版、上一版、仲等緊 shadow 判決嘅版本同佢哋嘅上一版永遠唔刪。回退從來唔刪檔。

    python3 au_residual_versions.py status
    python3 au_residual_versions.py unpin  --actor kelvin        # 回退之後、修好成因先用
    python3 au_residual_versions.py rollback --to <version> --reason "..."   # 人手回退
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

KEEP = 14
HISTORY_KEEP = 60
EXPERIMENT = "EXP-20261125-08"


def _paths(live: Path) -> tuple[Path, Path, Path]:
    live = Path(live)
    return (live.with_name(live.stem + ".versions"), live.with_name(live.stem + ".active.json"),
            live.with_name(live.stem + ".events.jsonl"))


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _sydney_date(moment: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        return moment.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()
    except Exception:  # noqa: BLE001 —— 冇 tz 資料就用 UTC 日期（只會令 window 遲一日開始）
        return moment.date().isoformat()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def load_pointer(live: Path) -> dict | None:
    try:
        return json.loads(_paths(live)[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_pointer(live: Path, ptr: dict) -> None:
    _atomic(_paths(live)[1], json.dumps(ptr, ensure_ascii=False, indent=1).encode("utf-8"))


def write_event(live: Path, event: dict) -> None:
    path = _paths(live)[2]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def version_file(live: Path, rel: str) -> Path:
    return Path(live).parent / rel


def read_table(live: Path, rel: str, field: str = "trainers") -> dict | None:
    try:
        return json.loads(version_file(live, rel).read_text(encoding="utf-8")).get(field) or {}
    except (OSError, ValueError):
        return None


def truncate(table: dict, cutoff: str | None) -> dict:
    """只留日期 ≤ cutoff 嘅累積紀錄（冇紀錄嘅練馬師剷走）。cutoff None → 原表。"""
    if cutoff is None:
        return {k: v for k, v in table.items() if v}
    out = {}
    for name, rows in table.items():
        kept = [r for r in rows if str(r[0]) <= str(cutoff)]
        if kept:
            out[name] = kept
    return out


def history_rewritten(new_table: dict, prev_table: dict, prev_as_of: str | None) -> bool:
    """新表截到上一版 as_of 之後同上一版唔一樣 = 改寫咗舊歷史（唔係純追加新賽日）。"""
    return truncate(new_table, prev_as_of) != truncate(prev_table, prev_as_of)


def _ref(entry: dict | None) -> dict | None:
    if not entry:
        return None
    return {k: entry.get(k) for k in ("version", "file", "sha256", "as_of")}


def commit(live: Path, data: bytes, *, as_of: str | None, now: datetime | None = None, keep: int = KEEP) -> dict:
    """存一份新版本；冇鎖定就啟用。→ 摘要 {version, action, history_rewritten}。"""
    live = Path(live)
    vdir, _, _ = _paths(live)
    moment = _now(now)
    sha = hashlib.sha256(data).hexdigest()
    vid = f"{as_of or 'none'}-{sha[:10]}"
    rel = f"{vdir.name}/{live.stem}.{vid}.json"
    target = version_file(live, rel)
    if not target.exists():
        _atomic(target, data)
    ptr = load_pointer(live)
    if ptr and ptr.get("sha256") == sha:
        return {"version": ptr.get("version"), "action": "unchanged"}
    if ptr and ptr.get("pinned"):
        write_event(live, {"at": moment.isoformat(), "event": "saved_while_pinned", "version": vid,
                           "active": ptr.get("version")})
        prune(live, keep=keep)
        return {"version": vid, "action": "saved_while_pinned", "active": ptr.get("version")}
    prev = _ref(ptr)
    rewritten = None
    if prev:
        prev_table = read_table(live, prev["file"])
        new_table = json.loads(data.decode("utf-8")).get("trainers") or {}
        rewritten = None if prev_table is None else history_rewritten(new_table, prev_table, prev.get("as_of"))
    entry = {"version": vid, "file": rel, "sha256": sha, "as_of": as_of, "activated_at": moment.isoformat(),
             "activated_on": _sydney_date(moment), "previous": prev, "history_rewritten": rewritten,
             "shadow": "pending" if rewritten else ("not_comparable" if prev and rewritten is None else "not_needed")}
    history = list((ptr or {}).get("history") or []) + [entry]
    new_ptr = {"experiment": EXPERIMENT, "table": live.name, **_ref(entry), "activated_at": entry["activated_at"],
               "activated_on": entry["activated_on"], "previous": prev, "pinned": False,
               "history": history[-HISTORY_KEEP:]}
    _write_pointer(live, new_ptr)
    write_event(live, {"at": moment.isoformat(), "event": "activated", "version": vid,
                       "previous": (prev or {}).get("version"), "history_rewritten": rewritten})
    prune(live, keep=keep)
    return {"version": vid, "action": "activated", "history_rewritten": rewritten}


def _protected(ptr: dict | None) -> set[str]:
    if not ptr:
        return set()
    keep = {ptr.get("file")}
    keep.add((ptr.get("previous") or {}).get("file"))
    keep.add((ptr.get("rolled_back_from") or {}).get("file"))
    history = ptr.get("history") or []
    recent = history[-10:]   # 連續 3 個窗口規則可能指返幾版之前嘅上一版
    for entry in history:
        if entry.get("shadow") == "pending" or (entry in recent and entry.get("shadow") == "done"):
            keep.add(entry.get("file"))
            keep.add((entry.get("previous") or {}).get("file"))
    return {Path(k).name for k in keep if k}


def prune(live: Path, *, keep: int = KEEP) -> list[str]:
    """只留最近 `keep` 份；受保護嘅（有效版、上一版、等 shadow 判決嘅）永遠唔刪。→ 刪咗嘅檔名。"""
    vdir = _paths(live)[0]
    files = sorted(vdir.glob(f"{Path(live).stem}.*.json"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    protect = _protected(load_pointer(live))
    removed = []
    for path in files[keep:]:
        if path.name in protect:
            continue
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def _find_version(live: Path, version: str) -> dict | None:
    ptr = load_pointer(live) or {}
    for entry in reversed(ptr.get("history") or []):
        for cand in (entry, entry.get("previous")):
            if cand and cand.get("version") == version:
                return _ref(cand)
    vdir = _paths(live)[0]
    path = vdir / f"{Path(live).stem}.{version}.json"
    if path.exists():
        data = path.read_bytes()
        return {"version": version, "file": f"{vdir.name}/{path.name}",
                "sha256": hashlib.sha256(data).hexdigest(), "as_of": version.rsplit("-", 1)[0]}
    return None


def rollback(live: Path, *, to_version: str, reason: str, evidence: dict | None = None,
             now: datetime | None = None) -> dict:
    """指針指返 `to_version` 並鎖定（`pinned`）。唔刪任何版本檔。→ 新指針。"""
    live = Path(live)
    moment = _now(now)
    ptr = load_pointer(live)
    if not ptr:
        raise ValueError("冇版本指針，冇嘢可以回退")
    target = _find_version(live, to_version)
    if not target:
        raise ValueError(f"搵唔到版本 {to_version}")
    data = version_file(live, target["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != target["sha256"]:
        raise ValueError(f"版本 {to_version} sha256 唔對，唔回退")
    current = _ref(ptr)
    event = {"event": "rollback", "at": moment.isoformat(), "from": current["version"], "to": to_version,
             "reason": reason, "evidence": evidence or {}}
    new_ptr = {**ptr, **target, "activated_at": moment.isoformat(), "activated_on": _sydney_date(moment),
               "previous": current, "pinned": True, "rolled_back_from": current, "rollback": event,
               "history": (list(ptr.get("history") or []) + [{**target, **event, "shadow": "not_needed"}])[-HISTORY_KEEP:]}
    _write_pointer(live, new_ptr)
    write_event(live, event)
    return new_ptr


def unpin(live: Path, *, actor: str, now: datetime | None = None) -> dict:
    """解除鎖定並啟用最新存咗嘅版本（照常記「有冇改寫歷史」，改寫咗就照樣排 shadow）。"""
    live = Path(live)
    ptr = load_pointer(live)
    if not ptr or not ptr.get("pinned"):
        return {"action": "not_pinned"}
    vdir = _paths(live)[0]
    files = sorted(vdir.glob(f"{live.stem}.*.json"), key=lambda p: (p.stat().st_mtime, p.name))
    _write_pointer(live, {**ptr, "pinned": False})
    write_event(live, {"at": _now(now).isoformat(), "event": "unpinned", "actor": actor})
    if not files:
        return {"action": "unpinned"}
    latest = files[-1]
    data = latest.read_bytes()
    as_of = json.loads(data.decode("utf-8")).get("as_of")
    return {"action": "unpinned", "activation": commit(live, data, as_of=as_of, now=now)}


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from au_racing_engine.people_overlays import live_table_path

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("status", "unpin", "rollback"))
    ap.add_argument("--table", default=None, help="live 表路徑（預設練馬師剩餘表現表）")
    ap.add_argument("--to", default=None)
    ap.add_argument("--reason", default="manual")
    ap.add_argument("--actor", default="manual")
    args = ap.parse_args(argv)
    live = Path(args.table) if args.table else live_table_path()
    if args.action == "status":
        ptr = load_pointer(live) or {}
        out = {k: ptr.get(k) for k in ("version", "as_of", "activated_on", "pinned")}
        out["pending_shadow"] = [e["version"] for e in ptr.get("history") or [] if e.get("shadow") == "pending"]
    elif args.action == "unpin":
        out = unpin(live, actor=args.actor)
    else:
        if not args.to:
            ap.error("rollback 要 --to <version>")
        out = {k: v for k, v in rollback(live, to_version=args.to, reason=args.reason).items() if k != "history"}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
