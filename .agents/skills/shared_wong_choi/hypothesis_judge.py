#!/usr/bin/env python3
"""假設驗證（自學循環 L3，Kelvin 2026-11-26；設計 docs/plans/2026-11-26-self-learning-loop.md §2 L3／§4，Astra 覆核）。

假設帳 `<WongChoiControl>/learning/hypotheses.jsonl` 入面 state = watching 嘅假設，**只用 born 之後**嘅新數據自動判一次：
  * 樣本（預先寫死）：born 之後（唔包 born 當日）有樣本嘅日子 ≥ MIN_DAYS（30），組別樣本 ≥ max(MIN_N, 功效樣本量)；
    功效樣本量 = 1.5 × p̄(1−p̄)·(2.8/0.03)²：真效應 6pp 時 ~80% 判支持、真效應 0 時 ~80% 判否決（支持要 CI 下限 > 3pp，
    即係要明顯大過 3pp；真效應啱啱 3pp 只有一半機會）。1.5 = 同場相關嘅設計效應。p̄ 只用模型預測（walk-forward 校準會間接
    受早期整體結果影響，但唔係用呢個組別自己嘅結果）—— 太早判會大部分變「未定」再鎖死。
  * 量度：組別入面「模型殘差」= 實際 − 賽前模型機率（賽馬：入頭三、校準機率 walk-forward；NBA：p_final；網球：model_prob_raw），
    按日 cluster bootstrap 95% CI；方向按假設（model_under = 殘差正、model_over = 殘差負）。
  * 判決：CI 全部喺預期方向而且超過 EFFECT（3pp）→ supported；CI 全部唔夠 3pp（包埋反方向）→ rejected；跨 3pp → undecided。
  * **判一次就鎖**（帳入面寫 verdict＋judged_at；之後唔會再判，唔延長窗口）。undecided 唔會重判；要再試就要新假設、新 born。
  * 唔夠數 = 只寫進度（盲：唔報殘差），等下次。
supported → Telegram primary「值得開預先登記 forward 測試」（AU：`au_hypothesis_forward.ARMS` 加一行）；**永遠唔自動改模型**。
每週一喺 Opus 總結之前跑（`review_ai.weekly`）。

    python3 hypothesis_judge.py [--today YYYY-MM-DD] [--telegram]
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RACING = REPO / ".agents" / "skills" / "shared_racing" / "scripts"
for _p in (str(HERE), str(RACING), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MIN_DAYS = 30
MIN_N = {"au": 200, "hkjc": 200, "nba": 300, "tennis": 300}
EFFECT = 0.03
DESIGN_EFFECT = 1.5      # 同場馬／同場波嘅腿互相相關（Sol）：樣本量乘 1.5
BOOT = 2000


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl"))


def ledger_path() -> Path:
    return control_root() / "learning" / "hypotheses.jsonl"


# ---------------------------------------------------------------- 數據（同覆盤同一套組別定義）

def racing_rows(platform: str, since: str, until: str) -> list[dict]:
    """born 之後（since 唔包）到 until 嘅每匹馬：hit3、p_top3、cohorts。同 post_review 同一套機率同組別。"""
    import model_probability as M
    import post_review as PR
    root = M.default_root(platform)
    core = PR._core()
    nxt = (Date.fromisoformat(until) + timedelta(days=1)).isoformat()
    races, _ = M.collect(platform, root, until=nxt)
    races = [r for r in races if r.get("published_at")]
    wf = M.walk_forward(races, platform)
    want = [r for r in races if since < r["date"] <= until and r["date"] in wf]
    meetings = {r["meeting"] for r in want}
    detail = {}
    for m in M.meeting_list(platform, root):
        if m.name in meetings:
            got, _ = PR.meeting_detail(platform, m, core)
            detail.update({(m.name, race, n): v for (race, n), v in got.items()})
    rows = []
    for r in want:
        for x in PR.race_probs(r, wf[r["date"]], platform):
            d = detail.get((r["meeting"], r["race"], x["n"]))
            if d and d.get("rank"):
                rows.append({"date": r["date"], "y": x["hit3"], "p": x["p_top3"], "cohorts": set(d.get("cohorts") or [])})
    return rows


def sports_rows(domain: str, since: str, until: str) -> list[dict]:
    import post_review_sports as S
    trail = (Date.fromisoformat(until) - Date.fromisoformat(since)).days
    rows = S.nba_rows(until, trail)[0] if domain == "nba" else S.tennis_rows(until, trail)
    return [{"date": x["date"], "y": x["hit3"], "p": x["p_top3"], "cohorts": set(x["cohorts"])}
            for x in rows if since < x["date"] <= until]


def rows_for(domain: str, since: str, until: str) -> list[dict]:
    return racing_rows(domain, since, until) if domain in ("au", "hkjc") else sports_rows(domain, since, until)


# ---------------------------------------------------------------- 判

def judge(h: dict, rows: list[dict], seed: int = 11) -> dict:
    cond = set(h.get("cohort") or [])
    xs = [r for r in rows if cond and cond <= r["cohorts"]]
    by_day = defaultdict(list)
    for r in xs:
        by_day[r["date"]].append(r["y"] - r["p"])
    days, n = len(by_day), len(xs)
    # 預先定功效樣本量（Astra）：80% 功效分辨 3pp，n ≥ p̄(1−p̄)·(2.8/0.03)²；p̄ 只用模型預測（冇睇結果，唔破盲）
    pbar = float(np.mean([r["p"] for r in xs])) if xs else 0.3
    need_n = max(MIN_N.get(h.get("domain"), 300),
                 int(np.ceil(DESIGN_EFFECT * pbar * (1 - pbar) * (2.8 / EFFECT) ** 2)))
    progress = {"days": days, "n": n, "need_days": MIN_DAYS, "need_n": need_n}
    if days < MIN_DAYS or n < need_n:
        return {"state": "watching", "progress": progress}            # 盲：唔報殘差
    keys = sorted(by_day)
    sums = np.array([sum(by_day[d]) for d in keys])
    cnts = np.array([len(by_day[d]) for d in keys])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(BOOT, len(keys)))
    est = sums[idx].sum(1) / cnts[idx].sum(1)
    sign = 1 if h.get("direction") == "model_under" else -1
    lo, hi = np.quantile(sign * est, [0.025, 0.975])
    mean = float(sign * sums.sum() / cnts.sum())
    if lo > EFFECT:
        verdict = "supported"
    elif hi < EFFECT:
        verdict = "rejected"
    else:
        verdict = "undecided"
    return {"state": verdict, "progress": progress,
            "result": {"directional_resid_pp": round(100 * mean, 2), "ci_pp": [round(100 * lo, 2), round(100 * hi, 2)],
                       "effect_pp": round(100 * EFFECT, 1), "rule": "CI 全部 > 3pp 支持；全部 < 3pp 否決；跨 3pp 未定（判一次就鎖）"}}


def _read_ledger(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(today: str | None = None, telegram: bool = False, rows_fn=rows_for) -> dict:
    """先喺鎖外面計（讀成個窗口要幾分鐘，唔好阻住 review_ai.register），之後攞鎖重讀帳、只更新仲係 watching 嘅。"""
    today = today or Date.today().isoformat()
    path = ledger_path()
    if not path.exists():
        return {"judged": [], "watching": 0}
    todo = [h for h in _read_ledger(path)
            if h.get("state") == "watching" and not h.get("judged_at") and str(h.get("born") or "") < today
            and h.get("born")]
    cache: dict[tuple, list] = {}
    updates: dict[str, dict] = {}
    for h in todo:
        key = (h.get("domain"), h["born"])
        if key not in cache:
            try:
                cache[key] = rows_fn(h["domain"], h["born"], today)
            except Exception as exc:  # noqa: BLE001 —— 一個 domain 讀唔到唔阻其他
                updates[h["id"]] = {"last_error": f"{type(exc).__name__}: {exc}", "checked_at": today}
                continue
        out = judge(h, cache[key])
        upd = {"progress": out["progress"], "checked_at": today}
        if out["state"] != "watching":
            upd.update(state=out["state"], result=out["result"], judged_at=today)
        updates[h["id"]] = upd
    lock = open(path.with_suffix(".lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)            # 同 review_ai.register 同一把鎖；入面只做讀寫，好快
    try:
        hyps = _read_ledger(path)
        judged = []
        for h in hyps:
            upd = updates.get(h.get("id"))
            if not upd or h.get("state") != "watching" or h.get("judged_at"):
                continue                          # 計緊嗰陣已經俾人改咗 → 唔覆蓋
            h.update(upd)
            if upd.get("judged_at"):
                judged.append(h)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".hypotheses.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in hyps))
        os.replace(tmp, path)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    if telegram and judged:
        sys.path.insert(0, str(RACING))
        import racing_telegram as T
        T.send_message(telegram_text(judged), audience="primary")
    return {"judged": judged, "watching": sum(1 for h in hyps if h.get("state") == "watching")}


def telegram_text(judged: list[dict]) -> str:
    zh = {"supported": "✅ 支持", "rejected": "❌ 否決", "undecided": "➖ 未定"}
    lines = ["📒 假設驗證（只用出世之後嘅新數據，判一次就鎖；唔會自動改模型）"]
    for h in judged:
        r = h.get("result") or {}
        lines.append(f"{zh.get(h['state'], h['state'])}｜{h.get('domain')}｜{h.get('title')}："
                     f"{r.get('directional_resid_pp')}pp [{(r.get('ci_pp') or [None, None])[0]}, {(r.get('ci_pp') or [None, None])[1]}]"
                     f"（{h['progress']['days']} 日、{h['progress']['n']}）")
    if any(h["state"] == "supported" for h in judged):
        lines.append("支持 = 值得開預先登記 forward 測試（AU：au_hypothesis_forward.ARMS 加一行）；上唔上線由你決定。")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--today")
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args(argv)
    r = run(a.today, a.telegram)
    print(f"判咗 {len(r['judged'])} 個；仲觀察緊 {r['watching']} 個")
    for h in r["judged"]:
        print(f"  {h['id']}: {h['state']} {h.get('result')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
