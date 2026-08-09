"""由 Racenet 賽果 PDF 抽逐場完整名次。

⚠️ 唔可以靠 race header 分段 —— PDF 版面會令上一場嘅尾段排喺下一場標題之後
（實測 Rosehill R4 嘅 7th–10th 出現喺 R5 標題後面）。改為「見到 1st 就開新一場」，
再同頁頂嘅 All 摘要行逐場對驗。唯讀。
"""
import re, json
from pathlib import Path
from pypdf import PdfReader

def parse(pdf):
    txt="\n".join((p.extract_text() or "") for p in PdfReader(pdf).pages)
    lines=[l.strip() for l in txt.splitlines()]
    # 頁頂摘要行：每場前三
    m=re.search(r"^All\s*$", txt, re.M)
    summ=[]
    for l in lines:
        if re.match(r"^(\d+,\s*){2,}", l):
            nums=[int(x) for x in re.findall(r"\d+", l)]
            summ=[nums[i:i+3] for i in range(0,len(nums)-2,3)]
            break
    races=[]; cur=None; pend=None
    posn=re.compile(r"^(\d+)(?:st|nd|rd|th)$")
    # 後備馬編號係 "14e." / "16e."，唔接受就會漏咗冠軍（Rosehill R10 中招）
    horse=re.compile(r"^(\d+)[a-z]?\.\s*(.+?)\((\d+)\)")
    for l in lines:
        mm=posn.match(l)
        if mm:
            p=int(mm.group(1))
            if p==1: races.append({}); cur=races[-1]
            pend=p; continue
        mm=horse.match(l)
        if mm and pend is not None and cur is not None:
            cur.setdefault(pend, {"n":int(mm.group(1)),"name":mm.group(2).strip()})
            pend=None
    out={}
    for i,rc in enumerate(races,1):
        rows=[{"pos":p,**v} for p,v in sorted(rc.items())]
        out[i]={"rows":rows,"top3_summary":summ[i-1] if i-1<len(summ) else None}
    return out

for tag,pdf in (("rosehill","/Users/imac/Desktop/Rosehill Gardens Horse Race Results - 01_08_2026 - Racenet.pdf"),
                ("flemington","/Users/imac/Desktop/Flemington Horse Race Results - 01_08_2026 - Racenet.pdf")):
    r=parse(pdf)
    Path(f"/Users/imac/Antigravity-repo/scratch/results_{tag}.json").write_text(json.dumps(r,ensure_ascii=False))
    print(f"\n=== {tag} : {len(r)} 場 ===")
    for k in sorted(r):
        rows=r[k]["rows"]; t3=[x["n"] for x in rows[:3]]
        s=r[k]["top3_summary"]
        ok = "✓" if (s and t3==s) else ("✗ 摘要:"+str(s) if s else "（摘要缺）")
        print(f"  R{k:<3} {len(rows):>2} 匹  前三 {t3}  {ok}   "
              + ", ".join(f"{x['pos']}.#{x['n']} {x['name']}" for x in rows[:3]))
