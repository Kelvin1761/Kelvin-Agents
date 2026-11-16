"""手機逐駒分段 parser／抓取守則，同 Lpos forward（EXP-20261116-20）凍結規格。"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import au_lpos_forward as fwd  # noqa: E402
import au_mobile_sectionals as ams  # noqa: E402


def _cell(label, secs, kmh):
    return (f'<div class="sectionals__speed-label">{label}</div> <div class="sectionals__speed-data">{secs}</div> '
            f'<div class="sectionals__speed-data">{kmh}</div>')


PAGE = ("<html>" + "x" * 100 + ' <div data-component="mobile-sectional-times"> '
        '<a class="sectionals__runner"> <div class="sectionals__runner-number">3</div> '
        '<div class="sectionals__runner-info">Fast &amp; Free (5)</div> '
        '<div class="sectionals__event-row"> <span class="sectionals__finishing-num">2</span> '
        '<span class="sectionals__finishing-starters"> of 10</span> '
        '<div class="sectionals__event-name">Moe</div> <div class="sectionals__track-conditions" x="y">Good 4</div> '
        '<div class="sectionals__event-info-row"> 03/11/2026, 1200m, 71.20s</div> '
        + _cell("400m", "11.5", "62.61") + " " + _cell("200m", "11.6", "62.07") + " " + _cell("Fnsh", "12.1", "59.50")
        + " " + _cell("1000m", "-", "-") +
        ' </div> </a> <script id="template-mobile-sectional-times"> {{x}} </script></html>')


def test_parse_reads_runner_run_and_cells():
    runners = ams.parse(PAGE)
    assert len(runners) == 1
    r = runners[0]
    assert (r["number"], r["name"], r["barrier"]) == (3, "Fast & Free", 5)
    run = r["runs"][0]
    assert run["date"] == "2026-11-03" and run["distance"] == 1200 and run["time"] == 71.20
    assert run["kmh"]["Fnsh"] == 59.50 and run["split"]["1000m"] is None
    expected = 200 * 3.6 / 62.61 + 200 * 3.6 / 62.07 + 200 * 3.6 / 59.50
    assert abs(ams.own_l600(run) - expected) < 1e-9


def test_own_l600_needs_all_three_cells():
    run = {"kmh": {"400m": 60.0, "200m": None, "Fnsh": 60.0}}
    assert ams.own_l600(run) is None


class _Resp:
    def __init__(self, code, body=b"", payload=None):
        self.status_code, self.content, self._payload = code, body, payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses, self.urls = list(responses), []

    def get(self, url, timeout=0):
        self.urls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


ALLR = {"dates": [{"sections": [{"raceType": "horse", "meetings": [
    {"name": "Moe", "regionName": "Australia", "events": [{"id": 11, "raceNumber": 1}, {"id": 12, "raceNumber": 2}]},
    {"name": "Ascot", "regionName": "UK", "events": [{"id": 99, "raceNumber": 1}]}]}]}]}
GOOD = PAGE.encode() + b" " * ams.MIN_BYTES
EARLY = lambda: datetime(2026, 11, 20, 4, 30)  # noqa: E731


def test_fetch_stops_on_first_bad_page_without_retry(tmp_path):
    sleeps = []
    s = _Session([_Resp(200, payload=ALLR), _Resp(200, GOOD), _Resp(403, b"no")])
    st = ams.fetch(days_back=1, max_pages=50, today=date(2026, 11, 20), session=s, sleep=sleeps.append,
                   now=EARLY, root=tmp_path, log=lambda *_: None)
    assert st["state"] == "stopped" and "403" in st["stop_reason"] and st["fetched"] == 1
    assert len(s.urls) == 3 and all(x >= 25 for x in sleeps) and len(sleeps) == 2
    saved = json.loads(gzip.decompress((tmp_path / "AU_Mobile_Sectionals" / "2026-11-19" / "11.json.gz").read_bytes()))
    assert saved["venue"] == "Moe" and saved["race"] == 1 and saved["runners"][0]["name"] == "Fast & Free"


def test_fetch_stops_on_timeout_and_short_body(tmp_path):
    s = _Session([_Resp(200, payload=ALLR), TimeoutError("t")])
    st = ams.fetch(days_back=1, max_pages=50, today=date(2026, 11, 20), session=s, sleep=lambda _x: None,
                   now=EARLY, root=tmp_path, log=lambda *_: None)
    assert st["state"] == "stopped" and "TimeoutError" in st["stop_reason"]
    s = _Session([_Resp(200, payload=ALLR), _Resp(200, b"tiny")])
    st = ams.fetch(days_back=1, max_pages=50, today=date(2026, 11, 20), session=s, sleep=lambda _x: None,
                   now=EARLY, root=tmp_path, log=lambda *_: None)
    assert st["state"] == "stopped" and st["fetched"] == 0


def test_fetch_refuses_outside_window_and_respects_cap_and_existing(tmp_path):
    s = _Session([])
    st = ams.fetch(days_back=1, max_pages=50, today=date(2026, 11, 20), session=s, sleep=lambda _x: None,
                   now=lambda: datetime(2026, 11, 20, 22, 30), root=tmp_path)
    assert st["state"] == "outside_window" and s.urls == []
    day = tmp_path / "AU_Mobile_Sectionals" / "2026-11-19"
    day.mkdir(parents=True)
    (day / "11.json.gz").write_bytes(gzip.compress(b"{}"))
    s = _Session([_Resp(200, payload=ALLR), _Resp(200, GOOD)])
    st = ams.fetch(days_back=1, max_pages=1, today=date(2026, 11, 20), session=s, sleep=lambda _x: None,
                   now=EARLY, root=tmp_path, log=lambda *_: None)
    assert st["skipped_existing"] == 1 and st["fetched"] == 1 and st["state"] == "ok"


def test_fetch_never_goes_before_forward_start(tmp_path):
    s = _Session([])
    st = ams.fetch(days_back=8, max_pages=50, today=date(2026, 11, 17), session=s, sleep=lambda _x: None,
                   now=EARLY, root=tmp_path)
    assert s.urls == [] and st["fetched"] == 0


def test_lpos_spec_is_frozen():
    assert fwd.EXPERIMENT_ID == "EXP-20261116-20" and fwd.WEIGHT == 0.10 and fwd.TARGET_RACES == 2500
    assert fwd.START_DATE == "2026-11-17" and fwd.LAST_N == 4
    assert (fwd.LPOS_A, fwd.LPOS_B) == (-1.1008497873571432, -0.10976351609298357)


def test_run_lpos_formula_and_avg4_uses_only_prior_runs():
    run = {"date": "2026-11-01", "kmh": {"400m": 60.0, "200m": 60.0, "Fnsh": 60.0}}  # 本駒 L600 = 36.0
    fg = {"race_l600": 35.5, "pos800": 3, "starters": 9}
    expected = -(36.0 - 35.5) - (fwd.LPOS_A + fwd.LPOS_B * (2 / 8))
    assert abs(fwd.run_lpos(run, fg) - expected) < 1e-9
    assert fwd.run_lpos(run, {"race_l600": None, "pos800": 3, "starters": 9}) is None
    runs = [dict(run, date=d) for d in ("2026-11-20", "2026-11-01", "2026-10-01", "2026-09-01", "2026-08-01", "2026-07-01")]
    fgs = {d: fg for d in ("2026-11-20", "2026-11-01", "2026-10-01", "2026-09-01", "2026-08-01", "2026-07-01")}
    assert abs(fwd.lpos_avg4(runs, fgs, "2026-11-20") - expected) < 1e-9   # 同日嗰仗唔計，最多 4 仗


def test_candidate_is_baseline_when_no_feature_and_moves_by_weight_sd():
    bases = [70.0, 65.0, 60.0, 55.0]
    assert fwd.candidate_scores(bases, [None] * 4) == bases
    cand = fwd.candidate_scores(bases, [1.0, None, None, -1.0])
    sd = statistics.pstdev(bases)
    assert abs(cand[0] - (70.0 + 0.10 * sd * 1.0)) < 1e-9 and cand[1] == 65.0 and abs(cand[3] - (55.0 - 0.10 * sd)) < 1e-9


def test_formguide_runs_reads_race_l600_and_position_skipping_trials():
    text = ("[3] Fast & Free (5)\n"
            "Moe R2 2026-11-01 1200m cond:Good $32000 J Doe (4) 58.0kg 3rd@800m 2nd@400m. margin:0.5L starters:9 "
            "finish:2/9 RaceClass:[MDN] WinningTime:1:11.200 RaceL600:35.500 PF[Source: sportsbet_race_context L600 Delta: 0.4]\n"
            "Moe **(TRIAL)** R9 2026-10-20 800m cond:None $0 starters:8 finish:3/8 RaceL600:34.000\n")
    fg = fwd.formguide_runs(text)
    (name, runs), = fg.items()
    assert runs == {"2026-11-01": {"race_l600": 35.5, "pos800": 3, "starters": 9}}
