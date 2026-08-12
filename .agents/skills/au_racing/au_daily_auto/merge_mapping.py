#!/usr/bin/env python3
"""把對應表（meeting ID mapping）做並集合併，唔好用 git checkout 抹走。

⚠️ 呢個檔係「已追蹤 + 每次 run 寫入」嘅組合，所以 fast-forward 之前唔可以簡單
還原佢。2026-08-12 實測：自動更新步驟做 `git checkout --` 抹走咗補跑辛苦抽返嘅
五個場次嘅 meeting ID，於是 10:00 覆核全部報「對應表冇呢個場次」，退出馬同場地
變化一個都覆核唔到。

當時我嘅註解寫「掉咗唔會錯，只係要再 derive 一次」—— 錯。覆盤路徑會由索引頁
重新推導，覆核路徑唔會，佢直接放棄。

並集係安全嘅：key 係場次夾名，同一個 key 兩邊內容一樣（都係由同一版索引頁推導）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def merge(local: Path, incoming: Path) -> tuple[int, int]:
    def load(p):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    a, b = load(local), load(incoming)
    added = [k for k in a if k not in b]
    out = dict(b)
    out.update(a)   # 本機新寫入嘅優先保留
    local.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return len(added), len(out)


def main() -> int:
    if len(sys.argv) < 3:
        print("用法：merge_mapping.py <本機檔> <git 版本檔>")
        return 2
    kept, total = merge(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"對應表合併：保住本機 {kept} 個新場次，共 {total} 條")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
