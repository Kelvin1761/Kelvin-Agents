"""將一個回放 dump 換成另一套外層權重（離線：raw' = raw + Σ(w' − w)·m，非初出馬；picks 重排）。

用嚟喺 S 版權重（EXP-20261114-03）之下比較審計／重試 arm：base 同 arm 都換同一套權重再比。
用法：python3 hkjc_replay_reweight.py <in.jsonl> <weights.json> <out.jsonl> [--key full_dev]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
from hkjc_racing_engine import scoring  # noqa: E402

DIMS = ("stability", "trainer_signal", "sectional", "race_shape", "horse_health", "trackwork", "form_line", "class_advantage")


def main():
    key = sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv else "full_dev"
    w = json.load(open(sys.argv[2]))[key]
    W = np.array([w[d] for d in DIMS])
    W0 = np.array([scoring.MATRIX_WEIGHTS[d] for d in DIMS])
    with open(sys.argv[3], "w") as fh:
        for line in open(sys.argv[1]):
            x = json.loads(line)
            if "horses" in x:
                hs = [h if h.get("debut") else dict(h, raw=h["raw"] + float((W - W0) @ np.array([h["m"].get(d, 60.0) for d in DIMS])))
                      for h in x["horses"]]
                ns = np.array([h["n"] for h in hs])
                raw = np.array([h["raw"] for h in hs])
                x = dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
