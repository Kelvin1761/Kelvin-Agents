#!/usr/bin/env python3
"""一個賽日嘅覆盤推送 —— 逐個馬場，列出頭兩揀邊隻真係入到前三。

⚠️ **揀馬名單一律由覆盤報告讀，唔可以自己再由排名表推一次。** 2026-08-09 實測：
我另寫咗個 script 由 `Race_N_Auto_Analysis.md` 嘅排名表攞頭幾揀，同覆盤報告嘅數
對唔上 —— 錯嘅係我：覆盤會**先剔走冇出賽嘅馬再重新排名**，我冇剔，於是攞住三匹
退出馬當自己嘅揀馬去評分，白白扣自己分。呢個檔淨係讀已經計好嘅結果。

賠率有兩個，係兩件事，唔可以混：
  * **SP** —— 賽果檔入面，開跑一刻嘅官方贏馬賠率。
  * **賽前位賠** —— Formguide 入面 `PlcOdds`，我哋分析嗰陣捕捉嘅市場位置賠率。
    冇賽後版本，因為位置賠率唔會有 SP。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RE_LABEL = re.compile(r"^## Race (\d+)\s*$\n- Performance label: \*\*(.+?)\*\*", re.M)
RE_TOP3 = re.compile(r"^- Model Top 3: (.+)$", re.M)
RE_ACTUAL = re.compile(r"^- Actual Top 3: (.+)$", re.M)
# ⚠️ 頭四選一定要由 shortlist 嗰行取 —— 「Model Top 3」只有三匹，
# 由佢取「頭四」會令捉齊三甲由 11/38 跌到 2/38（實測）。
RE_SHORTLIST = re.compile(r"^- Model Top 5 shortlist: (.+)$", re.M)
RE_HORSE = re.compile(r"#(\d+)\s+([^,#]+?)(?=,|$)")
RE_ACT_ONE = re.compile(r"(\d+)\.\s*#(\d+)\s+([^,]+?)(?=,|$)")
RE_SP = re.compile(r"^(\d+)(?:st|nd|rd|th):\s*#(\d+)\s+.*?SP\$([\d.]+)", re.M)
RE_FG_HORSE = re.compile(r"^\[(\d+)\]\s", re.M)
RE_FG_ODDS = re.compile(r"WinOdds:\s*([\d.]+|-)\s+PlcOdds:\s*([\d.]+|-)")
POS = {1: "冠軍", 2: "亞軍", 3: "季軍"}
PICK = {1: "①", 2: "②"}


RE_FIELD = re.compile(r"\| 出馬數 \| (\d+) \|")


def places_paid(field: int | None) -> int:
    """一場派幾多個位。⚠️ 唔係一律頭三。

    澳洲派彩規則：8 匹或以上派三個位、5 至 7 匹派兩個位、4 匹或以下淨係贏
    （冇位置池）。所以喺一場七匹嘅賽事跑第三**根本冇入位** —— 當佢中咗就係
    報大咗自己。2026-08-09 Muswellbrook 七場入面就有兩場係短爪（6 匹同 7 匹）。

    `出馬數` 已經係扣走退出馬之後嘅數（實測同 Racecard 逐場對得上），所以直接用。
    數唔到就當三個位 —— 寧願跟返舊行為，都好過憑空猜一個細數令命中率虛高。
    """
    if not field:
        return 3
    if field >= 8:
        return 3
    if field >= 5:
        return 2
    return 1


def field_size(folder: Path, race_no: int) -> int | None:
    f = next(iter(folder.glob(f"Race_{race_no}_Auto_Analysis.md")), None)
    if not f:
        return None
    m = RE_FIELD.search(f.read_text(errors="replace"))
    return int(m.group(1)) if m else None


def place_odds(folder: Path, race_no: int) -> dict[int, str]:
    """{馬號: 賽前位賠}。Formguide 用 `[馬號] 馬名 (檔位)` 做每匹馬嘅起點。"""
    hits = list(folder.glob(f"*Race {race_no} Formguide.md"))
    if not hits:
        return {}
    body = hits[0].read_text(errors="replace")
    starts = [(m.start(), int(m.group(1))) for m in RE_FG_HORSE.finditer(body)]
    out = {}
    for i, (pos, num) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
        m = RE_FG_ODDS.search(body, pos, end)
        if m and m.group(2) != "-":
            out[num] = m.group(2)
    return out


def meeting_lines(folder: Path) -> tuple[str, dict] | None:
    rep = next(iter(folder.glob("*_Reflector_Report.md")), None)
    res = folder / "Race_Results_Reflector.md"
    if not rep or not res.exists():
        return None
    body = rep.read_text(errors="replace")
    labels = {int(n): lab for n, lab in RE_LABEL.findall(body)}
    if not labels:
        return None

    sp: dict[int, dict[int, str]] = {}
    rbody = res.read_text(errors="replace")
    for chunk in re.split(r"^## Race (\d+)\s*$", rbody, flags=re.M)[1:]:
        pass
    parts = re.split(r"^## Race (\d+)\s*$", rbody, flags=re.M)
    for i in range(1, len(parts), 2):
        sp[int(parts[i])] = {int(n): p for _, n, p in RE_SP.findall(parts[i + 1])}

    blocks = re.split(r"^## Race \d+\s*$", body, flags=re.M)[1:]
    nums = [int(n) for n, _ in RE_LABEL.findall(body)]
    hits, counts = [], {"Gold": 0, "Good": 0, "Pass": 0, "1 Hit": 0, "Miss": 0}
    top2_hit = top2_tot = 0
    both_placed: list[int] = []
    gold_direct: list[int] = []
    # 頭三選有幾隻入位 —— 呢個分佈係互斥而且加埋等於場數。
    top3_dist = {3: 0, 2: 0, 1: 0, 0: 0}
    for rno, blk in zip(nums, blocks):
        counts[labels[rno]] = counts.get(labels[rno], 0) + 1
        m3, ma = RE_TOP3.search(blk), RE_ACTUAL.search(blk)
        if not m3 or not ma:
            continue
        all3 = [(int(n), nm.strip()) for n, nm in RE_HORSE.findall(m3.group(1))][:3]
        picks = all3[:2]
        actual = {int(n): int(p) for p, n, _ in RE_ACT_ONE.findall(ma.group(1))}
        po = place_odds(folder, rno)
        fs = field_size(folder, rno)
        pays = places_paid(fs)
        top2_tot += len(picks)
        # ⚠️ 「兩隻都入位」要**直接計**，唔可以讀 Good 標籤。五個評級係互斥嘅，
        # Gold 蓋過 Good，所以一場兩隻都入位而又捉齊三甲嘅賽事只會標 Gold ——
        # 讀標籤嘅話 2026-08-09 會報 4/38，真實係 8/38，少報一半。
        placed = lambda num: (actual.get(num) is not None
                              and actual[num] <= pays)  # noqa: E731
        if len(picks) == 2 and all(placed(p[0]) for p in picks):
            both_placed.append(rno)
        # ⚠️ 捉齊三甲同兩隻都入位**各自獨立計**，一場可以同時算入兩邊。
        # 覆盤報告嗰個 `exclusive_label` 係 backtest 共用嘅尺，Gold 蓋過 Good；
        # 呢度係展示用，Kelvin 明確要兩樣都標。所以兩個數字唔可以同 backtest
        # 嘅 Good 並排比較 —— 定義唔同。
        top3_actual = {n for n, p in actual.items() if p <= 3}
        ms = RE_SHORTLIST.search(blk)
        p4 = {int(n) for n, _ in RE_HORSE.findall(ms.group(1))[:4]} if ms \
            else {p[0] for p in all3}
        if len(top3_actual) == 3 and top3_actual <= p4:
            gold_direct.append(rno)
        top3_dist[sum(1 for p in all3 if placed(p[0]))] += 1
        for idx, (num, name) in enumerate(picks, start=1):
            pos = actual.get(num)
            # ⚠️ 入位 = 名次喺派彩範圍內，唔係一律頭三。
            if pos is None or pos > pays:
                continue
            top2_hit += 1
            win = sp.get(rno, {}).get(num)
            bits = []
            if win:
                bits.append(f"贏${win}")
            if po.get(num):
                bits.append(f"位${po[num]}")
            tag = f"　⟨{fs}匹·{pays}位⟩" if pays != 3 else ""
            label = "首選" if idx == 1 else "次選"
            hits.append(f"R{rno:<2} {label} {name[:20]:20} {POS.get(pos, ''):2}"
                        + (f" {' · '.join(bits)}" if bits else "") + tag)
    venue = folder.name[11:].rsplit(" Race", 1)[0]
    pct = 100 * top2_hit / max(top2_tot, 1)
    n = len(labels)
    gold_races = sorted(gold_direct)
    good_races = sorted(both_placed)
    head = [
        f"━━ {venue} · {n} 場 ━━",
        f"捉齊三甲　　{len(gold_races)}/{n}"
        + (f"　({', '.join('R'+str(r) for r in gold_races)})" if gold_races else ""),
        f"頭兩選皆入位　{len(good_races)}/{n}"
        + (f"　({', '.join('R'+str(r) for r in good_races)})" if good_races else ""),
        f"頭兩選入位率　{top2_hit}/{top2_tot}（{pct:.0f}%）",
        f"頭三選入位　三隻 {top3_dist[3]} · 兩隻 {top3_dist[2]}"
        f" · 一隻 {top3_dist[1]} · 零隻 {top3_dist[0]}",
    ]
    body = ["", "入位馬匹"] + hits if hits else ["", "（頭兩選今場一隻都冇入位）"]
    text = "\n".join(head + body)
    return text, {"races": n, "top2_hit": top2_hit, "top2_tot": top2_tot,
                  "gold_races": len(gold_races), "good_races": len(good_races),
                  **{f"t3_{k}": v for k, v in top3_dist.items()}}


def build(day: str) -> str | None:
    from wongchoi_paths import AU_RACING  # noqa: PLC0415

    folders = sorted((Path(AU_RACING) / "Archive").glob(f"{day} *"))
    blocks, tot = [], {}
    scored = []
    for f in folders:
        got = meeting_lines(f)
        if not got:
            continue
        text, c = got
        # 好嘅馬場排前面 —— 手機上一眼就見到今日邊度準、邊度唔準。
        rate = (c.get("Gold", 0) + c.get("Good", 0)) / max(c.get("races", 1), 1)
        scored.append((rate, c.get("top2_hit", 0) / max(c.get("top2_tot", 1), 1), text))
        for k, v in c.items():
            tot[k] = tot.get(k, 0) + v
    blocks = [t for _, _, t in sorted(scored, key=lambda x: (-x[0], -x[1]))]
    if not blocks:
        return None
    races = tot.get("races", 0)
    g, gd = tot.get("gold_races", 0), tot.get("good_races", 0)
    hit, tot2 = tot.get("top2_hit", 0), tot.get("top2_tot", 0)
    head = "\n".join([
        f"🏇 覆盤 {day} · {len(blocks)} 個馬場 / {races} 場",
        "",
        f"捉齊三甲（頭四選包住前三名）　{g}/{races}（{100*g/max(races,1):.0f}%）",
        f"頭兩選皆入位　　　　　　　　　{gd}/{races}（{100*gd/max(races,1):.0f}%）",
        f"頭兩選入位率　　　　　　　　　{hit}/{tot2}（{100*hit/max(tot2,1):.0f}%）",
        "",
        f"頭三選入位隻數（加埋 = {races}）",
        f"　三隻　{tot.get('t3_3', 0)}",
        f"　兩隻　{tot.get('t3_2', 0)}",
        f"　一隻　{tot.get('t3_1', 0)}",
        f"　零隻　{tot.get('t3_0', 0)}",
    ])
    return head + "\n\n" + "\n\n".join(blocks)


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else None
    if not day:
        from wongchoi_paths import AU_RACING  # noqa: PLC0415
        reps = sorted((Path(AU_RACING) / "Archive").glob("*/*_Reflector_Report.md"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if not reps:
            print("冇覆盤報告")
            return 1
        day = reps[0].parent.name[:10]
    text = build(day)
    if not text:
        print(f"{day} 冇覆盤報告")
        return 1
    print(text)
    if "--send" in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import au_notify
        print("\n送出：", au_notify.push(text) or "冇配置出口")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    raise SystemExit(main())
