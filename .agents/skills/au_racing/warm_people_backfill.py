#!/usr/bin/env python3
"""補齊所有澳洲馬場嘅騎練個人頁，令 `(LY:)` 同騎練評分唔再靠「中性 60」頂住。

點解需要：2026-08-05 實測 —— Hobart `(LY:)` 覆蓋率 23.1%，於是 **78.0% 嘅馬騎師分
剛好 60、75.8% 練馬師分剛好 60**；Canterbury 覆蓋率 98.2%，剛好 60 嘅比率係 0.0%
同 3.5%。即係「屬中性配置」其實係「冇官方記錄」—— 一個缺數據被顯示成中性判斷。
people cache 由大城市場次砌起，塔斯馬尼亞／西澳／南澳嘅騎練從來冇抓過。

做法：由**已 cache 嘅賽事頁**抽 `/Jockey/{id}/`、`/Trainer/{id}/`，按出現次數排序
（頻率極度傾斜，所以排好序之後幾時停都係「用嗰段時間攞到最好嘅覆蓋」），逐個
經真 Chrome 落 cache。之後 `sb_people_stats.refresh(cache_only=True)` 讀返。

⚠️ 全程守原本嘅網絡紀律：預設 20 秒一版、撞到穩定非 200 即刻停低唔重試。
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from claw_sportsbet_form import BASE, CACHE_DIR  # noqa: E402
from sb_browser_fetch import BrowserFetcher, cache_path  # noqa: E402


def wanted(limit: int) -> list[tuple[str, str, int]]:
    """(kind, id, 出現次數)，按出現次數由高到低，只回未落 cache 嘅。"""
    seen: collections.Counter = collections.Counter()
    for page in Path(CACHE_DIR).glob("*.html"):
        try:
            html = page.read_text(errors="replace")
        except OSError:
            continue
        for kind, pid in re.findall(r'href="/(Jockey|Trainer)/(\d+)/"', html):
            seen[(kind, pid)] += 1
    todo = [(k, i, n) for (k, i), n in seen.most_common()
            if not cache_path(f"{BASE}/{k}/{i}/").exists()]
    return todo[:limit] if limit else todo


def main() -> int:
    ap = argparse.ArgumentParser(description="補齊騎練個人頁（真瀏覽器）")
    ap.add_argument("--delay", type=float, default=20.0)
    ap.add_argument("--limit", type=int, default=0, help="0 = 全部")
    args = ap.parse_args()

    todo = wanted(args.limit)
    print(f"要補 {len(todo)} 個個人頁 @ {args.delay:.0f} 秒 ≈ "
          f"{len(todo) * args.delay / 3600:.1f} 個鐘", flush=True)
    done = 0
    with BrowserFetcher(delay=args.delay) as bf:
        for kind, pid, hits in todo:
            if bf.get(f"{BASE}/{kind}/{pid}/"):
                done += 1
                if done % 10 == 0:
                    print(f"   {done}/{len(todo)}", flush=True)
                continue
            print(f"⛔ 停手：{bf.stop_reason}", flush=True)
            break
    print(f"完成 {done}/{len(todo)}", flush=True)

    # 即刻把新頁面轉換入 people cache（cache-only，零請求）
    import sb_people_stats
    people = []
    for kind, pid, _ in todo[:done]:
        people.append((kind, pid, ""))
    if people:
        sb_people_stats.refresh(people, cache_only=True, max_people=len(people))
        cache = sb_people_stats.load_cache()
        with_ly = sum(1 for v in cache.values()
                      if isinstance(v, dict) and (v.get("ly") or "-") != "-")
        print(f"people cache 而家 {len(cache)} 條，有 ly {with_ly}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
