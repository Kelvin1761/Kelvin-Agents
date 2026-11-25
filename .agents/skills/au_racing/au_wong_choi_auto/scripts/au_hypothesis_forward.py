#!/usr/bin/env python3
"""AU 通用假設 forward（shadow）引擎 —— 每個預先登記嘅假設係一個 arm（自學循環 P0，Kelvin 2026-11-26）。

同 `au_h1_forward.py`（EXP-20261125-11）同一套做法，只係將「加咩 shift」抽出嚟做 arm 規格，之後自學循環
（docs/plans/2026-11-26-self-learning-loop.md L4）提出嘅假設都喺 `ARMS` 加一行就得，唔使逐個寫新腳本。
H1 唔搬過嚟（已預先登記，code 唔郁）。

每個 arm：
    候選 ability = live ability + Σ w_k · term_k
    term 兩種：
      * `z:<leaf>`          場內標準化（(x − 場均) / 場內母體 SD；SD < 1e-9 → 0），leaf 讀快照 `Race_*_Auto_Scoring.csv`
      * `ind:<field><op><v>` 指示變數（0／1），field 讀快照 `Race_N_Logic.json`（而家只有 `days_since_last`
                             = `horses[*].python_auto.preparation_cycle.days_since_last_run`；冇值 = 0，即唔喺組別）
    w 嚟自 arm 嘅 frozen.json（`docs/experiments/patches/au_hyp_forward/fit_frozen.py` 一次過 fit），載入時核對 sha256。
live 排名完全唔郁：只讀已發佈嘅賽前快照、喺記憶體入面加 shift。

數據、配對、判法、判決鎖、盲測全部同 H1（見 au_h1_forward docstring）：
  * 賽前快照 = `unified_reflector_core.select_prerace_snapshot`；冇就成個場次唔要。
  * 候選 shift 喺**成個賽前快照場**計好先 join 賽果。
  * cutoff = START 起第一次同時夠 target_days 同 target_races；之前嘅快照場次只做 walk-forward 校準。
  * 判法（合約 m3 追市場軌）：排名尺 v2 PASS 而且 `windowed_gap_change` 點估計 ≤ 0。
  * 判決鎖 `<資料根>/WongChoiControl/forward_verdicts/<arm id>.json`，判一次就凍結。
  * 未判：只報數量，`outcomes_visible=false`。

    python3 au_hypothesis_forward.py status   --arm EXP-… --output STATUS.json
    python3 au_hypothesis_forward.py evaluate --arm EXP-… --output STATUS.json
    python3 au_hypothesis_forward.py nightly  --work-dir DIR [--arm EXP-…]   # status，夠數就 evaluate 一次
    python3 au_hypothesis_forward.py list                                    # 列出 arm（排程逐個跑、各自逾時）
  判決只准喺生產語料（wongchoi_paths.AU_RACING）封；--output 唔准指去判決鎖目錄。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import operator
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS = SCRIPT_DIR.parents[2]
REPO = SKILLS.parents[1]
for _p in (str(SCRIPT_DIR), str(SKILLS / "shared_racing"), str(SKILLS / "shared_racing" / "scripts"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import au_h1_forward as H1  # noqa: E402  （共用：race_z、_core、_float、meeting_list、_atomic_write）

CALIBRATION_SINCE = H1.CALIBRATION_SINCE
PATCH_DIR = REPO / "docs" / "experiments" / "patches" / "au_hyp_forward"
SOURCE_TAG = "prerace_snapshot"
OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}
LOGIC_FIELDS = {"days_since_last": ("python_auto", "preparation_cycle", "days_since_last_run")}


@dataclass(frozen=True)
class Term:
    key: str            # frozen.json weights 嘅 key
    kind: str           # "z" | "ind"
    name: str           # leaf（z）或者 LOGIC_FIELDS key（ind）
    op: str = ""
    value: float = 0.0
    lower_exclusive: float | None = None   # ind：另加 name > lower_exclusive（例：0 < 日數 ≤ 14）

    def indicator(self, v) -> float:
        if v is None:
            return 0.0
        if self.lower_exclusive is not None and not v > self.lower_exclusive:
            return 0.0
        return 1.0 if OPS[self.op](v, self.value) else 0.0


@dataclass(frozen=True)
class Arm:
    id: str
    title: str
    source: str
    frozen: str          # PATCH_DIR 入面嘅檔名
    sha256: str
    start: str
    target_days: int
    target_races: int
    terms: tuple[Term, ...]

    @property
    def frozen_path(self) -> Path:
        return PATCH_DIR / self.frozen

    @property
    def z_leaves(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.terms if t.kind == "z")

    @property
    def logic_fields(self) -> tuple[str, ...]:
        return tuple(sorted({t.name for t in self.terms if t.kind == "ind"}))


# 登記：加 arm = code 改動（要 Sol 覆核＋保存）。sha256 喺 fit 完之後先填，唔准之後改。
ARMS: dict[str, Arm] = {
    "EXP-20261126-01": Arm(
        "EXP-20261126-01", "H2 騎師＋練馬師分加重", "EXP-20261125-06 H2",
        "EXP-20261126-01.frozen.json", "669259094c0d2ee4bdb80d1bb5fdd9f82002e49ac39f1c1f7465d55cba75c76c", "2026-11-27", 60, 2000,
        (Term("jockey_score", "z", "jockey_score"), Term("trainer_score", "z", "trainer_score"))),
    "EXP-20261126-02": Arm(
        "EXP-20261126-02", "H3 休後狀態曲線（休 ≥90 日、隔 ≤14 日）", "EXP-20261125-06 H3",
        "EXP-20261126-02.frozen.json", "ac287683f5584635dc69d2cef6573aa53db2224dbc1a0af77ae94cfa7d5caf5b", "2026-11-27", 60, 2000,
        (Term("spell90", "ind", "days_since_last", ">=", 90.0),
         Term("backup14", "ind", "days_since_last", "<=", 14.0, lower_exclusive=0.0))),
}


class FrozenParamsChanged(RuntimeError):
    """frozen.json 唔係登記嗰份。"""


class AlreadyJudged(RuntimeError):
    """呢個 arm 已經判過。"""


def load_frozen(arm: Arm) -> dict:
    raw = arm.frozen_path.read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != arm.sha256:
        raise FrozenParamsChanged(f"{arm.frozen_path}: sha256 {got} ≠ 登記 {arm.sha256}")
    w = json.loads(raw)["weights"]
    if set(w) != {t.key for t in arm.terms}:
        raise FrozenParamsChanged(f"{arm.id}: frozen weights {sorted(w)} 同 terms 唔夾")
    return {k: float(v) for k, v in w.items()}


def term_values(arm: Arm, field: list[dict]) -> dict[str, np.ndarray]:
    """→ 每個 term 喺成個賽前場嘅值（z 已場內標準化）。fit 同 forward 共用，保證同一個定義。"""
    out = {}
    for t in arm.terms:
        if t.kind == "z":
            out[t.key] = H1.race_z([x[t.name] for x in field])
        elif t.kind == "ind":
            out[t.key] = np.array([t.indicator(x.get(t.name)) for x in field], float)
        else:
            raise ValueError(f"唔識 term kind {t.kind}")
    return out


def score_field(arm: Arm, field: list[dict], weights: dict) -> None:
    vals = term_values(arm, field)
    shift = sum(weights[k] * v for k, v in vals.items())
    for x, s in zip(field, np.broadcast_to(shift, (len(field),))):
        x["cand_ability"] = float(x["ability"] + s)


def candidate(races: list[dict]) -> list[dict]:
    return H1.candidate(races)


# ---------------------------------------------------------------- 判決鎖

def verdict_path(arm: Arm) -> Path:
    from wongchoi_paths import DATA_ROOT
    return Path(DATA_ROOT) / "WongChoiControl" / "forward_verdicts" / f"{arm.id}.json"


def load_verdict(arm: Arm) -> dict | None:
    p = verdict_path(arm)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_verdict_once(arm: Arm, evaluation: dict) -> Path:
    path = verdict_path(arm)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{arm.id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"experiment": arm.id, "frozen_sha256": arm.sha256, "evaluation": evaluation},
                      fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError as exc:
            raise AlreadyJudged(f"{path} 已經有判決") from exc
    finally:
        os.unlink(tmp)
    return path


# ---------------------------------------------------------------- 讀賽前快照 + 賽果

def _logic_value(horse: dict, field: str):
    cur = horse
    for k in LOGIC_FIELDS[field]:
        cur = cur.get(k) if isinstance(cur, dict) else None
    return H1._float(cur) if cur not in (None, "") else None


def load_logic_fields(snapshot: Path, race_num: int, fields: tuple[str, ...]) -> dict[int, dict]:
    """→ {馬號: {field: 值或 None}}；冇 Logic 檔 = {}（之後成場唔要）。"""
    if not fields:
        return {}
    p = Path(snapshot) / f"Race_{race_num}_Logic.json"
    if not p.exists():
        return {}
    horses = (json.loads(p.read_text(encoding="utf-8")).get("horses") or {})
    out = {}
    for key, h in horses.items():
        try:
            n = int(float(h.get("horse_number") or key))
        except (TypeError, ValueError):
            continue
        out[n] = {f: _logic_value(h, f) for f in fields}
    return out


def collect_meeting(arm: Arm, meeting_dir: Path, core, weights: dict) -> tuple[list[dict], dict]:
    from live_record_exclusions import is_excluded
    from wongchoi_paths import SnapshotArchiveOffline

    info = {"source": "snapshot", "skipped_races": 0}
    if is_excluded("au", meeting_dir.name):
        return [], dict(info, source="excluded")
    results_file = core.find_existing_results_file("au", meeting_dir)
    if not results_file:
        return [], dict(info, source="no_results")
    try:
        snapshot, created, cutoff = core.select_prerace_snapshot(meeting_dir, "au")
    except SnapshotArchiveOffline:
        return [], dict(info, source="offline")
    if snapshot is None or created is None or cutoff is None or created >= cutoff:
        return [], dict(info, source="no_snapshot")
    results = core.load_structured_results("au", Path(results_file))
    preds = core.load_prediction_rows(Path(snapshot), "au")
    date_s = meeting_dir.name[:10]
    races = []
    for race_num in sorted(results):
        scratched = set(results[race_num].get("scratched_horse_numbers") or [])
        actual = {r["horse_no"]: r for r in results[race_num].get("results") or []
                  if r.get("horse_no") and r["horse_no"] not in scratched and 0 < int(r.get("placing") or 0) < 90}
        logic = load_logic_fields(Path(snapshot), int(race_num), arm.logic_fields)
        field = []
        for p in sorted(preds.get(race_num, []), key=lambda q: q["horse_no"]):
            fs = p.get("factor_scores") or {}
            if p.get("ability_score") is None or any(fs.get(f) is None for f in arm.z_leaves) \
                    or (arm.logic_fields and p["horse_no"] not in logic):
                field = None
                break
            row = {"n": p["horse_no"], "name": p.get("horse_name"), "ability": float(p["ability_score"])}
            row.update({f: float(fs[f]) for f in arm.z_leaves})
            row.update(logic.get(p["horse_no"], {}))
            field.append(row)
        if not field:
            info["skipped_races"] += 1
            continue
        score_field(arm, field, weights)
        rows = [dict(x, pos=int(actual[x["n"]]["placing"]), sp=H1._float(actual[x["n"]].get("odds")))
                for x in field if x["n"] in actual]
        field_ns = [x["n"] for x in field]
        # 逐個馬號對（Sol 2026-11-26）：重複馬號唔准、每匹有賽果嘅馬都要喺快照場入面
        if len(rows) < 2 or len(set(field_ns)) != len(field_ns) or set(actual) - set(field_ns):
            info["skipped_races"] += 1
            continue
        races.append({"date": date_s, "meeting": meeting_dir.name, "race": int(race_num), "rows": rows,
                      "source": SOURCE_TAG, "snapshot": Path(snapshot).name, "published_at": created.isoformat()})
    return races, info


def collect(arm: Arm, meetings, weights: dict, core=None) -> tuple[list[dict], dict]:
    core = core or H1._core()
    races, sources, skipped, offline = [], defaultdict(int), 0, []
    for m in meetings:
        got, info = collect_meeting(arm, Path(m), core, weights)
        sources[info["source"]] += 1
        skipped += info["skipped_races"]
        if info["source"] == "offline":
            offline.append(Path(m).name)
        races.extend(got)
    races = [r for r in races if r.get("source") == SOURCE_TAG]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"])), \
        {"meetings": dict(sources), "skipped_races": skipped, "offline": offline}


# ---------------------------------------------------------------- 計數（盲）同判決

def forward_counts(arm: Arm, races: list[dict]) -> dict:
    fwd = [r for r in H1._eligible(races) if r["date"] >= arm.start]
    by_day = defaultdict(int)
    for r in fwd:
        by_day[r["date"]] += 1
    cutoff, days, total = None, 0, 0
    for d in sorted(by_day):
        days += 1
        total += by_day[d]
        if days >= arm.target_days and total >= arm.target_races:
            cutoff = d
            break
    return {"races": len(fwd), "days": len(by_day), "cutoff": cutoff,
            "races_at_cutoff": total if cutoff else None, "days_at_cutoff": days if cutoff else None}


def status(arm: Arm, races: list[dict], sources: dict, weights: dict) -> dict:
    c = forward_counts(arm, races)
    fwd = [r for r in races if r["date"] >= arm.start]
    shift = [abs(x["cand_ability"] - x["ability"]) for r in fwd for x in r["rows"] if "cand_ability" in x]
    ready = c["cutoff"] is not None
    return {"experiment": arm.id, "title": arm.title, "source": arm.source, "start_date": arm.start,
            "target_races": arm.target_races, "target_days": arm.target_days,
            "races_collected": c["races"], "race_days": c["days"], "ready": ready,
            "cutoff_date": c["cutoff"], "frozen_sha256": arm.sha256, "weights": weights,
            "data_source": "賽前快照 select_prerace_snapshot：Race_*_Auto_Scoring.csv＋Race_N_Logic.json",
            "sources": sources,
            "interim": {"mean_abs_shift": float(np.mean(shift)) if shift else None,
                        "note": "盲測：未判之前只報數量（shift 唔睇賽果）"},
            "outcomes_visible": False, "state": "ready" if ready else "collecting",
            "generated_at": datetime.now(timezone.utc).isoformat()}


def evaluate(arm: Arm, races: list[dict], *, nnull: int = 200) -> dict:
    import au_logloss_ruler as L
    import market_ruler as M

    if any(r.get("source") != SOURCE_TAG for r in races):
        raise ValueError("evaluate 只收賽前快照場次")
    c = forward_counts(arm, races)
    if c["cutoff"] is None:
        raise ValueError("未夠數，唔准判")
    cutoff = c["cutoff"]
    base = H1._eligible([r for r in races if r["date"] <= cutoff])
    cand = candidate(base)
    keys = lambda rs: [(r["date"], r["meeting"], r["race"], tuple(x["n"] for x in r["rows"]),  # noqa: E731
                        tuple(x["pos"] for x in r["rows"]), tuple(x["sp"] for x in r["rows"])) for r in rs]
    if keys(base) != keys(cand):
        raise AssertionError("baseline／candidate 未配對")
    full = L.calibrations

    def forward_only(rs, version="v1"):
        return {d: v for d, v in full(rs, version).items() if d >= arm.start}

    scored = sorted(forward_only(base, "v2"))
    if not scored or scored[0] < arm.start or scored[-1] > cutoff:
        raise AssertionError(f"計分賽日唔喺 [{arm.start}, {cutoff}]")
    L.calibrations = forward_only
    try:
        rank = L.evaluate(base, cand, nnull=nnull, version="v2")
    finally:
        L.calibrations = full
    market = M.evaluate(base, cand, price_key="sp", since=CALIBRATION_SINCE, score_window=(arm.start, cutoff))
    gap = H1.windowed_gap_change(base, cand, arm.start, cutoff)
    gap_point = gap.get("dll_per_race")
    keep = rank["verdict"] == "PASS" and gap_point is not None and gap_point <= 0
    a = (market.get("arms") or {}).get("candidate") or {}
    return {"rule": "m3 追市場軌：排名尺 v2 PASS 而且 windowed gap_change 點估計 ≤ 0",
            "cutoff_date": cutoff, "forward_races": c["races_at_cutoff"], "forward_days": c["days_at_cutoff"],
            "scored_days": [scored[0], scored[-1], len(scored)],
            "verdict": "PASS" if keep else "FAIL", "ranking_ruler": rank,
            "market_ruler": {"gap_change": gap,
                             "paired_judge": {k: (market.get("paired") or {}).get(k)
                                              for k in ("verdict", "checks", "win_positive_blocks")},
                             "candidate_has_info_beyond_market": a.get("has_info_beyond_market"),
                             "candidate_arm": {k: a.get(k) for k in ("win", "top3", "gap_to_market")},
                             "common_races": market.get("common_races"), "version": market.get("version")},
            "next": "PASS = Kelvin 決定上唔上線（另一個改動＋model-regression-gate）；FAIL = 記錄，唔准同一批數據重試",
            "evaluated_at": datetime.now(timezone.utc).isoformat()}


def judge_once(arm: Arm, races: list[dict], **kw) -> dict:
    if verdict_path(arm).exists():
        raise AlreadyJudged(f"{arm.id} 已經判過")
    ev = evaluate(arm, races, **kw)
    write_verdict_once(arm, ev)
    return ev


# ---------------------------------------------------------------- CLI

class NonProductionJudge(RuntimeError):
    """判決只准喺生產語料度封（Sol 2026-11-26：換 --data-root 唔可以封正式判決）。"""


def run_arm(arm: Arm, command: str, out_path: Path, root: Path, *, production_root: Path | None = None) -> dict:
    if Path(out_path).resolve().parent == verdict_path(arm).resolve().parent:
        raise ValueError(f"--output 唔准寫入判決鎖目錄 {verdict_path(arm).parent}")
    locked = load_verdict(arm)
    if locked:
        previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
        st = dict(previous, experiment=arm.id, evaluation=locked["evaluation"], outcomes_visible=True,
                  state="evaluated", ready=True, verdict_file=str(verdict_path(arm)))
        if previous != st:
            H1._atomic_write(out_path, st)
        return st
    weights = load_frozen(arm)
    since = arm.start if command == "status" else CALIBRATION_SINCE
    races, sources = collect(arm, H1.meeting_list(root, since), weights)
    st = status(arm, races, sources, weights)
    st["verdict_file"] = str(verdict_path(arm))
    if command == "evaluate" and st["ready"]:
        if production_root is None or Path(root).resolve() != Path(production_root).resolve():
            raise NonProductionJudge(f"{root} 唔係生產語料 {production_root}，唔准封判決")
        if sources["offline"]:
            st["state"] = "blocked_offline"
            st["blocked"] = sources["offline"][:20]
        else:
            st["evaluation"] = judge_once(arm, races)
            st["outcomes_visible"] = True
            st["state"] = "evaluated"
    H1._atomic_write(out_path, st)
    return st


def status_file_name(arm: Arm) -> str:
    return f"au-hyp-forward-{arm.id}.json"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "evaluate", "nightly", "list"])
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output")
    ap.add_argument("--work-dir")
    a = ap.parse_args(argv)
    from wongchoi_paths import AU_RACING
    root = Path(a.data_root) if a.data_root else Path(AU_RACING)
    if a.command == "list":
        print("\n".join(ARMS))
        return 0
    if a.command == "nightly":
        if not a.work_dir:
            ap.error("nightly 要 --work-dir")
        rc = 0
        arms = [ARMS[a.arm]] if a.arm else list(ARMS.values())
        for arm in arms:
            try:
                out = Path(a.work_dir) / status_file_name(arm)
                st = run_arm(arm, "status", out, root, production_root=Path(AU_RACING))
                if st.get("ready") and st.get("state") != "evaluated":
                    st = run_arm(arm, "evaluate", out, root, production_root=Path(AU_RACING))
                print(f"{arm.id}: {st.get('state')} {st.get('races_collected')} 場／{st.get('race_days')} 日")
            except Exception as exc:  # 一個 arm 壞唔好拖死其他
                rc = 1
                print(f"{arm.id}: error {type(exc).__name__}: {exc}", file=sys.stderr)
        return rc
    if not (a.arm and a.output):
        ap.error("status／evaluate 要 --arm 同 --output")
    st = run_arm(ARMS[a.arm], a.command, Path(a.output), root, production_root=Path(AU_RACING))
    print(json.dumps({k: v for k, v in st.items() if k != "evaluation"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
