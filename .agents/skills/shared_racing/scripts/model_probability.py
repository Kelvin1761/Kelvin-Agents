#!/usr/bin/env python3
"""校準模型機率（SHADOW，EXP-20261125-07）：由綜合分出「入頭三」同「獨贏」機率，只寫 JSON，未上 dashboard。

點解要有：dashboard 而家只有排名同分數，冇「呢匹馬幾大機會入位」。分數本身唔係機率 —— 要用已結算賽果校準。
呢度用同判決尺**同一條公式**，唔另起一套（AGENTS.md「一樣嘢只准有一個標準」）：

  入頭三   p = σ(a + α·(raw − 場均) + γ·logit(3/N))      —— AU log-loss 尺 v2 / HKJC 回放尺 v5 嘅校準
  獨贏     p_i = softmax(β·(raw − 場均))                  —— 同 `market_ruler.py` 淨模型部分同一個形狀（條件 logit）

  AU：raw = 已發佈 `ability_score`（同 `au_eval.default_scorer` = live ability）；(X, y) 同 fit 直接用
      `au_logloss_ruler._xy(version="v2")` 同 `_fit` —— bit-identical，logit(3/N) 用 AU 尺嘅 `max(N−3, 1e-9)`。
  HKJC：raw = 已發佈 Logic 嘅 `ability_score_raw`（回放尺用嘅 raw，唔係顯示用嘅 `ability_score`）；
      logit(3/N) 用 HKJC 回放尺 v5 嘅 `field_logit`（N ≤ 3 當 N = 4）。兩邊喺 N ≥ 4 一模一樣，只係 N ≤ 3 嘅場唔同；
      fit 都用 `au_logloss_ruler._fit`（冇罰則 Newton，同 v5 sklearn C=1e6 嘅 MLE 一樣）。

防洩漏：
  * 只用**目標日之前**嘅賽日 fit（嚴格 <）；頭 20 個賽日只做訓練（warm-up），未夠就 `insufficient`。
  * 輸入係**賽前已發佈**嗰份預測（`unified_reflector_core.select_prerace_snapshot`，同覆盤／失手體檢同一個揀法；
    快照經 `wongchoi_paths.prediction_snapshot_dir`），唔係賽後重評嘅 meeting 目錄。
  * `live_record_exclusions` 入面嘅場次唔計。
  * 賠率**唔入**呢個模型；收市價只喺 `calibration_board.py` 做比較基準。
  * model_id：AU = golden fingerprint（`scoring_golden.json` sha256），HKJC = `SCORING_CONTRACT_VERSION`。
    只用「現行模型」嘅數據 fit：HKJC 逐匹睇 Logic 記低嘅 `scoring_contract_id`；AU Logic 冇記模型版本，
    所以用 golden 最後一次改動嘅 commit 時間做分界（快照 created_at 要遲過佢）。未夠 20 個賽日 = `insufficient`，
    另外附 `reference_all_models`（混埋舊模型數據 fit，只供參考，唔准當現行模型機率）。

    python3 model_probability.py --platform au|hkjc [--target-date YYYY-MM-DD] [--output PATH] [--dry-run]

輸出 `<資料根>/<AU|HKJC>_Prob_Calibration.json`：{model_id, fit_until, n_races, a, alpha, gamma, beta_win, status, ...}。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SHARED = HERE.parent
AU_SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
HKJC_SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for _p in (str(AU_SCRIPTS), str(SHARED), str(HERE), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import au_logloss_ruler as L  # noqa: E402

WARMUP_DAYS = L.WARMUP_DAYS          # 20：同判決尺
AU_GOLDEN = REPO / ".agents/skills/au_racing/au_wong_choi_auto/tests/golden/scoring_golden.json"
HKJC_SCORING = HKJC_SCRIPTS / "hkjc_racing_engine" / "scoring.py"
HKJC_MEETING = re.compile(r"^\d{4}-\d{2}-\d{2}_(ShaTin|HappyValley)$")
OUTPUT_NAMES = {"au": "AU_Prob_Calibration.json", "hkjc": "HKJC_Prob_Calibration.json"}
EXPERIMENT = "EXP-20261125-07"


# ---------------------------------------------------------------- 公式

def field_logit(n: int, platform: str) -> float:
    """logit(3/N)。AU = au_logloss_ruler v2（max(N−3, 1e-9)）；HKJC = 回放尺 v5（N ≤ 3 當 4）。"""
    if platform == "au":
        return float(np.log(3 / max(n - 3, 1e-9)))
    n = max(int(n), 4)
    return float(np.log(3.0 / (n - 3.0)))


def top3_xy(race: dict, platform: str):
    """→ (X[n×2], y)。AU 直接用判決尺嘅 `_xy`，保證同一條公式。"""
    if platform == "au":
        return L._xy(race, version="v2")
    r = np.array([x["ability"] for x in race["rows"]], float)
    y = np.array([int(x["pos"] <= 3) for x in race["rows"]])
    return np.column_stack([r - r.mean(), np.full(len(r), field_logit(len(r), platform))]), y


def eligible(races: list[dict], platform: str) -> list[dict]:
    """AU = `au_logloss_ruler.eligible`（乾淨語料起點 2026-08-05）；HKJC 同一套條件但冇起點。"""
    if platform == "au":
        return L.eligible(races)
    out = [r for r in races if sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(out, key=lambda r: (r["date"], r["meeting"], r["race"]))


def fit_top3(races: list[dict], platform: str):
    """→ (a, α, γ)。冇罰則 logistic Newton（`au_logloss_ruler._fit`）。"""
    X, Y = zip(*(top3_xy(r, platform) for r in races))
    return L._fit(np.concatenate(X), np.concatenate(Y))


def _win_parts(race: dict):
    r = np.array([x["ability"] for x in race["rows"]], float)
    winners = [i for i, x in enumerate(race["rows"]) if x["pos"] == 1]
    return r - r.mean(), (winners[0] if len(winners) == 1 else None)


def fit_win(races: list[dict]) -> float:
    """條件 logit 頭馬：max Σ [β·x_w − log Σ exp(β·x_i)]，x = raw − 場均。一維 Newton。死熱頭馬嘅場唔計。"""
    parts = [p for p in map(_win_parts, races) if p[1] is not None and len(p[0]) >= 2]
    beta = 0.0
    for _ in range(100):
        g = h = 0.0
        for x, w in parts:
            z = beta * x
            e = np.exp(z - z.max())
            p = e / e.sum()
            m = float(p @ x)
            g += float(x[w]) - m
            h -= float(p @ (x * x)) - m * m
        if h >= 0:
            break
        step = -g / h
        beta += step
        if abs(step) < 1e-10:
            break
    return float(beta)


def top3_probs(abilities, params: dict, platform: str) -> np.ndarray:
    r = np.asarray(abilities, float)
    z = params["a"] + params["alpha"] * (r - r.mean()) + params["gamma"] * field_logit(len(r), platform)
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def win_probs(abilities, beta: float) -> np.ndarray:
    r = np.asarray(abilities, float)
    z = beta * (r - r.mean())
    e = np.exp(z - z.max())
    return e / e.sum()


def fit_params(races: list[dict], platform: str) -> dict:
    a, alpha, gamma = fit_top3(races, platform)
    return {"a": a, "alpha": alpha, "gamma": gamma, "beta_win": fit_win(races)}


def params_before(races: list[dict], target_date: str, platform: str, warmup: int = WARMUP_DAYS) -> dict:
    """只用 target_date **之前**嘅賽日 fit。少過 warm-up 日數 = insufficient（冇參數）。"""
    train = [r for r in eligible(races, platform) if r["date"] < target_date]
    days = sorted({r["date"] for r in train})
    base = {"fit_until": days[-1] if days else None, "n_races": len(train), "n_days": len(days)}
    if len(days) < warmup:
        return {**base, "status": "insufficient", "a": None, "alpha": None, "gamma": None, "beta_win": None}
    return {**base, "status": "ok", **fit_params(train, platform)}


def walk_forward(races: list[dict], platform: str, warmup: int = WARMUP_DAYS) -> dict:
    """→ {賽日: params}：每個賽日用嗰日之前全部賽日重 fit（每日重 fit）；頭 warm-up 日冇。"""
    races = eligible(races, platform)
    days = sorted({r["date"] for r in races})
    by = defaultdict(list)
    for r in races:
        by[r["date"]].append(r)
    out, train = {}, []
    for i, d in enumerate(days):
        if i >= warmup:
            out[d] = fit_params(train, platform)
        train.extend(by[d])
    return out


# ---------------------------------------------------------------- model_id

def model_id(platform: str) -> str:
    if platform == "au":
        return "au_golden:" + hashlib.sha256(AU_GOLDEN.read_bytes()).hexdigest()[:16]
    tree = ast.parse(HKJC_SCORING.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SCORING_CONTRACT_VERSION" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("搵唔到 SCORING_CONTRACT_VERSION")


def au_model_epoch() -> str | None:
    """AU golden 最後一次改動嘅 commit 時間（ISO）。冇 git = None。"""
    try:
        out = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%cI", "--", str(AU_GOLDEN)],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def current_model_races(races: list[dict], platform: str, mid: str, epoch: str | None) -> list[dict]:
    if platform == "hkjc":
        return [r for r in races if r.get("model_ids") == {mid}]
    if not epoch:
        return []
    cut = datetime.fromisoformat(epoch)
    return [r for r in races if r.get("published_at") and datetime.fromisoformat(r["published_at"]) > cut]


# ---------------------------------------------------------------- 讀已發佈預測 + 賽果

def _core():
    sys.path.insert(0, str(SHARED / "race_reflector" / "scripts"))
    import unified_reflector_core as core  # noqa: E402
    return core


def _float(v):
    try:
        f = float(str(v).replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def meeting_list(platform: str, root: Path) -> list[Path]:
    if platform == "au":
        from corpus_paths import meeting_dirs
        return [m for m in meeting_dirs(root) if m.name[:10] >= L.CLEAN_SINCE]
    return sorted(p for p in Path(root).iterdir() if p.is_dir() and HKJC_MEETING.match(p.name))


def _hkjc_logic_rows(analysis_dir: Path, race_num: int) -> dict[int, dict]:
    path = analysis_dir / f"Race_{race_num}_Logic.json"
    if not path.is_file():
        return {}
    horses = (json.loads(path.read_text(encoding="utf-8")).get("horses") or {})
    out = {}
    for key, horse in horses.items():
        auto = (horse or {}).get("python_auto") or {}
        try:
            n = int(key)
        except ValueError:
            continue
        if auto.get("ability_score_raw") is None:
            continue
        out[n] = {"ability": float(auto["ability_score_raw"]), "model_id": auto.get("scoring_contract_id"),
                  "name": horse.get("horse_name")}
    return out


def collect_meeting(platform: str, meeting_dir: Path, core=None) -> tuple[list[dict], str]:
    """→ (場次 list, 來源標籤)。來源：snapshot / meeting_dir / offline / no_results / excluded。"""
    from live_record_exclusions import is_excluded
    from wongchoi_paths import SnapshotArchiveOffline

    core = core or _core()
    if is_excluded(platform, meeting_dir.name):
        return [], "excluded"
    results_file = (sorted(meeting_dir.glob("*全日賽果.json")) or [None])[0] if platform == "hkjc" \
        else core.find_existing_results_file(platform, meeting_dir)
    if not results_file:
        return [], "no_results"
    try:
        snapshot, created, _post = core.select_prerace_snapshot(meeting_dir, platform)
    except SnapshotArchiveOffline:
        return [], "offline"
    analysis_dir = snapshot or meeting_dir
    results = core.load_structured_results(platform, Path(results_file))
    preds = core.load_prediction_rows(analysis_dir, platform) if platform == "au" else None
    date_s = meeting_dir.name[:10]
    races = []
    for race_num in sorted(results):
        scratched = set(results[race_num].get("scratched_horse_numbers") or [])
        actual = {r["horse_no"]: r for r in results[race_num].get("results") or []
                  if r.get("horse_no") and r["horse_no"] not in scratched and 0 < int(r.get("placing") or 0) < 90}
        if platform == "au":
            scored = {p["horse_no"]: {"ability": p["ability_score"], "name": p["horse_name"], "model_id": None}
                      for p in (preds or {}).get(race_num, []) if p.get("ability_score") is not None}
        else:
            scored = _hkjc_logic_rows(analysis_dir, race_num)
        rows = [{"n": n, "name": s["name"], "ability": float(s["ability"]), "pos": int(actual[n]["placing"]),
                 "sp": _float(actual[n].get("odds")), "model_id": s["model_id"]}
                for n, s in sorted(scored.items()) if n in actual]
        # 有結果但冇預測嘅馬 = 預測唔齊，成場唔要（唔好靜靜令 N 細咗）
        if len(rows) < 2 or len(rows) != len(actual):
            continue
        races.append({"date": date_s, "meeting": meeting_dir.name, "race": int(race_num), "rows": rows,
                      "published_at": created.isoformat() if created else None,
                      "model_ids": {x["model_id"] for x in rows}})
    return races, ("snapshot" if snapshot else "meeting_dir")


def collect(platform: str, root: Path, until: str | None = None) -> tuple[list[dict], dict]:
    core = _core()
    races, sources = [], defaultdict(int)
    for m in meeting_list(platform, root):
        if until and m.name[:10] >= until:
            continue
        got, src = collect_meeting(platform, m, core)
        sources[src] += 1
        races.extend(got)
    return races, dict(sources)


def default_root(platform: str) -> Path:
    from wongchoi_paths import AU_RACING, HK_RACING
    return Path(AU_RACING if platform == "au" else HK_RACING)


def default_target(platform: str) -> str:
    if platform == "hkjc":
        sys.path.insert(0, str(HKJC_SCRIPTS))
        from hkjc_racing_engine.live_priors import hk_today
        return hk_today().isoformat()
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Australia/Sydney")).date().isoformat()


def build(platform: str, races: list[dict], target: str, *, mid: str, epoch: str | None, previous: dict | None = None,
          sources: dict | None = None) -> dict:
    cur = current_model_races(races, platform, mid, epoch)
    p = params_before(cur, target, platform)
    ref = params_before(races, target, platform)
    out = {
        "experiment": EXPERIMENT, "shadow": True, "platform": platform, "model_id": mid,
        "model_epoch": epoch if platform == "au" else None, "target_date": target,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "formula": {"top3": "sigmoid(a + alpha*(raw - race_mean) + gamma*logit(3/N))",
                    "win": "softmax(beta_win*(raw - race_mean))",
                    "raw": "ability_score" if platform == "au" else "ability_score_raw",
                    "field_logit": "log(3/max(N-3,1e-9)) (AU ruler v2)" if platform == "au"
                    else "log(3/(max(N,4)-3)) (HKJC replay ruler v5)"},
        **p,
        "reference_all_models": {k: ref[k] for k in ("status", "fit_until", "n_races", "n_days", "a", "alpha",
                                                     "gamma", "beta_win")},
        "sources": sources or {},
    }
    if p["status"] == "insufficient":
        out["reason"] = "current_model_days_below_warmup" if cur or races else "no_data"
    if previous and previous.get("model_id") not in (None, mid):
        out["model_changed_from"] = previous.get("model_id")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=("au", "hkjc"), required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--target-date", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.data_root) if args.data_root else default_root(args.platform)
    target = args.target_date or default_target(args.platform)
    out = Path(args.output) if args.output else root / OUTPUT_NAMES[args.platform]
    previous = None
    if out.is_file():
        try:
            previous = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
    races, sources = collect(args.platform, root, until=target)
    payload = build(args.platform, races, target, mid=model_id(args.platform),
                    epoch=au_model_epoch() if args.platform == "au" else None, previous=previous, sources=sources)
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if not args.dry_run:
        tmp = out.with_suffix(".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(out)
    print(json.dumps({k: payload[k] for k in ("platform", "status", "model_id", "fit_until", "n_races", "n_days",
                                              "a", "alpha", "gamma", "beta_win")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
