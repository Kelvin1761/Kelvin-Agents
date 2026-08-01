#!/usr/bin/env python3
"""由一句話搵返 AU meeting 目錄 —— 令「analyse / review 08-01 rosehill gardens」
唔使貼任何 URL 或者路徑。

點解要呢個：`au_wong_choi`（分析）同 `au_reflector`（覆盤）兩邊都收「meeting 目錄」，
但用戶手上只有「08-01 rosehill gardens」呢類講法。以前要人手貼路徑或者 Racenet
連結，所以兩個 skill 用落好似兩件事。有咗呢個 resolver，兩邊就係同一個入口。

匹配規則（刻意保守 —— 撞錯馬場好過靜靜咁分析錯一個）：
  * 日期：接受 08-01 / 8-1 / 2026-08-01 / 20260801；冇年份就當今年，
    但如果今年搵唔到而舊年有，會回舊年嗰個。
  * 馬場：大小寫無關嘅子字串，`Rosehill` 對得住 `Rosehill Gardens`。
  * 同時搵 live 根目錄同 Archive/。
  * **多過一個 match 就唔猜** —— 列晒出嚟叫人揀。

用法：
    python3 au_meeting_resolver.py "08-01 rosehill gardens"
    python3 au_meeting_resolver.py "rosehill" --list
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def _roots():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from wongchoi_paths import AU_RACING

    root = Path(AU_RACING)
    out = [root]
    arch = root / "Archive"
    if arch.exists():
        out.append(arch)
    return out


def all_meetings():
    seen, out = set(), []
    for root in _roots():
        try:
            entries = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            continue
        for p in entries:
            if p.name == "Archive" or p.name in seen:
                continue
            if not re.match(r"\d{4}-\d{2}-\d{2}", p.name):
                continue
            seen.add(p.name)
            out.append(p)
    return out


def _dates_in(phrase):
    """由句子抽出可能嘅 YYYY-MM-DD。冇年份就試今年同舊年。"""
    out = []
    m = re.search(r"(20\d{2})[-/]?(\d{1,2})[-/]?(\d{1,2})", phrase)
    if m:
        out.append(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})\b", phrase)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        y = date.today().year
        # 08-01 慣常讀成「月-日」，但 1-8 呢類就兩邊都試
        for mm, dd in ({(a, b), (b, a)} if a <= 12 and b <= 12 else {(a, b)}):
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                out += [f"{y}-{mm:02d}-{dd:02d}", f"{y-1}-{mm:02d}-{dd:02d}"]
    return out


def resolve(phrase, meetings=None):
    """回傳 (matches, reason)。matches 係 Path list —— 唔止一個就唔好猜。"""
    meetings = meetings if meetings is not None else all_meetings()
    text = phrase.lower()
    dates = _dates_in(phrase)
    # 剩返嘅字當馬場名（去走日期同指令動詞）
    words = [w for w in re.findall(r"[a-z]{3,}", text)
             if w not in {"analyse", "analyze", "review", "the", "race", "races",
                          "meeting", "and", "for", "run", "please", "gardens"}]
    cand = meetings
    if dates:
        cand = [p for p in cand if any(p.name.startswith(d) for d in dates)]
    if words:
        cand = [p for p in cand if all(w in p.name.lower() for w in words)] or \
               [p for p in cand if any(w in p.name.lower() for w in words)]
    if not cand:
        return [], f"搵唔到（日期 {dates or '未指定'}，馬場關鍵字 {words or '未指定'}）"
    if len(cand) == 1:
        return cand, "唯一匹配"
    return cand, f"{len(cand)} 個匹配 —— 唔猜，請指明"


def main():
    ap = argparse.ArgumentParser(description="由一句話搵 AU meeting 目錄")
    ap.add_argument("phrase", nargs="*", help='例："08-01 rosehill gardens"')
    ap.add_argument("--list", action="store_true", help="列出全部 meeting")
    args = ap.parse_args()
    if args.list or not args.phrase:
        for p in all_meetings():
            print(p.name)
        return 0
    matches, why = resolve(" ".join(args.phrase))
    if len(matches) == 1:
        print(matches[0])
        return 0
    print(f"⚠️ {why}", file=sys.stderr)
    for p in matches:
        print(f"   {p.name}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
