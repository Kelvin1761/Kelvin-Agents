import json,re,glob,sys,statistics as st,collections,zipfile
import xml.etree.ElementTree as ET
sys.path.insert(0,'/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts')
from au_racing_engine.full_time_speed import seconds, norm
from au_racing_engine.engine_core import _normalize_track_name
from au_result_identity import normalize_venue_name
D="/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing_Time_Evidence/"
truth={}
for z in glob.glob(D+"*.zip"):
    try: zf=zipfile.ZipFile(z)
    except Exception: continue
    for name in zf.namelist():
        if not name.lower().endswith(".xml"): continue
        try: root=ET.fromstring(zf.read(name))
        except Exception: continue
        m=re.search(r"_R(\d+)\.xml$",name,re.I)
        if not m: continue
        date=root.attrib.get("EventDate","")[:10]; course=normalize_venue_name(root.findtext("CourseName") or "")
        if re.search(r"TRIAL|JUMP.?OUT",root.findtext("RaceName") or "",re.I): continue
        horses=[]
        for h in root.findall("./Horses/HorseSummary"):
            secs=h.findall("./Sections/SectionSummary")
            try:
                pts=[float(s.attrib["CumulatedDistance"]) for s in secs]; sp=[seconds(s.find("SectionTime").attrib["Time"]) for s in secs]
                fin=seconds(h.find("FinishTime").attrib["Time"])
            except Exception: continue
            if len(sp)<5 or any(b-a!=200 for a,b in zip(pts,pts[1:])) or abs(sum(sp)-fin)>0.05: continue
            horses.append({"horse":norm(h.attrib["Name"]),"fin":fin,"l600":sum(sp[-3:]),"t_at_600":sum(sp[:-3]),"dist":int(pts[-1])})
        if len(horses)>=4: truth[(course,date,int(m[1]))]=horses
print("RQ races parsed",len(truth))
json.dump({"|".join(map(str,k)):v for k,v in truth.items()},open("/private/tmp/claude-501/-Users-imac-Antigravity-repo/9d297031-6e0b-4014-9024-4e4d7fc622a0/scratchpad/rq_truth.json","w"))
