#!/usr/bin/env python3
"""每週健康巡查（Kelvin 2026-11-26：「每一個欄位每一個分數都做一次健康檢查 … 由 hydrogen／luna／terra 做」）。

分工：Python 計晒所有欄位（`field_health.py`、`data_contract`、golden，照舊）；呢度加兩樣要「大量人手睇」嘅嘢交 Hydrogen：
  1. **原文抽查**：隨機抽上週 AU／HKJC 各 N 匹馬，將「抓返嚟嘅原文」（AU Racecard／Formguide、HKJC 排位表／賽績）同
     「入分用嘅欄位」（賽前快照 Logic）擺埋一齊，叫 Hydrogen 逐項對：檔位、負磅、騎師、練馬師、出賽數、上仗名次、
     相隔日數、評分（HKJC）。捉「欄位仲喺度、數值靜靜錯咗」（解析／建 Logic 嗰層）。
  2. **欄位健康趨勢**：最近 8 週 `<平台>_Field_Health.jsonl`（填充率、弱證據率、來源），叫佢搵慢慢變壞或者突然唔妥嘅欄位。
Python 核實：Hydrogen 話「對唔上」嘅，要佢引嘅原文真係喺嗰份原文入面、我哋嘅值真係係我哋嘅值，先算「確認」；
趨勢異常要欄位名真係存在。確認咗先 Telegram primary（要 Opus／Kelvin 睇），冇就一句「全部正常」。
Gemini 撞額度 → codex_delegate 自動停派；呢度退返 Luna（`run quick`）。唔改任何嘢。

輸出：`<WongChoiControl>/health_sweep/<日>.json`＋`.md`。排程：每星期一 07:30（`central-wong-choi.health-sweep`）。

    python3 health_sweep.py [--sample 20] [--telegram] [--seed N]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RACING = REPO / ".agents" / "skills" / "shared_racing" / "scripts"
DELEGATE = REPO / ".agents" / "scripts" / "codex_delegate.py"
for _p in (str(RACING), str(HERE), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

VERSION = "health-sweep-v1"
EXTRA_PATH = ["/opt/homebrew/bin", str(Path.home() / ".local" / "bin"), "/usr/local/bin"]

TASK = """你係 Wong Choi 數據質素檢查員。讀 {packet}（JSON）。
**只可以用讀檔工具直接讀，唔准行任何 shell／python 命令（會被拒絕，成個任務就會失敗）。**入面有兩部分：

A. `spot_checks`：每個樣本有 `raw`（我哋抓返嚟嘅原文）同 `ours`（入分用嘅欄位值）。逐個欄位對：原文講嘅同 `ours` 一唔一樣？
   - 單位／寫法唔同但意思一樣（59.5kg vs 59.5、「周俊樂 (-2)」vs「周俊樂」）= match。
   - 原文搵唔到嗰項 = unclear（唔好估）。
   - 相隔日數 ±1 日、名次寫法（5/12 vs 5）= match。
   - 負磅：HKJC 排位表係「分配負磅」，騎師名後面有 (-2)／(-5) 即係見習減磅，入分用減咗之後（124 同 (-2) → 122）= match；
     AU 同理（Weight 係分配，入分可能係扣咗見習減磅）。
   - 騎師／練馬師名：多咗少咗頭銜、合夥練馬師寫法次序唔同 = match。
   - AU last_start_finish 係最近一場**正式賽**（試閘 TRIAL 唔計）；HKJC last_6_finishes 係由近到遠。
   - AU barrier：有退出馬時入分用「密集排位」（剩低嘅馬按原檔位重新排 1..N，`data_prep` 刻意修正），所以
     入分檔位 ≤ 原文檔位、而且同場次序一樣 = match。只有入分檔位 > 原文、或者次序調轉先算 mismatch。
   - AU age：2026-11-22 之前嘅 Logic 冇 age（欄位係嗰日先加），ours 係 None = unclear，唔係 mismatch。
B. `field_health`：每個平台最近 8 週每個欄位嘅 fill_rate／weak_rate／n。搵：突然跌（例如由 >0.9 跌到 <0.5）、
   連續幾週慢慢變差、變咗常數、n 突然少咗好多。正常波動唔好報。
   **最新一週可能未完**：佢 n 細係正常，唔好報。field 要照抄表入面嘅欄位名（唔使加來源）。

只輸出一個 JSON：
{{"spot_checks": [{{"id": "…", "field": "…", "ours": "…", "raw": "原文入面嘅字（照抄）", "verdict": "match|mismatch|unclear"}}],
  "field_health": [{{"platform": "au|hkjc", "field": "…", "issue": "一句", "weeks": "例：W45→W48"}}]}}
spot_checks 只需要列 mismatch 同 unclear（match 唔使列）。唔肯定就 unclear，唔好作。
"""


def _env() -> dict:
    env = os.environ.copy()
    env["PATH"] = ":".join(EXTRA_PATH + [env.get("PATH", "")])
    return env


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl"))


# ---------------------------------------------------------------- 抽樣

def _block(text: str, start_pat: str, next_pat: str, limit: int = 1800) -> str | None:
    m = re.search(start_pat, text, re.M)
    if not m:
        return None
    rest = text[m.start():]
    first_nl = rest.find("\n")            # 由第二行開始搵下一個標題（Sol：「10. X」用 rest[1:] 會即刻撞到「0. 」）
    if first_nl < 0:
        return rest[:limit]
    n = re.search(next_pat, rest[first_nl + 1:], re.M)
    return rest[: (first_nl + 1 + n.start()) if n else limit][:limit]


def _au_ours(h: dict) -> dict:
    pa = h.get("python_auto") or {}
    rows = (((pa.get("stability_detail") or {}).get("form") or {}).get("rows") or [])
    return {"barrier": h.get("barrier"), "weight": h.get("weight"), "jockey": h.get("jockey"), "trainer": h.get("trainer"),
            "career_starts": h.get("career_race_starts"), "age": h.get("age"),
            "last_start_finish": rows[0].get("place") if rows else None,
            "days_since_last_run": (pa.get("preparation_cycle") or {}).get("days_since_last_run"),
            "gear_changes": (h.get("_data") or {}).get("gear_changes")}


def _hkjc_ours(h: dict) -> dict:
    d = h.get("_data") or {}
    return {"barrier": h.get("barrier"), "weight": h.get("weight"), "jockey": h.get("jockey"), "trainer": h.get("trainer"),
            "last_6_finishes": h.get("last_6_finishes"), "days_since_last": h.get("days_since_last"),
            "rating": d.get("current_rating")}


def sample_platform(platform: str, since: str, until: str, n: int, rng: random.Random) -> tuple[list[dict], dict]:
    import model_probability as M
    core = M._core()
    meetings = [m for m in M.meeting_list(platform, M.default_root(platform)) if since <= m.name[:10] <= until]
    pool = []
    for m in meetings:
        try:
            snap, _c, _cut = core.select_prerace_snapshot(m, platform)
        except Exception:  # noqa: BLE001 — 斷碟等等：呢個場次唔抽
            continue
        if not snap:
            continue
        for logic in sorted(Path(snap).glob("Race_*_Logic.json")):
            race = int(re.search(r"Race_(\d+)_", logic.name).group(1))
            try:
                horses = json.loads(logic.read_text(encoding="utf-8")).get("horses") or {}
            except (OSError, ValueError):
                continue
            for key in horses:
                pool.append((m, Path(snap), race, key))
    picks = rng.sample(pool, min(n, len(pool)))
    out = []
    for m, snap, race, key in picks:
        h = json.loads((snap / f"Race_{race}_Logic.json").read_text(encoding="utf-8"))["horses"][key]
        num = str(h.get("horse_number") or key)
        raw = _raw_au(snap, race, num) if platform == "au" else _raw_hkjc(m, snap, race, num)
        if not raw:
            continue
        out.append({"id": f"{platform}|{m.name}|R{race}|{num}", "platform": platform, "horse": h.get("horse_name"),
                    "raw": raw, "ours": _au_ours(h) if platform == "au" else _hkjc_ours(h)})
    return out, {"meetings": len(meetings), "pool": len(pool), "sampled": len(out)}


def _read(paths) -> str:
    for p in paths:
        try:
            return Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def _raw_au(snap: Path, race: int, num: str) -> str | None:
    card = _read(sorted(snap.glob(f"* Race {race} Racecard.md")))
    form = _read(sorted(snap.glob(f"* Race {race} Formguide.md")))
    a = _block(card, rf"^{num}\. ", r"^\d+\. ")
    b = _block(form, rf"^\[{num}\] ", r"^\[\d+\] ", limit=2600)
    if not (a or b):
        return None
    return "【Racecard】\n" + (a or "（搵唔到）") + "\n【Formguide】\n" + (b or "（搵唔到）")


def _raw_hkjc(meeting: Path, snap: Path, race: int, num: str) -> str | None:
    card = _read(sorted(snap.glob(f"* Race {race} 排位表.md")) + sorted(meeting.glob(f"* Race {race} 排位表.md")))
    form = _read(sorted(meeting.glob(f"* Race {race} 賽績.md")))
    a = _block(card, rf"^馬號: {num}\s*$", r"^馬號: \d+\s*$")
    b = _block(form, rf"^馬號: {num}\s*$", r"^馬號: \d+\s*$", limit=1500)
    if not (a or b):
        return None
    return "【排位表】\n" + (a or "（搵唔到）") + "\n【賽績】\n" + (b or "（搵唔到）")


def field_health_table(platform: str, weeks: int = 8) -> list[dict]:
    import model_probability as M
    name = {"au": "AU_Field_Health.jsonl", "hkjc": "HKJC_Field_Health.jsonl"}[platform]
    path = M.default_root(platform) / name
    try:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []
    keep = sorted({r["week"] for r in rows})[-weeks:]
    out = []
    for r in rows:
        if r.get("week") in keep:
            out.append({k: r.get(k) for k in ("week", "source", "field", "fill_rate", "weak_rate", "n")
                        if r.get(k) is not None})
    return out


# ---------------------------------------------------------------- Hydrogen

def run_ai(packet: dict, timeout: int = 900) -> tuple[dict | None, str, str]:
    """→ (結果, 錯誤, 用咗邊個)。先 Hydrogen（run third）；Gemini 停派／失敗就退 Luna（run quick）。"""
    sys.path.insert(0, str(REPO / ".agents" / "scripts"))
    from self_repair_triage import _json_from      # 同一個抽 JSON 嘅 helper
    work = Path(tempfile.mkdtemp(prefix="health_sweep_"))
    try:
        (work / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1), encoding="utf-8")
        brief = work / "brief.md"
        brief.write_text(TASK.format(packet=work / "packet.json"), encoding="utf-8")
        err = ""
        for role, who in (("third", "Hydrogen"), ("quick", "Luna")):
            out = work / f"out_{role}.md"
            proc = subprocess.run([sys.executable, str(DELEGATE), "run", role, "--cd", str(work), "--prompt-file", str(brief),
                                   "--out", str(out), "--title", f"每週健康巡查（{who}）", "--reply-limit", "3000",
                                   "--timeout", str(timeout)],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout + 180, env=_env())
            data = _json_from(out.read_text(encoding="utf-8")) if out.exists() else None
            if proc.returncode == 0 and data:
                return data, "", who
            err = (((proc.stderr or "") + (proc.stdout or "")).strip()[-300:] or f"rc={proc.returncode}")
        return None, err, ""
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}", ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- Python 核實

def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def verify(result: dict, samples: list[dict], health: dict[str, list[dict]]) -> dict:
    by_id = {s["id"]: s for s in samples}
    confirmed, rejected, unclear = [], [], []
    for c in result.get("spot_checks") or []:
        if not isinstance(c, dict):
            continue
        s = by_id.get(c.get("id"))
        verdict = c.get("verdict")
        if verdict == "unclear":
            unclear.append(c)
            continue
        if verdict != "mismatch":
            continue
        if not s or c.get("field") not in s["ours"]:
            rejected.append(dict(c, why="樣本／欄位唔存在"))
        elif len(_norm(c.get("raw"))) < 2 or _norm(c.get("raw")) not in _norm(s["raw"]):
            rejected.append(dict(c, why="引用嘅原文係空白／太短，或者喺原文入面搵唔到"))
        elif _norm(c.get("ours")) != _norm(s["ours"].get(c["field"])):
            rejected.append(dict(c, why="講嘅「我哋嘅值」唔係我哋嘅值"))
        else:
            confirmed.append(dict(c, ours_actual=s["ours"].get(c["field"]), horse=s.get("horse")))
    values: dict[tuple, set[str]] = {}
    for p, rows in health.items():
        for r in rows:
            vs = values.setdefault((p, r["field"]), set())
            for k in ("fill_rate", "weak_rate", "n"):
                v = r.get(k)
                if isinstance(v, (int, float)):
                    vs.update({f"{v:g}", f"{v:.1f}", f"{v:.2f}", f"{v:.3f}", f"{v:.4f}", f"{100 * v:.1f}", f"{100 * v:.0f}"})
    trend_ok, trend_bad = [], []
    for t in result.get("field_health") or []:
        if not isinstance(t, dict):
            continue
        field = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", str(t.get("field") or "")).strip()   # 「x (leaf)」→「x」
        key = (t.get("platform"), field)
        t = dict(t, field=field)
        if key not in values:
            trend_bad.append(dict(t, why="欄位唔存在"))
            continue
        # 只核 ≥2 位小數嘅精確數字（最易作）；佢自己除出嚟嘅百分比、整數唔核
        nums = re.findall(r"(?<![\d.])\d+\.\d{2,}(?!%)", str(t.get("issue") or ""))
        if any(x not in values[key] for x in nums):     # 引用嘅數字要喺嗰個欄位嘅數據入面
            trend_bad.append(dict(t, why="引用嘅數字喺欄位數據搵唔到"))
        else:
            trend_ok.append(t)
    return {"confirmed_mismatches": confirmed, "rejected_claims": rejected, "unclear": unclear,
            "trend_flags": trend_ok, "rejected_trends": trend_bad}


# ---------------------------------------------------------------- 主流程

def build(n: int = 20, seed: int | None = None, today: str | None = None) -> dict:
    today = today or Date.today().isoformat()
    since = (Date.fromisoformat(today) - timedelta(days=7)).isoformat()
    rng = random.Random(seed if seed is not None else int(today.replace("-", "")))
    samples, meta = [], {}
    for plat in ("au", "hkjc"):
        got, meta[plat] = sample_platform(plat, since, today, n, rng)
        samples += got
    health = {p: field_health_table(p) for p in ("au", "hkjc")}
    out = {"version": VERSION, "date": today, "window": [since, today], "sampling": meta,
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "checked_by": None}
    if not samples:          # 冇樣本就唔叫 AI、唔當新鮮
        out.update(status="no_samples", error="上週冇抽到任何樣本（快照斷碟？冇場次？）")
        return out
    data, err, who = run_ai({"spot_checks": samples, "field_health": health})
    out["checked_by"] = who or None
    if not data or not isinstance(data.get("spot_checks", []), list) or not isinstance(data.get("field_health", []), list):
        out.update(status="ai_failed", error=err or "AI 輸出格式唔啱")
        return out
    out.update(status="ok", **verify(data, samples, health), samples=len(samples))
    return out


def render_md(r: dict) -> str:
    L = [f"# 每週健康巡查 {r['date']}（{r.get('checked_by') or '—'} 抽查、Python 核實）", ""]
    if r["status"] != "ok":
        return "\n".join(L + [f"⚠️ {r['status']}：{r.get('error')}（Python 欄位健康照舊由健康.sh 跑）"]) + "\n"
    L.append(f"原文抽查 {r['samples']} 匹（{r['window'][0]} → {r['window'][1]}）："
             f"確認對唔上 {len(r['confirmed_mismatches'])}、AI 講錯被剔 {len(r['rejected_claims'])}、睇唔清 {len(r['unclear'])}")
    if r["confirmed_mismatches"]:
        L += ["", "| 樣本 | 欄位 | 入分用嘅值 | 原文 |", "|---|---|---|---|"]
        L += [f"| {c['id']}（{c.get('horse')}） | {c['field']} | {c.get('ours_actual')} | {c.get('raw')} |"
              for c in r["confirmed_mismatches"]]
    L += ["", f"欄位趨勢異常：{len(r['trend_flags'])}"]
    L += [f"- {t['platform']}／{t['field']}：{t.get('issue')}（{t.get('weeks') or ''}）" for t in r["trend_flags"]]
    return "\n".join(L) + "\n"


def _clean(text, n: int = 160) -> str:
    """AI／原文文字入 Telegram 之前：剷網址、限長度（Sol：防注入文字原樣轉發）。"""
    t = re.sub(r"https?://\S+|www\.\S+", "〔網址已刪〕", str(text or ""))
    return t if len(t) <= n else t[: n - 1] + "…"


def telegram_text(r: dict) -> str:
    if r["status"] != "ok":
        what = {"ai_failed": "AI 巡查失敗", "no_samples": "冇抽到樣本"}.get(r["status"], r["status"])
        return f"⚠️ 每週健康巡查：{what}（{_clean(r.get('error'), 120)}）；Python 健康檢查照舊。"
    cm, tf = r["confirmed_mismatches"], r["trend_flags"]
    if not cm and not tf:
        return f"✅ 每週健康巡查（{r.get('checked_by')}）：原文抽查 {r['samples']} 匹全部對得上，欄位趨勢冇異常。"
    lines = [f"🩺 每週健康巡查（{r.get('checked_by')} 抽查、Python 核實）：要 Opus 跟進"]
    lines += [f"・{c['id']} {c['field']}：入分 {c.get('ours_actual')}，原文「{_clean(c.get('raw'), 60)}」" for c in cm[:6]]
    lines += [f"・趨勢：{t['platform']}／{t['field']} {_clean(t.get('issue'))}" for t in tf[:6]]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--output-dir")
    a = ap.parse_args(argv)
    r = build(a.sample, a.seed)
    out = Path(a.output_dir) if a.output_dir else control_root() / "health_sweep"
    out.mkdir(parents=True, exist_ok=True)
    # 失敗唔寫 .json（job_freshness 睇 health_sweep/*.json）
    name = f"{r['date']}.json" if r["status"] == "ok" else f"{r['date']}.failed.log"
    (out / name).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / f"{r['date']}.md").write_text(render_md(r), encoding="utf-8")
    print(render_md(r))
    marker = out / f".{r['date']}.telegram-sent"
    if a.telegram and not marker.exists():           # 同一日重跑唔重發
        sys.path.insert(0, str(RACING))
        import racing_telegram as T
        res = T.send_message(telegram_text(r), audience="primary")
        if isinstance(res, dict) and res.get("ok"):
            marker.write_text(r["generated_at"], encoding="utf-8")
    return 0 if r["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
