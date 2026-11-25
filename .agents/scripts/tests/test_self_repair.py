"""self_repair：fake launchctl／freshness／state，唔會真係叫 launchctl。"""
from __future__ import annotations

import fcntl
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_freshness  # noqa: E402
import self_repair as sr  # noqa: E402

NOW = 1_795_000_000.0  # 固定時間
TICK = "tennis-wong-choi.settle"      # REPAIR_SAFE
SLOT = "au-wong-choi.morning"         # 日曆 slot job


class FakeSystem(sr.System):
    def __init__(self, tmp: Path, plists: dict, *, disabled=(), paused=(), busy=(), free=50.0,
                 alive=(), mounted=True, recovery_mtime=None):
        self.plists = {}
        for label in plists:
            p = tmp / f"{sr.PREFIX}{label}.plist"
            p.write_bytes(plistlib.dumps({"Label": sr.PREFIX + label}))
            self.plists[label] = p
        self.info = plists  # label → ("loaded", info) | ("missing", None) | ("error", msg)
        self.disabled = None if disabled is None else set(disabled)
        self.paused = set(paused)
        self.busy = {str(b) for b in busy}
        self.free = free
        self.alive = set(alive)
        self.mounted = mounted
        self.recovery_mtime = recovery_mtime
        self.calls: list[tuple] = []
        self.telegrams: list[str] = []
        self.on_act = None

    def _run(self, cmd, timeout=30):
        self.calls.append(("run", tuple(cmd)))
        return 0, ""

    def installed_plists(self):
        return dict(self.plists)

    def launchctl_print(self, label):
        return self.info[label]

    def disabled_labels(self):
        return self.disabled

    def paused_labels(self):
        return self.paused

    def _record(self, call):
        self.calls.append(call)
        if self.on_act:
            self.on_act(call)
        return 0, ""

    def bootstrap(self, plist):
        return self._record(("bootstrap", plist.name))

    def kickstart(self, label):
        return self._record(("kickstart", label))

    def file_in_use(self, path):
        return str(path) in self.busy

    def pid_alive(self, pid):
        return pid in self.alive

    def newest_mtime(self, folder):
        return self.recovery_mtime

    def disk_free_gb(self):
        return self.free

    def is_mounted(self, path):
        return self.mounted

    def run_cleaner(self, cmd):
        return self._record(("cleaner", Path(cmd[1]).name))

    def tail(self, path, lines=80):
        return ""

    def send_telegram(self, text):
        self.telegrams.append(text)
        return {"status": "sent"}

    def spawn_llm(self, cmd, cwd, out):
        self.calls.append(("llm", tuple(cmd)))
        return 4242


def loaded(running=False):
    return ("loaded", {"loaded": True, "state": "running" if running else "not running",
                       "pid": 99 if running else None, "last_exit": 0, "running": running})


MISSING = ("missing", None)


class SelfRepairTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.control = self.tmp / "control"
        self.control.mkdir()
        self._locks = sr.PRODUCTION_LOCKS
        sr.PRODUCTION_LOCKS = [self.tmp / "prod.lock"]
        self.fresh = {}

    def tearDown(self):
        sr.PRODUCTION_LOCKS = self._locks
        self._tmp.cleanup()

    def freshness(self, label, now):
        return self.fresh.get(label, {"fresh": True, "state": "succeeded"})

    def make(self, system, *, dry_run=False, now=NOW, allow_llm=False, holders=()):
        return sr.SelfRepair(system, dry_run=dry_run, now=now, control=self.control,
                             freshness=self.freshness, allow_llm=allow_llm, holder_records=list(holders))

    def stale(self, label):
        self.fresh[label] = {"fresh": False, "age_hours": 9.0, "max_age_hours": 1, "state": None}

    def kinds(self, fake, kind):
        return [c for c in fake.calls if c[0] == kind]

    # ── 1. bootstrap ──
    def test_unloaded_tick_job_bootstraps_only_on_second_confirming_run(self):
        fake = FakeSystem(self.tmp, {TICK: MISSING})
        self.make(fake).run()
        self.make(fake, now=NOW + 10 * 60).run()  # 未夠 25 分鐘
        self.assertFalse(self.kinds(fake, "bootstrap"))
        self.make(fake, now=NOW + 30 * 60).run()
        self.assertEqual(self.kinds(fake, "bootstrap"), [("bootstrap", f"{sr.PREFIX}{TICK}.plist")])

    def test_unloaded_calendar_slot_job_is_never_bootstrapped(self):
        fake = FakeSystem(self.tmp, {SLOT: MISSING})
        for i in range(3):
            report = self.make(fake, now=NOW + i * 3600).run()
        self.assertFalse(self.kinds(fake, "bootstrap"))
        self.assertEqual(report.unknown[0]["label"], SLOT)

    def test_launchctl_error_is_not_treated_as_unloaded(self):
        fake = FakeSystem(self.tmp, {TICK: ("error", "launchctl print rc=5: boom")})
        for i in range(3):
            report = self.make(fake, now=NOW + i * 3600).run()
        self.assertFalse(self.kinds(fake, "bootstrap"))
        self.assertIn("launchctl 查唔到狀態", report.unknown[0]["reason"])

    def test_system_maps_only_exit_113_to_missing(self):
        class Probe(sr.System):
            def __init__(self, rc):
                self.rc = rc

            def _run(self, cmd, timeout=30):
                return self.rc, "Could not find service" if self.rc == 113 else "Operation not permitted"
        self.assertEqual(Probe(113).launchctl_print("x"), ("missing", None))
        self.assertEqual(Probe(1).launchctl_print("x")[0], "error")

    def test_disabled_paused_ignored_or_unknown_disabled_set_never_bootstrap(self):
        labels = ["tennis-wong-choi.settle", "tennis-wong-choi.preclose", "tennis-wong-choi.betfair"]
        fake = FakeSystem(self.tmp, {lab: MISSING for lab in labels},
                          disabled={labels[0]}, paused={labels[1]})
        (self.control / "self_repair_ignore.json").write_text(json.dumps([labels[2]]))
        for i in range(3):
            self.make(fake, now=NOW + i * 3600).run()
        self.assertFalse(self.kinds(fake, "bootstrap"))
        fake2 = FakeSystem(self.tmp, {TICK: MISSING}, disabled=None)  # print-disabled 讀唔到
        for i in range(3):
            self.make(fake2, now=NOW + i * 3600).run()
        self.assertFalse(self.kinds(fake2, "bootstrap"))

    # ── release 互鎖 ──
    def test_release_in_progress_blocks_every_action(self):
        cases = [
            dict(busy={self.control / "auto-release.lock"}),
            dict(alive={777}),
            dict(recovery_mtime=NOW - 600),
        ]
        for kwargs in cases:
            (self.control / "auto-release.lock.json").write_text(json.dumps({"pid": 777}))
            fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()}, free=5.0, **kwargs)
            self.stale("au-wong-choi.bot")
            report = self.make(fake).run()
            self.assertFalse(self.kinds(fake, "kickstart") + self.kinds(fake, "cleaner"), kwargs)
            self.assertTrue(any("release 互鎖" in n for n in report.notes), kwargs)

    def test_old_activation_snapshot_and_dead_holder_do_not_block(self):
        (self.control / "auto-release.lock.json").write_text(json.dumps({"pid": 777}))
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()}, recovery_mtime=NOW - 86400)
        self.stale("au-wong-choi.bot")
        self.make(fake).run()
        self.assertEqual(self.kinds(fake, "kickstart"), [("kickstart", "au-wong-choi.bot")])

    # ── 2. kickstart ──
    def test_stale_safe_job_kickstarts_once_per_day_then_escalates(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")
        self.make(fake).run()
        report = self.make(fake, now=NOW + 1800).run()
        self.assertEqual(self.kinds(fake, "kickstart"), [("kickstart", "au-wong-choi.bot")])
        self.assertEqual([u["label"] for u in report.unknown], ["au-wong-choi.bot"])
        self.assertEqual(len(fake.telegrams), 1)

    def test_calendar_slot_job_is_diagnosed_not_kickstarted(self):
        fake = FakeSystem(self.tmp, {SLOT: loaded()})
        self.stale(SLOT)
        report = self.make(fake).run()
        self.assertFalse(self.kinds(fake, "kickstart"))
        bundle = Path(report.unknown[0]["bundle"])
        self.assertEqual(json.loads(bundle.read_text())["label"], SLOT)
        self.assertIn("--permission-mode plan", fake.telegrams[0])

    def test_running_job_or_busy_production_lock_waits(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded(running=True), TICK: loaded()},
                          busy={self.tmp / "prod.lock"})
        self.stale("au-wong-choi.bot")
        self.stale(TICK)
        report = self.make(fake).run()
        self.assertFalse(self.kinds(fake, "kickstart"))
        self.assertEqual(len(report.skipped), 2)
        self.assertEqual(report.unknown, [])

    def test_fresh_but_failed_run_is_unknown_and_alerts_once_a_day(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.evening": loaded()})
        self.fresh["au-wong-choi.evening"] = {"fresh": True, "state": "partial"}
        report = self.make(fake).run()
        self.assertEqual(report.unknown[0]["label"], "au-wong-choi.evening")
        self.make(fake, now=NOW + 1800).run()
        self.assertEqual(len(fake.telegrams), 1)

    # ── 3. 鎖、上限、state ──
    def test_quota_is_on_disk_before_the_action_runs(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")
        seen = {}

        def check(call):
            state = json.loads((self.control / "self_repair_state.json").read_text())
            seen["count"] = state["actions"][sr.datetime.fromtimestamp(NOW).date().isoformat()]
        fake.on_act = check
        self.make(fake).run()
        self.assertEqual(seen["count"], {"kickstart:au-wong-choi.bot": 1})

    def test_crash_mid_action_does_not_repeat_it(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")

        def boom(call):
            raise SystemExit("killed")
        fake.on_act = boom
        with self.assertRaises(SystemExit):
            self.make(fake).run()
        fake.on_act = None
        self.make(fake, now=NOW + 1800).run()
        self.assertEqual(len(self.kinds(fake, "kickstart")), 1)

    def test_corrupt_state_refuses_to_act_and_keeps_the_file(self):
        bad = self.control / "self_repair_state.json"
        bad.write_text("{not json")
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()}, free=5.0)
        self.stale("au-wong-choi.bot")
        report = self.make(fake).run()
        self.assertFalse(self.kinds(fake, "kickstart") + self.kinds(fake, "cleaner"))
        self.assertEqual(bad.read_text(), "{not json")
        self.assertIn("self_repair.state", [u["label"] for u in report.unknown])
        self.assertEqual(len(fake.telegrams), 1)

    def test_second_instance_exits_while_first_holds_the_lock(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")
        with (self.control / "self_repair.lock").open("a") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            report = self.make(fake).run()
        self.assertFalse(self.kinds(fake, "kickstart"))
        self.assertIn("另一個 self_repair 跑緊，今輪唔做", report.notes)

    def test_dead_holder_record_is_only_diagnosed_never_deleted(self):
        rec = self.tmp / "a.json"
        rec.write_text(json.dumps({"pid": 111}))
        fake = FakeSystem(self.tmp, {})
        report = self.make(fake, holders=[(rec, self.tmp / "a.lock")]).run()
        self.assertTrue(rec.exists())
        reason = next(u["reason"] for u in report.unknown if u["label"] == "holder:a.json")
        self.assertIn(f"rm -- '{rec}'", reason)

    # ── 4. 磁碟 ──
    def test_low_disk_runs_safe_cleaners_and_skips_offload_without_disk(self):
        fake = FakeSystem(self.tmp, {}, free=6.0, mounted=False)
        self.make(fake).run()
        self.assertEqual(self.kinds(fake, "cleaner"), [("cleaner", "compress_data_root.py")])
        self.control = self.tmp / "control2"
        self.control.mkdir()
        fake2 = FakeSystem(self.tmp, {}, free=6.0, mounted=True)
        self.make(fake2).run()
        self.assertEqual([c[1] for c in self.kinds(fake2, "cleaner")],
                         ["compress_data_root.py", "offload_prediction_snapshots.py"])

    # ── dry-run ──
    def test_dry_run_changes_nothing_and_writes_dryrun_latest(self):
        fake = FakeSystem(self.tmp, {TICK: MISSING, "au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")
        report = self.make(fake, dry_run=True).run()
        self.assertFalse([c for c in fake.calls if c[0] in {"bootstrap", "kickstart", "run"}])
        self.assertEqual({a["kind"] for a in report.actions}, {"bootstrap", "kickstart"})
        self.assertFalse((self.control / "self_repair_state.json").exists())
        self.assertTrue((self.control / "self_repair" / "latest-dryrun.json").exists())
        self.assertFalse((self.control / "self_repair" / "latest.json").exists())
        self.assertEqual(fake.telegrams, [])

    # ── LLM ──
    def test_llm_is_opt_in_read_only_and_once_per_day(self):
        fake = FakeSystem(self.tmp, {SLOT: loaded()})
        self.stale(SLOT)
        self.make(fake).run()
        self.assertFalse(self.kinds(fake, "llm"))
        self.control = self.tmp / "control3"
        self.control.mkdir()
        self.make(fake, allow_llm=True).run()
        self.make(fake, allow_llm=True, now=NOW + 1800).run()
        llm = self.kinds(fake, "llm")
        self.assertEqual(len(llm), 1)
        cmd = list(llm[0][1])
        allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
        self.assertEqual(allowed, ["Read", "Grep", "Glob"])
        for tool in ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"):
            self.assertIn(tool, cmd[cmd.index("--disallowedTools") + 1:])
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "plan")
        worktree_cmds = [c[1] for c in fake.calls if c[0] == "run" and "worktree" in c[1]]
        self.assertIn("--detach", worktree_cmds[0])

    # ── 其他 ──
    def test_parse_launchctl_print_uses_top_level_state(self):
        text = "gui/501/x = {\n\tstate = not running\n\tlast exit code = 75: EX_TEMPFAIL\n" \
               "\tendpoints = {\n\t\tstate = active\n\t}\n}"
        info = sr.parse_launchctl_print(text)
        self.assertEqual((info["state"], info["last_exit"], info["running"]), ("not running", 75, False))

    def test_plist_template_renders_dry_run_by_default_and_live_on_request(self):
        tpl = (Path(__file__).resolve().parents[2] / "skills/central_wong_choi/launchd"
               / "com.antigravity.central-wong-choi.self-repair.plist.template").read_text()
        for mode, extra in (("", []), ("<string>--live</string>", ["--live"])):
            body = tpl.replace("__SCRIPT_DIR__", "/s").replace("__PROJECT_ROOT__", "/p").replace("__MODE_ARGS__", mode)
            spec = plistlib.loads(body.encode())
            self.assertEqual(spec["ProgramArguments"], ["/bin/zsh", "/s/run_self_repair.sh", *extra])
            self.assertEqual(spec["StartInterval"], 1800)

    def test_pending_first_run_is_skipped_not_unknown(self):
        label = "central-wong-choi.astra-audit"
        fake = FakeSystem(self.tmp, {label: loaded()})
        self.fresh[label] = {"fresh": False, "age_hours": None, "max_age_hours": 172,
                             "pending_first_run": True, "state": None}
        report = self.make(fake).run()
        self.assertFalse(report.unknown)
        self.assertFalse(self.kinds(fake, "kickstart"))
        self.assertIn("新裝、未到第一次排程", [s["reason"] for s in report.skipped if s["label"] == label])
        self.assertFalse(list((self.control).rglob("*bundle*")))

    def test_skipped_locked_is_skipped_not_unknown(self):
        label = "nba-wong-choi.warmup"
        fake = FakeSystem(self.tmp, {label: loaded()})
        self.fresh[label] = {"fresh": True, "state": "blocked", "skipped_locked": True}
        report = self.make(fake).run()
        self.assertFalse(report.unknown)
        self.fresh[label] = {"fresh": True, "state": "blocked", "skipped_locked": False}
        self.assertEqual(self.make(fake).run().unknown[0]["label"], label)

    def test_freshness_registry_accepts_live_or_dryrun_latest(self):
        patterns = job_freshness.REGISTRY["central-wong-choi.self-repair"][0]
        self.assertEqual(sorted(Path(p).name for p in patterns), ["latest-dryrun.json", "latest.json"])


if __name__ == "__main__":
    unittest.main()
