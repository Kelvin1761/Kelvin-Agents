import json
import sys
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = DASHBOARD_DIR / "backend"
REPO_ROOT = DASHBOARD_DIR.parent
HKJC_EXTRACTOR_DIR = REPO_ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "scripts"
for path in (str(BACKEND_DIR), str(DASHBOARD_DIR), str(REPO_ROOT), str(HKJC_EXTRACTOR_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from generate_static import (
    _enrich_au_silks,
    _enrich_hkjc_silks,
    _parse_au_racecard_silks,
    _parse_hkjc_pdf_english_names,
    _parse_hkjc_racecard_silks,
)
from models.race import AnalystName, HorseAnalysis, Meeting, RaceAnalysis, Region
from services.parser_au import parse_mc_results_json
from extract_racecard import parse_english_name_map
from api import races as races_api


def test_old_numeric_mc_concordance_does_not_break_parser(tmp_path):
    mc_path = tmp_path / "Race_1_MC_Results.json"
    mc_path.write_text(
        json.dumps(
            {
                "concordance": 3,
                "results": {
                    "Example Horse": {
                        "win_pct": 21.5,
                        "top3_pct": 55.0,
                        "top4_pct": 68.0,
                        "avg_rank": 3.1,
                        "predicted_win_odds": 4.7,
                        "predicted_place_odds": 1.8,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    picks = parse_mc_results_json(str(mc_path))

    assert len(picks) == 1
    assert picks[0].horse_name == "Example Horse"
    assert picks[0].forensic_rank is None


def test_hkjc_racecard_silk_parser_uses_brand_number(tmp_path):
    racecard = tmp_path / "07-15 Race 1 排位表.md"
    racecard.write_text(
        """馬號: 1
馬名: 摘星聲升
英文馬名: EMERGING STAR
烙號: K390

馬號: 2
馬名: 勇者無敵
烙號: K217
""",
        encoding="utf-8",
    )

    silks = _parse_hkjc_racecard_silks(racecard)

    assert silks[1] == {
        "horse_code": "K390",
        "silk_url": "https://racing.hkjc.com/racing/content/Images/RaceColor/K390.gif",
        "horse_name_en": "EMERGING STAR",
    }
    assert silks[2]["horse_code"] == "K217"


def test_hkjc_silks_are_enriched_for_every_analyst(tmp_path):
    racecard = tmp_path / "07-15 Race 1 排位表.md"
    racecard.write_text("馬號: 1\n馬名: 摘星聲升\n烙號: K390\n", encoding="utf-8")
    starter_pdf = tmp_path / "07-15 全日出賽馬匹資料 (PDF).md"
    starter_pdf.write_text("Standby 2 摘星聲升 EMERGING STAR\n", encoding="utf-8")
    meeting = Meeting(
        date="2026-07-15",
        venue="HappyValley",
        region=Region.HKJC,
        analysts=[AnalystName.KELVIN, AnalystName.HEISON],
        folder_paths={"Kelvin": str(tmp_path), "Heison": str(tmp_path)},
    )
    all_races = {
        "Kelvin": [RaceAnalysis(race_number=1, horses=[HorseAnalysis(horse_number=1, horse_name="摘星聲升")])],
        "Heison": [RaceAnalysis(race_number=1, horses=[HorseAnalysis(horse_number=1, horse_name="摘星聲升")])],
    }

    _enrich_hkjc_silks(meeting, all_races)

    for races in all_races.values():
        horse = races[0].horses[0]
        assert horse.horse_code == "K390"
        assert horse.silk_url.endswith("/K390.gif")
        assert horse.horse_name_en == "EMERGING STAR"


def test_hkjc_pdf_english_name_parser_handles_race_and_standby_rows(tmp_path):
    starter_pdf = tmp_path / "07-15 全日出賽馬匹資料 (PDF).md"
    starter_pdf.write_text(
        "1 1 特別美麗 BEAUTY MISSILE\n"
        "3 至高心得 KOLACHI\n"
        "Standby 2 摘星聲升 EMERGING STAR\n",
        encoding="utf-8",
    )

    names = _parse_hkjc_pdf_english_names(starter_pdf)

    assert names["特別美麗"] == "BEAUTY MISSILE"
    assert names["至高心得"] == "KOLACHI"
    assert names["摘星聲升"] == "EMERGING STAR"


def test_hkjc_english_racecard_parser_maps_brand_to_name():
    html = """
    <table class="draggable"><tbody><tr>
      <td>1</td><td>1/2/3</td><td></td><td>EMERGING STAR</td><td>K390</td>
    </tr></tbody></table>
    """

    assert parse_english_name_map(html) == {"K390": "EMERGING STAR"}


def test_au_racecard_silk_is_parsed_and_enriched(tmp_path):
    silk_url = "https://images.puntcdn.com/silks/svg/019cb5e2-fbac-71dd-9b90-3b7e96104fa7_1.svg"
    racecard = tmp_path / "07-15 Race 1 Racecard.md"
    racecard.write_text(
        f"RACE 1 — 1400m\n1. Example Horse (3)\nSilk: {silk_url}\n",
        encoding="utf-8",
    )
    race_number, silks = _parse_au_racecard_silks(racecard)
    assert race_number == 1
    assert silks[1] == silk_url

    meeting = Meeting(
        date="2026-07-15",
        venue="Warwick Farm",
        region=Region.AU,
        analysts=[AnalystName.KELVIN],
        folder_paths={"Kelvin": str(tmp_path)},
    )
    all_races = {
        "Kelvin": [RaceAnalysis(race_number=1, horses=[HorseAnalysis(horse_number=1, horse_name="Example Horse")])]
    }
    _enrich_au_silks(meeting, all_races)
    assert all_races["Kelvin"][0].horses[0].silk_url == silk_url


def test_local_test_api_uses_same_antigravity_silk_enrichment(tmp_path, monkeypatch):
    racecard = tmp_path / "07-15 Race 1 排位表.md"
    racecard.write_text(
        "馬號: 1\n馬名: 摘星聲升\n英文馬名: EMERGING STAR\n烙號: K390\n",
        encoding="utf-8",
    )
    meeting = Meeting(
        date="2026-07-15",
        venue="HappyValley",
        region=Region.HKJC,
        analysts=[AnalystName.KELVIN],
        folder_paths={"Kelvin": str(tmp_path)},
    )
    parsed = {
        "Kelvin": [
            RaceAnalysis(
                race_number=1,
                horses=[HorseAnalysis(horse_number=1, horse_name="摘星聲升")],
            )
        ]
    }
    monkeypatch.setattr(races_api, "load_meeting_races", lambda _meeting: parsed)
    races_api._races_cache = {}

    result = races_api._get_races_cached(meeting)
    horse = result["Kelvin"][0].horses[0]

    assert horse.horse_name_en == "EMERGING STAR"
    assert horse.silk_url.endswith("/K390.gif")
