#!/usr/bin/env python3
"""EXP-20261121-33：由每場賽前 Facts 讀生涯「同程」「同場同程」紀錄（同 tags.py 首本路程同一個來源）。

    features.py OUT.json        → {"meeting|race|n": {"dist": "4:0-3-0", "vdist": "1:0-1-0"}}
"""
import glob, json, re, sys
from pathlib import Path
W = Path(__file__).resolve().parents[4]
ROOT = open(W / ".wongchoi_au_data_root").read().strip()
HEAD = re.compile(r"^### 馬匹 #(\d+)\b", re.M)
STATS = re.compile(r"同場:\s*([^|\n]*)\|\s*同程:\s*([^|\n]*)\|\s*同場同程:\s*([^\n]*)")


def main(out):
    table = {}
    dirs = glob.glob(ROOT + "/2026-*") + glob.glob(ROOT + "/Archive/**/2026-*", recursive=True)
    for d in sorted(set(dirs)):
        name = Path(d).name
        if name[:10] < "2026-08-05" or not Path(d).is_dir():
            continue
        for f in glob.glob(d + "/* Race * Facts.md"):
            m = re.search(r" Race (\d+) Facts\.md$", f)
            if not m:
                continue
            text = Path(f).read_text(encoding="utf-8", errors="replace")
            heads = list(HEAD.finditer(text))
            for i, h in enumerate(heads):
                block = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
                s = STATS.search(block)
                if s:
                    table[f"{name}|{m.group(1)}|{h.group(1)}"] = {"dist": s.group(2).strip(), "vdist": s.group(3).strip()}
    Path(out).write_text(json.dumps(table))
    print(len(table))


if __name__ == "__main__":
    main(sys.argv[1])
