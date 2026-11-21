#!/usr/bin/env python3
"""由 Sportsbet cache 生成 `au_archive_calibrator` 食嘅歷史賽果 CSV。

點解需要：`au_runtime_micro_ablation.py`、`au_archive_calibrator.py` 同一系列
離線工具全部要一個 `--results-csv`，而現有嗰個係 Racenet 年代嘅產物。要喺
Sportsbet 語料上跑任何 ablation 或者重配權，就要一個由 Sportsbet 生成、
覆蓋同一批場次嘅賽果檔。

⚠️ 賽果由**每匹馬往績嘅第一行**嚟（`Finished 3/11 0.42L`）—— 即係
`claw_sportsbet_form.write_meeting` 為咗防洩漏而特意丟走嗰行。
**做標準答案啱，做評分輸入唔啱**，同 `au_source_compare.results_from_cache`
同一個道理。呢個檔只准喺評分完成之後 join，唔可以入 race_context。

全程讀 cache，零網絡請求。

用法：
    python3 sb_results_csv.py --out /tmp/sb_results.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FIELDS = ("Date", "Track", "Race", "Distance", "Condition", "Pos", "Horse",
          "Barrier", "Weight", "Jockey", "Trainer", "Margin", "SP", "Time")


def track_key(value):
    """Conservative venue identity; retain different course/layout qualifiers."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


# 首戰馬嘅往績標題係「First Start Moe」，唔係「Moe」。2026-10-13 實測
# 2026-07 → 10 有 17 行真實賽果因此被當成「場地唔對」跳走。只剝呢一個前綴 ——
# 「Barrier Trial Pakenham Synthetic」係試閘，唔係呢場賽果，一定要繼續拒絕。
_DEBUT_PREFIX = re.compile(r"^\s*first\s+start\s+", re.I)


def same_venue(header_track, meeting_track) -> bool:
    """往績標題場地係咪就係呢個場次。空白一律當唔係。"""
    header = track_key(_DEBUT_PREFIX.sub("", str(header_track or "")))
    return bool(header) and header == track_key(meeting_track)


def iso_date(value: str) -> str:
    """Argparse validator; keeping the normalised ISO string makes comparisons cheap."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日期要用 YYYY-MM-DD：{value}") from exc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="由 cache 生成歷史賽果 CSV")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--from-date",
        type=iso_date,
        help="只處理呢日或之後嘅 meeting；避免 daily ingest 每晚重掃完整 cache",
    )
    ap.add_argument("--mapping", type=Path,
                    help="自訂 meeting-ID mapping；預設用現役 AU data mapping")
    ap.add_argument("--memo", type=Path,
                    help="逐場次結果 memo（JSON）。cache 檔同解析 code 都冇變嘅場次直接重用，"
                         "唔再 parse HTML；輸出 CSV 逐 byte 一樣")
    return ap


# ── 逐場次 memo ─────────────────────────────────────────────────────────────
# 點解：晚更 `ingest-results` 每次都由 2026-07-01 起重新 parse ~5,100 場 cache，
# 2026-11-21 實測每次 ~15 分鐘 CPU，而結果係「new rows to add: 0」，夜更重試
# 一晚仲可以行三次。cache 頁一經寫低極少再變，所以逐場次記住結果就得。
#
# 失效條件（任何一樣變咗就重新 parse 嗰個場次）：
#   * 解析 code：本檔 + `claw_sportsbet_form.py` 嘅內容、bs4 版本、Python 版本
#     （`parse_race`／`parse_runner_blocks`／`run_date` 只依賴呢幾樣，2026-11-21
#     用 AST 追過）；
#   * 場次 meta（meetingId、日期、slug、races 列表）；
#   * 每個 race cache 檔存唔存在、mtime_ns、大細。
# memo 讀唔到／壞咗 = 當冇 memo，全部重新 parse —— 永遠唔會因為 memo 輸出唔同嘢。
MEMO_VERSION = 1


def code_fingerprint() -> str:
    import hashlib
    here = Path(__file__).resolve().parent
    h = hashlib.sha256(f"v{MEMO_VERSION}|{sys.version_info[:2]}".encode())
    for name in ("sb_results_csv.py", "claw_sportsbet_form.py"):
        h.update(name.encode())
        h.update((here / name).read_bytes())
    try:
        import bs4
        h.update(f"bs4={bs4.__version__}".encode())
    except ImportError:
        h.update(b"bs4=missing")
    return h.hexdigest()


def meeting_signature(meta, fetcher) -> str:
    from claw_sportsbet_form import BASE
    files = []
    for rid in meta["races"]:
        cp = fetcher._cache_path(f"{BASE}/{meta['meetingId']}/{rid}/")
        try:
            st = cp.stat()
            files.append([str(rid), st.st_mtime_ns, st.st_size])
        except OSError:
            files.append([str(rid), None, None])
    return json.dumps([meta.get("meetingId"), meta.get("date"), meta.get("slug"),
                       files], ensure_ascii=False, separators=(",", ":"))


def load_memo(path: Path | None, fingerprint: str) -> dict:
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("fingerprint") != fingerprint:
        return {}
    meetings = data.get("meetings")
    return meetings if isinstance(meetings, dict) else {}


def save_memo(path: Path | None, fingerprint: str, meetings: dict) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"fingerprint": fingerprint, "meetings": meetings},
                                  ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        # memo 只係加速；寫唔到唔可以令 ingest 失敗。
        print(f"⚠️ memo 寫唔到（下次照全部重新 parse）：{exc}", file=sys.stderr)


def meeting_items(ids: dict, from_date: str | None = None):
    """Return deterministically ordered meetings, optionally bounded by race date."""
    items = sorted(ids.items(), key=lambda kv: str(kv[1].get("date") or ""))
    if from_date:
        items = [item for item in items
                 if str(item[1].get("date") or "") >= from_date]
    return items


def _warn_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def rows_for_meeting(meta, fetcher, warn=_warn_stderr):
    """→ 每個跑手一行。淨讀 cache；未抽過嘅場次直接跳。"""
    from claw_sportsbet_form import (BASE, parse_race, parse_runner_blocks,
                                     run_date)

    track = meta["slug"].replace("_", " ").title()
    out = []
    for rid in meta["races"]:
        url = f"{BASE}/{meta['meetingId']}/{rid}/"
        if not fetcher._cache_path(url).exists():
            continue
        html = fetcher.get(url)
        pr = parse_race(html)
        rno = pr["meta"].get("race_number")
        if rno is None:
            continue
        cond = pr["meta"].get("track_condition") or ""
        # Only the dated result run supplies historical runner metadata.
        # An alternate entry can run at another venue on the same date/race.
        # Overview has no historical barrier and current Trainer is not dated.
        for blk in parse_runner_blocks(html):
            for run in blk.get("runs", []):
                h = run.get("header") or {}
                if run_date(run) != meta["date"] or str(h.get("race")) != str(rno):
                    continue
                if not same_venue(h.get("track"), track):
                    warn(f"⚠️ result venue mismatch: {meta['date']} {track} R{rno} "
                         f"{blk['name']} -> {h.get('track')!r}; row skipped")
                    continue
                try:
                    pos = int(run["pos"])
                except (TypeError, ValueError, KeyError):
                    break
                out.append({"Date": meta["date"], "Track": track, "Race": rno,
                            "Horse": blk["name"], "Pos": pos,
                            "Distance": h.get("dist") or "",
                            "Barrier": run.get("barrier") or "",
                            "Weight": run.get("weight") or "",
                            "Jockey": (run.get("jockey") or "").strip(),
                            "Trainer": "",  # Dated run has no trainer; never use current overview.
                            "Margin": "0" if pos == 1 else (run.get("margin") or ""),
                            "Time": "",  # WinningTime is not this runner's Time.
                            "SP": run.get("sp") or "", "Condition": cond})
                break
    return out


def main():
    args = build_parser().parse_args()

    from claw_sportsbet_form import SportsbetFormFetcher
    from sb_backfill_archive import load_meeting_ids

    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    ids = load_meeting_ids(args.mapping) if args.mapping else load_meeting_ids()
    fingerprint = code_fingerprint() if args.memo else ""
    memo = load_memo(args.memo, fingerprint)
    new_memo: dict = {}
    reused = parsed = 0
    rows, meetings = [], 0
    for name, meta in meeting_items(ids, args.from_date):
        sig = meeting_signature(meta, f) if args.memo else ""
        hit = memo.get(name)
        if args.memo and isinstance(hit, dict) and hit.get("sig") == sig:
            got, warnings = hit.get("rows") or [], hit.get("warnings") or []
            for message in warnings:
                _warn_stderr(message)
            reused += 1
        else:
            warnings = []

            def collect(message, _sink=warnings):
                _sink.append(message)
                _warn_stderr(message)

            got = rows_for_meeting(meta, f, warn=collect)
            parsed += 1
        if args.memo:
            new_memo[name] = {"sig": sig, "rows": got, "warnings": warnings}
        if got:
            meetings += 1
            rows += got
    if args.memo:
        save_memo(args.memo, fingerprint, new_memo)
        print(f"memo：重用 {reused} 個場次、重新 parse {parsed} 個")
    if not rows:
        print("❌ cache 冇任何賽果 —— 先跑抽取")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    races = len({(r["Date"], r["Race"], r["Track"]) for r in rows})
    scope = f"（{args.from_date} 起）" if args.from_date else ""
    print(f"✅ {meetings} 場次 / {races} 場 / {len(rows)} 個跑手{scope} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
