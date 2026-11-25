#!/usr/bin/env python3
"""Claude 主導、Codex 分擔：Claude Code 用呢個腳本將子任務派畀 Codex CLI。

Kelvin 2026-11-24：佢自己唔再點用 Codex，全部交畀 Claude 決定幾時用、用邊個模型。
所以呢度負責三樣嘢：揀模型、睇住 Codex 額度、記帳。派唔派、派咩，係 Claude 按
`.claude/skills/codex-delegate/SKILL.md` 判斷。

角色（模型一律揀該系列最新一代，Codex 出新版自動跟）：
  grunt   Terra  —— 粗重、重複、攰人嘅工作：寫測試、批量改、資料審計腳本、搵 code
  review  Sol    —— 第二意見：同 Opus 獨立睇同一樣嘢（leakage、實驗結論、diff）
  quick   Luna   —— （Codex 版，Gemini 停派時嘅後備）唯讀：查詢、摘要、搵 code、睇 log
  chore   Luna   —— （Codex 版，Gemini 停派時嘅後備）寫入：簡單機械式改動；做唔掂先升 Terra
  deep    Astra  —— 只喺 Sol 同 Opus 意見唔同、又值得再判嗰陣先用
  design  Astra  —— 首席顧問：開工前睇架構／實驗設計夠唔夠穩、Hydrogen／Terra 做兩次都唔掂嘅難題
  scan    Gemini Hydrogen —— 唯讀，超大 context：一次過讀成堆 log／語料／實驗記錄再摘要
          （Kelvin 2026-11-25：唔用 Gemini Flash —— 就退役兼太弱，只揀非 flash／lite 系列）
  third   Gemini Hydrogen —— 唯讀，快速獨立檢查（唔係 Sol 級；真分歧交 deep）
  quick   Gemini Hydrogen —— 唯讀日常查詢（Kelvin 2026-11-25：取代 Luna；Gemini 停派就自動退返 Luna）
  chore   Gemini Hydrogen —— 寫入簡單改動（只改檔、行唔到 shell；Gemini 停派就退返 Luna）
  sprint  Gemini Hydrogen —— 寫入快手 feature／測試／批量改（Terra 級但快好多；Gemini 停派就退返 Terra）

分工（Kelvin 2026-11-25）：Opus 總指揮；Hydrogen＋Terra 做日常；Sol 把關；Astra 做設計同難題。
Codex 每週額度預算：Terra 45pp、Sol 30pp、Astra 15pp（design＋deep 共用），其餘預留。
每次 Codex run 記低前後 7 日窗用量差（`weekly_pp`），超預算嗰個系列唔准派（`--force` 可越過，喺 `--title` 寫原因）。

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
    "design": ("astra", "high", "read-only"),
}
# Codex 每週額度預算（7 日窗 pp，按模型系列；Luna 唔計）
FAMILY_BUDGET_PP = {"terra": 45.0, "sol": 30.0, "astra": 15.0}
# 冇 models_cache.json 嗰陣嘅後備（2026-11-24 嘅最新）
FALLBACK_MODELS = {"terra": "gpt-6.1-terra", "sol": "gpt-6.2-sol",
                   "luna": "gpt-6-luna", "astra": "gpt-6.2-astra"}

# Gemini（Antigravity CLI）：role -> (effort, write?)。一律用最新非 flash／lite 系列（而家 Hydrogen）；
# Kelvin 2026-11-25：唔准用 Gemini Flash。quick／chore 同 Codex 嘅 Luna 角色同名 —— Gemini 用唔到就退返 Luna。
GEMINI_ROLES: dict[str, tuple[str, bool]] = {
    "scan": ("medium", False),
    "third": ("high", False),
    "quick": ("low", False),
    "chore": ("medium", True),
    "sprint": ("high", True),
}
# Gemini 用唔到嗰陣退返邊個 Codex 角色
GEMINI_FALLBACK_ROLE = {"scan": "quick", "quick": "quick", "chore": "chore", "sprint": "grunt"}
GEMINI_WRITE_RULES = """- 你冇權行任何 shell 命令（會被拒絕，唔好試），只可以讀檔同改檔。測試同 git 由 Claude 做。
"""
GEMINI_FALLBACK = "gemini-4-hydrogen"  # 讀唔到 `agy models` 嘅後備（2026-11-25 最新）
GEMINI_EXCLUDED = frozenset({"flash", "lite"})
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


def eligible_gemini(slugs: list[str]) -> list[str]:
    out = []
    for slug in slugs:
        m = _GEMINI_SLUG.match(slug)
        if m and m.group(2) not in GEMINI_EXCLUDED:
            out.append(slug)
    return out


def latest_gemini(effort: str, slugs: list[str] | None = None) -> str:
    """最新非 flash／lite 系列（Kelvin 2026-11-25：唔用 Flash）。effort 冇就揀最近嘅。"""
    slugs = gemini_catalog() if slugs is None else slugs
    by_base: dict[tuple, dict[str, str]] = {}
    for slug in slugs:
        m = _GEMINI_SLUG.match(slug)
        if not m:
            continue
        name = m.group(2)
        if name in GEMINI_EXCLUDED:
            continue
        by_base.setdefault((_version(m.group(1)), name), {})[m.group(3)] = slug
    if not by_base:
        return f"{GEMINI_FALLBACK}-{effort}"
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
    "offload-max": "Claude 額度緊：實作同重活派 Terra、覆核派 Sol（唔開 Opus subagent）、讀檔／摘要派 Hydrogen；Opus 只做計劃、判決、保存",
    "offload-light": "Claude 緊但 Codex 都緊：只派 review／quick／chore；Claude 本週 ≥85% 先可以 --force 派 grunt",
    "balanced": "兩邊都正常：照常規分工（機械式先試 Hydrogen，重活 Terra，結論要第二意見就 Sol）",
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
        if e.get("ts", 0) < cutoff or e.get("type") == "grade":
            continue
        row = out.setdefault(e.get("role", "?"), {"runs": 0, "ok": 0, "input": 0, "output": 0})
        row["runs"] += 1
        row["ok"] += int(e.get("ok", False))
        row["input"] += int(e.get("input_tokens") or 0)
        row["output"] += int(e.get("output_tokens") or 0)
    return out


def _ledger_entries() -> list[dict]:
    try:
        lines = (control_root() / LEDGER_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def _family_of(model: str | None) -> str | None:
    m = _SLUG.match(model or "")
    return m.group(2) if m else None


def family_spent(limits: Limits | None, entries: list[dict] | None = None) -> dict[str, float] | None:
    """今個 7 日窗每個 Codex 系列食咗幾多 pp（由每次 run 嘅 weekly_pp 加埋）。冇窗資料 = None。"""
    if not limits or not limits.weekly:
        return None
    if time.time() >= limits.weekly.resets_at:
        return {}  # 讀到嘅窗已經重置咗（session 檔舊）：當新窗，唔好用舊數鎖死預算
    start = limits.weekly.resets_at - limits.weekly.window_minutes * 60
    out: dict[str, float] = {}
    for e in _ledger_entries() if entries is None else entries:
        if e.get("type") == "grade" or e.get("ts", 0) < start or e.get("weekly_pp") is None:
            continue
        fam = _family_of(e.get("model"))
        if fam:
            out[fam] = out.get(fam, 0.0) + max(0.0, float(e["weekly_pp"]))
    return out


def over_budget(family: str, limits: Limits | None, entries: list[dict] | None = None) -> str | None:
    cap = FAMILY_BUDGET_PP.get(family)
    spent = family_spent(limits, entries)
    if cap is None or spent is None:
        return None
    used = spent.get(family, 0.0)
    return f"{family.title()} 今週已用 {used:.1f}pp ≥ 預算 {cap:.0f}pp" if used >= cap else None


GRADES = ("accepted", "rework", "redo")


def grade_summary(days: int = 14, entries: list[dict] | None = None) -> dict[str, dict[str, int]]:
    """按模型計收貨評分：grade 記錄經 run_ts 對返 run 嘅模型。"""
    entries = _ledger_entries() if entries is None else entries
    cutoff = time.time() - days * 86400
    runs = {e.get("ts"): e for e in entries if e.get("type") != "grade"}
    latest: dict = {}
    for e in entries:  # 同一次 run 評咗幾次，只計最後一次
        if e.get("type") == "grade" and e.get("ts", 0) >= cutoff:
            latest[e.get("run_ts")] = e
    out: dict[str, dict[str, int]] = {}
    for e in latest.values():
        run = runs.get(e.get("run_ts"))
        model = (run or {}).get("model") or "?"
        row = out.setdefault(model, {})
        row[e["grade"]] = row.get(e["grade"], 0) + 1
    return out


def cmd_grade(args) -> int:
    entries = _ledger_entries()
    runs = [e for e in entries if e.get("type") != "grade" and e.get("ok")]
    if not runs:
        print("⛔ 記帳入面冇成功嘅 run 可以評", file=sys.stderr)
        return 2
    if args.run in (None, "last"):
        target = runs[-1]
    else:
        try:
            ts = float(args.run)
        except ValueError:
            print("⛔ --run 要係 run 嘅 ts（status --json 或者記帳入面）或者 last", file=sys.stderr)
            return 2
        target = next((e for e in runs if abs(float(e.get("ts", 0)) - ts) < 1e-3), None)
        if target is None:
            print(f"⛔ 搵唔到 ts={args.run} 嘅 run", file=sys.stderr)
            return 2
    entry = {"type": "grade", "ts": time.time(), "run_ts": target["ts"], "grade": args.grade,
             "note": args.note or "", "model": target.get("model"), "role": target.get("role")}
    if append_ledger(entry) is None:
        print("⛔ 記帳寫唔到", file=sys.stderr)
        return 1
    print(f"已評：{target.get('role')}（{target.get('model')}）「{target.get('title') or ''}」→ {args.grade}")
    return 0


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
    for role, (effort, write) in GEMINI_ROLES.items():
        mark = "✗" if paused else "✓"
        fb_role = GEMINI_FALLBACK_ROLE.get(role)
        fb = f"（停派時退返 Codex {fb_role}＝{ROLES[fb_role][0].title()}）" if fb_role else ""
        print(f"  {mark} {role:<6} {latest_gemini(effort):<26} {'寫入' if write else '唯讀'}{fb}")
    spent = family_spent(limits)
    if spent is not None:
        print("Codex 每週預算（pp，按每次 run 前後用量差估算）：" + "，".join(
            f"{fam.title()} {spent.get(fam, 0.0):.1f}/{cap:.0f}" for fam, cap in FAMILY_BUDGET_PP.items()))
    grades = grade_summary()
    if grades:
        print("收貨率（近 14 日，Claude 收貨時評）：")
        for model, g in sorted(grades.items()):
            total = sum(g.values())
            print(f"  {model:<26} 收貨 {g.get('accepted', 0)}／要改 {g.get('rework', 0)}／重做 {g.get('redo', 0)}"
                  f"（收貨率 {100 * g.get('accepted', 0) / total:.0f}%）")
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


# ── 模型健康（Kelvin 2026-11-25：模型唔正常要 Telegram；出新型號要講）──────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_FAIL_STREAK = 2  # 同一個模型連續失敗幾多次先報


def health_file() -> Path:
    return control_root() / "model_health.json"


def _load_health() -> dict:
    try:
        d = json.loads(health_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_health(d: dict) -> None:
    """原子寫入（tmp＋rename），兩個委派同時寫都唔會寫爛個檔。"""
    path = health_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def model_is_bad(model: str) -> str | None:
    v = _load_health().get("models", {}).get(model, {})
    return f"{model} 標咗唔正常（{v.get('error', '')[:60]}）" if v.get("status") == "bad" else None


def alert(text: str) -> bool:
    """Telegram primary（只畀 Kelvin）。測試同 WC_DELEGATE_ALERTS=0 唔發；發唔到唔會令委派失敗。"""
    if os.environ.get("WC_DELEGATE_ALERTS") == "0" or "PYTEST_CURRENT_TEST" in os.environ:
        print(f"[alert 未發] {text}", file=sys.stderr)
        return False
    sys.path.insert(0, str(REPO_ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))
    try:
        from racing_telegram import send_message
        result = send_message(text, audience="primary")
        return bool(isinstance(result, dict) and result.get("ok"))
    except Exception as exc:
        print(f"⚠️ Telegram 發唔到：{exc}", file=sys.stderr)
        return False


def note_run_health(model: str, ok: bool, error: str | None, entries: list[dict] | None = None) -> None:
    """每次委派之後：同一個模型連續 HEALTH_FAIL_STREAK 次失敗 → 報一次；之後成功 → 報恢復。"""
    entries = _ledger_entries() if entries is None else entries
    runs = [e for e in entries if e.get("type") != "grade" and e.get("model") == model]
    state = _load_health()
    models = state.setdefault("models", {})
    was_bad = models.get(model, {}).get("status") == "bad"
    recent = runs[-HEALTH_FAIL_STREAK:]
    if not ok and len(recent) >= HEALTH_FAIL_STREAK and not any(e.get("ok") for e in recent):
        if not was_bad or not models[model].get("alerted"):  # 上次發唔到就下次再試
            sent = alert(f"⚠️ 委派模型唔正常：{model} 連續 {HEALTH_FAIL_STREAK} 次失敗\n最後錯誤：{(error or '冇輸出')[:300]}\n"
                         "Claude 派工會跳過佢、改派後備或者自己做；每朝探測會再試。")
            models[model] = {"status": "bad", "since": time.time(), "error": (error or "")[:300], "alerted": sent}
            _save_health(state)
    elif ok and was_bad:
        models[model] = {"status": "ok", "since": time.time()}
        _save_health(state)
        alert(f"✅ 委派模型已恢復：{model}")


VERSION_CHECK_EVERY = 6 * 3600


def check_model_versions(today: str | None = None, force: bool = False) -> list[str]:
    """揀到嘅最新型號同上次唔同 → 報「已自動轉用」；讀唔到目錄（用緊後備型號）→ 每日報一次。
    派工時最多每 6 個鐘查一次（讀目錄要幾秒）；探測子程序設 WC_SKIP_VERSION_CHECK=1。"""
    if os.environ.get("WC_SKIP_VERSION_CHECK") == "1":
        return []
    today = today or time.strftime("%Y-%m-%d")
    state = _load_health()
    if not force and time.time() - float(state.get("version_checked_at") or 0) < VERSION_CHECK_EVERY:
        return []
    state["version_checked_at"] = time.time()
    seen = state.setdefault("latest", {})
    msgs = []
    current = {fam: latest_model(fam) for fam in FALLBACK_MODELS}
    if gemini_unavailable() is None or gemini_catalog():
        current["gemini"] = latest_gemini("high").rsplit("-", 1)[0]
    for fam, slug in current.items():
        old = seen.get(fam)
        if old and old != slug:
            msgs.append(f"🔄 {fam.title()}：{old} → {slug}（已自動轉用）")
        seen[fam] = slug
    missing = []
    if not model_catalog():
        missing.append("Codex（`codex debug models` 同 cache 都讀唔到）")
    if shutil_which("agy"):
        cat = gemini_catalog()
        if not cat:
            missing.append("Gemini（`agy models` 讀唔到）")
        elif not eligible_gemini(cat):
            missing.append("Gemini（目錄得 Flash／Lite，冇合格型號）")
    if missing and state.get("catalog_alert_day") != today:
        state["catalog_alert_day"] = today
        msgs.append("⚠️ 讀唔到型號目錄，用緊寫死嘅後備型號（可能過時）：" + "；".join(missing))
    _save_health(state)
    if msgs:
        alert("委派模型更新\n" + "\n".join(msgs))
    return msgs


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


PROBES = [  # (標籤, run 參數)：每日一次，最平設定
    ("Luna", ["quick", "--provider", "codex", "--effort", "low"]),
    ("Terra", ["grunt", "--effort", "low"]),
    ("Sol", ["review", "--effort", "low"]),
    ("Astra", ["design", "--effort", "low"]),
    ("Hydrogen", ["quick", "--provider", "gemini", "--effort", "low"]),
]


def cmd_health(args) -> int:
    if not args.probe:
        state = _load_health()
        bad = {m: v for m, v in state.get("models", {}).items() if v.get("status") == "bad"}
        print("模型健康：" + ("全部正常" if not bad else "；".join(f"{m} ⚠️ {v.get('error', '')[:80]}" for m, v in bad.items())))
        for fam, slug in state.get("latest", {}).items():
            print(f"  {fam:<8} {slug}")
        return 0
    import tempfile
    msgs = check_model_versions(force=True)
    results = []
    child_env = {**os.environ, "WC_SKIP_VERSION_CHECK": "1"}
    with tempfile.TemporaryDirectory(prefix="model_probe_") as tmp:
        brief = Path(tmp) / "brief.md"
        brief.write_text("健康探測：唔使讀任何檔、唔使改任何嘢，只覆「OK」。\n", encoding="utf-8")
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True)
        for label, argv in PROBES:
            cmd = [sys.executable, str(Path(__file__).resolve()), "run", *argv, "--cd", str(repo),
                   "--prompt-file", str(brief), "--reply-limit", "20", "--timeout", "300",
                   "--title", f"健康探測 {label}", "--out", str(Path(tmp) / f"{label}.md")]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=420, env=child_env)
                rc, err = proc.returncode, (proc.stderr or proc.stdout).strip()[-200:]
            except subprocess.TimeoutExpired:
                rc, err = 1, "探測逾時"
            # rc 3 = 額度唔准派（跳過）；但 CLI 唔喺 PATH 係壞咗，唔係額度
            status = "ok" if rc == 0 else ("skipped" if rc == 3 and "唔喺 PATH" not in err else "failed")
            results.append({"model": label, "status": status, "detail": "" if rc == 0 else err})
            print(f"  {label:<9} {status}" + (f"：{err}" if rc else ""))
    out = control_root() / "model_probe"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps({"ts": time.time(), "results": results,
                                                 "status": "failed" if any(r["status"] == "failed" for r in results) else "succeeded"},
                                                ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        alert("⚠️ 每日模型探測：" + "、".join(r["model"] for r in failed) + " 唔正常\n"
              + "\n".join(f"• {r['model']}：{r['detail'][:150]}" for r in failed)
              + "\nClaude 派工會自動跳過／改派後備。")
    return 1 if failed else 0


# ── 派工路由（Kelvin 2026-11-25）：按三邊額度揀邊個做，Opus 永遠兜底 ──────────────
# 每類工作嘅優先次序：(角色, provider)；"opus" = Claude 自己做。B 級覆核永遠唔會落到淨係 Hydrogen。
ROUTES: dict[str, tuple[str, list[tuple[str, str]], str]] = {
    "lookup": ("A", [("quick", "gemini"), ("quick", "codex"), ("opus", "")], "查詢、搵 code、讀 log"),
    "big-read": ("A", [("scan", "gemini"), ("quick", "codex"), ("opus", "")], "一次過讀大批資料／語料／實驗記錄"),
    "edit": ("A", [("chore", "gemini"), ("chore", "codex"), ("opus", "")], "簡單機械式改動"),
    "feature": ("A", [("sprint", "gemini"), ("grunt", "codex"), ("opus", "")], "A 級細 feature、測試、批量改"),
    "heavy": ("A", [("grunt", "codex"), ("opus", "")], "大型實作、長時間腳本、重構（太大就拆細畀 sprint）"),
    "3d": ("C", [("grunt", "codex"), ("opus", "")], "3D／Blender（bpy）、遊戲素材；難題先 route design"),
    "review": ("B", [("review", "codex"), ("opus", "")], "B 級覆核：模型、leakage、release、排程（Opus 頂上時可加 third 輔助）"),
    "design": ("C", [("design", "codex"), ("review", "codex"), ("opus", "")], "架構／實驗設計／Hydrogen、Terra 做兩次都唔掂嘅難題"),
    "arbitrate": ("C", [("deep", "codex"), ("opus", "")], "Sol 同 Opus 真分歧嘅終審"),
}
# 「放心用 Opus」開住嗰陣，呢幾類 Opus 自己做先（覆核／設計／終審照樣要獨立意見，唔郁）
OPUS_FIRST_WHEN_SPENDING = frozenset({"lookup", "big-read", "edit", "feature", "heavy"})
CLAUDE_EXHAUSTED = 95.0


def candidate_problem(role: str, provider: str, codex: Limits | None, codex_state: str,
                      gemini_problem: str | None, claude_used: float | None) -> str | None:
    """呢個人選而家用唔用得？用得 = None；用唔得 = 原因。"""
    if role == "opus":
        if claude_used is not None and claude_used >= CLAUDE_EXHAUSTED:
            return f"Claude 本週 {claude_used:.0f}% ≥ {CLAUDE_EXHAUSTED:.0f}%"
        return None
    if provider == "gemini":
        return gemini_problem or model_is_bad(latest_gemini(GEMINI_ROLES[role][0]))
    if codex_state == "stop":
        return "Codex 停派"
    if not role_allowed(role, codex_state):
        return f"Codex {codex_state}，{role} 唔准派"
    return over_budget(ROLES[role][0], codex) or model_is_bad(latest_model(ROLES[role][0]))


def route(task: str, codex: Limits | None, codex_state: str, gemini_problem: str | None,
          claude_used: float | None = None, spend_freely: bool = False) -> dict:
    risk, chain, desc = ROUTES[task]
    if spend_freely and task in OPUS_FIRST_WHEN_SPENDING:
        chain = [("opus", "")] + [c for c in chain if c[0] != "opus"]
    skipped = []
    for role, provider in chain:
        problem = candidate_problem(role, provider, codex, codex_state, gemini_problem, claude_used)
        if problem is None:
            return {"task": task, "risk": risk, "role": role, "provider": provider or "claude",
                    "skipped": skipped, "spend_freely": spend_freely}
        skipped.append(f"{role}（{provider or 'claude'}）：{problem}")
    return {"task": task, "risk": risk, "role": None, "provider": None, "skipped": skipped,
            "spend_freely": spend_freely}


def _route_label(r: dict) -> str:
    if r["role"] is None:
        return "⛔ 全部都緊：只做必要嘅嘢、拆細，或者等重置；同 Kelvin 講"
    if r["role"] == "opus":
        return "Opus 自己做" + ("（放心用 Opus 開住）" if r["spend_freely"] and not r["skipped"] else "")
    if r["provider"] == "gemini":
        return f"Gemini {r['role']}（{latest_gemini(GEMINI_ROLES[r['role']][0])}）"
    return f"Codex {r['role']}（{latest_model(ROLES[r['role']][0])}）"


def cmd_route(args) -> int:
    limits = read_limits()
    state, _ = budget_state(limits)
    gem = gemini_unavailable()
    spend = spend_freely_until() is not None
    tasks = [args.task] if args.task else list(ROUTES)
    out = []
    for task in tasks:
        r = route(task, limits, state, gem, args.claude_weekly, spend)
        out.append(r)
        risk, _, desc = ROUTES[task]
        print(f"{task:<10}[{risk}] → {_route_label(r)}    ｜{desc}")
        for why in r["skipped"]:
            print(f"{'':<14}跳過 {why}")
    if args.json:
        print(json.dumps(out if not args.task else out[0], ensure_ascii=False))
    return 0


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
    default_effort, write = GEMINI_ROLES[role]
    if write:
        problem = write_target_problem(cwd)
        if problem:
            print(f"⛔ {problem}", file=sys.stderr)
            return 2
    effort = "xhigh" if args.effort == "max" else (args.effort if args.effort in GEMINI_EFFORTS else default_effort)
    model = args.model or latest_gemini(effort)
    if not eligible_gemini([model]):
        print(f"⛔ 唔准用 {model}（Kelvin 2026-11-25：唔用 Gemini Flash／Lite；型號要似 gemini-4-hydrogen-high）",
              file=sys.stderr)
        return 2
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
           "--model", model, "--mode", "accept-edits" if write else "plan", "--output-format", "json",
           "--disable-slash-commands", "--add-dir", str(brief_dir),
           "--print-timeout", f"{args.timeout}s"]
    started = time.time()
    data: dict = {}
    error = None
    raw_error = ""
    try:
        preamble = BRIEF_PREAMBLE.format(limit=args.reply_limit)
        if write:
            preamble = preamble.replace("任務：\n", GEMINI_WRITE_RULES + "\n任務：\n")
        brief.write_text(preamble + task.strip() + "\n", encoding="utf-8")
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
        denied = [d.get("display_name") or d.get("action") for d in (data.get("denied_actions") or [])
                  if isinstance(d, dict)]
        if data.get("status") == "SUCCESS" and not str(data.get("response") or "").strip() and denied:
            data["error"] = f"冇輸出：被拒動作 {denied}（brief 要講明只改檔、唔行命令）"
            data["status"] = "ERROR"
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
    changes = changed_files(cwd) if write else []
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
            alert(f"⚠️ Gemini（Hydrogen）撞到額度上限，停派到 {_fmt_reset(until)}；期間 scan／quick／chore 退返 Luna、sprint 退返 Terra。")
        except OSError:
            error += "（⚠️ 停派狀態寫唔到）"
    usage = data.get("usage") or {}
    entry = {
        "ts": started, "provider": "gemini", "role": role, "model": model, "effort": effort,
        "cwd": str(cwd), "ok": ok, "seconds": round(time.time() - started, 1),
        "thread_id": data.get("conversation_id"), "budget_state": "n/a", "forced": False,
        "input_tokens": usage.get("input_tokens"), "cached_input_tokens": usage.get("cache_read_tokens"),
        "output_tokens": usage.get("output_tokens"), "changed_files": len(changes),
        "title": args.title, "error": None if ok else (error or "冇輸出"),
    }
    if append_ledger(entry) is None:
        print("⚠️ 記帳失敗（codex_delegations.jsonl 寫唔到）", file=sys.stderr)
    note_run_health(model, ok, entry["error"])
    print(f"Gemini {role}（{model}）{'完成' if ok else '失敗'}，{entry['seconds']}s，"
          f"input {usage.get('input_tokens', '?')} / output {usage.get('output_tokens', '?')} tokens → {out_file}")
    if write:
        print(f"worktree 改動：{len(changes)} 個檔" + ("" if changes else " ⚠️ 冇改動 —— 睇佢答覆講咩"))
    if not ok:
        print(f"錯誤：{entry['error']}", file=sys.stderr)
    if reply:
        print("-----")
        print(reply)
    return 0 if ok else 1


def gemini_unavailable() -> str | None:
    paused = gemini_paused_until()
    if paused:
        return f"Gemini 額度用完（{_fmt_reset(paused)} 之後再試）"
    import shutil
    if shutil.which("agy") is None:
        return "agy 唔喺 PATH"
    return None


def cmd_run(args) -> int:
    try:
        check_model_versions()
    except Exception as exc:  # 版本檢查出錯唔可以阻住派工
        print(f"⚠️ 型號檢查失敗：{exc}", file=sys.stderr)
    role = args.role
    args.provider = getattr(args, "provider", "auto")
    if args.provider == "gemini" and role not in GEMINI_ROLES:
        print(f"⛔ {role} 冇 Gemini 版本", file=sys.stderr)
        return 2
    if args.provider == "codex" and role not in ROLES:
        if role not in GEMINI_FALLBACK_ROLE:
            print(f"⛔ {role} 冇 Codex 版本", file=sys.stderr)
            return 2
        args.role = role = GEMINI_FALLBACK_ROLE[role]
        args.model = None if (args.model or "").startswith("gemini-") else args.model
    if role in GEMINI_ROLES and args.provider != "codex":
        why_not = gemini_unavailable()
        if why_not is None:
            return cmd_run_gemini(args)
        fallback = GEMINI_FALLBACK_ROLE.get(role)
        if fallback is None or args.provider == "gemini":
            print(f"⛔ 唔派：{why_not}。", file=sys.stderr)
            return 3
        print(f"↪ {why_not}，{role} 改派 Codex {fallback}", file=sys.stderr)
        args.role = role = fallback
        if (args.model or "").startswith("gemini-"):
            args.model = None  # Gemini 模型名唔可以帶去 Codex
    before = read_limits()
    state, why = budget_state(before)
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

    family, _, sandbox = ROLES[role]
    budget_problem = over_budget(_family_of(args.model) or family, before)
    if budget_problem:
        if not args.force:
            print(f"⛔ 唔派：{budget_problem}。改派其他角色、Claude 自己做，或者真係值得就加 --force。",
                  file=sys.stderr)
            return 3
        forced = True
    cwd = _resolved(Path(args.cd or os.getcwd()))
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
    weekly_pp = None
    after = read_limits()
    if before and after and before.weekly and after.weekly \
            and abs(before.weekly.resets_at - after.weekly.resets_at) < 3600:
        weekly_pp = round(after.weekly.used - before.weekly.used, 2)

    entry = {
        "ts": started, "role": role, "model": model, "effort": args.effort or ROLES[role][1],
        "cwd": str(cwd), "ok": ok, "seconds": round(time.time() - started, 1),
        "thread_id": thread_id, "budget_state": state, "forced": forced,
        "input_tokens": usage.get("input_tokens"), "cached_input_tokens": usage.get("cached_input_tokens"),
        "output_tokens": usage.get("output_tokens"), "changed_files": len(changes),
        "weekly_pp": weekly_pp,
        "title": args.title, "error": None if ok else (" | ".join(errors) or "冇輸出"),
    }
    if append_ledger(entry) is None:
        print("⚠️ 記帳失敗（codex_delegations.jsonl 寫唔到）", file=sys.stderr)
    note_run_health(model, ok, entry["error"])

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
    rn.add_argument("role", choices=sorted(set(ROLES) | set(GEMINI_ROLES)))
    rn.add_argument("--provider", choices=["auto", "gemini", "codex"], default="auto",
                    help="scan／quick／chore／sprint 預設 Gemini Hydrogen（用唔到退返 Luna／Terra）；codex = 指定用 Codex 版")
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
    he = sub.add_parser("health", help="模型健康：睇狀態；--probe 每個模型試一句（排程每日跑）")
    he.add_argument("--probe", action="store_true")
    he.set_defaults(func=cmd_health)
    ro = sub.add_parser("route", help="按 Claude／Codex／Gemini 額度揀邊個做（Opus 兜底）")
    ro.add_argument("task", nargs="?", choices=sorted(ROUTES), help="唔填 = 列晒所有工作類型")
    ro.add_argument("--claude-weekly", type=float, help="Claude 每週已用 %%（get_usage）")
    ro.add_argument("--json", action="store_true")
    ro.set_defaults(func=cmd_route)
    gr = sub.add_parser("grade", help="收貨評分：accepted（收貨）／rework（要改）／redo（重做）")
    gr.add_argument("grade", choices=GRADES)
    gr.add_argument("--run", help="run 嘅 ts；預設 last（最近一次成功 run）")
    gr.add_argument("--note")
    gr.set_defaults(func=cmd_grade)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
