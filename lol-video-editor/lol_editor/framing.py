"""Find the League client window; hide desktop when a safe window is unavailable."""
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from .common import load, project_analysis, save


def safe_edges(rect, gray):
    """Client edges are dark; reject bright wallpaper even inside a remembered box."""
    x,y,w,h=rect
    for side in range(4):
        for _ in range(25):
            edge=(gray[y:y+h,x:x+2] if side==0 else gray[y:y+h,x+w-2:x+w] if side==1
                  else gray[y:y+2,x:x+w] if side==2 else gray[y+h-2:y+h,x:x+w])
            if edge.size and np.median(edge)<70 and np.mean(edge<90)>.7:
                break
            if side==0:x+=1;w-=1
            elif side==1:w-=1
            elif side==2:y+=1;h-=1
            else:h-=1
        else:
            return None
    return [x,y,w,h] if w>100 and h>70 else None


def client_rectangle(frame):
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.morphologyEx(cv2.Canny(gray, 30, 80), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    fh, fw = gray.shape
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        x, y, w, h = cv2.boundingRect(contour)
        if not (.15 < w*h/(fw*fh) < .8 and 1.72 < w/h < 1.85 and x > 3 and y > 3
                and x+w < fw-3 and y+h < fh-3):
            continue
        if cv2.contourArea(contour)/(w*h) < .8 or gray[y:y+h, x:x+w].mean() > 80:
            continue
        candidate=safe_edges([x+4, y+4, w-8, h-8],gray)
        if candidate:
            return candidate
    return None


def build(project):
    import cv2
    project = Path(project)
    manifest, _ = project_analysis(project)
    output = project / "framing.json"
    if output.exists():
        old=load(output)
        if old.get("version")==3:
            return old
        save(project/f"framing-v{old.get('version',1)}.json",old)
    width, height = 640, 360
    size = width*height*3
    regions = []
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-i", manifest["source"]["path"],
                                    "-an", "-vf", f"fps=1,scale={width}:{height}", "-pix_fmt", "bgr24",
                                    "-f", "rawvideo", "pipe:1"], stdout=subprocess.PIPE, stderr=errors)
        t, last_rect = 0, None
        try:
            while True:
                raw = process.stdout.read(size)
                if not raw:
                    break
                if len(raw) != size:
                    raise RuntimeError("Incomplete framing frame")
                frame = np.frombuffer(raw, np.uint8).reshape(height,width,3)
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                bar = hsv[:5,:,2]
                desktop = np.median(bar) > 110 and np.std(bar) < 45
                rect = client_rectangle(frame) if desktop else None
                if desktop and rect is None and last_rect:
                    x,y,w,h=last_rect
                    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
                    rect=safe_edges(last_rect,gray)
                if rect:
                    last_rect=rect
                mode = "client" if rect else ("hidden" if desktop else "game")
                if rect:
                    sx, sy = manifest["media"]["width"]/width, manifest["media"]["height"]/height
                    rect = [int(v*s)//2*2 for v,s in zip(rect,[sx,sy,sx,sy])]
                if (regions and mode==regions[-1]["mode"] and
                        (rect==regions[-1].get("crop") or (rect and regions[-1].get("crop") and
                         max(abs(a-b) for a,b in zip(rect,regions[-1]["crop"]))<=8))):
                    regions[-1]["end"]=min(t+1,manifest["media"]["duration"])
                else:
                    regions.append(dict(start=t,end=min(t+1,manifest["media"]["duration"]),mode=mode,crop=rect))
                t+=1
                if t%600==0:
                    print(f"Client framing {t/60:.0f}/{manifest['media']['duration']/60:.0f} min",flush=True)
            if process.wait():
                errors.seek(0)
                raise RuntimeError(errors.read().decode(errors="replace")[-1000:])
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill();process.wait()
    # Hide a short visual guard around mode/window changes; sampled boxes can precede real windows.
    safe=[]
    for i,r in enumerate(regions):
        r=dict(r)
        if r['mode']!='hidden':
            if i:r['start']+=1
            if i+1<len(regions):r['end']-=1
        if r['end']<=r['start']:continue
        last=safe[-1]['end'] if safe else 0
        if r['start']>last:safe.append(dict(start=last,end=r['start'],mode='hidden',crop=None))
        safe.append(r)
    if safe and safe[-1]['end']<manifest['media']['duration']:
        safe.append(dict(start=safe[-1]['end'],end=manifest['media']['duration'],mode='hidden',crop=None))
    data=dict(version=3,source=manifest["source"],regions=safe,
              notes=["Client window crop; desktop without a detected window is hidden.",
                     "Sampled at 1fps; verify phase boundaries before publishing."])
    save(output,data)
    return data


def split(clips, framing):
    pieces=[]
    for clip in clips:
        for r in framing["regions"]:
            start,end=max(clip["start"],r["start"]),min(clip["end"],r["end"])
            if start<end:
                pieces.append(dict(clip,start=start,end=end,frame_mode=r["mode"],crop=r.get("crop")))
    return pieces


def prefix(clip):
    if clip.get("frame_mode")=="client":
        x,y,w,h=clip["crop"]
        return f"crop={w}:{h}:{x}:{y},"
    if clip.get("frame_mode")=="hidden":
        return "drawbox=x=0:y=0:w=iw:h=ih:color=0x10141c:t=fill,"
    return ""
