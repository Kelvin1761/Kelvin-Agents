#!/usr/bin/env python3
"""Claude 主導、Codex 分擔：Claude Code 用呢個腳本將子任務派畀 Codex CLI。

Kelvin 2026-11-24：佢自己唔再點用 Codex，全部交畀 Claude 決定幾時用、用邊個模型。
所以呢度負責三樣嘢：揀模型、睇住 Codex 額度、記帳。派唔派、派咩，係 Claude 按
`.claude/skills/codex-delegate/SKILL.md` 判斷。

角色（模型一律揀該系列最新一代，Codex 出新版自動跟）：
  grunt   Terra  —— 粗重、重複、攰人嘅工作：寫測試、批量改、資料審計腳本、搵 code
  review  Sol    —— 第二意見：同 Opus 獨立睇同一樣嘢（leakage、實驗結論、diff）
  quick   Luna   —— 唯讀：查詢、摘要、搵 code、睇 log
  chore   Luna   —— 寫入：簡單機械式改動（改名、格式、補 docstring、小測試）；做唔掂先升 Terra
  deep    Astra  —— 只喺 Sol 同 Opus 意見唔同、又值得再判嗰陣先用
  scan    Gemini Flash    —— 唯讀，超大 context（~1M）：一次過讀成堆 log／語料／實驗記錄再摘要
  third   Gemini Hydrogen —— 唯讀，第三家嘅獨立意見：Sol 同 Opus 唔同意見時先問佢（再唔夠先 deep）

Gemini 經 Antigravity CLI（`agy`，Kelvin 嘅 Google 訂閱；舊 Gemini CLI 2026-11-25 已唔再支援個人用戶）。
agy 冇得讀額度：撞到 429／RESOURCE_EXHAUSTED 就自動停派 5 個鐘（`gemini_quota.json`）。

用法：
  python3 codex_delegate.py status                       # 兩個窗嘅用量、節奏、建議
  python3 codex_delegate.py run review  --prompt-file brief.md
  python3 codex_delegate.py run grunt   --cd <worktree> --prompt-file brief.md --out result.md
  python3 codex_delegate.py run chore   --cd <worktree> --prompt-file brief.md

額度：Codex `exec --json` 唔會報額度，但每個 session 檔（~/.codex/sessions/**.jsonl）
入面有 `rate_limits`（5 小時窗＋7 日窗 used_percent／resets_at）。讀最新嗰個。
所以唔可以用 `--ephemeral`，否則冇 session 檔，下一次就讀唔到最新用量。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
PRIMARY_REPO = Path(os.environ.get("WC_PRIMARY_REPO_ROOT", Path.home() / "Antigravity-repo"))
LEDGER_NAME = "codex_delegations.jsonl"

# role -> (model family, reasoning effort, sandbox)
ROLES: dict[str, tuple[str, str, str]] = {
    "grunt": ("terra", "medium", "workspace-write"),
    "review": ("sol", "high", "read-only"),
    "quick": ("luna", "low", "read-only"),
    "chore": ("luna", "medium", "workspace-write"),
    "deep": ("astra", "xhigh", "read-only"),
}
# 冇 models_cache.json 嗰陣嘅後備（2026-11-24 嘅最新）
FALLBACK_MODELS = {"terra": "gpt-6.1-terra", "sol": "gpt-6.2-sol",
                   "luna": "gpt-6-luna", "astra": "gpt-6.2-astra"}

# Gemini（Antigravity CLI）：role -> (kind, effort)。kind：flash = 平、快；pro = 最強嘅非 flash 系列（而家 Hydrogen）
GEMINI_ROLES: dict[str, tuple[str, str]] = {
    "scan": ("flash", "medium"),
    "third": ("pro", "high"),
}
GEMINI_FALLBACK = {"flash": "gemini-3.8-flash", "pro": "gemini-4-hydrogen"}
GEMINI_EFFORTS = ("low", "medium", "high", "xhigh")
GEMINI_COOLDOWN = 5 * 3600
_GEMINI_SLUG = re.compile(r"^gemini-(\d+(?:\.\d+)*)-([a-z]+)-(low|medium|high|xhigh)$")
_GEMINI_CATALOG: list[str] | None = None

# 節流門檻（Kelvin 唔再自己用 Codex，所以唔使留額度畀佢）
STOP_WEEKLY = 95.0      # 7 日窗 ≥ 呢個 = 停派
STOP_FIVE_HOUR = 85.0   # 5 小時窗 ≥ 呢個 = 停派（等佢重置）
# 收緊：剩低嘅額度（距停派線）唔夠每日 TIGHT_PER_DAY 個百分點撐到重置。
# 唔用「用量 vs 時間進度」：Kelvin 以前自己用嘅額度已經用咗，再罰落去冇意思；
# 要問嘅係「剩低嗰份夠唔夠用到重置」。
TIGHT_PER_DAY = 4.0
# 收緊嗰陣仲准派嘅角色：review 最值錢；Luna（quick／chore）最平（Kelvin 2026-11-24：當免費勞工用）
TIGHT_ROLES = frozenset({"review", "quick", "chore"})

BRIEF_PREAMBLE = """\
你係被 Claude Code 委派嘅子任務（Claude 主導、Codex 分擔，見 AGENTS.md）。
硬性規則：
- 唔准 git commit／push／merge，唔准行 ./保存.sh、deploy、Telegram、launchd 或者任何排程。
- 唔准再委派畀其他 agent。
- 唔准郁 holdout、唔准改 docs/model-evaluation-contract.md。
- 唔肯定就照講唔肯定，唔好砌結論；冇跑過嘅嘢唔好講「通過」。
- 最後答覆用中文，最多 {limit} 字：做咗咩／發現咩、改咗邊啲檔（如有）、未確定或者要 Claude 判斷嘅嘢。

任務：
"""


def control_root() -> Path:
    root = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (
        Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(root)


# ── 模型 ────────────────────────────────────────────────────────────────

_SLUG = re.compile(r"^gpt-(\d+(?:\.\d+)*)-([a-z]+)$")


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split("."))


_CATALOG: list[dict] | None = None


def model_catalog() -> list[dict]:
    """Codex 嘅模型目錄。先問 `codex debug models`（即時，~0.5s），失敗先用
    ~/.codex/models_cache.json（上一次 run 嗰陣抓嘅）。Kelvin 2026-11-24：一出新模型就要即刻用。"""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    models: list[dict] = []
    try:
        proc = subprocess.run(["codex", "debug", "models"], capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            models = data.get("models", []) if isinstance(data, dict) else list(data)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        models = []
    if not models:
        try:
            models = json.loads((CODEX_HOME / "models_cache.json").read_text()).get("models", [])
        except (OSError, ValueError):
            models = []
    _CATALOG = models
    return models


def latest_model(family: str, models: list[dict] | None = None) -> str:
    """該系列最新、公開（visibility=list）嘅模型 slug。"""
    if models is None:
        models = model_catalog()
    best: tuple[tuple[int, ...], str] | None = None
    for m in models:
        slug = str(m.get("slug") or "")
        match = _SLUG.match(slug)
        if not match or match.group(2) != family or m.get("visibility", "list") != "list":
            continue
        key = (_version(match.group(1)), slug)
        if best is None or key > best:
            best = key
    return best[1] if best else FALLBACK_MODELS[family]


def gemini_catalog() -> list[str]:
    """`agy models` 即時讀（每行「slug<TAB>名」）；讀唔到就空 list（用後備）。"""
    global _GEMINI_CATALOG
    if _GEMINI_CATALOG is None:
        try:
            out = subprocess.run(["agy", "models"], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        _GEMINI_CATALOG = [line.split("\t", 1)[0].strip() for line in out.splitlines()
                           if line.startswith("gemini-")]
    return _GEMINI_CATALOG


def latest_gemini(kind: str, effort: str, slugs: list[str] | None = None) -> str:
    """kind=flash：最新 flash；kind=pro：最新非 flash／lite 系列。effort 冇就揀最近嘅。"""
    slugs = gemini_catalog() if slugs is None else slugs
    by_base: dict[tuple, dict[str, str]] = {}
    for slug in slugs:
        m = _GEMINI_SLUG.match(slug)
        if not m:
            continue
        name = m.group(2)
        if (kind == "flash") != (name == "flash") or name == "lite":
            continue
        by_base.setdefault((_version(m.group(1)), name), {})[m.group(3)] = slug
    if not by_base:
        return f"{GEMINI_FALLBACK[kind]}-{effort}"
    efforts = by_base[max(by_base)]
    if effort in efforts:
        return efforts[effort]
    want = GEMINI_EFFORTS.index(effort) if effort in GEMINI_EFFORTS else 1
    return min(efforts.items(), key=lambda kv: abs(GEMINI_EFFORTS.index(kv[0]) - want))[1]


def gemini_quota_file() -> Path:
    return control_root() / "gemini_quota.json"


def gemini_paused_until(now: float | None = None, path: Path | None = None) -> float | None:
    now = time.time() if now is None else now
    try:
        until = float(json.loads((path or gemini_quota_file()).read_text())["exhausted_until"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return until if until > now else None


def _gemini_quota_error(text: str) -> bool:
    t = text.lower()
    return bool(re.search(r"\b429\b", t)) or any(k in t for k in (
        "resource_exhausted", "resource has been exhausted", "quota exceeded", "exceeded your", "rate limit"))


# ── 額度 ────────────────────────────────────────────────────────────────

@dataclass
class Window:
    used: float
    window_minutes: int
    resets_at: float

    def effective_used(self, now: float) -> float:
        return 0.0 if now >= self.resets_at else self.used

    def elapsed_pct(self, now: float) -> float:
        span = self.window_minutes * 60
        left = max(0.0, self.resets_at - now)
        return max(0.0, min(100.0, 100.0 * (1 - left / span))) if span else 0.0


@dataclass
class Limits:
    five_hour: Window | None
    weekly: Window | None
    observed_at: float  # 嗰個 session 檔嘅 mtime


def _window(raw: dict | None) -> Window | None:
    if not raw or raw.get("used_percent") is None:
        return None
    return Window(float(raw["used_percent"]), int(raw.get("window_minutes") or 0),
                  float(raw.get("resets_at") or 0))


def read_limits(sessions_dir: Path | None = None, scan: int = 40) -> Limits | None:
    """由最新嘅 Codex session 檔讀最後一個 rate_limits。"""
    sessions_dir = sessions_dir or CODEX_HOME / "sessions"
    try:
        files = sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for path in files[:scan]:
        last = None
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    found = _find_key(event, "rate_limits")
                    if (isinstance(found, dict) and found.get("primary") is not None
                            and found.get("limit_id") in (None, "codex")):
                        last = found
        except OSError:
            continue
        if last:
            windows = [w for w in (_window(last.get("primary")), _window(last.get("secondary"))) if w]
            five = next((w for w in windows if w.window_minutes <= 600), None)
            week = next((w for w in windows if w.window_minutes > 600), None)
            return Limits(five, week, path.stat().st_mtime)
    return None


def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            hit = _find_key(v, key)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_key(v, key)
            if hit is not None:
                return hit
    return None


def budget_state(limits: Limits | None, now: float | None = None) -> tuple[str, str]:
    """返回 (state, 原因)。state ∈ normal / tight / stop / unknown。"""
    now = time.time() if now is None else now
    if limits is None:
        return "unknown", "讀唔到 Codex 額度（未有 session 檔）；當 normal 但要細心"
    if limits.five_hour and limits.five_hour.effective_used(now) >= STOP_FIVE_HOUR:
        return "stop", f"5 小時窗 {limits.five_hour.effective_used(now):.0f}% ≥ {STOP_FIVE_HOUR:.0f}%"
    if limits.weekly:
        used = limits.weekly.effective_used(now)
        if used >= STOP_WEEKLY:
            return "stop", f"本週 {used:.0f}% ≥ {STOP_WEEKLY:.0f}%"
        days_left = max(0.0, limits.weekly.resets_at - now) / 86400
        headroom = STOP_WEEKLY - used
        if headroom < TIGHT_PER_DAY * days_left:
            return "tight", (f"本週 {used:.0f}%，剩 {headroom:.0f}pp 要撐 {days_left:.1f} 日"
                             f"（< 每日 {TIGHT_PER_DAY:.0f}pp）")
        return "normal", f"本週 {used:.0f}%，剩 {headroom:.0f}pp 撐 {days_left:.1f} 日"
    return "normal", "只有 5 小時窗資料"


def role_allowed(role: str, state: str) -> bool:
    if state == "stop":
        return False
    if state == "tight":
        return role in TIGHT_ROLES
    return True


# ── 分工模式（Kelvin 2026-11-24：按兩邊額度調整 offload 幾多）──────────────
# Claude 嘅額度 Codex 腳本讀唔到；Claude 開工前用 mcp__ccd_session_mgmt__get_usage 睇
# 「Weekly · all models」嘅 percentUsed 同 resetsAt，再傳 `status --claude-weekly --claude-resets`。
CLAUDE_WEEK_SECONDS = 7 * 86400
CLAUDE_AHEAD_PP = 10.0     # Claude 用得快過時間 ≥ 呢個 pp = 盡量 offload
CLAUDE_BEHIND_PP = -20.0   # Claude 慢過時間 ≥ 20pp 而 Codex 又緊 = Claude 自己做多啲
CLAUDE_CRITICAL = 85.0     # Claude 本週 ≥ 呢個 = 連 grunt 都可以 --force（Codex 未 stop 嘅話）
USE_IT_DAYS = 2.0          # Codex 就嚟重置（< 2 日）而剩好多 = 用盡佢

MODES = {
    "offload-max": "Claude 額度緊：實作同重活派 Terra、覆核派 Sol（唔開 Opus subagent）、讀檔／摘要派 Luna；Opus 只做計劃、判決、保存",
    "offload-light": "Claude 緊但 Codex 都緊：只派 review／quick／chore；Claude 本週 ≥85% 先可以 --force 派 grunt",
    "balanced": "兩邊都正常：照常規分工（機械式先試 Luna，重活 Terra，結論要第二意見就 Sol）",
    "keep-claude": "Codex 緊而 Claude 有大把：Opus 自己做多啲，Codex 留畀 review",
    "claude-only": "Codex 停派：全部 Claude 做，慳住用（subagent 用平啲嘅模型）",
}


def pacing_file() -> Path:
    return control_root() / "claude_pacing.json"


def spend_freely_until(now: float | None = None, path: Path | None = None) -> tuple[float, str] | None:
    """Kelvin 話「呢個禮拜放心用 Opus」嘅開關：返回 (到期, 原因)；冇設或者過咗期 = None。"""
    now = time.time() if now is None else now
    try:
        data = json.loads((path or pacing_file()).read_text(encoding="utf-8"))
        until = _parse_ts(data["spend_freely_until"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (until, str(data.get("reason") or "")) if until > now else None


def claude_pace(used: float, resets_at: float, now: float) -> tuple[float, float]:
    """返回 (已過時間 %, 用量快過時間幾多 pp)。"""
    left = max(0.0, resets_at - now)
    elapsed = max(0.0, min(100.0, 100.0 * (1 - left / CLAUDE_WEEK_SECONDS)))
    return elapsed, used - elapsed


def offload_mode(codex_state: str, codex: Limits | None, claude_used: float,
                 claude_resets_at: float, now: float | None = None,
                 spend_freely: bool = False) -> tuple[str, str]:
    """spend_freely = Kelvin 開咗「放心用 Opus」：唔理 Claude 用得幾快，只有 ≥85% 先當緊。"""
    now = time.time() if now is None else now
    elapsed, ahead = claude_pace(claude_used, claude_resets_at, now)
    pace = f"Claude 本週 {claude_used:.0f}%（時間過咗 {elapsed:.0f}%，{ahead:+.0f}pp）"
    if spend_freely:
        pace += "；放心用 Opus 開關生效中"
        ahead = min(ahead, 0.0)
    if codex_state == "stop":
        return "claude-only", pace
    codex_rich = False
    if codex and codex.weekly and codex_state in ("normal", "unknown"):
        days_left = max(0.0, codex.weekly.resets_at - now) / 86400
        headroom = STOP_WEEKLY - codex.weekly.effective_used(now)
        codex_rich = days_left < USE_IT_DAYS and headroom > 2 * TIGHT_PER_DAY * max(days_left, 0.5)
        if codex_rich:
            pace += f"；Codex {days_left:.1f} 日後重置仲剩 {headroom:.0f}pp，唔用就嘥"
    claude_tight = ahead >= CLAUDE_AHEAD_PP or claude_used >= CLAUDE_CRITICAL
    if codex_state == "tight":
        if claude_tight:
            return "offload-light", pace
        if ahead <= CLAUDE_BEHIND_PP or spend_freely:
            return "keep-claude", pace
        return "balanced", pace
    if claude_tight or codex_rich:
        return "offload-max", pace
    return "balanced", pace


def _parse_ts(text: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


# ── 帳 ────────────────────────────────────────────────────────────────

def append_ledger(entry: dict) -> Path | None:
    path = control_root() / LEDGER_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path
    except OSError:
        return None


def ledger_summary(days: int = 7) -> dict:
    path = control_root() / LEDGER_NAME
    cutoff = time.time() - days * 86400
    out: dict[str, dict[str, int]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("ts", 0) < cutoff:
            continue
        row = out.setdefault(e.get("role", "?"), {"runs": 0, "ok": 0, "input": 0, "output": 0})
        row["runs"] += 1
        row["ok"] += int(e.get("ok", False))
        row["input"] += int(e.get("input_tokens") or 0)
        row["output"] += int(e.get("output_tokens") or 0)
    return out


# ── 命令 ────────────────────────────────────────────────────────────────

def _fmt_reset(ts: float) -> str:
    return time.strftime("%m-%d %H:%M", time.localtime(ts))


def cmd_status(args) -> int:
    limits = read_limits()
    state, why = budget_state(limits)
    print(f"Codex 狀態：{state} —— {why}")
    if limits:
        for name, w in (("5 小時窗", limits.five_hour), ("7 日窗", limits.weekly)):
            if w:
                print(f"  {name}：用咗 {w.effective_used(time.time()):.0f}%，{_fmt_reset(w.resets_at)} 重置")
        age_h = (time.time() - limits.observed_at) / 3600
        print(f"  （讀自 {age_h:.1f} 個鐘前嘅 session 檔）")
    print("角色 → 模型：")
    for role, (family, effort, sandbox) in ROLES.items():
        mark = "✓" if role_allowed(role, state) else "✗"
        print(f"  {mark} {role:<6} {latest_model(family):<16} effort={effort:<6} {sandbox}")
    paused = gemini_paused_until()
    print("Gemini（agy）：" + (f"⛔ 額度用完，{_fmt_reset(paused)} 之後再試" if paused else "✓ 可派（冇得讀額度，撞 429 先自動停 5 個鐘）"))
    for role, (kind, effort) in GEMINI_ROLES.items():
        mark = "✗" if paused else "✓"
        print(f"  {mark} {role:<6} {latest_gemini(kind, effort):<26} 唯讀")
    summary = ledger_summary()
    if summary:
        print("近 7 日委派：")
        for role, row in sorted(summary.items()):
            print(f"  {role:<6} {row['runs']} 次（成功 {row['ok']}），"
                  f"input {row['input']:,} / output {row['output']:,} tokens")
    out = {"state": state, "reason": why}
    if args.claude_weekly is not None and args.claude_resets:
        switch = spend_freely_until()
        mode, pace = offload_mode(state, limits, args.claude_weekly, _parse_ts(args.claude_resets),
                                  spend_freely=switch is not None)
        if switch:
            print(f"放心用 Opus：開住，{_fmt_reset(switch[0])} 自動失效（{switch[1] or '冇寫原因'}）")
        print(f"分工模式：{mode} —— {pace}")
        print(f"  {MODES[mode]}")
        out.update(mode=mode, pace=pace)
    else:
        print("分工模式：未計（加 --claude-weekly <%> --claude-resets <ISO> ，數字由 get_usage 嚟）")
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    return 0


# Codex workspace-write 會將 writable root 入面嘅 `.agents`、`.claude`、`.git` 設成唯讀
# （2026-11-24 實測：Terra 寫唔到 .agents/scripts/tests）。我哋大部分 code 喺 `.agents`，
# 所以寫入角色要用 --add-dir 開返呢兩個；`.git` 保持唯讀 = Codex commit 唔到，正合規矩。
WRITABLE_DOT_DIRS = (".agents", ".claude")


def cmd_pacing(args) -> int:
    path = pacing_file()
    if args.clear:
        path.unlink(missing_ok=True)
        print("放心用 Opus：已閂，返去按速度平衡")
        return 0
    if args.spend_freely_until:
        until = _parse_ts(args.spend_freely_until)
        if until <= time.time():
            print("到期時間要喺未來", file=sys.stderr)
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"spend_freely_until": args.spend_freely_until,
                                    "reason": args.reason or "", "set_at": time.time()},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"放心用 Opus：開咗，{_fmt_reset(until)} 自動失效")
        return 0
    switch = spend_freely_until()
    print(f"放心用 Opus：開住，{_fmt_reset(switch[0])} 失效（{switch[1]}）" if switch else "放心用 Opus：閂咗")
    return 0


def build_command(role: str, cwd: Path, out_file: Path,
                  model: str | None = None, effort: str | None = None) -> list[str]:
    """prompt 經 stdin 傳（`-`），長 brief 唔會撞 argv 上限。"""
    family, default_effort, sandbox = ROLES[role]
    cmd = [
        "codex", "exec", "--json",
        "-m", model or latest_model(family),
        "-c", f'model_reasoning_effort="{effort or default_effort}"',
        "-c", 'approval_policy="never"',
        "-s", sandbox,
        "-C", str(cwd),
        "--skip-git-repo-check",
        "-o", str(out_file),
    ]
    if sandbox == "workspace-write":
        for name in WRITABLE_DOT_DIRS:
            if (cwd / name).is_dir():
                cmd += ["--add-dir", str(cwd / name)]
    return cmd + ["-"]


def _resolved(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


def _git_out(cwd: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def write_target_problem(cwd: Path, primary: Path | None = None) -> str | None:
    """寫入角色只准喺主 checkout 以外嘅 git linked worktree 行。返回問題描述或者 None。"""
    primary = _resolved(primary or PRIMARY_REPO)
    cwd = _resolved(cwd)
    if cwd == primary or primary in cwd.parents:
        return "寫入角色唔准喺主 checkout（或者佢嘅子目錄）行；開一個 worktree 再用 --cd。"
    top = _git_out(cwd, "rev-parse", "--show-toplevel")
    if top is None:
        return "--cd 唔係 git worktree；寫入角色一定要喺一個獨立 worktree 行。"
    if _resolved(Path(top)) == primary:
        return "--cd 嘅 git toplevel 係主 checkout；開一個 worktree。"
    return None


def changed_files(cwd: Path) -> list[str]:
    out = _git_out(cwd, "status", "--porcelain", "--untracked-files=all")
    return [line[3:] for line in out.splitlines()] if out else []


def cmd_run_gemini(args) -> int:
    role = args.role
    paused = gemini_paused_until()
    if paused:
        print(f"⛔ 唔派：Gemini 額度用完，{_fmt_reset(paused)} 之後先再試。", file=sys.stderr)
        return 3
    try:
        task = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else sys.stdin.read()
    except OSError as exc:
        print(f"⛔ 讀唔到 brief：{exc}", file=sys.stderr)
        return 2
    if not task.strip():
        print("⛔ 冇任務內容。", file=sys.stderr)
        return 2
    cwd = _resolved(Path(args.cd or os.getcwd()))
    if not cwd.is_dir():
        print(f"⛔ --cd 唔存在：{cwd}", file=sys.stderr)
        return 2
    kind, default_effort = GEMINI_ROLES[role]
    effort = "xhigh" if args.effort == "max" else (args.effort if args.effort in GEMINI_EFFORTS else default_effort)
    model = args.model or latest_gemini(kind, effort)
    out_file = Path(args.out) if args.out else Path(
        os.environ.get("TMPDIR", "/tmp")) / f"gemini_{role}_{int(time.time())}.md"
    try:
        out_file.unlink()
    except FileNotFoundError:
        pass
    # agy -p 唔讀 stdin（2026-11-25 實測），長 brief 寫入檔再叫佢讀
    import shutil
    import tempfile
    brief_dir = Path(tempfile.mkdtemp(prefix="gemini_brief_"))
    brief = brief_dir / "brief.md"
    cmd = ["agy", "-p", f"讀 {brief}，嚴格照入面嘅規則同任務做，最後只輸出答覆。",
           "--model", model, "--mode", "plan", "--output-format", "json",
           "--disable-slash-commands", "--add-dir", str(brief_dir),
           "--print-timeout", f"{args.timeout}s"]
    started = time.time()
    data: dict = {}
    error = None
    raw_error = ""
    try:
        brief.write_text(BRIEF_PREAMBLE.format(limit=args.reply_limit) + task.strip() + "\n", encoding="utf-8")
        proc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=args.timeout + 60)
        for line in reversed(proc.stdout.strip().splitlines()):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                data = parsed
                break
        if data.get("status") != "SUCCESS" or proc.returncode != 0:
            raw_error = " | ".join(x for x in (str(data.get("error") or ""), proc.stderr.strip()) if x)
            error = (raw_error or f"冇輸出（returncode {proc.returncode}）")[-300:]
    except subprocess.TimeoutExpired:
        error = f"timeout after {args.timeout}s"
    except FileNotFoundError:
        error = "agy 唔喺 PATH（brew install --cask antigravity-cli）"
    except OSError as exc:
        error = f"OSError：{exc}"
    finally:
        shutil.rmtree(brief_dir, ignore_errors=True)
    reply = str(data.get("response") or "").strip()
    ok = error is None and bool(reply)
    if reply:
        try:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(reply + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"⚠️ 寫唔到輸出檔：{exc}", file=sys.stderr)
    if error and _gemini_quota_error(raw_error or error):
        until = time.time() + GEMINI_COOLDOWN
        try:
            gemini_quota_file().parent.mkdir(parents=True, exist_ok=True)
            gemini_quota_file().write_text(json.dumps({"exhausted_until": until, "error": error}, ensure_ascii=False))
            error += f"（已停派 Gemini 到 {_fmt_reset(until)}）"
        except OSError:
            error += "（⚠️ 停派狀態寫唔到）"
    usage = data.get("usage") or {}
    entry = {
        "ts": started, "provider": "gemini", "role": role, "model": model, "effort": effort,
        "cwd": str(cwd), "ok": ok, "seconds": round(time.time() - started, 1),
        "thread_id": data.get("conversation_id"), "budget_state": "n/a", "forced": False,
        "input_tokens": usage.get("input_tokens"), "cached_input_tokens": usage.get("cache_read_tokens"),
        "output_tokens": usage.get("output_tokens"), "changed_files": 0,
        "title": args.title, "error": None if ok else (error or "冇輸出"),
    }
    if append_ledger(entry) is None:
        print("⚠️ 記帳失敗（codex_delegations.jsonl 寫唔到）", file=sys.stderr)
    print(f"Gemini {role}（{model}）{'完成' if ok else '失敗'}，{entry['seconds']}s，"
          f"input {usage.get('input_tokens', '?')} / output {usage.get('output_tokens', '?')} tokens → {out_file}")
    if not ok:
        print(f"錯誤：{entry['error']}", file=sys.stderr)
    if reply:
        print("-----")
        print(reply)
    return 0 if ok else 1


def cmd_run(args) -> int:
    role = args.role
    if role in GEMINI_ROLES:
        return cmd_run_gemini(args)
    state, why = budget_state(read_limits())
    if state == "stop":
        # --force 都唔可以越過停派線（AGENTS.md）
        print(f"⛔ 唔派：Codex 停派中（{why}）。Claude 自己做。", file=sys.stderr)
        return 3
    forced = False
    if not role_allowed(role, state):
        if not args.force:
            print(f"⛔ 唔派：Codex 狀態 {state}（{why}）—— {role} 唔准派。Claude 自己做，"
                  "或者 Claude 嗰邊更緊就加 --force。", file=sys.stderr)
            return 3
        forced = True

    cwd = _resolved(Path(args.cd or os.getcwd()))
    family, _, sandbox = ROLES[role]
    if sandbox != "read-only":
        problem = write_target_problem(cwd)
        if problem:
            print(f"⛔ {problem}", file=sys.stderr)
            return 2

    try:
        task = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else sys.stdin.read()
    except OSError as exc:
        print(f"⛔ 讀唔到 brief：{exc}", file=sys.stderr)
        return 2
    if not task.strip():
        print("⛔ 冇任務內容。", file=sys.stderr)
        return 2
    prompt = BRIEF_PREAMBLE.format(limit=args.reply_limit) + task.strip() + "\n"

    out_file = Path(args.out) if args.out else Path(
        os.environ.get("TMPDIR", "/tmp")) / f"codex_{role}_{int(time.time())}.md"
    try:
        out_file.unlink()  # 舊輸出唔可以扮成今次嘅結果
    except FileNotFoundError:
        pass
    model = args.model or latest_model(family)
    cmd = build_command(role, cwd, out_file, model=model, effort=args.effort)

    started = time.time()
    usage: dict = {}
    thread_id = None
    completed = False
    errors: list[str] = []
    returncode = None
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=args.timeout)
        returncode = proc.returncode
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "thread.started":
                thread_id = event.get("thread_id")
            elif kind == "turn.completed":
                completed = True
                usage = event.get("usage") or {}
            elif kind in ("error", "turn.failed"):
                # 中途可重試嘅 error 唔等於失敗；最後有冇 turn.completed 先算
                errors.append(json.dumps(event, ensure_ascii=False)[:300])
        if returncode != 0 and proc.stderr:
            errors.append(proc.stderr.strip()[-300:])
    except subprocess.TimeoutExpired:
        errors.append(f"timeout after {args.timeout}s")
    except FileNotFoundError:
        errors.append("codex CLI 唔喺 PATH（brew install --cask codex）")

    try:
        reply = out_file.read_text(encoding="utf-8").strip()
    except OSError:
        reply = ""
    ok = returncode == 0 and completed and bool(reply)
    changes = changed_files(cwd) if sandbox != "read-only" else []

    entry = {
        "ts": started, "role": role, "model": model, "effort": args.effort or ROLES[role][1],
        "cwd": str(cwd), "ok": ok, "seconds": round(time.time() - started, 1),
        "thread_id": thread_id, "budget_state": state, "forced": forced,
        "input_tokens": usage.get("input_tokens"), "cached_input_tokens": usage.get("cached_input_tokens"),
        "output_tokens": usage.get("output_tokens"), "changed_files": len(changes),
        "title": args.title, "error": None if ok else (" | ".join(errors) or "冇輸出"),
    }
    if append_ledger(entry) is None:
        print("⚠️ 記帳失敗（codex_delegations.jsonl 寫唔到）", file=sys.stderr)

    print(f"Codex {role}（{model}）{'完成' if ok else '失敗'}，{entry['seconds']}s，"
          f"output {usage.get('output_tokens', '?')} tokens → {out_file}")
    if sandbox != "read-only":
        print(f"worktree 改動：{len(changes)} 個檔" + ("" if changes else " ⚠️ 冇改動 —— 睇佢答覆講咩"))
    if not ok:
        print(f"錯誤：{entry['error']}", file=sys.stderr)
    if reply:
        print("-----")
        print(reply)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    st.add_argument("--claude-weekly", type=float, help="Claude 每週已用 %%（get_usage 嘅 Weekly · all models）")
    st.add_argument("--claude-resets", help="Claude 每週重置時間（ISO，例如 2026-11-30T07:59:59Z）")
    st.set_defaults(func=cmd_status)
    pc = sub.add_parser("pacing", help="「放心用 Opus」開關（有到期日，過期自動失效）")
    pc.add_argument("--spend-freely-until", help="ISO 時間，通常係 Claude 每週重置時間")
    pc.add_argument("--reason")
    pc.add_argument("--clear", action="store_true")
    pc.set_defaults(func=cmd_pacing)
    rn = sub.add_parser("run")
    rn.add_argument("role", choices=sorted(ROLES) + sorted(GEMINI_ROLES))
    rn.add_argument("--prompt-file")
    rn.add_argument("--cd")
    rn.add_argument("--out")
    rn.add_argument("--title", help="一句講呢個委派做咩（記帳用）")
    rn.add_argument("--model", help="覆蓋自動揀嘅模型")
    rn.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    rn.add_argument("--reply-limit", type=int, default=300)
    rn.add_argument("--timeout", type=int, default=1800)
    rn.add_argument("--force", action="store_true", help="額度 tight 都照派（Claude 更緊先用）；越唔過 stop")
    rn.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
