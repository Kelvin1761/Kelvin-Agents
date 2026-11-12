import glob,re,collections
R="/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"
c=collections.Counter()
for f in glob.glob(R+"/Archive/2026-11-0*/Race_*_Auto_Analysis.md"):
    t=open(f).read()
    for blk in t.split("### 【No.")[1:]:
        up=re.search(r"賽績線級別: ([^\n(]*)\(強組比例: ([^)]*)\)",blk)
        en=re.search(r"賽績線分 (\d+) ← 賽績線級別([^；\n]*)",blk)
        if up and en: c[(up.group(1).strip(),en.group(2))]+=1
for k,v in sorted(c.items(),key=lambda x:-x[1]): print(v,k)
