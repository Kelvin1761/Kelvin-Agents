#!/usr/bin/env python3
"""排程自動維修（Kelvin 2026-11-25：「scheduler 有問題你可以自動幫我維修」）。

只修**已知形狀**嘅故障，每樣都係冪等、每個 job 每日有上限，預設 dry-run（淨係講會做咩）：

  1. `REPAIR_SAFE` 入面嘅 tick job 冇 load（launchctl 明確答「service 唔存在」，exit 113）但
     `~/Library/LaunchAgents/<label>.plist` 喺度 → `launchctl bootstrap`。要連續兩輪（≥25 分鐘）
     都見到先做。`launchctl disable` 咗、`self_repair_ignore.json`、`WongChoiControl/paused-launchd/`
     入面有嘅唔郁。日曆 slot job 冇 load → 只診斷。launchctl 其他錯誤 → 只診斷，唔當冇 load。
  2. `REPAIR_SAFE` 入面嘅 tick job 輸出過期 + 已 load + 冇跑緊 → `launchctl kickstart` 一次（冇 `-k`）。
     呢啲 job 自己有 flock 防重疊、自己決定做唔做。主排程 flock 有人開住就等。
     日曆 slot job（AU morning、HKJC prerace、NBA production…）唔 kickstart —— slot 由觸發時間決定。
  3. 內置碟淨 < 10GB → 只跑現成安全清理：`compress_data_root.py`（APFS 透明壓縮，內容唔變）同
     `offload_prediction_snapshots.py`（sha256 驗完先刪本機；外置碟冇掛載就唔跑）。
  其他一律只診斷：寫診斷包去 `WongChoiControl/self_repair/<日期>/`，live 模式同一 job 每日只發一條
  primary Telegram。死 PID 嘅鎖 holder 紀錄都只係診斷（附人手命令）—— 自動刪有 TOCTOU 競態。

安全閘（Sol 覆核 2026-11-25）：
  * 整個 run 揸 `self_repair.lock` flock；第二個 instance 即走。
  * 每日上限喺**動手之前**先原子寫落 state；中途 crash 都唔會重做。
  * state 檔讀唔到／壞咗 → 拒絕動手（只診斷 + 通知），唔會當空白重新開始。
  * release／activation 進行中（auto-release flock 有人開住、holder pid 仲生、或者 activation-recovery
    啱啱有新 snapshot）→ 一樣都唔郁。
  * `--allow-llm-diagnosis`（預設關，只喺 --live）：detached worktree 入面開 `self_repair_triage.py` ——
    Hydrogen（唯讀）診斷、Python 核證據、分流去「Opus 收貨」或者「升 Opus 處理」；輸出 diagnosis markdown，唔會改檔、唔會跑命令。

永遠唔會：改 code、merge、部署、改 plist 內容、掂 secrets、刪資料。

    python3 self_repair.py              # dry-run（預設；寫 latest-dryrun.json）
    python3 self_repair.py --live       # 真係做（寫 latest.json）
    python3 self_repair.py --json
"""
from __future__ import annotations

import argparse
import fcntl
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

LAUNCHCTL_NOT_FOUND = 113  # "Could not find service"
DISK_MIN_GB = 10.0
UNLOADED_CONFIRM_SECONDS = 25 * 60
ACTIVATION_RECENT_SECONDS = 2 * 3600
DAILY_LIMIT = {"bootstrap": 2, "kickstart": 1, "cleaner": 1, "llm": 1}
STATE_KEEP_DAYS = 14

# 唯一可以自動 bootstrap／kickstart 嘅 job：StartInterval／密集日曆 tick，有自己 flock，晚咗開一次唔會雙重做嘢。
REPAIR_SAFE: dict[str, str] = {
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
KICKSTART_SAFE = REPAIR_SAFE  # 舊名

# 主排程 flock：有人開住 = 主 pipeline 跑緊，唔好 kickstart 搶資源（等下一輪）。
PRODUCTION_LOCKS = [
    HOME / "WongChoiData" / "Wong Choi Horse Race Analysis" / "AU_Racing" / ".au_daily_schedule.lock",
    SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock",
    SCHED / ".agents/skills/nba/nba_daily_auto/state/nba_daily_schedule.lock",
    SCHED / "tennis-wong-choi/data/logs/tennis_daily_schedule.lock",
]

# (holder 紀錄, 佢對應嘅 flock 檔)。只診斷，唔自動刪。
HOLDER_RECORDS = [
    (CONTROL / "auto-release.lock.json", CONTROL / "auto-release.lock"),
    (SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock.holder",
     SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock"),
]


class StateCorrupt(Exception):
    pass


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
        return {p.name[len(PREFIX):-len(".plist")]: p for p in sorted(LAUNCH_AGENTS.glob(f"{PREFIX}*.plist"))}

    def launchctl_print(self, label: str) -> tuple[str, dict | str | None]:
        """→ ("loaded", info) ／ ("missing", None) ／ ("error", 訊息)。只有 exit 113 先算冇 load。"""
        rc, out = self._run(["launchctl", "print", f"gui/{self.uid}/{PREFIX}{label}"])
        if rc == 0:
            return "loaded", parse_launchctl_print(out)
        if rc == LAUNCHCTL_NOT_FOUND:
            return "missing", None
        return "error", f"launchctl print rc={rc}: {out.strip()[-200:]}"

    def disabled_labels(self) -> set[str] | None:
        rc, out = self._run(["launchctl", "print-disabled", f"gui/{self.uid}"])
        if rc != 0:
            return None  # 唔知邊個 disable 咗 → 唔好 bootstrap
        return {m.group(1)[len(PREFIX):] for m in re.finditer(r'"([^"]+)"\s*=>\s*(?:disabled|true)', out)
                if m.group(1).startswith(PREFIX)}

    def paused_labels(self) -> set[str]:
        folder = CONTROL / "paused-launchd"
        return {p.name[len(PREFIX):].split(".plist")[0] for p in folder.glob(f"{PREFIX}*")} if folder.is_dir() else set()

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

    def newest_mtime(self, folder: Path) -> float | None:
        try:
            return max((p.stat().st_mtime for p in folder.iterdir()), default=None)
        except OSError:
            return None

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

    def spawn_llm(self, cmd: list[str], cwd: Path, out: Path) -> int:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh,
                                    stderr=subprocess.STDOUT, start_new_session=True)
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
    """冇檔 = 新開始；有檔但讀唔到／唔係 JSON object = StateCorrupt（唔准當空白）。"""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateCorrupt(f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise StateCorrupt(f"state 唔係 object：{type(data).__name__}")
    return data


def prune_state(state: dict, today: str) -> dict:
    cutoff = (datetime.fromisoformat(today) - timedelta(days=STATE_KEEP_DAYS)).date().isoformat()
    for key in ("actions", "notified"):
        state[key] = {d: v for d, v in (state.get(key) or {}).items() if d >= cutoff}
    state.setdefault("unloaded_seen", {})
    return state


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


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
                 allow_llm: bool = False, holder_records=None):
        self.sys = system or System()
        self.dry_run = dry_run
        self.now = time.time() if now is None else now
        self.today = datetime.fromtimestamp(self.now).date().isoformat()
        self.control = control
        self.state_path = control / "self_repair_state.json"
        self.freshness = freshness
        self.allow_llm = allow_llm
        self.holder_records = HOLDER_RECORDS if holder_records is None else holder_records
        self.report = Report(dry_run=dry_run, today=self.today)
        self.frozen_reason: str | None = None  # 有值 = 今輪一律唔動手
        try:
            self.state = prune_state(load_state(self.state_path), self.today)
            self.state_ok = True
        except StateCorrupt as exc:
            self.state = prune_state({}, self.today)
            self.state_ok = False
            self.frozen_reason = f"state 檔壞咗（{exc}）"
            self.report.unknown.append({"label": "self_repair.state", "reason":
                                        f"{self.state_path} 讀唔到：{exc}。今輪唔動手；人手睇完先刪／修個檔"})

    # ── 上限：動手之前先寫落碟 ──
    def _used(self, kind: str, label: str) -> int:
        return int(((self.state["actions"].get(self.today) or {}).get(f"{kind}:{label}")) or 0)

    def _allowed(self, kind: str, label: str) -> bool:
        return self._used(kind, label) < DAILY_LIMIT[kind]

    def _reserve(self, kind: str, label: str) -> None:
        day = self.state["actions"].setdefault(self.today, {})
        day[f"{kind}:{label}"] = int(day.get(f"{kind}:{label}") or 0) + 1
        atomic_write(self.state_path, self.state)

    def _save_state(self) -> None:
        if not self.dry_run and self.state_ok:
            atomic_write(self.state_path, self.state)

    def _act(self, kind: str, label: str, detail: str, fn) -> None:
        entry = {"kind": kind, "label": label, "detail": detail}
        if self.frozen_reason:
            entry["result"] = f"冇做：{self.frozen_reason}"
            self.report.skipped.append({"label": label, "reason": entry["result"], "would": kind})
            return
        if self.dry_run:
            entry["result"] = "dry-run（冇做）"
        else:
            self._reserve(kind, label)  # crash 喺下一行都唔會今日再做多次
            rc, out = fn()
            entry["result"] = "ok" if rc == 0 else f"失敗 rc={rc}: {out.strip()[-300:]}"
        self.report.actions.append(entry)

    def _ignored(self) -> set[str]:
        try:
            return set(json.loads((self.control / "self_repair_ignore.json").read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return set()

    # ── release／activation 互鎖 ──
    def check_release_activity(self) -> None:
        record, lock = self.control / "auto-release.lock.json", self.control / "auto-release.lock"
        reason = None
        if self.sys.file_in_use(lock):
            reason = "auto-release flock 有人開住（release 進行中）"
        elif record.exists():
            try:
                pid = int(json.loads(record.read_text(encoding="utf-8")).get("pid"))
                if self.sys.pid_alive(pid):
                    reason = f"auto-release holder pid {pid} 仲生"
            except (OSError, ValueError, TypeError, AttributeError):
                reason = "auto-release holder 紀錄讀唔到，當 release 進行中"
        if reason is None:
            newest = self.sys.newest_mtime(self.control / "activation-recovery")
            if newest is not None and self.now - newest < ACTIVATION_RECENT_SECONDS:
                reason = "activation-recovery 兩個鐘內有新 snapshot（cutover 可能未完）"
        if reason:
            self.frozen_reason = self.frozen_reason or reason
            self.report.notes.append(f"release 互鎖：{reason}，今輪唔動手")

    # ── 1 + 2：launchd job ──
    def check_jobs(self) -> None:
        plists = self.sys.installed_plists()
        disabled = self.sys.disabled_labels()
        paused = self.sys.paused_labels()
        ignored = self._ignored()
        busy = [str(p) for p in PRODUCTION_LOCKS if self.sys.file_in_use(p)]
        seen = self.state["unloaded_seen"]
        for label, plist in plists.items():
            if label in ignored:
                self.report.skipped.append({"label": label, "reason": "self_repair_ignore.json"})
                continue
            status, info = self.sys.launchctl_print(label)
            if status == "error":
                self._unknown(label, plist, None, None, f"launchctl 查唔到狀態：{info}")
                continue
            if status == "missing":
                self._unloaded(label, plist, disabled, paused, seen)
                continue
            seen.pop(label, None)
            if label not in job_freshness.REGISTRY:
                continue  # 冇可靠輸出可以核對（live／startup）→ 健康.sh 照睇退出碼
            fresh = self.freshness(label, self.now)
            state = (fresh.get("state") or "").lower()
            if fresh.get("pending_first_run"):
                self.report.skipped.append({"label": label, "reason": "新裝、未到第一次排程"})
                continue
            if fresh.get("fresh") and state not in job_freshness.FAILED_STATES:
                continue
            if fresh.get("fresh") and state == "blocked" and fresh.get("skipped_locked"):
                self.report.skipped.append({"label": label, "reason": "最新 run 撞鎖跳過，下一轉會做返"})
                continue
            if fresh.get("fresh"):
                self._unknown(label, plist, info, fresh, "最新 run 自己寫住失敗（新鮮但 failed）")
                continue
            if info["running"]:
                self.report.skipped.append({"label": label, "reason": "輸出過期但正在跑，等佢完"})
                continue
            if label not in REPAIR_SAFE:
                self._unknown(label, plist, info, fresh, "輸出過期；日曆 slot job 唔自動 kickstart")
                continue
            if busy:
                self.report.skipped.append({"label": label, "reason": f"主排程跑緊（{busy[0]}），下輪先 kickstart"})
                continue
            if not self._allowed("kickstart", label):
                self._unknown(label, plist, info, fresh, "今日已 kickstart 過一次仍然過期")
                continue
            self._act("kickstart", label,
                      f"輸出 {fresh.get('age_hours')} 鐘前（上限 {fresh.get('max_age_hours')}）；{REPAIR_SAFE[label]}",
                      lambda label=label: self.sys.kickstart(label))

    def _unloaded(self, label: str, plist: Path, disabled: set[str] | None, paused: set[str], seen: dict) -> None:
        if label in paused:
            self.report.skipped.append({"label": label, "reason": "paused-launchd 入面有，人手暫停"})
            return
        if disabled is None or label in disabled:
            why = "launchctl print-disabled 讀唔到" if disabled is None else "launchctl disable 咗（人手決定）"
            self.report.skipped.append({"label": label, "reason": f"{why}，唔 bootstrap"})
            return
        if label not in REPAIR_SAFE:
            self._unknown(label, plist, None, None, "plist 喺度但冇 load；日曆 slot job 唔自動 bootstrap")
            return
        first = seen.get(label)
        if first is None and not self.dry_run:
            seen[label] = self.now
            self._save_state()
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
        if not self.dry_run and not self.frozen_reason:
            seen.pop(label, None)
            self._save_state()

    # ── 鎖 holder 紀錄：只診斷 ──
    def check_holders(self) -> None:
        for record, lock in self.holder_records:
            if not record.exists():
                continue
            try:
                pid = int(json.loads(record.read_text(encoding="utf-8")).get("pid"))
            except (OSError, ValueError, TypeError, AttributeError):
                continue
            if self.sys.pid_alive(pid) or self.sys.file_in_use(lock):
                continue
            self.report.unknown.append({
                "label": f"holder:{record.name}",
                "reason": (f"holder 紀錄 pid {pid} 已死、{lock.name} 冇人開住。佢只係 advisory，唔會擋 flock；"
                           f"要清就人手：lsof -- '{lock}' 冇輸出，再 rm -- '{record}'")})

    # ── 磁碟 ──
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
        ran_before = self._used("cleaner", "compress") > 0
        for name, cmd in cleaners:
            if not self._allowed("cleaner", name):
                self.report.skipped.append({"label": name, "reason": "今日已跑過"})
                continue
            self._act("cleaner", name, f"碟淨 {free:.1f} GB < {DISK_MIN_GB:g}", lambda cmd=cmd: self.sys.run_cleaner(cmd))
        if ran_before:
            self.report.unknown.append({"label": "disk", "reason": f"碟淨 {free:.1f} GB；安全清理今日已跑過，要人手揀刪咩"})

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

    # ── 通知 + 可選 LLM（唯讀） ──
    def diagnosis_command(self, label: str, bundle: str, worktree: Path | None = None) -> list[str]:
        """第二層（Kelvin 2026-11-26）：Hydrogen 先診斷（唯讀，Gemini 停派退 Luna），Python 核證據，
        細修補＋高信心 → Opus 收貨；其他 → 升 Opus 處理。AI 唔改檔（`self_repair_triage.py`）。"""
        return [sys.executable, str(REPO / ".agents" / "scripts" / "self_repair_triage.py"), "--bundle", str(bundle),
                "--label", f"{PREFIX}{label}", "--worktree", str(worktree or self.worktree_for(label))]

    def worktree_for(self, label: str) -> Path:
        name = f"self-repair-{label.replace('.', '-')}-{self.today.replace('-', '')}"
        return MAIN_REPO / ".claude" / "worktrees" / name

    def notify(self) -> None:
        notified = self.state["notified"].setdefault(self.today, [])
        fresh = [u for u in self.report.unknown if u["label"] not in notified]
        if not fresh:
            return
        lines = [f"🛠️ 排程自動維修：{len(fresh)} 個問題唔識自己修"]
        lines.extend(f"• {u['label']}：{u['reason']}" for u in fresh)
        if self.report.actions:
            lines.append("已自動處理：" + "、".join(f"{a['kind']} {a['label']}（{a['result']}）" for a in self.report.actions))
        first = next((u for u in fresh if u.get("bundle")), None)
        if first:
            wt = self.worktree_for(first["label"])
            lines.append(f"診斷包：{Path(first['bundle']).parent}")
            if self.allow_llm:
                lines.append("Hydrogen 會先診斷（唯讀），結果另一條 Telegram；搞唔掂會講明要 Opus 處理。")
            else:
                lines.append("手動診斷：開 Claude Code，叫佢讀上面嘅診斷包。")
        text = "\n".join(lines)
        if self.dry_run:
            self.report.notes.append("dry-run：唔發 Telegram。會發：\n" + text)
            return
        result = self.sys.send_telegram(text)
        self.report.notes.append(f"Telegram primary：{result.get('status') or result.get('ok')}")
        notified.extend(u["label"] for u in fresh)
        self._save_state()
        if self.allow_llm and first and self.state_ok:
            self._launch_llm(first)

    def _launch_llm(self, item: dict) -> None:
        if not self._allowed("llm", "all"):
            self.report.notes.append("LLM 診斷今日已開過一次")
            return
        wt = self.worktree_for(item["label"])
        if not wt.exists():
            self.sys._run(["git", "-C", str(MAIN_REPO), "fetch", "origin"], timeout=120)
            rc, out = self.sys._run(["git", "-C", str(MAIN_REPO), "worktree", "add", "--detach", str(wt), "origin/main"])
            if rc != 0:
                self.report.notes.append(f"開 worktree 失敗：{out.strip()[-200:]}")
                return
        self._reserve("llm", "all")
        out = Path(item["bundle"]).with_suffix(".diagnosis.md")
        pid = self.sys.spawn_llm(self.diagnosis_command(item["label"], item["bundle"], wt), wt, out.with_suffix(".log"))
        self.report.notes.append(f"已開 Hydrogen 診斷 pid {pid} → {out}（detached worktree {wt}）")

    # ── 主流程 ──
    def run(self) -> Report:
        self.control.mkdir(parents=True, exist_ok=True)
        with (self.control / "self_repair.lock").open("a") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.report.notes.append("另一個 self_repair 跑緊，今輪唔做")
                return self.report
            for step in (self.check_release_activity, self.check_jobs, self.check_holders, self.check_disk):
                try:
                    step()
                except Exception as exc:  # noqa: BLE001 — 一步壞唔好令其他步唔做
                    self.report.unknown.append({"label": f"self_repair.{step.__name__}",
                                                "reason": f"{type(exc).__name__}: {exc}"})
            self.notify()
            self._save_state()
            name = "latest-dryrun.json" if self.dry_run else "latest.json"
            atomic_write(self.control / "self_repair" / name, self.report.as_dict())
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
                    help="live 模式下有未知問題就自動開唯讀 claude -p 診斷（detached worktree，只出 markdown）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    report = SelfRepair(dry_run=not a.live, allow_llm=a.allow_llm_diagnosis and a.live).run()
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=1) if a.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
