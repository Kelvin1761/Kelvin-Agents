#!/usr/bin/env python3
"""自動覆盤 AI 解讀（自學循環 L2，Kelvin 2026-11-26：「覆盤 there should be ai involved」）。

分工（Kelvin 揀：Gemini 寫、再核實）：
  1. **Gemini 寫**（`codex_delegate.py run third`：唯讀、Kelvin 嘅 Google 訂閱、撞 429 自動停派、記帳）：
     讀當日覆盤 JSON（`post_review`／`post_review_sports` 出嘅），寫港式中文解讀＋最多 3 個假設（結構化 JSON）。
  2. **Python 核事實**（免費、最可靠）：解讀入面每個帶小數／分數／百分比嘅數字、每個「」引住嘅名，都要喺當日覆盤
     JSON 搵到；搵唔到嘅句刪走並記數。假設嘅條件只可以用當日覆盤 `cohorts[].cohort` 入面嘅賽前組別（最多 2 個 AND）。
  3. **Sonnet 審假設**（`claude -p --model sonnet`，plan mode，只准 Read／Grep／Glob）：逐個問「有冇用賽後資訊」
     「`docs/experiments/` 有冇做過」「值唔值得驗證」。
  4. 過咗嘅假設寫入假設帳 `<WongChoiControl>/learning/hypotheses.jsonl`（state = watching，born = 當日）。
     **只係登記**：驗證由 Python 用 born 之後嘅新數據做（L3），上唔上線係 Kelvin。AI 永遠唔改模型。
  5. 每週（`weekly`）Opus 讀過去 7 日四個 domain 嘅覆盤＋AI 解讀＋假設帳，揀最值得做嘅 1–2 個，Telegram primary。

輸出：`reviews/<domain>/<日>.ai.json`；`.md` 尾加「AI 解讀」一節；content Telegram 一條（每日一次）。
任何一步失敗 = 只寫 log，唔影響覆盤本身。

    python3 review_ai.py daily  --domain au|hkjc|nba|tennis --date YYYY-MM-DD [--telegram]
    python3 review_ai.py weekly [--telegram]
"""
from __future__ import annotations

import argparse
import json
import os
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
for _p in (str(RACING), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import post_review as PR  # noqa: E402

VERSION = "review-ai-v1"
DOMAIN_ZH = {"au": "AU 賽馬", "hkjc": "香港賽馬", "nba": "NBA", "tennis": "網球"}
MAX_HYP = 3
EXTRA_PATH = ["/opt/homebrew/bin", str(Path.home() / ".local" / "bin"), "/usr/local/bin"]

GEMINI_TASK = """你係 Wong Choi（{domain_zh}預測系統）嘅賽後覆盤分析員。讀 {review_json}（當日自動覆盤，全部數字已由 Python 計好）。

要做：
1. 用港式中文寫一段覆盤解讀（最多 350 字），似一個資深分析員同老闆講：今日整體點、邊幾場／幾注點解中、點解唔中、
   有冇重複出現嘅 pattern。分清「賽中意外／運氣（預測唔到）」、「市場都估錯」同「模型自己判錯」。
2. 最多提 {max_hyp} 個「值得之後用新數據驗證」嘅假設。每個假設嘅條件**只准**用 JSON 入面 `cohorts` 清單嘅 `cohort`
   字串（原文照抄，最多 2 個，AND 關係）；方向係 "model_under"（模型低估）或 "model_over"（模型高估）。
   冇好嘅假設就俾空清單，唔好硬作。

硬性規則：
- 只可以引用 JSON 入面有嘅數字同名；唔肯定就唔好寫數字。名用「」引住。
- 唔准建議即刻改權重；只可以提假設。單晚結果冇統計意義，要講清楚。
- 最後**只輸出一個 JSON**（唔好有 markdown code fence 以外嘅文字），格式：
{{"narrative": "……", "hypotheses": [{{"title": "……", "cohort": ["tag:…"], "direction": "model_under", "why": "……"}}]}}
"""

SONNET_TASK = """你係 Wong Choi 研究覆核員。下面係 AI 由 {date} {domain_zh} 覆盤提出嘅假設（JSON）。逐個判斷：
1. leak：條件有冇用到賽後先知嘅資訊（賽果、SP／收盤價、賽中事件）？組別名 "model:" 開頭嘅係用賽後 SP 分組，一律當 leak。
2. done_before：喺 {exp_dir}（先 grep INDEX.md 關鍵字）有冇做過差唔多嘅實驗？有就寫 EXP 編號，冇就 null。
3. worth：值唔值得用之後嘅新數據驗證（唔係單晚噪音、有機制講得通）？
只輸出一個 JSON：{{"reviews": [{{"i": 0, "leak": false, "done_before": null, "worth": true, "note": "一句"}}]}}

假設：
{hypotheses}
"""

OPUS_WEEKLY = """你係 Wong Choi 首席研究員。讀 {reviews_dir} 入面過去 7 日（{since} 至 {until}）四個 domain（au／hkjc／nba／tennis）
嘅 `<日>.json`（Python 覆盤）同 `<日>.ai.json`（AI 解讀）、假設帳 {ledger}（state：watching 觀察中＋progress 進度、
supported／rejected／undecided 已判，result 有 CI），同埋本週健康巡查
{sweep_dir}（最新一份 `<日>.json`：原文抽查確認對唔上、欄位趨勢異常）。
用港式中文寫一份 ≤ 400 字嘅每週總結俾老闆（Kelvin）：
- 每個 domain 一句：本週表現同市場比點。
- 本週重複出現、跨日都成立嘅 pattern（引用 JSON 數字）。
- 健康巡查有確認問題就排第一講（數據錯比模型差更貴）。
- **「改善空間」最少 3 項**：讀改善空間清單 {gap_report}（填唔滿嘅輸入欄、觀察中假設、可以重評嘅舊 REJECT），揀最值得做嘅 3 項，
  每項講：係咩、點解可能有用、下一步點做（新資料來源？新登記嘅 forward？）。**唔准寫「已經做晒／冇得再改善」**（Kelvin 2026-11-26）。
- 本週有假設判咗 supported 就排前講，建議開預先登記 forward（AU：`au_hypothesis_forward.ARMS` 加一行）。
- 揀**最多 2 個**最值得開預先登記 forward 測試嘅假設，講點解、預計要幾耐有答案；冇就講冇。
- 唔准建議即刻改模型；只可以建議開測試。
最後只輸出純文字（唔使 JSON）。
"""


def _env() -> dict:
    env = os.environ.copy()
    env["PATH"] = ":".join(EXTRA_PATH + [env.get("PATH", "")])
    return env


def _json_from(text: str) -> dict | None:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    cand = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""
    try:
        out = json.loads(cand)
        return out if isinstance(out, dict) else None
    except ValueError:
        return None


# ---------------------------------------------------------------- 1. Gemini

def run_gemini(domain: str, review_path: Path, timeout: int = 600) -> tuple[dict | None, str]:
    work = Path(tempfile.mkdtemp(prefix="review_ai_"))
    try:
        shutil.copy(review_path, work / "review.json")
        brief = work / "brief.md"
        brief.write_text(GEMINI_TASK.format(domain_zh=DOMAIN_ZH[domain], review_json=work / "review.json",
                                            max_hyp=MAX_HYP), encoding="utf-8")
        out = work / "out.md"
        proc = subprocess.run([sys.executable, str(DELEGATE), "run", "third", "--cd", str(work), "--prompt-file", str(brief),
                               "--out", str(out), "--title", f"覆盤 AI 解讀 {domain} {review_path.stem}",
                               "--reply-limit", "1500", "--timeout", str(timeout)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout + 120, env=_env())
        reply = out.read_text(encoding="utf-8") if out.exists() else ""
        if proc.returncode != 0 or not reply:
            return None, ((proc.stderr or "") + (proc.stdout or "")).strip()[-300:] or f"rc={proc.returncode}"
        data = _json_from(reply)
        return (data, "") if data else (None, "Gemini 冇出合法 JSON")
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- 2. Python 核事實

NUM_RE = re.compile(r"[+\-−]?\d+(?:\.\d+)?(?:/\d+)?")
NAME_RE = re.compile(r"「([^」]{2,40})」")


def _numbers_in_json(review: dict) -> set[str]:
    """覆盤 JSON 入面所有數字嘅常見寫法（原值、1 位小數、百分比、pp、分數）。"""
    out: set[str] = set()

    def add(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            f = float(v)
            for x in (f, 100 * f):
                out.update({f"{x:g}", f"{x:.1f}", f"{x:.2f}", f"{x:.0f}", f"{x:.4f}"})
                out.update({f"{x:+.1f}", f"{x:+.2f}", f"{x:+g}"})          # 有正負號嘅寫法（正負號要對）
                ax = abs(x)                                                 # 冇寫號（「跌 5.9pp」）就比絕對值
                out.update({f"{ax:g}", f"{ax:.1f}", f"{ax:.2f}", f"{ax:.0f}"})
        elif isinstance(v, str):
            for m in NUM_RE.finditer(v):
                out.update({m.group(0).replace("−", "-"), m.group(0).lstrip("+-−")})
        elif isinstance(v, dict):
            for x in v.values():
                add(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)
    add(review)
    # 分數（a/b）：summary 嘅組合
    s = review.get("summary") or {}
    for a, b in (("model_top3_hits", "slots"), ("market_top3_hits", "slots"), ("model_top1_wins", "races"),
                 ("fav_wins", "races"), ("winner_in_model_top5", "races")):
        if s.get(a) is not None and s.get(b) is not None:
            out.add(f"{s[a]}/{s[b]}")
    for c in review.get("cohorts") or []:
        out.add(f"{c.get('today_hits')}/{c.get('today_n')}")
    fs = review.get("featured_summary") or {}
    if fs:
        out.add(f"{fs.get('won')}/{fs.get('settled')}")
    for m in review.get("meetings") or []:
        if m.get("over_total"):
            out.add(f"{m.get('over_with_incident')}/{m.get('over_total')}")
    return {x.replace("−", "-") for x in out}


def _significant(tok: str) -> bool:
    """要核嘅數字：有小數、分數、或者 ≥ 10（細嘅整數好多係「三場」「第 2」，唔核）。"""
    t = tok.lstrip("+-−")
    if "/" in t or "." in t:
        return True
    try:
        return float(t) >= 10
    except ValueError:
        return False


def _num_key(tok: str) -> str:
    """有寫正負號就要連號都對（Sol：「−5.9」唔可以靠「5.9」過關）；冇寫號就比絕對值。"""
    return tok if tok[:1] in "+-" else tok


def fact_check(narrative: str, review: dict) -> tuple[str, list[str]]:
    """→ (淨低嘅解讀, 被刪嘅句)。每句入面嘅重要數字同「名」都要喺覆盤 JSON 搵到；網址一律刪。

    限制（寫明）：只保證數字／名「存在」於當日覆盤，唔保證引用嘅欄位啱；細整數（<10）同冇用「」引住嘅名唔核。"""
    nums = _numbers_in_json(review)
    blob = json.dumps(review, ensure_ascii=False)
    kept, dropped = [], []
    for sent in re.split(r"(?<=[。！？\n])", narrative or ""):
        if not sent.strip():
            continue
        bad_num = [t for t in (m.group(0).replace("−", "-") for m in NUM_RE.finditer(sent))
                   if _significant(t) and _num_key(t) not in nums]
        bad_name = [n for n in NAME_RE.findall(sent) if n not in blob]
        has_url = bool(re.search(r"https?://|www\.", sent))
        (dropped if bad_num or bad_name or has_url else kept).append(sent.strip())
    return "".join(kept), dropped


def check_hypotheses(hyps: list, review: dict) -> tuple[list[dict], list[dict]]:
    """→ (語法 OK, 拒絕＋原因)。條件只准用當日 cohorts 嘅組別、≤2 個、方向合法。"""
    allowed = {c.get("cohort") for c in review.get("cohorts") or []}
    ok, bad = [], []
    for h in (hyps or [])[:MAX_HYP]:
        if not isinstance(h, dict):
            continue
        raw = h.get("cohort")
        cond = [c for c in raw if isinstance(c, str)] if isinstance(raw, list) else []
        reason = None
        if not isinstance(raw, list) or len(cond) != len(raw):
            reason = "條件格式唔啱（要字串清單）"
        elif not cond or len(cond) > 2:
            reason = "條件要 1–2 個"
        elif any(c not in allowed for c in cond):
            reason = "條件唔喺當日組別清單"
        elif any(c.startswith("model:") for c in cond):
            reason = "用賽後 SP 分組（洩漏）"
        elif h.get("direction") not in ("model_under", "model_over"):
            reason = "方向唔合法"
        (bad if reason else ok).append(dict(h, cohort=cond, **({"rejected": reason} if reason else {})))
    return ok, bad


# ---------------------------------------------------------------- 3. Sonnet

def _claude(prompt: str, model: str, timeout: int = 600, read_dirs: tuple[Path, ...] = ()) -> tuple[str, str]:
    """唯讀 `claude -p`。喺空臨時目錄跑（唔載 project 嘅 .claude hook／settings —— Stop hook 會將「未保存」提醒
    蓋過答覆），只用 `--add-dir` 開放要讀嘅目錄；`--output-format json` 淨攞最終答覆。"""
    exe = shutil.which("claude", path=_env()["PATH"])
    if not exe:
        return "", "搵唔到 claude CLI"
    work = Path(tempfile.mkdtemp(prefix="review_ai_claude_"))
    # Sol 2026-11-26：輸入（覆盤 JSON 嘅馬名／事件報告、Gemini 嘅假設）係外來文字，可能有 prompt injection →
    # 只開 Read／Grep／Glob（--tools 限死內建工具）、唔載任何 MCP（用戶層有 Telegram plugin）、只讀 user 設定。
    cmd = [exe, "-p", prompt, "--model", model, "--permission-mode", "plan", "--output-format", "json",
           "--tools", "Read", "Grep", "Glob", "--strict-mcp-config", "--setting-sources", "user",
           "--allowedTools", "Read", "Grep", "Glob",
           "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"]
    for d in read_dirs:
        cmd += ["--add-dir", str(d)]
    try:
        proc = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=_env(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if proc.returncode != 0:
        return "", ((proc.stderr or "") + (proc.stdout or "")).strip()[-300:] or f"rc={proc.returncode}"
    try:
        data = json.loads(proc.stdout)
        if data.get("is_error"):
            return "", str(data.get("result") or "claude 出錯")[-300:]
        return str(data.get("result") or "").strip(), ""
    except ValueError:
        return proc.stdout.strip(), ""


def sonnet_review(domain: str, day: str, hyps: list[dict]) -> tuple[list[dict], str]:
    if not hyps:
        return [], ""
    text, err = _claude(SONNET_TASK.format(exp_dir=REPO / "docs" / "experiments", date=day, domain_zh=DOMAIN_ZH[domain],
                                           hypotheses=json.dumps(hyps, ensure_ascii=False, indent=1)), "sonnet",
                        read_dirs=(REPO / "docs" / "experiments",))
    data = _json_from(text) if text else None
    if not data:
        return [], err or "Sonnet 冇出合法 JSON"
    by_i = {r.get("i"): r for r in data.get("reviews") or [] if isinstance(r, dict)}
    return [dict(h, review=by_i.get(i)) for i, h in enumerate(hyps)], ""


# ---------------------------------------------------------------- 4. 假設帳

def ledger_path() -> Path:
    return PR.output_dir("au").parents[1] / "learning" / "hypotheses.jsonl"


def register(domain: str, day: str, hyps: list[dict], today: str | None = None) -> int:
    """過咗 Sonnet（明確冇洩漏、值得驗證）嘅先入帳；同 domain 同條件已經喺帳就唔重複。
    `born` = **登記當日**（唔係覆盤日）：補跑舊日子都只可以用登記之後嘅數據驗證（Sol 2026-11-26）。檔案鎖防並行。"""
    import fcntl
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    born = today or Date.today().isoformat()
    lock = open(path.with_suffix(".lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        return _register_locked(path, domain, day, born, hyps)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _register_locked(path: Path, domain: str, day: str, born: str, hyps: list[dict]) -> int:
    existing, ids = set(), set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                existing.add((r["domain"], tuple(sorted(r["cohort"])), r["direction"]))
                ids.add(r.get("id"))
            except (ValueError, KeyError):
                continue
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for h in hyps:
            rv = h.get("review") or {}
            if rv.get("leak") is not False or rv.get("worth") is not True:   # 冇明確判「冇洩漏、值得」就唔入
                continue
            key = (domain, tuple(sorted(h["cohort"])), h["direction"])
            if key in existing:
                continue
            existing.add(key)
            k = 1
            while f"H-{domain}-{day}-{k}" in ids:
                k += 1
            ids.add(f"H-{domain}-{day}-{k}")
            fh.write(json.dumps({"id": f"H-{domain}-{day}-{k}", "domain": domain, "born": born, "source_day": day,
                                 "source": "gemini+sonnet",
                                 "title": h.get("title"), "cohort": h["cohort"], "direction": h["direction"],
                                 "why": h.get("why"), "done_before": rv.get("done_before"),
                                 # 做過／測緊（Sonnet 搵到 EXP）= 已有測試覆蓋，唔當新假設，避免同一個 idea 開兩次
                                 "state": "covered" if rv.get("done_before") else "watching",
                                 "note": "只係登記；驗證用 born 之後嘅新數據（L3），上線由 Kelvin 決定"},
                                ensure_ascii=False) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------- 流程

def daily(domain: str, day: str, telegram: bool = False, out_dir: Path | None = None, force: bool = False) -> dict:
    out = Path(out_dir) if out_dir else PR.output_dir(domain)
    done = out / f"{day}.ai.json"
    if not force and done.exists():
        try:
            prev = json.loads(done.read_text(encoding="utf-8"))
            if prev.get("status") == "ok":
                return dict(prev, skipped="已經做過（--force 先重做）")
        except ValueError:
            pass
    lock_path = out / f".{day}.ai.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # 同一日同時只准一個
        os.close(fd)
    except FileExistsError:
        if time_since(lock_path) < 3600:
            return {"status": "busy", "domain": domain, "date": day}
        lock_path.unlink(missing_ok=True)
        return daily(domain, day, telegram, out_dir, force)
    try:
        return _daily(domain, day, telegram, out)
    finally:
        lock_path.unlink(missing_ok=True)


def time_since(path: Path) -> float:
    try:
        return datetime.now().timestamp() - path.stat().st_mtime
    except OSError:
        return 1e9


def _daily(domain: str, day: str, telegram: bool, out: Path) -> dict:
    review_path = out / f"{day}.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    result = {"version": VERSION, "domain": domain, "date": day,
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    data, err = run_gemini(domain, review_path)
    if not data:
        result.update(status="gemini_failed", error=err)
        PR._atomic(out / f"{day}.ai.json", json.dumps(result, ensure_ascii=False, indent=1))
        return result
    narrative, dropped = fact_check(str(data.get("narrative") or ""), review)
    ok_h, bad_h = check_hypotheses(data.get("hypotheses") or [], review)
    reviewed, serr = sonnet_review(domain, day, ok_h)
    registered = register(domain, day, reviewed) if reviewed else 0
    result.update(status="partial" if (ok_h and serr) else "ok",
                  narrative=narrative, dropped_sentences=dropped, hypotheses=reviewed or ok_h,
                  rejected_hypotheses=bad_h, sonnet_error=serr or None, registered=registered)
    PR._atomic(out / f"{day}.ai.json", json.dumps(result, ensure_ascii=False, indent=1))
    md = out / f"{day}.md"
    if md.exists():
        text = md.read_text(encoding="utf-8").split("\n## 🤖 AI 解讀")[0].rstrip("\n")
        PR._atomic(md, text + "\n\n" + render_md(result))
    marker = out / f".{day}.ai-telegram-sent"
    if telegram and narrative and not marker.exists():
        import racing_telegram as T
        res = T.send_message(telegram_text(result), audience="content")
        if isinstance(res, dict) and res.get("ok"):
            PR._atomic(marker, result["generated_at"])
    return result


def render_md(r: dict) -> str:
    L = ["## 🤖 AI 解讀（Gemini 寫、Python 核數字、Sonnet 審假設；只係參考，唔改模型）", "", r.get("narrative") or "—", ""]
    if r.get("dropped_sentences"):
        L += [f"> 核實刪咗 {len(r['dropped_sentences'])} 句（數字或者名喺覆盤數據搵唔到）", ""]
    hs = r.get("hypotheses") or []
    if hs:
        L += ["| 假設 | 條件 | 方向 | Sonnet 審 |", "|---|---|---|---|"]
        for h in hs:
            rv = h.get("review") or {}
            verdict = ("❌ 洩漏" if rv.get("leak") else "↩️ 做過 " + str(rv.get("done_before")) if rv.get("done_before")
                       else "✅ 值得驗證" if rv.get("worth") else "➖ 唔值得") if rv else "未審"
            L.append(f"| {h.get('title')} | {' ＋ '.join(h['cohort'])} | "
                     f"{'模型低估' if h.get('direction') == 'model_under' else '模型高估'} | {verdict}：{rv.get('note') or ''} |")
        L.append(f"\n入咗假設帳：{r.get('registered', 0)} 個（驗證用之後嘅新數據）")
    return "\n".join(L) + "\n"


def telegram_text(r: dict) -> str:
    lines = [f"🤖 {DOMAIN_ZH[r['domain']]} AI 覆盤解讀 {r['date']}", r.get("narrative") or ""]
    hs = [h for h in r.get("hypotheses") or [] if (h.get("review") or {}).get("worth") and not (h.get("review") or {}).get("leak")]
    if hs:
        lines.append("值得之後驗證：" + "；".join(h.get("title") or "" for h in hs))
    return "\n".join(x for x in lines if x)


def weekly(telegram: bool = False, today: str | None = None) -> dict:
    until = today or Date.today().isoformat()
    since = (Date.fromisoformat(until) - timedelta(days=7)).isoformat()
    reviews_dir = PR.output_dir("au").parent
    sweep_dir = reviews_dir.parent / "health_sweep"
    try:                                   # L3 假設驗證：只用出世之後嘅新數據，夠數判一次就鎖（結果寫返假設帳，Opus 會讀）
        import hypothesis_judge
        hypothesis_judge.run(until, telegram=telegram)
    except Exception as exc:  # noqa: BLE001
        print(f"hypothesis_judge 失敗：{exc}", file=sys.stderr)
    try:                                   # 改善空間清單（Kelvin 2026-11-26：唔准假設已經做晒）
        import gap_report
        gap_path = gap_report.write(gap_report.build(until))
    except Exception as exc:  # noqa: BLE001 —— 清單失敗：明講，唔好叫 Opus 讀舊檔（Sol）
        gap_path = f"（今週改善空間清單產生失敗：{type(exc).__name__}；唔好讀舊檔，改為由覆盤／假設帳自己揀 3 項並註明清單失敗）"
        print(f"gap_report 失敗：{exc}", file=sys.stderr)
    text, err = _claude(OPUS_WEEKLY.format(reviews_dir=reviews_dir, since=since, until=until, ledger=ledger_path(),
                                           sweep_dir=sweep_dir, gap_report=gap_path),
                        "opus", timeout=1200, read_dirs=(reviews_dir, ledger_path().parent, sweep_dir))
    result = {"version": VERSION, "kind": "weekly", "since": since, "until": until, "text": text, "error": err or None,
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    # 失敗唔寫 .json（job_freshness 睇 weekly/*.json；失敗都寫就會當咗新鮮）
    name = f"{until}.json" if text and not err else f"{until}.failed.log"
    PR._atomic(reviews_dir / "weekly" / name, json.dumps(result, ensure_ascii=False, indent=1))
    if telegram and text:
        import racing_telegram as T
        T.send_message(f"🧠 Wong Choi 每週 AI 總結（{since} → {until}）\n{text}", audience="primary")
    return result


def spawn_daily(domain: str, day: str) -> None:
    """覆盤腳本完成後背景開 AI 解讀（唔阻排程）。測試／WC_DISABLE_REVIEW_AI 唔開。"""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("WC_DISABLE_REVIEW_AI"):
        return
    log = PR.output_dir(domain) / "review_ai.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "daily", "--domain", domain, "--date", day,
                              "--telegram"], cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                             start_new_session=True, env=_env())
    except OSError:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--domain", choices=sorted(DOMAIN_ZH), required=True)
    d.add_argument("--date", required=True)
    d.add_argument("--output-dir")
    d.add_argument("--telegram", action="store_true")
    d.add_argument("--force", action="store_true", help="已經做過都重做")
    w = sub.add_parser("weekly")
    w.add_argument("--telegram", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "daily":
        r = daily(a.domain, a.date, a.telegram, Path(a.output_dir) if a.output_dir else None, a.force)
    else:
        r = weekly(a.telegram)
    print(json.dumps({k: v for k, v in r.items() if k not in ("narrative", "text")}, ensure_ascii=False)[:600])
    return 0 if r.get("status", "ok") in ("ok", "busy") and not r.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
