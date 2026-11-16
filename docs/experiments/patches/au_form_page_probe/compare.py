#!/usr/bin/env python3
"""對照測試：sportsbetform `/form/<CODE>.html`（curl_cffi，唔使瀏覽器）vs
瀏覽器抓落 cache 嘅 `/{meetingId}/{raceId}/` 賽事頁。

兩邊都行同一個 `parse_race()`，逐項比較 meta / overview / runs。
抓取守現有規矩：每版隔 --delay 秒，撞到非 200 或者細過 MIN_BYTES 即停，唔重試。

用法：
    python3 compare.py --date 2026-11-16 --venues Goulburn Wangaratta \
        --cache <scheduler>/.agents/skills/au_racing/.sportsbet_cache --out <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
AU = HERE.parents[4] / ".agents" / "skills" / "au_racing"
sys.path.insert(0, str(AU))
from claw_sportsbet_form import parse_race  # noqa: E402
from curl_cffi import requests  # noqa: E402

API = "https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/Racing/"
MIN_BYTES = 5000
VOLATILE_META = {"odds"}  # 瀏覽器 render 先有，/form/ 頁冇；另由 API 補


def walk(o, pred, out):
    if isinstance(o, dict):
        if pred(o):
            out.append(o)
        for v in o.values():
            walk(v, pred, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, pred, out)
    return out


def norm(x):
    if isinstance(x, dict):  # people_names 用 tuple 做 key
        return {str(k): norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [norm(v) for v in x]
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def runner_key(parsed):
    return frozenset(str(v.get("name", "")).strip().lower()
                     for v in parsed["overview"].values() if isinstance(v, dict))


def diff(a, b, path="", out=None, limit=40):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: {'只有瀏覽器' if k in a else '只有 /form/'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: 長度 {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--venues", nargs="+", required=True)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--delay", type=float, default=25.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    s = requests.Session(impersonate="chrome120")
    log = []

    def note(msg):
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        log.append(line)

    # 1. 今日賽事（主站 API，NBA／網球用緊嗰類）
    allr = s.get(API + f"AllRacing/{args.date}", timeout=30).json()
    meetings = walk(allr, lambda o: o.get("name") in args.venues and "events" in o, [])
    events = [(m["name"], e) for m in meetings for e in m["events"]]
    note(f"{len(events)} 場：{[m['name'] for m in meetings]}")

    # 2. 瀏覽器 cache：今日寫過嘅賽事頁，按馬名索引
    day0 = datetime.strptime(args.date, "%Y-%m-%d").timestamp() - 86400
    cached = {}
    for f in args.cache.iterdir():
        if f.suffix != ".html" or f.stat().st_mtime < day0:
            continue
        try:
            p = parse_race(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        if p["runs"] and p["overview"]:
            k = runner_key(p)
            if k and (k not in cached or f.stat().st_mtime > cached[k][0]):
                cached[k] = (f.stat().st_mtime, f, p)
    note(f"瀏覽器 cache 今日賽事頁：{len(cached)}")

    results, fetched, stop = [], 0, None
    for venue, ev in events:
        if stop:
            break
        tag = f"{venue} R{ev.get('raceNumber')}"
        time.sleep(3)
        try:
            rc = s.get(API + f"Events/{ev['id']}/RacecardWithContext", timeout=30)
        except Exception as exc:  # noqa: BLE001 — 網絡問題唔係個站拒絕
            note(f"{tag}: API 網絡錯誤 {type(exc).__name__}，跳過")
            results.append({"race": tag, "status": "api-network-error"})
            continue
        if rc.status_code != 200:
            note(f"{tag}: API {rc.status_code}，跳過")
            continue
        link = rc.json().get("racecardEvent", {}).get("longFormLink")
        if not link:
            note(f"{tag}: 冇 longFormLink")
            continue
        saved = args.out / f"{venue}_R{ev.get('raceNumber')}.html"
        if saved.exists():  # 上一次已經抓咗，唔再出網
            body = saved.read_bytes()
        else:
            if fetched:
                time.sleep(args.delay)
            try:
                r = s.get(link, timeout=30)
            except Exception as exc:  # noqa: BLE001
                note(f"{tag}: /form/ 網絡錯誤 {type(exc).__name__}，跳過")
                results.append({"race": tag, "status": "form-network-error"})
                continue
            fetched += 1
            if r.status_code != 200 or len(r.content) < MIN_BYTES:
                stop = f"{tag}: {r.status_code} {len(r.content)}B（第 {fetched} 版）"
                note("⛔ 個站拒絕，停 —— " + stop)
                break
            body = r.content
            saved.write_bytes(body)
        mob = parse_race(body.decode("utf-8", errors="replace"))
        k = runner_key(mob)
        best = max(cached, key=lambda c: len(c & k) / max(1, len(c | k)), default=None)
        if not best or len(best & k) / max(1, len(best | k)) < 0.8:
            note(f"{tag}: 200，cache 搵唔到對應頁")
            results.append({"race": tag, "status": "no-cache-match"})
            continue
        _, cf, brw = cached[best]
        def strip(p):
            # fixed_win 同 meta.odds 一樣：要 JS render 先有，另由 API 補
            ov = {n: {k3: v3 for k3, v3 in r.items() if k3 != "fixed_win"}
                  for n, r in p["overview"].items()}
            return norm({"meta": {k2: v for k2, v in p["meta"].items() if k2 not in VOLATILE_META},
                         "overview": ov, "runs": p["runs"]})
        a, b = strip(brw), strip(mob)
        d = diff(a, b)
        results.append({"race": tag, "status": "same" if not d else "diff",
                        "cache_file": cf.name, "runs": [len(brw["runs"]), len(mob["runs"])],
                        "in_running": [sum(bool(x.get("p800") or x.get("settled")) for x in brw["runs"]),
                                       sum(bool(x.get("p800") or x.get("settled")) for x in mob["runs"])],
                        "diffs": d})
        note(f"{tag}: 200 {len(body)}B  {'一致' if not d else f'{len(d)} 處唔同'}  "
             f"往績 {len(brw['runs'])}/{len(mob['runs'])}")

    summary = {"date": args.date, "fetched": fetched, "stop": stop, "results": results, "log": log}
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    same = sum(r["status"] == "same" for r in results)
    note(f"完成：抓 {fetched} 版，{same}/{len(results)} 場完全一致，stop={stop}")


if __name__ == "__main__":
    main()
