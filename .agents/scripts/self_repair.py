#!/usr/bin/env python3
"""排程自動維修（Kelvin 2026-11-25：「scheduler 有問題你可以自動幫我維修」）。

只修**已知形狀**嘅故障，每樣都係冪等、每個 job 每日有上限，預設 dry-run（淨係講會做咩）：

  1. launchd job 冇 load 但 `~/Library/LaunchAgents/<label>.plist` 喺度 → `launchctl bootstrap`。
     要**連續兩輪（≥25 分鐘）**都見到冇 load 先做 —— release cutover 期間會短暫 bootout。
     `launchctl disable` 咗嘅、或者列咗喺 `self_repair_ignore.json` 嘅唔郁。
  2. 輸出過期 + 已 load + 冇跑緊 → `launchctl kickstart` 一次。只限 `KICKSTART_SAFE`：
     定時 tick／poll job，自己有 flock 防重疊、自己決定做唔做（時段、賽日）。主排程正在跑
     （生產 flock 有人揸住）就等。日曆 slot job（AU morning、HKJC prerace、NBA production…）
     唔 kickstart —— 佢哋嘅 slot 由觸發時間決定，亂開會食咗另一格或者重發 card；只做診斷。
  3. 鎖嘅 holder 紀錄（`auto-release.lock.json`、HKJC `*.lock.holder`）入面嘅 PID 已死，
     而把 flock 冇任何 process 開住 → 刪紀錄。flock 本身由 OS 放，從來唔刪 `.lock` 檔。
  4. 內置碟淨 < 10GB → 只跑現成嘅安全清理：`compress_data_root.py`（APFS 透明壓縮，內容唔變）
     同 `offload_prediction_snapshots.py`（先驗 sha256 抄去外置碟先刪本機；碟冇掛載就唔跑）。
  其他（未知）→ 寫診斷包去 `WongChoiControl/self_repair/<日期>/`，live 模式先發**一條** primary
  Telegram，附 Claude Code 診斷命令。`--allow-llm-diagnosis` 先會自動開 `claude -p`
  （喺新 worktree、新分支，淨係出診斷同 patch，唔 push、唔 merge、唔部署），每日最多一次。

永遠唔會：改 code、merge、部署、改 plist 內容、掂 secrets、刪資料。

    python3 self_repair.py              # dry-run（預設）
    python3 self_repair.py --live       # 真係做
    python3 self_repair.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import job_freshness  # noqa: E402

HOME = Path.home()
CONTROL = Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT", HOME / "WongChoiData" / "WongChoiControl"))
LAUNCH_AGENTS = HOME / "Library" / "LaunchAgents"
PREFIX = "com.antigravity."
SCHED = job_freshness.SCHED
EXTERNAL_DISK = Path("/Volumes/Kelvin Hardisk 1")
MAIN_REPO = Path("/Users/imac/Antigravity-repo")

DISK_MIN_GB = 10.0
UNLOADED_CONFIRM_SECONDS = 25 * 60
DAILY_LIMIT = {"bootstrap": 2, "kickstart": 1, "cleaner": 1, "llm": 1}
STATE_KEEP_DAYS = 14

# label → 點解 kickstart 安全。全部係 StartInterval／密集日曆 tick，有自己 flock，晚咗開一次唔會雙重做嘢。
KICKSTART_SAFE: dict[str, str] = {
    "au-wong-choi.betfair-snapshot": "60 秒 tick，只讀 Betfair 快照",
    "au-wong-choi.bot": "120 秒 poll，bot 自己 flock",
    "hkjc-wong-choi.intraday": "15 分鐘 tick，HKJC 全域 flock（有界等待）",
    "hkjc-wong-choi.recovery": "30 分鐘復原 tick，本身就係重試",
    "nba-wong-choi.postgame": "15 分鐘 incremental，flock + notify_once 去重",
    "tennis-wong-choi.betfair": "15 分鐘 tick，tennis_betfair_tick.lock flock；決定凍結唔會重做",
    "tennis-wong-choi.preclose": "30 分鐘 tick，自己 flock",
    "tennis-wong-choi.settle": "結算 tick，自己 flock、已結算唔重做",
    "central-wong-choi.durability": "central-durability.lock flock，冪等備份",
}

# 主排程 flock：有人揸住 = 主 pipeline 跑緊，唔好 kickstart 搶資源（等下一輪）。
PRODUCTION_LOCKS = [
    HOME / "WongChoiData" / "Wong Choi Horse Race Analysis" / "AU_Racing" / ".au_daily_schedule.lock",
    SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock",
    SCHED / ".agents/skills/nba/nba_daily_auto/state/nba_daily_schedule.lock",
    SCHED / "tennis-wong-choi/data/logs/tennis_daily_schedule.lock",
]

# (holder 紀錄, 佢對應嘅 flock 檔)。紀錄係 advisory；flock 死咗 OS 會放。
HOLDER_RECORDS = [
    (CONTROL / "auto-release.lock.json", CONTROL / "auto-release.lock"),
    (SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock.holder",
     SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock"),
]


# ───────────────────────── 系統介面（測試用 fake 換走） ─────────────────────────

class System:
    """所有郁到機器嘅嘢都經呢度；測試換 FakeSystem，唔會真係叫 launchctl。"""

    uid = os.getuid()

    def _run(self, cmd: list[str], timeout: float = 30) -> tuple[int, str]:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout)
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, f"{type(exc).__name__}: {exc}"

    def installed_plists(self) -> dict[str, Path]:
        out = {}
        for path in sorted(LAUNCH_AGENTS.glob(f"{PREFIX}*.plist")):
            out[path.name[len(PREFIX):-len(".plist")]] = path
        return out

    def launchctl_print(self, label: str) -> dict | None:
        rc, out = self._run(["launchctl", "print", f"gui/{self.uid}/{PREFIX}{label}"])
        return parse_launchctl_print(out) if rc == 0 else None

    def disabled_labels(self) -> set[str]:
        _, out = self._run(["launchctl", "print-disabled", f"gui/{self.uid}"])
        return {m.group(1)[len(PREFIX):] for m in re.finditer(r'"([^"]+)"\s*=>\s*(?:disabled|true)', out)
                if m.group(1).startswith(PREFIX)}

    def bootstrap(self, plist: Path) -> tuple[int, str]:
        return self._run(["launchctl", "bootstrap", f"gui/{self.uid}", str(plist)])

    def kickstart(self, label: str) -> tuple[int, str]:
        # 冇 -k：如果佢啱啱自己開咗，唔會殺咗佢重開。
        return self._run(["launchctl", "kickstart", f"gui/{self.uid}/{PREFIX}{label}"])

    def file_in_use(self, path: Path) -> bool:
        """有冇任何 process 開住呢個檔（flock 持有者一定開住）。唔試攞鎖 —— 試攞會令真 job skip。"""
        if not path.exists():
            return False
        rc, out = self._run(["/usr/sbin/lsof", "-t", "--", str(path)], timeout=20)
        return rc == 0 and bool(out.strip())

    def pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def remove(self, path: Path) -> None:
        path.unlink()

    def disk_free_gb(self) -> float:
        return shutil.disk_usage("/System/Volumes/Data" if Path("/System/Volumes/Data").exists() else "/").free / 1e9

    def is_mounted(self, path: Path) -> bool:
        return os.path.ismount(path)

    def run_cleaner(self, cmd: list[str]) -> tuple[int, str]:
        return self._run(cmd, timeout=1900)

    def tail(self, path: Path, lines: int = 80) -> str:
        try:
            with path.open("rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 64_000))
                text = fh.read().decode("utf-8", "replace")
        except OSError as exc:
            return f"(讀唔到 {path}：{type(exc).__name__})"
        return "\n".join(text.splitlines()[-lines:])

    def send_telegram(self, text: str) -> dict:
        sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))
        import racing_telegram  # noqa: PLC0415
        return racing_telegram.send_message(text, audience="primary")

    def spawn_llm(self, cmd: list[str], cwd: Path, log: Path) -> int:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        return proc.pid


def parse_launchctl_print(text: str) -> dict:
    """頂層 state／pid／last exit code。子區段（endpoints…）入面都有 `state =`，所以攞第一個。"""
    info: dict = {"loaded": True, "state": None, "pid": None, "last_exit": None}
    for line in text.splitlines():
        s = line.strip()
        if info["state"] is None and s.startswith("state = "):
            info["state"] = s.split("=", 1)[1].strip()
        elif info["pid"] is None and s.startswith("pid = "):
            v = s.split("=", 1)[1].strip()
            info["pid"] = int(v) if v.isdigit() else None
        elif info["last_exit"] is None and s.startswith("last exit code = "):
            m = re.match(r"-?\d+", s.split("=", 1)[1].strip())  # 「75: EX_TEMPFAIL」
            info["last_exit"] = int(m.group(0)) if m else None
    info["running"] = info["state"] == "running" or info["pid"] is not None
    return info


# ───────────────────────── state（每日上限） ─────────────────────────

def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def prune_state(state: dict, today: str) -> dict:
    cutoff = (datetime.fromisoformat(today) - timedelta(days=STATE_KEEP_DAYS)).date().isoformat()
    for key in ("actions", "notified"):
        state[key] = {d: v for d, v in (state.get(key) or {}).items() if d >= cutoff}
    state.setdefault("unloaded_seen", {})
    return state


@dataclass
class Report:
    dry_run: bool
    today: str
    actions: list = field(default_factory=list)      # 做咗／會做嘅修理
    skipped: list = field(default_factory=list)      # 見到但唔郁（同埋原因）
    unknown: list = field(default_factory=list)      # 要人／LLM 睇
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"dry_run": self.dry_run, "date": self.today, "actions": self.actions,
                "skipped": self.skipped, "unknown": self.unknown, "notes": self.notes}


class SelfRepair:
    def __init__(self, system: System | None = None, *, dry_run: bool = True, now: float | None = None,
                 control: Path = CONTROL, freshness=job_freshness.check,
                 allow_llm: bool = False):
        self.sys = system or System()
        self.dry_run = dry_run
        self.now = time.time() if now is None else now
        self.today = datetime.fromtimestamp(self.now).date().isoformat()
        self.control = control
        self.state_path = control / "self_repair_state.json"
        self.state = prune_state(load_state(self.state_path), self.today)
        self.freshness = freshness
        self.allow_llm = allow_llm
        self.report = Report(dry_run=dry_run, today=self.today)

    # ── 上限 ──
    def _used(self, kind: str, label: str) -> int:
        return int(((self.state["actions"].get(self.today) or {}).get(f"{kind}:{label}")) or 0)

    def _allowed(self, kind: str, label: str) -> bool:
        return self._used(kind, label) < DAILY_LIMIT[kind]

    def _count(self, kind: str, label: str) -> None:
        day = self.state["actions"].setdefault(self.today, {})
        day[f"{kind}:{label}"] = int(day.get(f"{kind}:{label}") or 0) + 1

    def _act(self, kind: str, label: str, detail: str, fn) -> None:
        entry = {"kind": kind, "label": label, "detail": detail}
        if self.dry_run:
            entry["result"] = "dry-run（冇做）"
        else:
            rc, out = fn()
            self._count(kind, label)
            entry["result"] = "ok" if rc == 0 else f"失敗 rc={rc}: {out.strip()[-300:]}"
        self.report.actions.append(entry)

    def _ignored(self) -> set[str]:
        try:
            return set(json.loads((self.control / "self_repair_ignore.json").read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return set()

    # ── 1 + 2：launchd job ──
    def check_jobs(self) -> None:
        plists = self.sys.installed_plists()
        disabled = self.sys.disabled_labels()
        ignored = self._ignored()
        busy = [str(p) for p in PRODUCTION_LOCKS if self.sys.file_in_use(p)]
        seen = self.state["unloaded_seen"]
        for label, plist in plists.items():
            if label in ignored:
                self.report.skipped.append({"label": label, "reason": "self_repair_ignore.json"})
                continue
            info = self.sys.launchctl_print(label)
            if info is None:
                self._unloaded(label, plist, disabled, seen)
                continue
            seen.pop(label, None)
            if label not in job_freshness.REGISTRY:
                continue  # 冇可靠輸出可以核對（live／startup）→ 健康.sh 照睇退出碼
            fresh = self.freshness(label, self.now)
            state = (fresh.get("state") or "").lower()
            if fresh.get("fresh") and state not in job_freshness.FAILED_STATES:
                continue
            if fresh.get("fresh"):
                self._unknown(label, plist, info, fresh, "最新 run 自己寫住失敗（新鮮但 failed）")
                continue
            if info["running"]:
                self.report.skipped.append({"label": label, "reason": "輸出過期但正在跑，等佢完"})
                continue
            if label not in KICKSTART_SAFE:
                self._unknown(label, plist, info, fresh, "輸出過期；日曆 slot job 唔自動 kickstart")
                continue
            if busy:
                self.report.skipped.append({"label": label, "reason": f"主排程跑緊（{busy[0]}），下輪先 kickstart"})
                continue
            if not self._allowed("kickstart", label):
                self._unknown(label, plist, info, fresh, "今日已 kickstart 過一次仍然過期")
                continue
            self._act("kickstart", label,
                      f"輸出 {fresh.get('age_hours')} 鐘前（上限 {fresh.get('max_age_hours')}）；{KICKSTART_SAFE[label]}",
                      lambda label=label: self.sys.kickstart(label))

    def _unloaded(self, label: str, plist: Path, disabled: set[str], seen: dict) -> None:
        if label in disabled:
            self.report.skipped.append({"label": label, "reason": "launchctl disable 咗（人手決定），唔 bootstrap"})
            return
        first = seen.get(label)
        if first is None and not self.dry_run:
            seen[label] = self.now
            self.report.skipped.append({"label": label, "reason": "第一次見到冇 load；下一輪仍然冇先 bootstrap"})
            return
        if first is not None and self.now - first < UNLOADED_CONFIRM_SECONDS:
            self.report.skipped.append({"label": label, "reason": "冇 load 未夠 25 分鐘（可能 release cutover 中）"})
            return
        if not self._allowed("bootstrap", label):
            self._unknown(label, plist, None, None, "今日 bootstrap 咗兩次仍然冇 load")
            return
        detail = "plist 喺 LaunchAgents 但冇 load" + ("（dry-run：live 要連續兩輪見到先做）" if first is None else "")
        self._act("bootstrap", label, detail, lambda: self.sys.bootstrap(plist))
        if not self.dry_run:
            seen.pop(label, None)

    # ── 3：holder 紀錄 ──
    def check_holders(self, records=None) -> None:
        for record, lock in (HOLDER_RECORDS if records is None else records):
            if not record.exists():
                continue
            try:
                pid = int(json.loads(record.read_text(encoding="utf-8")).get("pid"))
            except (OSError, ValueError, TypeError, AttributeError):
                self.report.skipped.append({"label": str(record), "reason": "holder 紀錄冇 pid，唔郁"})
                continue
            if self.sys.pid_alive(pid):
                continue
            if self.sys.file_in_use(lock):
                self.report.skipped.append({"label": str(record), "reason": f"pid {pid} 死咗但 flock 仍有人開住"})
                continue
            self._act("holder", str(record), f"pid {pid} 已死、{lock.name} 冇人開住",
                      lambda record=record: (self.sys.remove(record), (0, ""))[1])

    # ── 4：磁碟 ──
    def check_disk(self) -> None:
        free = self.sys.disk_free_gb()
        self.report.notes.append(f"內置碟淨 {free:.1f} GB")
        if free >= DISK_MIN_GB:
            return
        py = sys.executable
        cleaners = [("compress", [py, str(REPO / ".agents/scripts/compress_data_root.py"),
                                  str(HOME / "WongChoiData"), "--time-budget", "900"])]
        if self.sys.is_mounted(EXTERNAL_DISK):
            cleaners.append(("offload", [py, str(REPO / ".agents/scripts/offload_prediction_snapshots.py"),
                                         "--time-budget", "900"]))
        else:
            self.report.skipped.append({"label": "offload", "reason": "外置碟冇掛載，唔搬快照"})
        for name, cmd in cleaners:
            if not self._allowed("cleaner", name):
                self.report.skipped.append({"label": name, "reason": "今日已跑過"})
                continue
            self._act("cleaner", name, f"碟淨 {free:.1f} GB < {DISK_MIN_GB:g}", lambda cmd=cmd: self.sys.run_cleaner(cmd))
        if self._used("cleaner", "compress") and free < DISK_MIN_GB:
            self.report.unknown.append({"label": "disk", "reason": f"碟淨 {free:.1f} GB；安全清理已跑過，要人手揀刪咩"})

    # ── 未知：診斷包 ──
    def _unknown(self, label: str, plist: Path, info: dict | None, fresh: dict | None, reason: str) -> None:
        bundle = self.control / "self_repair" / self.today / f"{label}.json"
        err_path = out_path = None
        try:
            spec = plistlib.loads(plist.read_bytes())
            err_path, out_path = spec.get("StandardErrorPath"), spec.get("StandardOutPath")
        except (OSError, plistlib.InvalidFileException, ValueError):
            pass
        manifest = None
        hit = job_freshness.newest(job_freshness.REGISTRY.get(label, ([], 0))[0])
        if hit and hit[1].endswith(".json"):
            manifest = {"path": hit[1], "text": self.sys.tail(Path(hit[1]), 200)}
        payload = {"label": label, "reason": reason, "at": datetime.fromtimestamp(self.now).isoformat(),
                   "launchctl": info, "freshness": fresh, "plist": str(plist),
                   "stderr_tail": self.sys.tail(Path(err_path)) if err_path else None,
                   "stdout_tail": self.sys.tail(Path(out_path), 40) if out_path else None,
                   "manifest": manifest}
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        self.report.unknown.append({"label": label, "reason": reason, "bundle": str(bundle)})

    # ── 通知 + 可選 LLM ──
    def diagnosis_command(self, label: str, bundle: str) -> list[str]:
        prompt = (f"Wong Choi 排程 job {PREFIX}{label} 出事。診斷包：{bundle}。讀 AGENTS.md，"
                  "搵根本原因；如果係細而清楚嘅 bug，喺呢個 worktree 改 code + 加 test，commit 落當前分支。"
                  "唔准 push、唔准 ./保存.sh、唔准 merge、唔准郁 launchctl／plist、唔准發 Telegram、唔准刪資料。"
                  "最後喺 diagnosis.md 寫低成因、證據同建議。")
        return ["claude", "-p", prompt, "--permission-mode", "acceptEdits",
                "--allowedTools", "Read,Grep,Glob,Edit,Write,Bash(git diff:*),Bash(git status:*),"
                "Bash(git add:*),Bash(git commit:*),Bash(python3 -m pytest:*),Bash(tail:*),Bash(cat:*)",
                "--disallowedTools", "Bash(git push:*),Bash(launchctl:*),Bash(./保存.sh:*),Bash(rm:*)"]

    def worktree_for(self, label: str) -> tuple[Path, str]:
        branch = f"self-repair-{label.replace('.', '-')}-{self.today.replace('-', '')}"
        return MAIN_REPO / ".claude" / "worktrees" / branch, branch

    def notify(self) -> None:
        notified = self.state["notified"].setdefault(self.today, [])
        fresh = [u for u in self.report.unknown if u["label"] not in notified]
        if not fresh:
            return
        lines = [f"🛠️ 排程自動維修：{len(fresh)} 個問題唔識自己修"]
        for u in fresh:
            lines.append(f"• {u['label']}：{u['reason']}")
        if self.report.actions:
            lines.append("已自動處理：" + "、".join(f"{a['kind']} {a['label']}（{a['result']}）" for a in self.report.actions))
        first = next((u for u in fresh if u.get("bundle")), None)
        if first:
            wt, branch = self.worktree_for(first["label"])
            lines.append(f"診斷包：{Path(first['bundle']).parent}")
            lines.append("Claude 診斷：\n"
                         f"git -C {MAIN_REPO} fetch origin && git -C {MAIN_REPO} worktree add -b {branch} {wt} origin/main"
                         f" && cd {wt} && claude -p \"讀 {first['bundle']} 診斷 {PREFIX}{first['label']}，唔准 push／保存\"")
        text = "\n".join(lines)
        if self.dry_run:
            self.report.notes.append("dry-run：唔發 Telegram。會發：\n" + text)
            return
        result = self.sys.send_telegram(text)
        self.report.notes.append(f"Telegram primary：{result.get('status') or result.get('ok')}")
        notified.extend(u["label"] for u in fresh)
        if self.allow_llm and first:
            self._launch_llm(first)

    def _launch_llm(self, item: dict) -> None:
        if not self._allowed("llm", "all"):
            self.report.notes.append("LLM 診斷今日已開過一次")
            return
        wt, branch = self.worktree_for(item["label"])
        if not wt.exists():
            rc, out = self.sys._run(["git", "-C", str(MAIN_REPO), "fetch", "origin"], timeout=120)
            rc, out = self.sys._run(["git", "-C", str(MAIN_REPO), "worktree", "add", "-b", branch, str(wt), "origin/main"])
            if rc != 0:
                self.report.notes.append(f"開 worktree 失敗：{out.strip()[-200:]}")
                return
        pid = self.sys.spawn_llm(self.diagnosis_command(item["label"], item["bundle"]), wt,
                                 Path(item["bundle"]).with_suffix(".claude.log"))
        self._count("llm", "all")
        self.report.notes.append(f"已開 Claude 診斷 pid {pid}（分支 {branch}，唔會 push／merge）")

    # ── 主流程 ──
    def run(self) -> Report:
        for step in (self.check_jobs, self.check_holders, self.check_disk):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 — 一步壞唔好令其他步唔做
                self.report.unknown.append({"label": f"self_repair.{step.__name__}",
                                            "reason": f"{type(exc).__name__}: {exc}"})
        self.notify()
        if not self.dry_run:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.state_path)
        latest = self.control / "self_repair" / "latest.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(self.report.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        return self.report


def render(report: Report) -> str:
    out = [f"== 排程自動維修 {report.today} {'(dry-run)' if report.dry_run else '(live)'}"]
    for a in report.actions:
        out.append(f"🔧 {a['kind']:9s} {a['label']}：{a['detail']} → {a['result']}")
    for s in report.skipped:
        out.append(f"⏸  {s['label']}：{s['reason']}")
    for u in report.unknown:
        out.append(f"❓ {u['label']}：{u['reason']}" + (f"（{u['bundle']}）" if u.get("bundle") else ""))
    out.extend(f"ℹ️  {n}" for n in report.notes)
    if len(out) == 1:
        out.append("✅ 冇嘢要修")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live", action="store_true", help="真係修（預設 dry-run）")
    ap.add_argument("--allow-llm-diagnosis", action="store_true",
                    help="live 模式下有未知問題就自動開 claude -p 診斷（新 worktree、唔 push）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    report = SelfRepair(dry_run=not a.live, allow_llm=a.allow_llm_diagnosis and a.live).run()
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=1) if a.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
