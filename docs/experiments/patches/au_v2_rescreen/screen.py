"""Kelvin 2026-11-23「所有舊判決當新候選重新跑」第一步：篩。外置碟上每對 base／arm dump 用 v2 尺快判（null 0），
log-loss CI 上界 < 0 而且 AUC 護欄過嘅先值得喺現行 live 上重建。⚠️ 舊 dump 係舊引擎；fit 類 arm 未必係 walk-forward（in-sample 會偏好）。"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(W / ".agents/skills/shared_racing"))
import au_logloss_ruler as R  # noqa: E402

SCR = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch")
SKIP = {"base", "describe", "similarity", "coverage"}
out = []
for base in sorted(SCR.glob("*/base.json")) + sorted(SCR.glob("*/arms/base.json")):
    try:
        B = R.eligible(json.loads(base.read_text())["races"])
    except Exception as e:  # noqa: BLE001
        print("skip base", base, e); continue
    for arm in sorted(base.parent.glob("*.json")):
        st = arm.stem
        if st.lower() in SKIP or st.startswith("weights") or "." in st:
            continue
        try:
            d = json.loads(arm.read_text())
            if "races" not in d:
                continue
            C = R.eligible(d["races"])
            v = R.evaluate(B, C, nnull=0)
        except Exception as e:  # noqa: BLE001
            print("skip", arm, str(e)[:60]); continue
        ok = v["checks"]["logloss_ci_upper_below_0"] and v["checks"]["auc_guardrail"]
        row = {"dir": str(base.parent.relative_to(SCR)), "arm": st, "ok": ok, **{k: v[k] for k in ("dlogloss", "gold_pp", "good_pp", "auc_delta", "top2_any_hit_pp", "races")}}
        out.append(row)
        print(("★ " if ok else "  ") + f"{row['dir']}/{st}: Δ {v['dlogloss'][0]:+.5f} [{v['dlogloss'][2]:+.5f}] AUC {v['auc_delta'][0]*100:+.3f}[{v['auc_delta'][1]*100:+.3f}] Gold {v['gold_pp'][0]:+.2f} Good {v['good_pp'][0]:+.2f}", flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1))
