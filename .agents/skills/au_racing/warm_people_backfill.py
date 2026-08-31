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
import html as _html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from claw_sportsbet_form import BASE, CACHE_DIR  # noqa: E402
from sb_browser_fetch import BrowserFetcher, cache_path  # noqa: E402


# 個人頁**本身冇名字** —— 佢係純統計表片段（`<div class="facebox-fixed-container">`
# 加幾張表），冇 title / h1 / og:title。所以名字唯一嘅來源係賽事頁嗰個連結。
#
# ⚠️ 用 `title=` 屬性，唔好用 anchor 文字：anchor 會截短
# （`Ben, Will & Jd ...`），`title` 係全名（`Ben, Will & Jd Hayes - Career
# Statistics`）。而且一定要 `html.unescape` —— 合夥練馬師名含 `&`，
# 剝 tag 之後 `&amp;` 會變 `amp`（見 [[au-html-entity-breaks-name-matching]]）。
PERSON_LINK_RE = re.compile(
    r'href="/(?P<kind>Jockey|Trainer)/(?P<pid>\d+)/"\s+title="(?P<name>[^"]*?)\s*-\s*Career Statistics"'
)


def _iter_cached_pages():
    for page in Path(CACHE_DIR).glob("*.html"):
        try:
            yield page.read_text(errors="replace")
        except OSError:
            continue


def person_names() -> dict[tuple[str, str], str]:
    """{(kind, id): 名字} —— 由已 cache 嘅賽事頁抽，零請求。"""
    out: dict[tuple[str, str], str] = {}
    for html_text in _iter_cached_pages():
        for m in PERSON_LINK_RE.finditer(html_text):
            name = _html.unescape(m.group("name")).strip()
            if name:
                out.setdefault((m.group("kind"), m.group("pid")), name)
    return out


def wanted(limit: int) -> list[tuple[str, str, int, str]]:
    """(kind, id, 出現次數, 名字)，按出現次數由高到低，只回未落 cache 嘅。

    2026-09-01：加返**名字**。之前 `refresh()` 收到嘅係硬寫嘅 `""`，所以
    `AU_Sportsbet_People_Cache.json` 全部 2,255 個人同 4,374 行快照嘅 `name`
    都係空 —— 一個 id-only 資料庫，將來要按名 join 就用唔到。
    """
    seen: collections.Counter = collections.Counter()
    names: dict[tuple[str, str], str] = {}
    for html_text in _iter_cached_pages():
        for m in PERSON_LINK_RE.finditer(html_text):
            key = (m.group("kind"), m.group("pid"))
            seen[key] += 1
            name = _html.unescape(m.group("name")).strip()
            if name:
                names.setdefault(key, name)
        # 舊 pattern 做 fallback：有啲頁面 title 缺失，但 id 仍然要數。
        for kind, pid in re.findall(r'href="/(Jockey|Trainer)/(\d+)/"', html_text):
            seen.setdefault((kind, pid), 0)
            if seen[(kind, pid)] == 0:
                seen[(kind, pid)] = 1
    todo = [(k, i, n, names.get((k, i), "")) for (k, i), n in seen.most_common()
            if not cache_path(f"{BASE}/{k}/{i}/").exists()]
    return todo[:limit] if limit else todo


def backfill_names(apply: bool) -> int:
    """把名字寫返已存在嘅 people cache（零請求）。

    `--backfill-names` 存在嘅原因：合併係就地改，而 cache 已經有 2,255 個
    無名記錄；重跑 `refresh` 唔會修佢哋（頁面已落 cache 就唔會再處理）。
    """
    import sb_people_stats

    names = person_names()
    print(f"由賽事頁抽到 {len(names)} 個 (kind,id) → 名字")
    cache = sb_people_stats.load_cache()
    filled = already = missing = 0
    for key, entry in cache.items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("name") or "").strip():
            already += 1
            continue
        kind, _, pid = str(key).partition("|")
        name = names.get((kind.title(), pid)) or names.get((kind.capitalize(), pid))
        if name:
            entry["name"] = name
            filled += 1
        else:
            missing += 1
    print(f"cache {len(cache)} 條｜本來有名 {already}｜補到 {filled}｜仍然冇名 {missing}")
    if not apply:
        print("dry run —— 冇寫入。加 --apply 落實")
        return 0
    if not filled:
        print("冇嘢要補。")
        return 0
    path = Path(sb_people_stats.cache_path())
    backup = path.with_suffix(f".json.bak_names")
    if path.exists():
        backup.write_bytes(path.read_bytes())
        print(f"備份：{backup.name}")
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"✅ 寫入 {path.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="補齊騎練個人頁（真瀏覽器）")
    ap.add_argument("--delay", type=float, default=20.0)
    ap.add_argument("--limit", type=int, default=0, help="0 = 全部")
    ap.add_argument("--backfill-names", action="store_true",
                    help="只補名字（零請求，讀已 cache 嘅賽事頁）")
    ap.add_argument("--apply", action="store_true", help="配 --backfill-names 用")
    args = ap.parse_args()

    if args.backfill_names:
        return backfill_names(args.apply)

    todo = wanted(args.limit)
    print(f"要補 {len(todo)} 個個人頁 @ {args.delay:.0f} 秒 ≈ "
          f"{len(todo) * args.delay / 3600:.1f} 個鐘", flush=True)
    done = 0
    with BrowserFetcher(delay=args.delay) as bf:
        for kind, pid, hits, _name in todo:
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
    for kind, pid, _hits, name in todo[:done]:
        people.append((kind, pid, name))
    if people:
        sb_people_stats.refresh(people, cache_only=True, max_people=len(people))
        cache = sb_people_stats.load_cache()
        with_ly = sum(1 for v in cache.values()
                      if isinstance(v, dict) and (v.get("ly") or "-") != "-")
        print(f"people cache 而家 {len(cache)} 條，有 ly {with_ly}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
