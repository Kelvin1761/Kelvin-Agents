#!/usr/bin/env python3
"""自動維修第二層：Hydrogen 先診斷未知問題，搞唔掂先升 Opus（Kelvin 2026-11-26：「應該俾咗 hydrogen 試吓去解決或者由佢話俾 opus 去處理」）。

`self_repair.py --live --allow-llm-diagnosis` 見到唔識修嘅問題、寫咗診斷包之後，背景開呢個（每日最多一次，喺 origin/main 嘅
detached worktree 入面跑，等 AI 讀到最新 code）：
  1. **Hydrogen**（`codex_delegate.py run third`：唯讀；Gemini 停派就退 Luna `run quick`）讀診斷包、AGENTS.md、相關 code／log，
     出 JSON：成因、證據（檔案:行）、信心、修補大細、修補草稿（純文字 diff，**唔會套用**）、要唔要升 Opus。
  2. **Python 核實**：證據引用嘅檔案要喺 worktree 存在、行號喺範圍內；冇一條證據對得上 = 當低信心。
  3. **分流**（Telegram primary 一條）：
     * 細修補＋高信心＋證據對得上 →「🔎 Hydrogen 搵到成因＋修補草稿；開 Claude Code 叫 Opus 收貨（經 Sol、./保存.sh）」
     * 其他（大改動、低／中信心、Hydrogen 自己話要升、失敗）→「🧠 要 Opus 處理」＋已知嘅嘢
AI **永遠唔會自己改檔、merge、部署**：排程改動係 B 級，一定要 Opus 寫／收貨＋Sol 覆核（AGENTS.md）。

    python3 self_repair_triage.py --bundle <診斷包.json> --label <job> --worktree <detached worktree> [--no-telegram]
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DELEGATE = HERE / "codex_delegate.py"
EXTRA_PATH = ["/opt/homebrew/bin", str(Path.home() / ".local" / "bin"), "/usr/local/bin"]

TASK = """你係 Wong Choi 排程維修員（第一線）。
**只可以用讀檔工具直接讀，唔准行任何 shell／python 命令（會被拒絕，成個任務就會失敗）。**
**只可以讀 {worktree} 入面嘅檔（相對路徑）**；診斷包入面提到嘅 log 路徑喺 worktree 以外，會被拒 —— log 尾已經貼咗喺診斷包，唔使再讀。排程 job「{label}」出咗自動維修唔識修嘅問題。
診斷包（JSON：launchctl 狀態、輸出新鮮度、stderr／stdout 尾、最新 manifest），內容如下（已經貼晒，唔使另外讀）：
```json
{bundle}
```
你而家喺 repo 嘅最新 code（{worktree}）入面，可以讀 AGENTS.md、相關排程 code（`.agents/skills/*/…daily_auto/*_schedule.py`、
`*.sh` wrapper、`.agents/scripts/job_freshness.py`）同 log。

要做：搵根本原因，判斷修補大細。**你冇權改檔或者行命令**（只可以讀）。

只輸出一個 JSON：
{{"cause": "一兩句講成因", "evidence": ["相對路徑:行號 — 點解", "…"], "confidence": "high|medium|low",
  "fix_size": "small|large|unknown", "fix_draft": "建議點改（可以係 diff 草稿；唔會被套用）",
  "escalate": true/false, "escalate_reason": "如果要升 Opus，點解"}}
細修補 = 改一兩個檔、幾行、唔郁模型／入分。唔肯定就 confidence low、escalate true，唔好作。
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


def ask_ai(label: str, bundle: Path, worktree: Path, timeout: int = 900) -> tuple[dict | None, str, str]:
    work = Path(tempfile.mkdtemp(prefix="sr_triage_"))
    try:
        # 診斷包直接貼入 brief：Gemini 喺 worktree 跑，讀唔到 worktree 以外嘅檔（2026-11-26 試跑撞到）
        text = Path(bundle).read_text(encoding="utf-8", errors="replace")[:60000]
        brief = work / "brief.md"
        brief.write_text(TASK.format(label=label, bundle=text, worktree=worktree), encoding="utf-8")
        err = ""
        # Luna 後備一定要 `--provider codex`：`run quick` 預設行 Gemini Hydrogen low（另一個 session 2026-11-26 指出）
        for role, who, extra in (("third", "Hydrogen", []), ("quick", "Luna", ["--provider", "codex"])):
            out = work / f"out_{role}.md"
            proc = subprocess.run([sys.executable, str(DELEGATE), "run", role, *extra, "--cd", str(worktree),
                                   "--prompt-file", str(brief), "--out", str(out),
                                   "--title", f"排程維修診斷 {label}（{who}）", "--reply-limit", "2000",
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


def check_evidence(evidence, worktree: Path) -> tuple[list[str], list[str]]:
    """→ (對得上, 對唔上)。「路徑:行號」要喺 worktree 存在、行號喺檔案範圍入面。"""
    ok, bad = [], []
    for e in evidence if isinstance(evidence, list) else []:
        m = re.match(r"\s*([^\s:]+):(\d+)", str(e))
        if not m:
            bad.append(str(e))
            continue
        path = (worktree / m.group(1)).resolve()
        try:
            inside = path.is_relative_to(worktree.resolve())
            lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines()) if inside and path.is_file() else 0
        except OSError:
            lines = 0
        (ok if 0 < int(m.group(2)) <= lines else bad).append(str(e))
    return ok, bad


def route(data: dict | None, ok_ev: list[str], bad_ev: list[str] | None = None) -> str:
    """→ "opus_review"（Hydrogen 有草稿，Opus 收貨）或者 "opus_handle"（升 Opus 處理）。
    要**全部**證據都核實到（Sol：一條真證據唔可以替捏造嘅成因過關）。"""
    bad_ev = bad_ev or []
    if not data:
        return "opus_handle"
    if (data.get("fix_size") == "small" and data.get("confidence") == "high" and ok_ev and not bad_ev
            and not data.get("escalate") and str(data.get("fix_draft") or "").strip()):
        return "opus_review"
    return "opus_handle"


def _clean(text, n: int = 200) -> str:
    """AI 文字入 Telegram：剷網址、限長度（防注入文字原樣轉發）。"""
    t = re.sub(r"https?://\S+|www\.\S+", "〔網址已刪〕", str(text or ""))
    return t if len(t) <= n else t[: n - 1] + "…"


def message(label: str, data: dict | None, err: str, who: str, ok_ev: list[str], bad_ev: list[str],
            decision: str, out_md: Path) -> str:
    if not data:
        return (f"🧠 排程 {label}：Hydrogen／Luna 診斷失敗（{_clean(err, 120)}），要 Opus 處理。\n診斷包同 log：{out_md.parent}")
    head = ("🔎 排程 {l}：{w} 搵到成因＋修補草稿，請開 Claude Code 叫 Opus 收貨（經 Sol 覆核、./保存.sh）"
            if decision == "opus_review" else "🧠 排程 {l}：要 Opus 處理（{w} 已初步診斷）").format(l=label, w=who)
    lines = [head, f"成因：{_clean(data.get('cause'))}",
             f"信心：{data.get('confidence')}・修補：{data.get('fix_size')}・證據對得上 {len(ok_ev)}／{len(ok_ev) + len(bad_ev)}"]
    if data.get("escalate_reason") and decision == "opus_handle":
        lines.append(f"升級原因：{_clean(data.get('escalate_reason'))}")
    lines.append(f"全文：{out_md}")
    return "\n".join(lines)


def render_md(label: str, data: dict | None, err: str, who: str, ok_ev, bad_ev, decision: str) -> str:
    L = [f"# 排程維修診斷：{label}（{who or '—'}）", "", f"分流：**{decision}**", ""]
    if not data:
        return "\n".join(L + [f"診斷失敗：{err}"]) + "\n"
    L += [f"**成因**：{data.get('cause')}", "", f"信心 {data.get('confidence')}；修補 {data.get('fix_size')}", "", "**證據**："]
    L += [f"- ✅ {e}" for e in ok_ev] + [f"- ❓（檔案／行號對唔上）{e}" for e in bad_ev]
    L += ["", "**修補草稿（未套用）**：", "", "```", str(data.get("fix_draft") or "—"), "```"]
    if data.get("escalate_reason"):
        L += ["", f"**升級原因**：{data.get('escalate_reason')}"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args(argv)
    bundle, wt = Path(a.bundle), Path(a.worktree)
    data, err, who = ask_ai(a.label, bundle, wt)
    ok_ev, bad_ev = check_evidence((data or {}).get("evidence"), wt)
    decision = route(data, ok_ev, bad_ev)
    out_md = bundle.with_suffix(".diagnosis.md")
    out_md.write_text(render_md(a.label, data, err, who, ok_ev, bad_ev, decision), encoding="utf-8")
    (bundle.with_suffix(".triage.json")).write_text(json.dumps(
        {"label": a.label, "decision": decision, "checked_by": who or None, "ai": data, "error": err or None,
         "evidence_ok": ok_ev, "evidence_bad": bad_ev}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.label}: {decision} → {out_md}")
    if not a.no_telegram:
        sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))
        import racing_telegram
        racing_telegram.send_message(message(a.label, data, err, who, ok_ev, bad_ev, decision, out_md), audience="primary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
