"""SpeedPro 只向前收集器。

HKJC 只喺 `current/` 放 SpeedPro，冇歷史檔 —— 抓錯日期、存咗半份、或者重複
存同一份都唔會有第二次機會改正。所以呢度最重要嘅測試係：
  * BOM 照解、base64 圖剝走但其餘欄位原封不動；
  * current/ 仲係上一個場次 → 拒絕存（exit 3），唔會寫任何檔；
  * 內容一樣 → 唔抄多份，只加 fetch_log；內容有變 → 存新版本，永不覆蓋；
  * fg／xls 缺咗唔可以連 sg 都唔存；sg 缺咗就成份唔存（唔可以存半份）。

Fixture 係人手砌嘅細檔（`fixtures/speedpro/`，以 UTF-8 BOM 開頭），唔掂網絡。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_speedpro.py"
_SPEC = importlib.util.spec_from_file_location("collect_speedpro_test", SCRIPT)
sp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sp)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "speedpro"
XLS = b"\xd0\xcf\x11\xe0fake-xls"
T0 = datetime(2026, 10, 14, 0, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 14, 1, 0, 0, tzinfo=timezone.utc)


def _source(overrides: dict | None = None, missing: tuple = ()) -> dict:
    files = {path.name: path.read_bytes() for path in FIXTURES.iterdir() if path.is_file()}
    files["20261014_energygrid_ch.xls"] = XLS
    files.update(overrides or {})
    for name in missing:
        files.pop(name, None)
    return files


def _fetcher(files: dict, calls: list | None = None):
    def fetch(url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        if calls is not None:
            calls.append(name)
        if name not in files:
            raise sp.SpeedProError(f"GET {url} 失敗：HTTP 404")
        return files[name]
    return fetch


def _bom_json(obj) -> bytes:
    return b"\xef\xbb\xbf" + json.dumps(obj, ensure_ascii=False).encode("utf-8")


def test_fixtures_really_start_with_a_bom() -> None:
    assert (FIXTURES / "sg_index").read_bytes().startswith(b"\xef\xbb\xbf")


def test_decode_json_handles_bom_and_rejects_html_error_page() -> None:
    assert sp.decode_json(_bom_json({"a": 1})) == {"a": 1}
    # 日期路徑返嚟嘅係 HTML 錯誤頁（~4368 bytes），唔可以當「格式改咗」
    with pytest.raises(sp.SpeedProError, match="HTML"):
        sp.decode_json(b"<!DOCTYPE html><html>error</html>", name="sg_index")
    with pytest.raises(sp.SpeedProError):
        sp.decode_json(b"\xef\xbb\xbf   ")


def test_strip_replaces_only_data_uris_and_keeps_everything_else() -> None:
    payload = {
        "RaceMap": "data:image/png;base64,AAAA",
        "nested": [{"img": "data:image/png;base64,BBBB", "energy": "88 "}],
        "comment": "data is fine when not a uri prefix? no: 'data:' only",
        "name": "開心旺財",
    }
    clean, count = sp.strip_data_uris(payload)
    assert count == 2
    assert clean["RaceMap"].startswith("<stripped data-uri image/png len=26 sha256=")
    assert clean["nested"][0]["energy"] == "88 "   # 尾空格都要原封不動
    assert clean["name"] == "開心旺財"
    assert clean["comment"] == payload["comment"]
    # 唔同嘅圖要得出唔同嘅標記 —— 圖改咗都睇得出
    assert clean["RaceMap"] != clean["nested"][0]["img"]


def test_parse_index_date_and_races() -> None:
    index = sp.decode_json((FIXTURES / "sg_index").read_bytes())
    assert sp.parse_racedate(index) == date(2026, 10, 14)
    assert sp.race_numbers(index) == [1, 2]
    with pytest.raises(sp.SpeedProError):
        sp.parse_racedate({"racedate": "next wednesday"})


def test_saves_stripped_snapshot_with_manifest(tmp_path: Path) -> None:
    result = sp.collect(data_root=tmp_path, expected_date=date(2026, 10, 14),
                        expected_course="HV", fetcher=_fetcher(_source()), now=T0)
    assert result["status"] == "saved"
    snap = Path(result["snapshot"])
    assert snap == tmp_path / "_speedpro_snapshots" / "2026-10-14_HV" / "20261014T000000Z"
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["races"] == 2
    assert manifest["runners"] == 5
    assert manifest["scratched"] == 1
    assert manifest["sg_index_lastupdatetime"] == "2026-10-13 11:26 AM"
    assert manifest["missing"] == []
    names = {f["name"] for f in manifest["files"]}
    assert names == {"sg_index.json", "sg_race_1.json", "sg_race_2.json",
                     "fg_race_1.json", "fg_race_2.json", "20261014_energygrid_ch.xls"}
    for entry in manifest["files"]:
        assert (snap / entry["name"]).stat().st_size == entry["size"]
    # 存落去嘅 JSON 冇 BOM、冇 base64，但能量數字照舊
    raw = (snap / "sg_race_1.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"base64" not in raw
    sg = json.loads(raw)
    assert sg["zh-hk"]["SpeedPRO"][0]["name_chi"] == "開心旺財"
    assert sg["zh-hk"]["SpeedPRO"][0]["energyrequired"] == "93"
    assert (snap / "20261014_energygrid_ch.xls").read_bytes() == XLS
    assert not list(snap.parent.glob(".partial-*"))
    log = (snap.parent / "fetch_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(log[-1])["status"] == "saved"


def test_stale_current_meeting_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    calls: list = []
    with pytest.raises(sp.NotCurrentMeeting) as err:
        sp.collect(data_root=tmp_path, expected_date=date(2026, 10, 18),
                   fetcher=_fetcher(_source(), calls), now=T0)
    assert err.value.exit_code == 3
    assert "2026-10-14" in str(err.value)
    assert calls == ["sg_index"]          # 唔使抓埋啲 race 檔
    assert not (tmp_path / "_speedpro_snapshots").exists()


def test_wrong_course_is_refused(tmp_path: Path) -> None:
    with pytest.raises(sp.NotCurrentMeeting):
        sp.collect(data_root=tmp_path, expected_date=date(2026, 10, 14),
                   expected_course="ST", fetcher=_fetcher(_source()), now=T0)
    assert not list(tmp_path.rglob("manifest.json"))


def test_identical_refetch_is_logged_not_copied(tmp_path: Path) -> None:
    first = sp.collect(data_root=tmp_path, fetcher=_fetcher(_source()), now=T0)
    second = sp.collect(data_root=tmp_path, fetcher=_fetcher(_source()), now=T1)
    assert second["status"] == "duplicate"
    assert second["snapshot"] == first["snapshot"]
    meeting_root = Path(first["snapshot"]).parent
    assert len(list(meeting_root.glob("*/manifest.json"))) == 1
    log = [json.loads(line) for line in
           (meeting_root / "fetch_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["status"] for entry in log] == ["saved", "duplicate"]


def test_changed_content_is_a_new_immutable_version(tmp_path: Path) -> None:
    first = sp.collect(data_root=tmp_path, fetcher=_fetcher(_source()), now=T0)
    before = (Path(first["snapshot"]) / "sg_race_1.json").read_bytes()

    sg = sp.decode_json((FIXTURES / "sg_race_1").read_bytes())
    sg["zh-hk"]["SpeedPRO"][1]["scratched"] = True       # 賽前公布退出
    second = sp.collect(data_root=tmp_path,
                        fetcher=_fetcher(_source({"sg_race_1": _bom_json(sg)})), now=T1)
    assert second["status"] == "saved"
    assert second["snapshot"] != first["snapshot"]
    assert second["scratched"] == 2
    # 舊版本冇被郁過
    assert (Path(first["snapshot"]) / "sg_race_1.json").read_bytes() == before
    manifest = json.loads((Path(second["snapshot"]) / "manifest.json").read_text("utf-8"))
    assert manifest["previous_snapshot"] == Path(first["snapshot"]).name


def test_same_second_fetch_never_overwrites(tmp_path: Path) -> None:
    sp.collect(data_root=tmp_path, fetcher=_fetcher(_source()), now=T0)
    sg = sp.decode_json((FIXTURES / "sg_race_2").read_bytes())
    sg["zh-hk"]["SpeedPRO"][0]["energyrequired"] = "95"
    second = sp.collect(data_root=tmp_path,
                        fetcher=_fetcher(_source({"sg_race_2": _bom_json(sg)})), now=T0)
    assert Path(second["snapshot"]).name == "20261014T000000Z-1"


def test_manual_snapshot_without_manifest_does_not_block_dedupe(tmp_path: Path) -> None:
    manual = tmp_path / "_speedpro_snapshots" / "2026-10-14_HV" / "manual_20261014T111907"
    manual.mkdir(parents=True)
    (manual / "sg_index.json").write_bytes(b"{}")
    result = sp.collect(data_root=tmp_path, fetcher=_fetcher(_source()), now=T0)
    assert result["status"] == "saved"


def test_missing_fg_and_xls_are_recorded_but_sg_still_saved(tmp_path: Path) -> None:
    result = sp.collect(data_root=tmp_path,
                        fetcher=_fetcher(_source(missing=("fg_race_2",
                                                          "20261014_energygrid_ch.xls"))),
                        now=T0)
    assert result["status"] == "saved"
    assert len(result["missing"]) == 2
    snap = Path(result["snapshot"])
    assert (snap / "sg_race_2.json").exists()
    assert not (snap / "fg_race_2.json").exists()


def test_missing_sg_race_saves_nothing(tmp_path: Path) -> None:
    with pytest.raises(sp.SpeedProError):
        sp.collect(data_root=tmp_path, fetcher=_fetcher(_source(missing=("sg_race_2",))),
                   now=T0)
    assert not list(tmp_path.rglob("manifest.json"))
    assert not list(tmp_path.rglob(".partial-*"))


def test_race_file_from_another_meeting_is_rejected(tmp_path: Path) -> None:
    # current/ 更新到一半：index 係新場次，race 檔仲係舊場次
    sg = sp.decode_json((FIXTURES / "sg_race_1").read_bytes())
    for lang in ("zh-hk", "en-us"):
        sg[lang]["RaceInfoEng"]["Date"] = "11/10/2026"
    with pytest.raises(sp.SpeedProError, match="對唔上"):
        sp.collect(data_root=tmp_path,
                   fetcher=_fetcher(_source({"sg_race_1": _bom_json(sg)})), now=T0)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    result = sp.collect(data_root=tmp_path, fetcher=_fetcher(_source()), now=T0,
                        dry_run=True)
    assert result["status"] == "would_save"
    assert not (tmp_path / "_speedpro_snapshots").exists()


def test_cli_exit_code_for_stale_meeting(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sp, "make_fetcher", lambda **_k: _fetcher(_source()))
    code = sp.main(["--date", "2026-10-18", "--data-root", str(tmp_path)])
    assert code == sp.EXIT_NOT_CURRENT
    assert "NOT_CURRENT" in capsys.readouterr().err
