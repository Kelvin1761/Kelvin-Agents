#!/usr/bin/env python3
"""Derive a forgiveness label from the past-run trajectory, then test whether it predicts."""
import csv, glob, re, sys, collections, os

TRAJ = re.compile(r"S(\d+)(?:→8th(\d+))?(?:→4th(\d+))?(?:→F(\d+))?")

def parse_traj(t):
    m = TRAJ.fullmatch(t.strip())
    if not m: return None
    s, p8, p4, f = m.groups()
    return dict(settle=int(s), p800=int(p8) if p8 else None,
                p400=int(p4) if p4 else None, finish=int(f) if f else None)

def label(tr, starters):
    """回一個寬恕標籤，或者 '' 表示冇。純由走位推導。"""
    if not tr or tr["finish"] is None or tr["p400"] is None:
        return ""
    fin, p400, settle = tr["finish"], tr["p400"], tr["settle"]
    n = starters or 0
    gain = p400 - fin                      # 尾 400m 執位（正 = 追上）
    # 1) 後上但仍然大敗：紙面名次低估
    if fin >= 4 and gain >= 3:
        return "尾段執位"
    # 2) 守後 + 全程冇位置改善：跑法被局限
    if n >= 8 and settle >= n * 0.75 and fin >= 4 and gain <= 0:
        return "全程守後"
    # 3) 搶前消耗：領放／貼近領放，最後 400m 大幅失位
    if settle <= 2 and (p400 - fin) <= -4:
        return "搶前消耗"
    return ""

def load_past_runs():
    """(day, venue, race, horse_name) → 上一場正式賽嘅 (traj, starters, finish)"""
    out = {}
    FA=[f for f in glob.glob("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive/2026-0[89]-*/*Facts.md")
        if "2026-08-13" <= f.split("/")[-2][:10] <= "2026-09-04"]
    for path in FA:
        day = os.path.basename(os.path.dirname(path))[:10]
        venue = re.sub(r"\s+Race\s+[\d\-]+$", "", os.path.basename(os.path.dirname(path))[11:]).strip()
        m = re.search(r"Race (\d+) Facts", os.path.basename(path))
        if not m: continue
        race = int(m.group(1))
        horse = None; hdr=None; ncol=0; taken=set()
        for line in open(path, errors="replace"):
            hm = re.match(r"^###\s+馬匹\s*#(\d+)\s+(.+?)\s*\(檔位", line.strip())
            if hm:
                horse = hm.group(2).strip(); hdr=None; continue
            s=line.lstrip()
            if not s.startswith("|"):
                if hdr is not None: hdr=None
                continue
            cells=[c.strip() for c in line.strip().strip("|").split("|")]
            if "走位消耗" in cells and "寬恕認定" in cells:
                hdr={x:i for i,x in enumerate(cells)}; ncol=len(cells); continue
            if hdr is None or len(cells)!=ncol or set(cells[0])<=set("-: "): continue
            if cells[hdr["類型／歷史HC"]].strip()=="試閘": continue
            key=(day,venue,race,horse)
            if key in taken: continue
            taken.add(key)
            out[key]=dict(traj=cells[hdr.get("跑位軌跡",0)],
                          finish=cells[hdr.get("名次",0)])
    return out

past = load_past_runs()
print(f"抽到 {len(past)} 個「上一場正式賽」記錄")
cur = {(r["day"], r["venue"], int(r["race"]), r["name"]): r
       for r in csv.DictReader(open("au_full.csv"))}
print(f"今仗結果 {len(cur)} 筆")
joined = [(past[k], cur[k]) for k in past if k in cur]
print(f"join 到 {len(joined)}\n")
if not joined: sys.exit("join 失敗")
buckets = collections.defaultdict(list)
for p, c in joined:
    tr = parse_traj(p["traj"])
    try: starters = int(c["field"])
    except (ValueError, TypeError): starters = 0
    lab = label(tr, starters)
    try: fin = int(re.sub(r"\D","",p["finish"]) or 0)
    except ValueError: fin = 0
    if fin < 4: continue          # 只睇上仗大敗嗰批 —— 寬恕先有意義
    buckets[lab or "（無寬恕）"].append(c)
print(f"{'上仗標籤':14s} {'n':>6s} {'今仗入位率':>9s} {'按馬匹數預期':>11s} {'超額':>9s}")
import math, statistics
for lab in sorted(buckets, key=lambda x:-len(buckets[x])):
    v=buckets[lab]
    if len(v)<60: continue
    pr=sum(1 for r in v if r["placed"]=="1")/len(v)
    exp=statistics.mean(int(r["pays"])/int(r["field"]) for r in v)
    sd=1.96*math.sqrt(pr*(1-pr)/len(v))
    print(f"   {lab:12s} {len(v):6d} {100*pr:8.1f}% {100*exp:10.1f}% {100*(pr-exp):+7.1f}pp ±{100*sd:.1f}")
