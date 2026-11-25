#!/usr/bin/env python3
"""Astra 每週深度審計（Kelvin 2026-11-25）。

每星期一朝 08:00（悉尼，launchd）派 Codex Astra 唯讀掃過去 7 日入咗 origin/main 嘅 code 改動，
專搵呢個 repo 最貴嗰類 bug：「欄位仍在、code 仍行、test 全綠，但值靜靜變空／變常數／變過期」、
被吞嘅 exception、未來資訊洩漏、時區、寫錯資料根、sys.path 插錯。

只做診斷：結果寫入 `<WongChoiControl>/astra_audit/<日期>.md`，摘要 Telegram primary 俾 Kelvin。
**唔改 code、唔開 PR** —— 要修嘅由 Claude 喺正常 session 判斷同做。
Codex 額度唔准（stop／Astra 超預算）就跳過，照樣寫狀態檔同通知。

    python3 astra_weekly_audit.py              # 正式跑
    python3 astra_weekly_audit.py --dry-run    # 只砌 brief、唔派、唔發 Telegram
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
SHARED_RACING = REPO_ROOT / ".agents" / "skills" / "shared_racing" / "scripts"
DELEGATE = REPO_ROOT / ".agents" / "scripts" / "codex_delegate.py"
SYD = ZoneInfo("Australia/Sydney")
DAYS = 7
# 唔值得 Astra 睇嘅路徑（實驗記錄、生成文件、fixture）—— 照列出嚟，但唔叫佢逐行睇
SKIP_PREFIXES = ("docs/", "Wong Choi 模型說明/", "Horse_Racing_Dashboard/static_snapshot")
MAX_COMMITS = 80


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT")
                or Path.home() / "WongChoiData" / "WongChoiControl")


GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def git(*args: str, cwd: Path = REPO_ROOT, timeout: int = 300) -> str:
    """排程入面行：禁互動、限時，免得認證／網絡問題令 job 卡死。"""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=GIT_ENV,
                          encoding="utf-8", errors="replace", check=True, timeout=timeout).stdout


def last_audited_head() -> str | None:
    try:
        d = json.loads((control_root() / "astra_audit" / "latest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d.get("head") if d.get("status") in ("succeeded", "no_changes") else None


def weekly_commits(head: str = "origin/main", since: str | None = None) -> list[dict]:
    """上次審計過嘅 head 之後入 main 嘅 commit（冇記錄就用最近 7 日）。用 SHA 範圍唔用日期 ——
    舊 commit 今週先 merge 都唔會漏。"""
    rng = [f"{since}..{head}"] if since else [head, f"--since={DAYS}.days"]
    try:
        out = git("log", *rng, "--no-merges", "--format=%H%x1f%s", "--numstat")
    except subprocess.CalledProcessError:  # 舊 head 唔喺歷史（例如 force push）→ 退返日期窗
        out = git("log", head, f"--since={DAYS}.days", "--no-merges", "--format=%H%x1f%s", "--numstat")
    commits: list[dict] = []
    for line in out.splitlines():
        if "\x1f" in line:
            sha, subject = line.split("\x1f", 1)
            commits.append({"sha": sha, "subject": subject, "files": []})
        elif line.strip() and commits:
            parts = line.split("\t")
            if len(parts) == 3:
                commits[-1]["files"].append(parts[2])
    return commits


def is_code(path: str) -> bool:
    """正式 code（唔計測試、docs、生成檔）—— 測試由 suite 自己把關，Astra 嘅時間留畀會出事嗰啲。"""
    name = path.rsplit("/", 1)[-1]
    if "/tests/" in f"/{path}" or name.startswith("test_") or name.endswith((".test.mjs", ".test.js")):
        return False
    return path.endswith((".py", ".sh", ".mjs", ".js", ".ts")) and not path.startswith(SKIP_PREFIXES)


def build_brief(commits: list[dict]) -> str:
    rows = []
    code_commits = [c for c in commits if any(is_code(f) for f in c["files"])]
    truncated = max(0, len(code_commits) - MAX_COMMITS)
    for c in code_commits[:MAX_COMMITS]:
        code = [f for f in c["files"] if is_code(f)]
        if not code:
            continue
        rows.append(f"- `{c['sha'][:10]}` {c['subject']}\n  code：" + "、".join(f"`{f}`" for f in code[:15])
                    + (f"（仲有 {len(code) - 15} 個）" if len(code) > 15 else ""))
    listing = "\n".join(rows) or "（冇 code 改動）"
    if truncated:
        listing += f"\n- ⚠️ 仲有 {truncated} 個較舊嘅 code commit 冇列出（超過 {MAX_COMMITS} 個上限），報告要講明冇審。"
    return f"""## 背景
你喺 Antigravity repo（Wong Choi 賽馬／NBA／網球分析系統）嘅 origin/main 唯讀 checkout 入面。
呢個 repo 最貴嘅 bug 幾乎全部係同一個形狀：**欄位仲喺度、code 照行、test 全綠、log 冇錯，但個值靜靜變空、
變常數、變過期或者讀錯檔**（例如一句被吞嘅 ImportError 令 12% 權重成個月中性；sys.path 插錯 package 目錄；
用 `date.today()` 判斷香港賽日；future 資訊漏入回測；寫去錯嘅資料根）。AGENTS.md 有晒規矩，可以參考。

## 要做
用 `git show <sha>` 睇下面每個 commit 嘅 code 改動（只睇列出嘅 code 檔；docs／實驗記錄唔使睇），搵：
1. 靜靜失效：bare／過闊 except 吞錯、預設值蓋住缺失數據（例如當中性 60）、空 list／None 照行落去冇警號；
2. 未來資訊洩漏：用賽後／今仗資料做賽前特徵、回測冇日期閘；
3. 日期／時區：HKJC 要用 `live_priors.hk_today()`，唔准 `date.today()`；
4. 路徑：寫錯資料根、hard-code 路徑、`sys.path` 插 package 目錄本身；
5. 一樣嘢兩個定義（AGENTS.md「一樣嘢只准有一個標準」）；
6. 其他你有實據嘅正確性 bug。
**唔准改檔。** 每個發現要有：commit、`檔:行`、點觸發、後果、建議點修、把握（高／中／低）。
冇實據嘅唔好報；冇發現就直接講「冇發現」。按嚴重程度排，最嚴重先。
**優先次序**：評分引擎（`*_racing_engine/`、`nba_engine/`、`tennis_wc/pricing/`）→ 抽取／scraper → 排程同發佈 → 其他。
睇唔晒就照講冇睇到邊幾個 commit，唔好扮睇晒。

## 呢 7 日入咗 main 嘅 commit（{len(commits)} 個）
{listing}
"""


def write_state(status: str, **extra) -> Path:
    root = control_root() / "astra_audit"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "latest.json"
    path.write_text(json.dumps({"status": status, "ts": time.time(), **extra}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def notify(text: str, dry_run: bool) -> bool:
    if dry_run:
        print("[dry-run Telegram]\n" + text)
        return True
    sys.path.insert(0, str(SHARED_RACING))
    try:
        from racing_telegram import send_message
        result = send_message(text, audience="primary")
    except Exception as exc:  # 通知失敗唔可以令審計結果冇咗；狀態檔照寫
        print(f"⚠️ Telegram 發唔到：{exc}", file=sys.stderr)
        return False
    ok = bool(isinstance(result, dict) and result.get("ok"))
    if not ok:
        print(f"⚠️ Telegram 冇送到：{result}", file=sys.stderr)
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args(argv)

    today = datetime.now(SYD).strftime("%Y-%m-%d")
    try:
        git("fetch", "-q", "origin")
        head = git("rev-parse", "origin/main").strip()
        commits = weekly_commits(head, last_audited_head())
    except (subprocess.SubprocessError, OSError) as exc:
        write_state("failed", error=f"git：{exc}"[-300:])
        notify(f"⚠️ Astra 每週審計（{today}）失敗：git fetch／log 出錯（{exc}）"[:500], args.dry_run)
        return 1
    code_commits = [c for c in commits if any(is_code(f) for f in c["files"])]
    if not code_commits:
        write_state("no_changes", head=head, commits=len(commits))
        notify(f"🔎 Astra 每週審計（{today}）：過去 7 日冇 code 改動，跳過。", args.dry_run)
        return 0

    brief_text = build_brief(commits)
    out_dir = control_root() / "astra_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"{today}.md"
    if args.dry_run:
        print(brief_text)
        return 0

    with tempfile.TemporaryDirectory(prefix="astra_audit_") as tmp:
        wt = Path(tmp) / "main"
        brief = Path(tmp) / "brief.md"
        try:
            brief.write_text(brief_text, encoding="utf-8")
            git("worktree", "add", "-q", "--detach", str(wt), head)
            proc = subprocess.run(
                [sys.executable, str(DELEGATE), "run", "deep", "--effort", "high", "--cd", str(wt),
                 "--prompt-file", str(brief), "--out", str(report), "--reply-limit", "900",
                 "--timeout", str(args.timeout), "--title", f"Astra 每週審計 {today}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=args.timeout + 300)
            rc, err = proc.returncode, proc.stderr.strip()
        except subprocess.TimeoutExpired:
            rc, err = 1, f"timeout after {args.timeout + 300}s"
        except (subprocess.SubprocessError, OSError) as exc:
            rc, err = 1, f"開唔到審計 worktree：{exc}"
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO_ROOT,
                           capture_output=True)
            subprocess.run(["git", "worktree", "prune"], cwd=REPO_ROOT, capture_output=True)

    if rc == 3:  # 額度唔准派
        write_state("skipped_quota", head=head, reason=err[-300:])
        notify(f"🔎 Astra 每週審計（{today}）：Codex 額度唔准派，今週跳過。\n{err[-300:]}", args.dry_run)
        return 0
    if rc != 0 or not report.exists():
        write_state("failed", head=head, error=err[-300:])
        notify(f"⚠️ Astra 每週審計（{today}）失敗：{err[-300:] or '冇輸出'}", args.dry_run)
        return 1

    body = report.read_text(encoding="utf-8").strip()
    summary = body if len(body) <= 1500 else body[:1500] + "…"
    sent = notify(f"🔎 Astra 每週審計（{today}，{len(code_commits)} 個 code commit）\n{summary}\n\n全文：{report}\n"
           "（只係診斷，未改任何嘢；要修嘅由 Claude 判斷）", args.dry_run)
    write_state("succeeded", head=head, commits=len(code_commits), report=str(report), notified=sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
