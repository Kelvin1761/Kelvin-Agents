#!/usr/bin/env python3
"""一個場次嘅揀馬命中報告：頭兩揀入前三？賠率幾多？Gold／Good位？

定義跟 memory 入面嘅 canonical 版本：
  * Gold   = 前三名全部落喺我哋頭四揀（capture-at-4）
  * Good位 = 我哋頭兩揀都跑入前三
賠率用賽果檔嘅 SP（официальный starting price）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RE_RANK = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|\s*([^|]*?)\s*\|", re.M)
RE_RACE_HDR = re.compile(r"^##\s*Race\s*(\d+)\s*$", re.M)
RE_PLACE = re.compile(r"^(\d+)(?:st|nd|rd|th):\s*#(\d+)\s+(.+?)(?:\s*\([\d.]+L\))?\s*SP\$([\d.]+)\s*$", re.M)


def picks(folder: Path, race_no: int):
    f = folder / f"Race_{race_no}_Auto_Analysis.md"
    if not f.exists():
        return []
    body = f.read_text(errors="replace")
    i = body.find("全場綜合戰力排名")
    if i < 0:
        return []
    rows = RE_RANK.findall(body[i:i + 4000])
    return [{"rank": int(r), "no": int(n), "name": nm.strip(),
             "score": float(s), "grade": g.strip()} for r, n, nm, s, g in rows]


def results(folder: Path):
    f = folder / "Race_Results_Reflector.md"
    if not f.exists():
        return {}
    body = f.read_text(errors="replace")
    out, parts = {}, RE_RACE_HDR.split(body)
    for i in range(1, len(parts), 2):
        rno = int(parts[i])
        out[rno] = [{"pos": int(p), "no": int(n), "name": nm.strip(), "sp": float(sp)}
                    for p, n, nm, sp in RE_PLACE.findall(parts[i + 1])]
    return out


def report(folder: Path):
    res = results(folder)
    if not res:
        return None
    rows, gold, good, hits, top2_total = [], 0, 0, 0, 0
    for rno in sorted(res):
        fin = res[rno]
        pk = picks(folder, rno)
        if not pk or not fin:
            continue
        top3 = {h["no"] for h in fin if h["pos"] <= 3}
        sp = {h["no"]: h["sp"] for h in fin}
        pos = {h["no"]: h["pos"] for h in fin}
        p2 = [p for p in pk if p["rank"] <= 2]
        p4 = {p["no"] for p in pk if p["rank"] <= 4}
        got = [p for p in p2 if p["no"] in top3]
        hits += len(got); top2_total += len(p2)
        # 一定要真係讀到三個名次先計 Gold。賽果檔 parse 少咗一個位嘅話，
        # `top3 <= p4` 會靜靜咁變易過關 —— 一個假 Gold 比冇 Gold 差。
        is_gold = len(top3) == 3 and top3 <= p4
        is_good = len(p2) == 2 and len(got) == 2
        gold += is_gold; good += is_good
        for p in p2:
            rows.append({"race": rno, "rank": p["rank"], "no": p["no"],
                         "name": p["name"], "grade": p["grade"],
                         "fin": pos.get(p["no"]), "sp": sp.get(p["no"]),
                         "hit": p["no"] in top3})
        rows.append({"race": rno, "_gold": is_gold, "_good": is_good})
    n = len(res)
    return {"races": n, "rows": rows, "hits": hits, "top2": top2_total,
            "gold": gold, "good": good}


def summary(folders):
    """多個場次一覽。單一場次十場樣本太細，隔籬場次先分得出
    「我哋準」定係「當日普遍難跑」。"""
    print(f"\n{'場次':30} {'場數':>4} {'頭兩揀入前三':>14} {'Gold':>10} {'Good位':>10}")
    print("─" * 74)
    tot = {"races": 0, "hits": 0, "top2": 0, "gold": 0, "good": 0}
    for f in folders:
        r = report(Path(f))
        if not r:
            print(f"{Path(f).name[:30]:30} {'—— 仲未有賽果 ——':>40}")
            continue
        for k in tot:
            tot[k] += r[k]
        print(f"{Path(f).name[11:41]:30} {r['races']:>4} "
              f"{r['hits']:>4}/{r['top2']:<3} {100*r['hits']/max(r['top2'],1):>5.1f}% "
              f"{r['gold']:>3}/{r['races']:<2} {100*r['gold']/max(r['races'],1):>4.1f}% "
              f"{r['good']:>3}/{r['races']:<2} {100*r['good']/max(r['races'],1):>4.1f}%")
    print("─" * 74)
    print(f"{'合計':30} {tot['races']:>4} "
          f"{tot['hits']:>4}/{tot['top2']:<3} {100*tot['hits']/max(tot['top2'],1):>5.1f}% "
          f"{tot['gold']:>3}/{tot['races']:<2} {100*tot['gold']/max(tot['races'],1):>4.1f}% "
          f"{tot['good']:>3}/{tot['races']:<2} {100*tot['good']/max(tot['races'],1):>4.1f}%")


def main():
    if sys.argv[1] == "--summary":
        summary(sys.argv[2:])
        return 0
    folder = Path(sys.argv[1])
    r = report(folder)
    if not r:
        print(f"❌ {folder.name}：仲未有 Race_Results_Reflector.md")
        return 1
    print(f"\n══ {folder.name} ══  {r['races']} 場")
    print(f"{'場':>3} {'揀':>3} {'馬號':>4}  {'馬名':22} {'評級':4} {'名次':>4} {'SP':>7}  命中")
    for x in r["rows"]:
        if "_gold" in x:
            print(f"      └ Gold {'✅' if x['_gold'] else '—'}   Good位 {'✅' if x['_good'] else '—'}")
            continue
        fin = x["fin"] if x["fin"] else "-"
        sp = f"${x['sp']:.2f}" if x["sp"] else "-"
        print(f"{x['race']:>3} {x['rank']:>3} {x['no']:>4}  {x['name'][:22]:22} {x['grade']:4} "
              f"{str(fin):>4} {sp:>7}  {'✅' if x['hit'] else ''}")
    pct = 100 * r["hits"] / max(r["top2"], 1)
    print(f"\n  頭兩揀入前三：{r['hits']}/{r['top2']}  ({pct:.1f}%)")
    print(f"  Gold（前三全喺頭四揀）：{r['gold']}/{r['races']}  ({100*r['gold']/max(r['races'],1):.1f}%)")
    print(f"  Good位（頭兩揀都上名）：{r['good']}/{r['races']}  ({100*r['good']/max(r['races'],1):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
