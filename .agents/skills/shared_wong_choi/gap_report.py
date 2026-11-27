#!/usr/bin/env python3
"""改善空間清單（Kelvin 2026-11-26：「唔好假設已經係最好」—— 網球被講「試晒」，但其實好多輸入欄好耐冇填）。

每週（`review_ai.weekly` 之前自動跑；亦可以人手跑）將「仲有咩可以改善」擺晒出嚟，唔靠任何一個 agent 記得謙虛：
  1. **輸入欄缺口**（四個 domain）：最新一週填充率 < 80%、或者證據弱率 > 50%、或者同 8 週前比跌咗 ≥ 20pp 嘅欄。
     賽馬讀 `<資料根>/<AU|HKJC>_Field_Health.jsonl`；NBA／網球讀 `field_health_sports.weekly_table`。
     0% 嘅欄照當缺口；只有 `resources/known_retired_fields.json` 列明（原因＋實驗）嘅刻意停用欄先隱藏。
  2. **觀察中嘅假設**（`learning/hypotheses.jsonl` state = watching）。
  3. **舊 REJECT**：`docs/experiments/INDEX.md` 入面 60 日以前判 REJECT 嘅記錄（按 domain 分）—— 只係嗰個做法喺嗰批數據唔得，
     樣本多咗／資料來源變咗就值得重評（重評要新登記、新數據，唔准用舊數據救）。60 日內 INDEX 有一行假設欄寫
     「重評 EXP-…」，嗰啲 EXP 就唔再列（重評記錄本身 60 日後如果仍係 REJECT 會再出現）。
輸出 `<WongChoiControl>/learning/gap_report.json`。每週 Opus 總結一定要由呢度揀最少 3 項「下一步可以做」。

    python3 gap_report.py [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RACING = REPO / ".agents" / "skills" / "shared_racing" / "scripts"
for _p in (str(HERE), str(RACING), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LOW_FILL, HIGH_WEAK, DROP = 0.80, 0.50, 0.20
OLD_REJECT_DAYS = 60
MAX_PER_DOMAIN = 15


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl"))


def _racing_rows(platform: str) -> list[dict]:
    import model_probability as M
    name = {"au": "AU_Field_Health.jsonl", "hkjc": "HKJC_Field_Health.jsonl"}[platform]
    try:
        text = (M.default_root(platform) / name).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def _sports_rows(domain: str) -> list[dict]:
    import field_health_sports as F
    return F.weekly_table(domain, weeks=9)


KNOWN = HERE / "resources" / "known_retired_fields.json"


def known_retired(domain: str) -> list[dict]:
    try:
        return [f for f in json.loads(KNOWN.read_text(encoding="utf-8"))["fields"] if f.get("domain") == domain]
    except (OSError, ValueError, KeyError):
        return []


def _is_known(field: str, known: list[dict]) -> bool:
    for k in known:
        pat = str(k.get("field") or "")
        if field == pat or (pat.endswith("*") and field.startswith(pat[:-1])):
            return True
    return False


def field_gaps(rows: list[dict], known: list[dict] | None = None) -> dict:
    """→ 缺口清單，用最新一週對 8 週前。**只有** `known_retired_fields.json` 列明嘅欄先隱藏（要寫原因＋實驗）；
    其他 0% 欄（一直空、或者近 3 週變 0%）照當缺口 —— 「睇落似停用」唔可以靠估（Kelvin 2026-11-26）。"""
    known = known or []
    weeks = sorted({r["week"] for r in rows})
    if not weeks:
        return {"week": None, "gaps": [], "always_empty": []}
    latest, first = weeks[-1], weeks[0]
    by = defaultdict(dict)
    for r in rows:
        by[(r.get("source"), r["field"])][r["week"]] = r
    gaps, hidden = [], []
    prev = weeks[-2] if len(weeks) > 1 else None
    for (src, field), wk in by.items():
        now = wk.get(latest)
        if not now:
            if prev and prev in wk and not _is_known(field, known):    # 上週仲有、今週冇咗（Sol）
                gaps.append({"field": field, "source": src, "fill_rate": None, "weak_rate": None, "n": 0,
                             "why": f"{latest} 冇咗呢欄（{prev} 仲有）"})
            continue
        if _is_known(field, known):
            hidden.append(field)
            continue
        fills = [w.get("fill_rate") for w in wk.values() if w.get("fill_rate") is not None]
        if str(field).startswith("source_lag."):          # 來源新鮮度（網球歷史源）：落後 ≥7 日 = 缺口
            lag = now.get("mean")
            if lag is not None and lag >= 7:
                gaps.append({"field": field, "source": src, "fill_rate": None, "weak_rate": None, "n": now.get("n"),
                             "why": f"來源最新資料落後 {lag:.0f} 日"})
            continue
        reasons = []
        fill, weak = now.get("fill_rate"), now.get("weak_rate")
        old = wk.get(first) or {}
        if fills and max(fills) == 0:
            reasons.append("一直都係 0%（從來冇填過）")
        elif fill is not None and fill < LOW_FILL:
            reasons.append(f"填充率 {fill:.0%}")
        if weak is not None and weak > HIGH_WEAK:
            reasons.append(f"證據弱率 {weak:.0%}")
        if fill is not None and old.get("fill_rate") is not None and old["fill_rate"] - fill >= DROP:
            reasons.append(f"由 {first} {old['fill_rate']:.0%} 跌到 {fill:.0%}")
        if reasons:
            gaps.append({"field": field, "source": src, "fill_rate": fill, "weak_rate": weak, "n": now.get("n"),
                         "why": "；".join(reasons)})
    gaps.sort(key=lambda g: (-(1 if ("跌到" in g["why"] or "冇咗" in g["why"]) else 0),
                             g["fill_rate"] if g["fill_rate"] is not None else 0))
    return {"week": latest, "gaps": gaps[:MAX_PER_DOMAIN], "gaps_total": len(gaps),
            "known_retired_hidden": sorted(hidden), "known_retired_total": len(hidden)}


DOMAIN_KEYS = {"au": (r"\bAU\b",), "hkjc": (r"HKJC",), "nba": (r"\bNBA\b",), "tennis": (r"Tennis", r"網球")}


def old_rejects(today: str, index: Path | None = None) -> dict[str, list[dict]]:
    index = index or (REPO / "docs" / "experiments" / "INDEX.md")
    cutoff = (Date.fromisoformat(today) - timedelta(days=OLD_REJECT_DAYS)).isoformat()
    out = defaultdict(list)
    try:
        lines = index.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    reevaluated = set()                     # 60 日內有新記錄寫明「重評 EXP-…」就當已重評（Kelvin 2026-11-27）
    for line in lines:
        m = re.search(r"EXP-(\d{4})(\d{2})(\d{2})-[\w-]+", line)
        if not m or f"{m.group(1)}-{m.group(2)}-{m.group(3)}" <= cutoff or "重評" not in line:
            continue
        span = line.split("重評", 1)[1].split("|", 1)[0]   # 只睇「重評」後面同一格，唔計判決欄提到嘅其他實驗
        reevaluated.update(re.findall(r"EXP-\d{8}-[\w]+", span))
    for line in lines:
        if "REJECT" not in line:          # INDEX 判決一律大楷；細楷「reject」可能係描述
            continue
        m = re.search(r"EXP-(\d{4})(\d{2})(\d{2})-[\w-]+", line)
        if not m:
            continue
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if d > cutoff:
            continue
        if m.group(0) in reevaluated:
            continue
        if any(x["id"] == m.group(0) for v in out.values() for x in v):
            continue                        # INDEX 有兩種格式重複記同一個 EXP
        for dom, pats in DOMAIN_KEYS.items():
            if any(re.search(p, line) for p in pats):
                text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line).strip("-| ").strip()
                out[dom].append({"id": m.group(0), "date": d, "text": text[:220]})
                break
    return {k: v[-8:][::-1] for k, v in out.items()}


def watching(root: Path) -> list[dict]:
    p = root / "learning" / "hypotheses.jsonl"
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                h = json.loads(line)
            except ValueError:
                continue
            if h.get("state") == "watching":
                rows.append({k: h.get(k) for k in ("id", "domain", "born", "title", "cohort", "direction")})
    return rows


def build(today: str | None = None) -> dict:
    today = today or Date.today().isoformat()
    domains = {}
    for dom in ("au", "hkjc", "nba", "tennis"):
        try:
            rows = _racing_rows(dom) if dom in ("au", "hkjc") else _sports_rows(dom)
            domains[dom] = field_gaps(rows, known_retired(dom))
        except Exception as exc:  # noqa: BLE001 — 一個 domain 讀唔到唔阻其他
            domains[dom] = {"error": f"{type(exc).__name__}: {exc}"}
    rej = old_rejects(today)
    for dom in domains:
        domains[dom]["old_rejects"] = rej.get(dom, [])
    return {"version": "gap-report-v1", "date": today, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rule": "唔准講「已經做晒」：呢度係仲未補嘅輸入、仲喺觀察嘅假設、可以重評嘅舊 REJECT（Kelvin 2026-11-26）",
            "domains": domains, "watching_hypotheses": watching(control_root())}


def write(report: dict) -> Path:
    p = control_root() / "learning" / "gap_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    r = build(a.today)
    p = write(r)
    for dom, d in r["domains"].items():
        print(f"{dom}: 缺口 {d.get('gaps_total', '?')}、確認停用（隱藏）{d.get('known_retired_total', 0)}、舊 REJECT {len(d.get('old_rejects') or [])}"
              + (f"（{d['error']}）" if d.get("error") else ""))
    print(f"觀察中假設 {len(r['watching_hypotheses'])} → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
