"""File-has vs parsed parity for the AU structured fields.

Why this exists: on 2026-09-02 an audit of 477 horses across 48 races found
`rank`, `ability_score`, `confidence_score`, `advantage` and `risk` present in
477/477 analysis files and reaching the dashboard payload 0% of the time.
`rank` / `ability_score` had simply never been read. `advantage` / `risk` WERE
read -- but only in the inline `競爭優勢: xxx` shape, while the generator had
moved to `#### 主要優勢` headings. The regex missed, the field became None, and
nothing anywhere raised. The dashboard rendered prose out of `raw_text` for
months because the structured columns behind it were empty.

A parser that silently returns None when the source format shifts is the
failure mode this repo pays for repeatedly. So these tests do not assert "the
field parses"; they count how many horses HAVE the section in the file and
require the parsed count to match. When the generator changes its format again,
this fails loudly instead of emptying a column.
"""
import sys
import re
import pytest
from pathlib import Path
from typing import Optional

sys.path.insert(0, '.')

from services.parser_au import parse_au_analysis
import config


def _newest_au_meeting() -> Optional[Path]:
    root = config.AU_ANALYSIS_ROOT
    try:
        if not root.is_dir():
            return None
        candidates = [d for d in root.iterdir()
                      if d.is_dir() and list(d.glob("Race_*_Auto_Analysis.md"))]
    except OSError:
        # AU lives outside the repo and the mirror is not always readable
        # (launchd is denied stat on the Drive copy). Skipping beats failing.
        return None
    return max(candidates, key=lambda d: d.name) if candidates else None


@pytest.fixture(scope="module")
def parsed_meeting():
    meeting = _newest_au_meeting()
    if meeting is None:
        pytest.skip("no materialized AU meeting available on this machine")
    horses, blocks = [], []
    for path in sorted(meeting.glob("Race_*_Auto_Analysis.md")):
        race = parse_au_analysis(str(path))
        if not race:
            continue
        horses.extend(race.horses)
        blocks.extend(re.split(r'^### 【No\.', path.read_text(), flags=re.M)[1:])
    if not horses:
        pytest.skip(f"no horses parsed from {meeting.name}")
    return meeting, horses, blocks


def _parity(blocks, horses, file_pattern, field, minimum_ratio=1.0):
    """Assert the parsed count matches how many blocks carry the section."""
    in_file = sum(1 for b in blocks if re.search(file_pattern, b, re.M))
    parsed = sum(1 for h in horses if getattr(h, field) not in (None, "", [], {}))
    if in_file == 0:
        pytest.skip(f"no block in this meeting carries {field}")
    assert in_file >= len(blocks) * 0.5, (
        f"{field}: only {in_file} of {len(blocks)} blocks matched the file "
        f"pattern. Either the meeting is unusual or this test's own pattern is "
        f"stale -- a near-empty denominator makes the parity check vacuous."
    )
    ratio = parsed / in_file
    assert ratio >= minimum_ratio, (
        f"{field}: {in_file} horse blocks contain it, only {parsed} parsed "
        f"({ratio:.1%}). The source format probably changed -- fix the parser, "
        f"do not lower this threshold."
    )


def test_rank_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'排名:\s*\*\*\d+\*\*', 'rank')


def test_ability_score_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'綜合戰力分:\s*\*\*[\d.]+\*\*', 'ability_score')


def test_confidence_score_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'信心分\s*[\d.]+', 'confidence_score')


def test_advantage_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'^#{3,6}\s*主要優勢\s*$', 'advantage')


def test_risk_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'^#{3,6}\s*主要風險\s*$', 'risk')


def test_evidence_confidence_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'數據信心\*{0,2}[：:]\s*\d+\s*/\s*\d+', 'evidence_dimensions')


def test_dimension_details_parity(parsed_meeting):
    _, horses, blocks = parsed_meeting
    _parity(blocks, horses, r'^#{5}\s*[^：:\n]+[：:]\s*[\d.]+\s*分', 'dimension_details')


def test_every_dimension_heading_becomes_a_detail(parsed_meeting):
    """Per-horse count, not just presence -- a parser that finds one dimension
    out of seven would pass a presence check."""
    _, horses, blocks = parsed_meeting
    short = []
    for horse, block in zip(horses, blocks):
        in_file = len(re.findall(r'^#{5}\s*[^：:\n]+[：:]\s*[\d.]+\s*分', block, re.M))
        parsed = len(horse.dimension_details or [])
        if in_file and parsed < in_file:
            short.append(f"{horse.horse_name}: {parsed}/{in_file}")
    assert not short, f"dimensions dropped for {len(short)} horses: {short[:5]}"


def test_reference_dimensions_are_kept_and_flagged(parsed_meeting):
    """檔位形勢 / 賽績線 are printed by the engine but marked 參考·不入排名.

    They must survive parsing with ranking_weighted=False -- dropping them is
    how the dashboard ended up showing 5 of the 7 dimensions the file prints,
    with nothing telling the reader the other two existed.
    """
    _, horses, blocks = parsed_meeting
    flagged = [d for h in horses for d in (h.dimension_details or [])
               if not d.ranking_weighted]
    weighted = [d for h in horses for d in (h.dimension_details or [])
                if d.ranking_weighted]
    if not any('參考' in b for b in blocks):
        pytest.skip("this meeting prints no reference dimensions")
    assert flagged, "reference dimensions were dropped instead of flagged"
    assert weighted, "no ranking dimensions survived"
    assert all(d.weight_pct is None for d in flagged), \
        "a reference dimension was given a ranking weight"
    assert all(d.weight_pct is not None for d in weighted), \
        "a ranking dimension lost its weight"


def test_weights_sum_to_one_hundred(parsed_meeting):
    """The weighted table is the engine's own; if our merge mangles it the
    total stops making sense."""
    _, horses, _ = parsed_meeting
    for horse in horses:
        weights = [d.weight_pct for d in (horse.dimension_details or [])
                   if d.ranking_weighted and d.weight_pct is not None]
        if not weights:
            continue
        assert 99.0 <= sum(weights) <= 101.0, \
            f"{horse.horse_name}: ranking weights sum to {sum(weights):.1f}%"


# ── Template wiring ────────────────────────────────────────────────────────
# There is no JS test harness here, and the failure these guard against is the
# one this repo keeps paying for: the code still exists, nothing errors, and the
# feature silently stops reaching the page. The odds prefill shipped in db6874b3
# and rendered empty for every horse until 2026-09-02 for exactly that reason.

TEMPLATE = Path(__file__).resolve().parents[2] / "static_template.html"


def _template_text():
    if not TEMPLATE.exists():
        pytest.skip("static_template.html not present")
    return TEMPLATE.read_text(encoding="utf-8")


def _definition_and_call_counts(text, fn):
    """(definitions, calls) for `fn`.

    Asserting that "renderDimensionStrip(horse)" merely appears in the file is
    a test that cannot fail: the substring is inside `function
    renderDimensionStrip(horse) {` itself, so deleting every call still passes.
    Counting occurrences separates the definition from its call sites.
    """
    definitions = len(re.findall(r'function\s+' + fn + r'\s*\(', text))
    total = len(re.findall(re.escape(fn) + r'\s*\(', text))
    return definitions, total - definitions


def test_dimension_strip_is_defined_and_called():
    text = _template_text()
    definitions, calls = _definition_and_call_counts(text, 'renderDimensionStrip')
    assert definitions == 1, f"expected one definition, found {definitions}"
    assert calls >= 1, \
        "renderDimensionStrip is defined but never called -- the strip would vanish silently"


def test_market_line_is_defined_and_called():
    text = _template_text()
    definitions, calls = _definition_and_call_counts(text, 'renderMarketLine')
    assert definitions == 1, f"expected one definition, found {definitions}"
    assert calls >= 1, "renderMarketLine is defined but never called"


def test_market_ranks_are_passed_from_every_horse_card_call_site():
    """renderHorseCard's third argument is what makes the market comparison
    possible; a call site that forgets it degrades to odds with no rank."""
    text = _template_text()
    calls = _renderhorsecard_calls(text)
    assert calls, "no renderHorseCard call sites found"
    missing = [c for c in calls if _top_level_arg_count(c) < 3
               or re.search(r',\s*(undefined|null)\s*\)$', c)]
    assert not missing, f"call sites without a market-rank argument: {missing}"


def _renderhorsecard_calls(text):
    r"""Extract whole calls, balancing parens.

    A naive `[^)]*\)` stops at the first `)` -- which is inside the
    `picks.find(...)` argument -- and reports every call site as missing an
    argument it actually has. The depth counter must also start AT the opening
    paren of renderHorseCard itself, not after it: starting mid-argument makes
    `find(`'s own closing paren look like the end of the call, which reproduces
    the same false positive by a different route.
    """
    calls, needle = [], "renderHorseCard(horse,"
    start = text.find(needle)
    while start != -1:
        depth, i = 0, start + len("renderHorseCard")
        while i < len(text):
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0:
                    calls.append(text[start:i + 1])
                    break
            i += 1
        start = text.find(needle, start + 1)
    return calls


def _top_level_arg_count(call):
    inner = call[call.index('(') + 1:-1]
    depth, args = 0, 1
    for ch in inner:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ',' and depth == 0:
            args += 1
    return args


def test_odds_prefill_reads_the_horse_record():
    """The prefill used to read `c.market_place_odds` off the consensus payload,
    which never carried odds -- 14 of 14 inputs rendered empty in production."""
    text = _template_text()
    assert "getMarketOdds(c, m, raceNum).place" in text, \
        "odds prefill no longer resolves through the horse-record lookup"


def test_impact_decomposition_matches_the_engines_own_contribution_column(parsed_meeting):
    """The dashboard's impact bars are (score - 60) x weight.

    That is only honest if it reproduces the engine's own published 貢獻
    column. It does, to within 0.05 across 477 horses. Both differ from the
    engine's stated `clean ranking score` by ~0.5 because the published table
    rounds scores and weights to one decimal -- so the bars are accurate to the
    TABLE, which is what they are drawn from, and the UI shows one decimal
    rather than implying more precision than that.
    """
    _, horses, _ = parsed_meeting
    worst = 0.0
    checked = 0
    for horse in horses:
        dims = [d for d in (horse.dimension_details or [])
                if d.ranking_weighted and d.score is not None
                and d.weight_pct is not None and d.contribution is not None]
        if len(dims) < 2:
            continue
        checked += 1
        rebuilt = 60 + sum((d.score - 60) * d.weight_pct / 100 for d in dims)
        engine = sum(d.contribution for d in dims)
        worst = max(worst, abs(rebuilt - engine))
    if not checked:
        pytest.skip("no horse carries a full weighted breakdown")
    assert worst < 0.10, (
        f"impact bars drift {worst:.3f} from the engine's own contribution "
        f"column -- the decomposition no longer matches what the engine says"
    )
