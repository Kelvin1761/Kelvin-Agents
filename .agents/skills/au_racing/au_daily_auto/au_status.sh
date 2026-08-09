#!/bin/zsh
# 一眼睇晒最近幾個 run 嘅結果。喺電腦前用呢個，唔喺就靠手機通知。
cd "${0:A:h}" || exit 1
N="${1:-6}"
print -r -- "最近 $N 個 run（新到舊）"
print -r -- "────────────────────────────────────────────────────────────────"
for f in $(ls -t logs/run-*.json 2>/dev/null | head -$N); do
  /usr/bin/python3 - "$f" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
icon = {"ok":"✅","partial":"⚠️","failed":"❌","running":"⏳"}.get(d.get("status"),"•")
dep = d.get("cloudflare_deployment") or {}
dep_s = ("冇行到" if not dep else "跳過(冇變)" if dep.get("skipped")
         else "成功" if dep.get("ok") else "失敗")
errs = len(d.get("errors") or [])
mins = round((d.get("duration_seconds") or 0)/60)
ver = (d.get("code_version") or {})
print(f"{icon} {d.get('started_at','')[:16]}  {d.get('mode','?'):8} "
      f"{d.get('status','?'):8} {mins:>4}分  發佈:{dep_s:<10} 錯誤:{errs}  "
      f"{ver.get('commit','?')}/{(ver.get('branch') or '?')[:22]}")
for e in (d.get("errors") or [])[:2]:
    print(f"      ❌ {e.get('step')}: {str(e.get('message'))[:90]}")
PY
done
