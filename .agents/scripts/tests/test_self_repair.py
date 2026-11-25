"""self_repair：fake launchctl／freshness／state，唔會真係叫 launchctl。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import self_repair as sr  # noqa: E402

NOW = 1_795_000_000.0  # 固定時間


class FakeSystem(sr.System):
    def __init__(self, tmp: Path, plists: dict[str, dict | None], *, disabled=(), busy=(), free=50.0,
                 alive=(), mounted=True):
        self.tmp = tmp
        self.plists = {}
        for label in plists:
            p = tmp / f"{sr.PREFIX}{label}.plist"
            p.write_bytes(b"<?xml version='1.0'?><plist version='1.0'><dict></dict></plist>")
            self.plists[label] = p
        self.info = plists
        self.disabled = set(disabled)
        self.busy = {str(b) for b in busy}
        self.free = free
        self.alive = set(alive)
        self.mounted = mounted
        self.calls: list[tuple] = []
        self.telegrams: list[str] = []

    def _run(self, cmd, timeout=30):
        self.calls.append(("run", tuple(cmd)))
        return 0, ""

    def installed_plists(self):
        return dict(self.plists)

    def launchctl_print(self, label):
        return self.info[label]

    def disabled_labels(self):
        return self.disabled

    def bootstrap(self, plist):
        self.calls.append(("bootstrap", plist.name))
        return 0, ""

    def kickstart(self, label):
        self.calls.append(("kickstart", label))
        return 0, ""

    def file_in_use(self, path):
        return str(path) in self.busy

    def pid_alive(self, pid):
        return pid in self.alive

    def remove(self, path):
        self.calls.append(("remove", str(path)))
        path.unlink()

    def disk_free_gb(self):
        return self.free

    def is_mounted(self, path):
        return self.mounted

    def run_cleaner(self, cmd):
        self.calls.append(("cleaner", Path(cmd[1]).name))
        return 0, ""

    def tail(self, path, lines=80):
        return ""

    def send_telegram(self, text):
        self.telegrams.append(text)
        return {"status": "sent"}

    def spawn_llm(self, cmd, cwd, log):
        self.calls.append(("llm", cmd[0]))
        return 4242


def loaded(running=False):
    return {"loaded": True, "state": "running" if running else "not running",
            "pid": 99 if running else None, "last_exit": 0, "running": running}


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

    def make(self, system, *, dry_run=False, now=NOW, allow_llm=False):
        return sr.SelfRepair(system, dry_run=dry_run, now=now, control=self.control,
                             freshness=self.freshness, allow_llm=allow_llm)

    def stale(self, label):
        self.fresh[label] = {"fresh": False, "age_hours": 9.0, "max_age_hours": 1, "state": None}

    # 1. bootstrap
    def test_unloaded_job_bootstraps_only_on_second_confirming_run(self):
        fake = FakeSystem(self.tmp, {"tennis-wong-choi.settle": None})
        self.make(fake).run()
        self.assertNotIn(("bootstrap", f"{sr.PREFIX}tennis-wong-choi.settle.plist"), fake.calls)
        self.make(fake, now=NOW + 10 * 60).run()  # 未夠 25 分鐘
        self.assertFalse([c for c in fake.calls if c[0] == "bootstrap"])
        self.make(fake, now=NOW + 30 * 60).run()
        self.assertEqual([c for c in fake.calls if c[0] == "bootstrap"],
                         [("bootstrap", f"{sr.PREFIX}tennis-wong-choi.settle.plist")])

    def test_disabled_or_ignored_job_is_never_bootstrapped(self):
        fake = FakeSystem(self.tmp, {"a.job": None, "b.job": None}, disabled={"a.job"})
        (self.control / "self_repair_ignore.json").write_text(json.dumps(["b.job"]))
        for i in range(3):
            self.make(fake, now=NOW + i * 3600).run()
        self.assertFalse([c for c in fake.calls if c[0] == "bootstrap"])

    def test_dry_run_changes_nothing_and_writes_no_state(self):
        fake = FakeSystem(self.tmp, {"tennis-wong-choi.settle": None, "au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")
        report = self.make(fake, dry_run=True).run()
        self.assertFalse([c for c in fake.calls if c[0] in {"bootstrap", "kickstart", "run"}])
        self.assertEqual({a["kind"] for a in report.actions}, {"bootstrap", "kickstart"})
        self.assertFalse((self.control / "self_repair_state.json").exists())
        self.assertEqual(fake.telegrams, [])

    # 2. kickstart
    def test_stale_safe_job_kickstarts_once_per_day_then_escalates(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded()})
        self.stale("au-wong-choi.bot")
        self.make(fake).run()
        report = self.make(fake, now=NOW + 1800).run()
        self.assertEqual([c for c in fake.calls if c[0] == "kickstart"], [("kickstart", "au-wong-choi.bot")])
        self.assertEqual([u["label"] for u in report.unknown], ["au-wong-choi.bot"])
        self.assertEqual(len(fake.telegrams), 1)

    def test_calendar_slot_job_is_diagnosed_not_kickstarted(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.morning": loaded()})
        self.stale("au-wong-choi.morning")
        report = self.make(fake).run()
        self.assertFalse([c for c in fake.calls if c[0] == "kickstart"])
        bundle = Path(report.unknown[0]["bundle"])
        self.assertTrue(bundle.exists())
        self.assertEqual(json.loads(bundle.read_text())["label"], "au-wong-choi.morning")
        self.assertIn("claude -p", fake.telegrams[0])

    def test_running_job_or_busy_production_lock_waits(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.bot": loaded(running=True),
                                     "tennis-wong-choi.settle": loaded()}, busy={self.tmp / "prod.lock"})
        self.stale("au-wong-choi.bot")
        self.stale("tennis-wong-choi.settle")
        report = self.make(fake).run()
        self.assertFalse([c for c in fake.calls if c[0] == "kickstart"])
        self.assertEqual(len(report.skipped), 2)
        self.assertEqual(report.unknown, [])

    def test_fresh_but_failed_run_is_unknown(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.evening": loaded()})
        self.fresh["au-wong-choi.evening"] = {"fresh": True, "state": "partial"}
        report = self.make(fake).run()
        self.assertEqual(report.unknown[0]["label"], "au-wong-choi.evening")
        self.make(fake, now=NOW + 1800).run()
        self.assertEqual(len(fake.telegrams), 1)  # 同一日同一個 job 只發一次

    # 3. holder 紀錄
    def test_dead_holder_record_removed_only_when_lock_unused(self):
        rec_dead, rec_busy, rec_alive = (self.tmp / n for n in ("a.json", "b.json", "c.json"))
        for rec, pid in ((rec_dead, 111), (rec_busy, 222), (rec_alive, 333)):
            rec.write_text(json.dumps({"pid": pid}))
        fake = FakeSystem(self.tmp, {}, alive={333}, busy={self.tmp / "b.lock"})
        repair = self.make(fake)
        repair.check_holders([(rec_dead, self.tmp / "a.lock"), (rec_busy, self.tmp / "b.lock"),
                              (rec_alive, self.tmp / "c.lock")])
        self.assertFalse(rec_dead.exists())
        self.assertTrue(rec_busy.exists())
        self.assertTrue(rec_alive.exists())

    # 4. 磁碟
    def test_low_disk_runs_safe_cleaners_and_skips_offload_without_disk(self):
        fake = FakeSystem(self.tmp, {}, free=6.0, mounted=False)
        self.make(fake).run()
        self.assertEqual([c for c in fake.calls if c[0] == "cleaner"], [("cleaner", "compress_data_root.py")])
        fake2 = FakeSystem(self.tmp, {}, free=6.0, mounted=True)
        self.control = self.tmp / "control2"
        self.control.mkdir()
        self.make(fake2).run()
        self.assertEqual([c[1] for c in fake2.calls if c[0] == "cleaner"],
                         ["compress_data_root.py", "offload_prediction_snapshots.py"])

    # LLM
    def test_llm_only_with_flag_and_once_per_day(self):
        fake = FakeSystem(self.tmp, {"au-wong-choi.morning": loaded()})
        self.stale("au-wong-choi.morning")
        self.make(fake).run()
        self.assertFalse([c for c in fake.calls if c[0] == "llm"])
        self.control = self.tmp / "control3"
        self.control.mkdir()
        self.make(fake, allow_llm=True).run()
        self.assertEqual([c for c in fake.calls if c[0] == "llm"], [("llm", "claude")])
        cmd = sr.SelfRepair(fake, control=self.control).diagnosis_command("x", "/b.json")
        self.assertIn("Bash(git push:*)", cmd[cmd.index("--disallowedTools") + 1])

    def test_parse_launchctl_print_uses_top_level_state(self):
        text = "gui/501/x = {\n\tstate = not running\n\tlast exit code = 75: EX_TEMPFAIL\n" \
               "\tendpoints = {\n\t\tstate = active\n\t}\n}"
        info = sr.parse_launchctl_print(text)
        self.assertEqual((info["state"], info["last_exit"], info["running"]), ("not running", 75, False))

    def test_plist_template_renders_dry_run_by_default_and_live_on_request(self):
        import plistlib
        tpl = (Path(__file__).resolve().parents[2] / "skills/central_wong_choi/launchd"
               / "com.antigravity.central-wong-choi.self-repair.plist.template").read_text()
        for mode, extra in (("", []), ("<string>--live</string>", ["--live"])):
            body = tpl.replace("__SCRIPT_DIR__", "/s").replace("__PROJECT_ROOT__", "/p").replace("__MODE_ARGS__", mode)
            spec = plistlib.loads(body.encode())
            self.assertEqual(spec["ProgramArguments"], ["/bin/zsh", "/s/run_self_repair.sh", *extra])
            self.assertEqual(spec["StartInterval"], 1800)

    def test_self_repair_output_is_registered_for_freshness(self):
        self.assertIn("central-wong-choi.self-repair", sr.job_freshness.REGISTRY)


if __name__ == "__main__":
    unittest.main()
