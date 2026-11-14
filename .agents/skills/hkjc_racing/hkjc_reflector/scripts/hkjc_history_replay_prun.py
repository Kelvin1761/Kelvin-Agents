"""HKJC 歷史回放：按季並行跑 harness（每季一個 process），再合併成一個 dump。

單一 process 跑 6,000 場要 ~2 個鐘；按季分 8 份、6 個並行約 20–30 分鐘。結果同單一 process 一樣
（harness 逐賽日獨立評分、PIT 騎練評分逐賽日 as-of，唔受分割影響）。
用法：python3 hkjc_history_replay_prun.py --meeting-root <replay_all> --out <dump.jsonl> [--arm <arm.py>] [--jobs 6]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_HERE = Path(__file__).resolve()
EVAL = _HERE.parent / "hkjc_history_replay_eval.py"
SEASONS = [(f"{y}-08-01", f"{y + 1}-07-31") for y in range(2019, 2027)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arm")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.out)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def one(win):
        part = out.with_suffix(f".{win[0][:4]}.part")
        cmd = [sys.executable, str(EVAL), "run", "--meeting-root", a.meeting_root, "--since", win[0], "--until", win[1],
               "--dump-matrix", "--out", str(part)]
        if a.arm:
            cmd += ["--arm", a.arm]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        return win, part, r.returncode, r.stderr[-800:]

    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, SEASONS))
    bad = [(w, e) for w, _, rc, e in res if rc != 0]
    if bad:
        for w, e in bad:
            print(f"❌ {w}: {e}", file=sys.stderr)
        sys.exit(1)
    with open(out, "w", encoding="utf-8") as fh:
        for _, part, _, _ in res:
            if part.exists():
                fh.write(part.read_text(encoding="utf-8"))
                part.unlink()
    print(f"合併 → {out}")


if __name__ == "__main__":
    main()
