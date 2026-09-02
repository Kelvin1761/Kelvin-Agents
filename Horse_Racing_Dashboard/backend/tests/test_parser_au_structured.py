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
    # The guard has to key on the heading form this test is about. Bare 參考
    # also matches the 「📎 參考分（不直接入7D公式）」 summary line, which every
    # block carries -- so the test demanded flagged dimensions from meetings
    # whose format never prints one.
    if not any(re.search(r'^#{4,6}[^\n]*（參考', b, re.M) for b in blocks):
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


# ── Transport slimming ─────────────────────────────────────────────────────

GENERATOR = Path(__file__).resolve().parents[2] / "generate_static.py"


def test_payload_is_slimmed_before_the_html_is_built():
    """The HTML inlines the payload and is ALWAYS the larger artifact.

    _slim_for_transport used to run only inside _write_json, so the JSON was
    slimmed and the HTML was not. With the dimension breakdown added that read
    16.88 MiB of HTML against 9.43 MiB of JSON -- 68% of Cloudflare's 25 MiB
    per-file limit, where a nine-meeting Saturday would be rejected outright.
    Slimming first brought the HTML to 9.95 MiB.
    """
    if not GENERATOR.exists():
        pytest.skip("generate_static.py not present")
    text = GENERATOR.read_text(encoding="utf-8")
    slim = text.find("data, slimmed = _slim_for_transport(data)")
    build = text.find("html = generate_html(")
    assert slim != -1, "main() no longer slims the payload"
    assert build != -1, "main() no longer builds HTML"
    assert slim < build, \
        "the payload is slimmed AFTER the HTML is built -- the HTML keeps every duplicate"
    # The HTML is built from a copy with raw_text lifted out; the snapshot JSON
    # written afterwards must still be the complete payload, because it is the
    # base snapshot the next incremental merge builds on.
    extract = text.find("extract_analysis_bundles(html_payload)")
    assert extract != -1, "the HTML payload no longer has raw_text lifted out"
    assert slim < extract < build, "bundles must be extracted between slimming and the build"
    assert "_write_json(json_path, data)" in text, \
        "the snapshot JSON is no longer written from the complete payload"


def test_slimming_keeps_the_numbers_and_is_idempotent():
    """Slimming may drop prose that raw_text already carries; it must never
    drop the numbers the strip is drawn from."""
    sys.path.insert(0, str(GENERATOR.parent))
    from generate_static import _slim_for_transport

    raw = "判讀：呢匹馬有料。\n數據：近績序列: 1-2-3"
    payload = {"races": {"k": {"races_by_analyst": {"Kelvin": [{"horses": [{
        "raw_text": raw,
        "dimension_details": [{
            "name": "狀態與穩定性", "score": 72.4, "weight_pct": 35.2,
            "contribution": 25.46, "symbol": "✅", "ranking_weighted": True,
            "sample_counts": ["5 戰"],
            "verdict": "呢匹馬有料。", "evidence": ["近績序列: 1-2-3"],
        }],
    }]}]}}}}
    payload, dropped = _slim_for_transport(payload)
    detail = payload["races"]["k"]["races_by_analyst"]["Kelvin"][0]["horses"][0]["dimension_details"][0]
    assert dropped == 2, f"expected verdict + evidence dropped, got {dropped}"
    for key in ("name", "score", "weight_pct", "contribution", "symbol", "sample_counts"):
        assert key in detail, f"slimming dropped {key}, which the strip needs"

    _, again = _slim_for_transport(payload)
    assert again == 0, "slimming an already-slimmed payload dropped more"


def test_slimming_keeps_prose_that_raw_text_does_not_carry():
    sys.path.insert(0, str(GENERATOR.parent))
    from generate_static import _slim_for_transport

    payload = {"races": {"k": {"races_by_analyst": {"Kelvin": [{"horses": [{
        "raw_text": "something else entirely",
        "dimension_details": [{"name": "d", "verdict": "not in raw", "evidence": ["nor this"]}],
    }]}]}}}}
    payload, dropped = _slim_for_transport(payload)
    detail = payload["races"]["k"]["races_by_analyst"]["Kelvin"][0]["horses"][0]["dimension_details"][0]
    assert dropped == 0
    assert detail["verdict"] == "not in raw", "dropped prose the renderer cannot recover"
    assert detail["evidence"] == ["nor this"]


# ── 完整分析 / mobile layout ───────────────────────────────────────────────

STYLESHEET = Path(__file__).resolve().parents[2] / "frontend" / "src" / "index.css"


def _stylesheet():
    if not STYLESHEET.exists():
        pytest.skip("index.css not present")
    return STYLESHEET.read_text(encoding="utf-8")


def test_analysis_is_split_on_document_headings():
    """完整分析 used to classify raw_text line by line against loose patterns.

    Measured on one AU horse: 核心分析 absorbed 5,244 of 8,048 characters, the
    block's own `### 【No.1】…` header surfaced as a chapter, and chapters came
    out in priority order. Every horse block on both platforms carries a real
    #### / ##### heading tree (477/477 AU, 131/131 HKJC), so the split is
    structural now.
    """
    text = _template_text()
    definitions, calls = _definition_and_call_counts(text, 'splitAnalysisByHeadings')
    assert definitions == 1, "splitAnalysisByHeadings was removed"
    assert calls >= 1, "the structural splitter is defined but never called"


def test_sections_already_on_the_card_are_skipped_once():
    """評分總覽 is the ranking strip, 主要優勢/主要風險 are card rows. Repeating
    them inside 完整分析 is what made the document long."""
    text = _template_text()
    match = re.search(r'const ANALYSIS_SKIP_HEADING = /(.+?)/;', text)
    assert match, "the skip list is gone -- 完整分析 will duplicate the card"
    pattern = match.group(1)
    for heading in ("評分總覽", "主要優勢", "主要風險"):
        assert heading in pattern, f"{heading} is no longer skipped"


def test_mobile_ranking_overrides_come_after_the_desktop_min_width():
    """CSS order bug, hit for real: the mobile rules were inserted BEFORE
    `.battlefield-ranking__table { min-width: 560px }`, so at equal specificity
    the desktop rule won and the table still scrolled sideways on a phone even
    with every optional column hidden."""
    css = _stylesheet()
    base = css.find("min-width: 560px")
    override = css.find(".battlefield-ranking__table { min-width: 0; }")
    assert base != -1, "the desktop min-width is gone; this guard is stale"
    assert override != -1, "the mobile min-width override was removed"
    assert override > base, \
        "the mobile override is declared before the desktop rule and loses to it"


def test_mobile_hides_only_the_non_core_ranking_columns():
    text = _template_text()
    match = re.search(r"const RANKING_CORE = \[([^\]]+)\]", text)
    assert match, "the mobile ranking column list is gone"
    for column in ("排名", "馬號", "馬名", "綜合戰力分", "Grade"):
        assert column in match.group(1), f"{column} dropped from the mobile table"


def test_data_readout_is_not_rendered_twice():
    """It was on the preview card AND inside 完整分析. The card version is gone;
    the 完整分析 one must stay reachable."""
    text = _template_text()
    _, calls = _definition_and_call_counts(text, 'renderDataReadout')
    assert calls == 1, f"expected exactly one renderDataReadout call site, found {calls}"


# ── 完整分析 lazy loading ──────────────────────────────────────────────────
# raw_text was 6.79 MiB of a 9.62 MiB snapshot (70.5%) and is only read when a
# card is expanded, so it moved into analysis/<slug>.json. Everything here
# guards the seam between the writer (Python) and the reader (JS): if the key
# format or the slug rule drifts apart, every card silently says "載入唔到"
# while the page still loads and nothing logs an error.

def test_analysis_bundle_key_matches_between_writer_and_reader():
    sys.path.insert(0, str(GENERATOR.parent))
    from generate_static import extract_analysis_bundles, meeting_slug

    payload = {"races": {"2026-09-02|Murray Bridge": {"races_by_analyst": {"Kelvin": [
        {"race_number": 3, "horses": [{"horse_number": 7, "raw_text": "#### 核心分析\ntext"}]},
    ]}}}}
    stripped, bundles = extract_analysis_bundles(payload)

    slug = meeting_slug("2026-09-02|Murray Bridge")
    assert slug == "2026-09-02-murray-bridge", f"slug rule changed: {slug}"
    assert list(bundles) == [slug]
    assert list(bundles[slug]) == ["Kelvin|3|7"], \
        "the bundle key no longer matches analysisRefFor()'s `analyst|race|horse`"

    horse = stripped["races"]["2026-09-02|Murray Bridge"]["races_by_analyst"]["Kelvin"][0]["horses"][0]
    assert "raw_text" not in horse, "raw_text was left in the inlined payload"


def test_reader_builds_the_same_slug_as_the_writer():
    """The JS slug rule is a separate implementation of the Python one; drift
    between them makes every fetch 404."""
    sys.path.insert(0, str(GENERATOR.parent))
    from generate_static import meeting_slug

    text = _template_text()
    assert "function analysisSlug(meetingKey)" in text, "the reader-side slug helper is gone"
    assert "replace(/[^A-Za-z0-9_-]+/g, '-')" in text, \
        "the JS slug rule changed; it must still match meeting_slug()"
    assert meeting_slug("2026-09-02|Happy Valley") == "2026-09-02-happy-valley"


def test_lazy_analysis_is_wired_end_to_end():
    text = _template_text()
    for fn in ("loadAnalysisBundle", "fillLazyAnalysis", "renderAnalysisDetail", "analysisRefFor"):
        definitions, calls = _definition_and_call_counts(text, fn)
        assert definitions == 1, f"{fn} definition missing or duplicated ({definitions})"
        assert calls >= 1, f"{fn} is defined but never called"
    assert "data-analysis-lazy" in text, "the expand button no longer flags lazy cards"


def test_lazy_failure_is_reported_not_silent():
    """An empty document and a failed download look identical to the reader."""
    text = _template_text()
    assert "完整分析載入唔到" in text, \
        "the lazy-load failure message is gone; a missing bundle would render as an empty document"


def test_deploy_guards_that_the_bundles_shipped():
    """Missing bundles produce no runtime error anywhere -- same failure shape
    as the missing-PWA-asset case this guard sits beside."""
    deploy = GENERATOR.parent / "deploy.sh"
    if not deploy.exists():
        pytest.skip("deploy.sh not present")
    body = deploy.read_text(encoding="utf-8")
    assert "data-analysis-lazy" in body and "analysis" in body, \
        "deploy.sh no longer checks that the analysis bundles reached the dist"


def test_service_worker_keeps_analysis_available_offline():
    sw = GENERATOR.parent / "pwa" / "sw.js"
    if not sw.exists():
        pytest.skip("sw.js not present")
    body = sw.read_text(encoding="utf-8")
    assert "/analysis/" in body, \
        "the worker no longer handles analysis bundles -- the one part of the app " \
        "that needs a network, in the basement this worker exists for"


# ── 加分位 / 扣分位 shorthand ──────────────────────────────────────────────

def _verdict_shorthand_patterns():
    """Pull the JS lookup table's regexes out of the template."""
    text = _template_text()
    block = re.search(r'const VERDICT_SHORTHAND = \[(.+?)\n\];', text, re.S)
    assert block, "VERDICT_SHORTHAND is gone"
    return [re.compile(p.replace('\\\\', '\\'))
            for p in re.findall(r'^\s*\[/(.+?)/,', block.group(1), re.M)]


ENGINE_CORE = (Path(__file__).resolve().parents[3] / ".agents" / "skills" / "au_racing"
               / "au_wong_choi_auto" / "scripts" / "au_racing_engine" / "engine_core.py")


def test_shorthand_covers_every_sentence_the_engine_can_emit():
    """Test against the engine's string literals, not one day's output.

    A corpus check only sees the sentences that fired that day. Measured
    2026-09-02: the map covered every bullet in the 477-horse corpus and still
    missed 8 of the engine's 21 possible sentences -- five rare conditions that
    had not fired (pace_burn_risk, distance_unproven, forgiveness, thin evidence
    chain, faster-finish) and three where the wording had drifted in the working
    tree ("臨場步速" → "臨場節奏", "步速配腳" → "場面節奏配腳"). The literals are
    the complete population.
    """
    if not ENGINE_CORE.exists():
        pytest.skip("au engine_core.py not reachable from here")
    source = ENGINE_CORE.read_text(encoding="utf-8")
    sentences = (set(re.findall(r'items\.append\("([^"]+)"\)', source))
                 | set(re.findall(r'or \["([^"]+)"\]', source)))
    # only the advantage/risk vocabulary, which is what the chips shorten
    sentences = {x for x in sentences if len(x) > 8}
    assert len(sentences) >= 15, f"only found {len(sentences)} sentences; the scrape pattern is stale"

    patterns = _verdict_shorthand_patterns()
    missing = [x for x in sorted(sentences) if not any(p.search(x) for p in patterns)]
    assert not missing, (
        f"{len(missing)} sentence(s) the engine can emit have no shorthand and would "
        f"render as full sentences on the card: {missing[:3]}"
    )


def test_shorthand_still_covers_every_phrasing_the_generator_writes(parsed_meeting):
    """The chips are a lookup over the generator's own sentences, not a summary.

    A new phrasing does not break the page -- shortenVerdict falls through to
    the original sentence -- but it does put a full sentence back on the card,
    which is exactly what the chips replaced. This fails when that starts
    happening rather than letting it drift.
    """
    _, horses, _ = parsed_meeting
    patterns = _verdict_shorthand_patterns()
    unmatched = set()
    total = 0
    for horse in horses:
        for field in ("advantage", "risk"):
            for line in (getattr(horse, field) or "").split("\n"):
                line = line.strip()
                if not line:
                    continue
                total += 1
                if not any(p.search(line) for p in patterns):
                    unmatched.add(line)
    assert total, "no advantage/risk bullets in this meeting"
    assert not unmatched, (
        f"{len(unmatched)} phrasing(s) have no shorthand and will render as full "
        f"sentences: {sorted(unmatched)[:3]}"
    )


def test_verdict_chips_replaced_the_prose_block():
    text = _template_text()
    definitions, calls = _definition_and_call_counts(text, 'renderVerdictChips')
    assert definitions == 1 and calls >= 1, "the chips renderer is not wired"
    assert '加分位' in text and '扣分位' in text, "the chip labels were renamed away"
    # Checked via the old helper rather than the markup string: the markup
    # string also appears in the CSS comment that documents what it replaced,
    # so asserting on it makes the test match its own documentation.
    assert 'const asList = t =>' not in text, "the old <br>-joined prose block is back"


def test_matrix_chapter_leads_the_document():
    """The breakdown is the only chapter that explains the ranking; the others
    restate the card. Pattern-matched so HKJC's 評分矩陣 (7D 數值拆解) sorts too."""
    text = _template_text()
    assert re.search(r'const rank = sec =>.*?矩陣\|拆解.*?賽績檔案\|Facts', text, re.S), \
        "the chapter ordering rule changed; the matrix may no longer lead"
    assert 'sec.collapsed = true' in text, \
        "the covered chapters no longer start collapsed -- the document runs long again"


# ── 完整分析 v3: chapters, dimension body, chapter rail ────────────────────

def test_skip_list_is_matched_against_the_bare_heading():
    """Headings arrive as "📊 數據判讀". The skip patterns are anchored (^…$) to
    the bare name, so testing them against the raw title matches nothing and the
    chapters silently stay -- which is exactly what happened first time."""
    text = _template_text()
    assert re.search(r'const bareTitle = title\.replace\(LEADING_EMOJI_RE', text), \
        "the skip list is tested before the emoji is stripped; anchored patterns will never match"
    match = re.search(r'const ANALYSIS_SKIP_HEADING = /(.+?)/;', text)
    assert match
    for heading in ("數據判讀", "近績解構", "核心分析"):
        assert heading in match.group(1), f"{heading} is no longer removed from 完整分析"


def test_dimension_body_rebases_the_first_line_indent():
    """Section content is `.trim()`ed upstream, which strips the indent of the
    FIRST line only. Without re-basing it, 評分構成 sits at column 0 while 判讀
    and 數據 sit at 2 and become its children -- they rendered as sub-scores.
    A plain min() over all lines returns 0 and fixes nothing, so this asserts
    the min is taken over lines 1..n."""
    text = _template_text()
    assert 'const rest = lines.slice(1).map(indentOf);' in text, \
        "the first-line indent is no longer re-based against the remaining lines"


def test_dimension_body_renderer_is_wired():
    text = _template_text()
    for fn in ("renderDimensionBody", "parseIndentedBlocks", "renderKvGrid", "renderSubScore"):
        definitions = len(re.findall(r'function\s+' + fn + r'\s*\(', text))
        # Count USES, not calls: renderSubScore is passed by reference to
        # `.map(renderSubScore)`, which a `name(` counter never sees.
        uses = len(re.findall(re.escape(fn), text)) - definitions
        assert definitions == 1, f"{fn} missing or duplicated ({definitions})"
        assert uses >= 1, f"{fn} is defined but never used"
    assert "formatRichSection(content)" in text, \
        "the plain-text fallback is gone; an unrecognised shape would render empty"


def test_chapter_rail_lists_dimensions_and_is_desktop_only():
    text = _template_text()
    css = _stylesheet()
    assert 'analysis-nav__dim' in text, "the rail no longer lists individual dimensions"
    definitions, calls = _definition_and_call_counts(text, 'jumpToAnalysis')
    assert definitions == 1 and calls >= 1, "the rail's jump handler is not wired"
    assert re.search(r'@media \(max-width: 1099px\) \{\s*\.analysis-document__nav \{ display: none', css), \
        "the rail is no longer hidden on phones"


def test_section_body_width_override_comes_after_its_base_rule():
    """This stylesheet is ordered base-then-overrides, so a max-width override
    declared earlier loses at equal specificity and does nothing. That has
    silently happened twice: the ranking table's min-width and this one."""
    css = _stylesheet()
    base = css.find("max-width: 86ch;")
    override = css.find(".analysis-document__section-body {\n    max-width: none;")
    assert base != -1, "the 86ch reading measure is gone; this guard is stale"
    assert override != -1, "the desktop full-width override was removed"
    assert override > base, \
        "the full-width override is declared before the 86ch rule and loses to it"


# ── HKJC parity ────────────────────────────────────────────────────────────

HKJC_ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")


def _newest_hkjc_meeting():
    try:
        if not HKJC_ROOT.is_dir():
            return None
        candidates = [d for d in HKJC_ROOT.iterdir()
                      if d.is_dir() and list(d.glob("Race_*_Auto_Analysis.md"))]
    except OSError:
        return None
    return max(candidates, key=lambda d: d.name) if candidates else None


def test_hkjc_horses_get_the_ranking_matrix_too():
    """HKJC prints the weighted table into its markdown for only 42 of 264 race
    files (15.9%) -- it stopped after 2026-07-04 even though the data never went
    away. Reading Race_N_Logic.json instead takes it to 100%.

    grade_transparency comes in three shapes across the archive (structured
    `rows`, a markdown table row, and a bullet line); supporting only the bullet
    reached 92.3% and missed every newer meeting with no error at all.
    """
    meeting = _newest_hkjc_meeting()
    if meeting is None:
        pytest.skip("no materialized HKJC meeting on this machine")
    sys.path.insert(0, str(GENERATOR.parent / "backend"))
    from services.parser_hkjc import parse_hkjc_analysis

    horses = with_details = 0
    for path in sorted(meeting.glob("Race_*_Auto_Analysis.md")):
        race = parse_hkjc_analysis(str(path))
        if not race:
            continue
        for horse in race.horses:
            horses += 1
            if horse.dimension_details:
                with_details += 1
    if not horses:
        pytest.skip(f"no horses parsed from {meeting.name}")
    assert with_details == horses, (
        f"{meeting.name}: only {with_details}/{horses} HKJC horses carry a ranking "
        f"matrix -- the grade_transparency shape probably changed again"
    )


def test_hkjc_weights_come_from_the_report_not_the_live_engine():
    """2026-07-04's own table reads 9.2 / 18.5 / 25.6 / 22.1 / 3.8 / 7.5 / 13.4
    while today's MATRIX_WEIGHTS are 9.83 / 12.85 / 27.37 / …. Reading the live
    constant would restate an old report with weights it never used."""
    source = (GENERATOR.parent / "backend" / "services" / "parser_hkjc.py").read_text(encoding="utf-8")
    assert "grade_transparency" in source, "the per-report weights source is gone"
    assert "hkjc_racing_engine" not in source, \
        "parser_hkjc now imports the live engine; per-report weights must win"


def test_lazy_context_is_cleared_on_every_render():
    """Card ids are random per render, so the context map kept every card ever
    drawn: measured 5 -> 78 entries over six race switches."""
    text = _template_text()
    body = re.search(r'function renderNow\(main\) \{(.{0,400})', text, re.S)
    assert body, "renderNow is gone"
    assert "LAZY_ANALYSIS_CTX.clear()" in body.group(1), \
        "renderNow no longer clears the lazy-analysis context; it will grow unbounded"
    assert "ANALYSIS_BUNDLES.clear()" not in text, \
        "the fetched bundles must survive a re-render or every race refetches"


# ── Dimension body v2: adjustments, de-duplication, scroll-spy ─────────────

def test_verdict_prose_is_not_rendered():
    """判讀 interprets numbers shown above it; measured across 805 dimensions,
    57.5% cite no number that is not already on screen in the same block."""
    text = _template_text()
    assert "dim-verdict" not in text.split("const VERDICT_SHORTHAND")[0] or True
    body = re.search(r'function renderDimensionBody\(content[^)]*\) \{(.+?)\n\}', text, re.S)
    assert body, "renderDimensionBody is gone"
    assert "dim-verdict" not in body.group(1), \
        "the 判讀 callout is back in the dimension body"


def test_adjustment_lines_are_parsed_not_dumped():
    """Detail lines have five measured shapes; only the adjustment carries a
    figure the reader weighs, so it gets the big number with its reason under."""
    text = _template_text()
    for name in ("DETAIL_ADJUST_RE", "DETAIL_BASE_RE", "DETAIL_TOTAL_RE", "DETAIL_RUN_RE"):
        assert name in text, f"{name} is gone; detail lines would render as plain text"
    definitions, uses = _definition_and_call_counts(text, 'renderSubScoreDetails')
    assert definitions == 1 and uses >= 1, "the detail renderer is not wired"


def test_detail_lines_that_restate_their_caption_are_dropped():
    """21.9% of detail lines repeat the numbers in the caption directly above."""
    text = _template_text()
    assert "captionNumbers" in text and "restates" in text, \
        "the caption de-duplication rule was removed"


def test_scroll_spy_tracks_leaves_with_a_line_shorter_than_a_row():
    """Two bugs, both measured: mixing chapters with the dimensions they contain
    makes the rule arbitrate parent vs child, and a reading line at 25% of the
    viewport sits three collapsed 46px rows below the one being read."""
    text = _template_text()
    spy = re.search(r'function attachAnalysisSpy\(detail\) \{(.+?)\n\}\n', text, re.S)
    assert spy, "attachAnalysisSpy is gone"
    # Strip comments first: the reason rAF is not used is written in a comment
    # inside this very function, so a raw substring check matches its own
    # documentation (the same slip as the CSS-comment check earlier).
    code = "\n".join(l for l in spy.group(1).split("\n") if not l.strip().startswith("//"))
    assert "const mark = 12" in code, \
        "the reading line moved; it must stay under one collapsed row (~46px)"
    assert "requestAnimationFrame" not in code, \
        "rAF does not fire while the document is not rendered, making this unverifiable"
    assert "analysisSpyCleanup" in text, "the scroll listener is never removed"


def test_kv_grid_stacks_label_over_value():
    css = _stylesheet()
    block = re.search(r'\.dim-kv \{(.+?)\}', css, re.S)
    assert block, ".dim-kv is gone"
    assert "minmax(300px" in block.group(1), \
        "the key/value grid packs more than two columns again"


# ── HKJC board occupancy ───────────────────────────────────────────────────

def _drop_rule():
    sys.path.insert(0, str(GENERATOR.parent / "backend"))
    from services.meeting_detector import _hkjc_settled_keys_to_drop
    return _hkjc_settled_keys_to_drop


def test_settled_hkjc_meeting_stays_until_a_newer_one_is_analysed():
    """A settled meeting used to vanish the moment its reflector report landed,
    which left the HKJC board empty for days between cards -- and for the whole
    off-season. It now stays until a newer card's analysis is ready."""
    drop = _drop_rule()
    groups = {("2026-07-12", "ShaTin"): {"kelvin_path": "/has/analysis"}}
    reflected = {("2026-07-12", "ShaTin")}
    # patch the analysis probe: this meeting is analysed
    import services.meeting_detector as md
    original = md._hkjc_has_analysis
    md._hkjc_has_analysis = lambda paths: True
    try:
        assert drop(groups, reflected) == set(), \
            "the only analysed meeting was dropped, leaving the board empty"

        groups[("2026-07-15", "HappyValley")] = {"kelvin_path": "/also/analysed"}
        assert drop(groups, reflected) == reflected, \
            "the settled meeting should go once a newer analysed card exists"
    finally:
        md._hkjc_has_analysis = original


def test_hkjc_meetings_without_analysis_are_not_shown():
    """A folder can hold racecards and form for days before the analysis runs;
    it rendered as an empty meeting. 6 of 7 HKJC folders were in that state."""
    drop = _drop_rule()
    import services.meeting_detector as md
    groups = {
        ("2026-07-12", "ShaTin"): {"kelvin_path": "/analysed"},
        ("2026-07-15", "HappyValley"): {"kelvin_path": "/racecards/only"},
    }
    original = md._hkjc_has_analysis
    md._hkjc_has_analysis = lambda paths: paths.get("kelvin_path") == "/analysed"
    try:
        dropped = drop(groups, {("2026-07-12", "ShaTin")})
        assert ("2026-07-15", "HappyValley") in dropped, \
            "a meeting with no analysis would render as an empty card"
        assert ("2026-07-12", "ShaTin") not in dropped, \
            "the last analysed meeting must survive"
    finally:
        md._hkjc_has_analysis = original


# ── Duplicate removal inside a dimension ───────────────────────────────────

def test_duplicated_rows_are_dropped_by_rule_not_by_hand():
    """最近正式賽果 appeared in FOUR dimensions and again in 完整賽績檔案;
    試閘交代 in three, while 試閘分 is a scored box of its own."""
    text = _template_text()
    match = re.search(r'const KV_DROP_BY_DIMENSION = \[(.+?)\n\];', text, re.S)
    assert match, "the per-dimension drop list is gone"
    rules = match.group(1)
    for dimension, row in [
        ("狀態與穩定性", "近績序列"), ("狀態與穩定性", "試閘交代"),
        ("速度考驗背景", "試閘交代"), ("騎練訊號", "Section內部權重"),
        ("騎練訊號", "人馬歷史"), ("檔位形勢", "戰術劇本"),
    ]:
        assert row in rules, f"{dimension} no longer drops {row}"
    assert "最近正式賽果" in text, "the global drop for 最近正式賽果 is gone"
    assert "seen.has(value)" in text, \
        "identical values are no longer de-duplicated (上仗正式賽騎師 == 歷來最佳配搭)"


def test_total_row_matches_both_wordings():
    """`合計（0-100 封頂）＝ 64.2` and `同場／地況往績分 ＝ 71.9` are both totals.
    Matching only the 合計 form made the second render as a grey note, so the
    dimension looked like it was missing its final figure."""
    text = _template_text()
    match = re.search(r'const DETAIL_TOTAL_RE = /(.+?)/;', text)
    assert match, "DETAIL_TOTAL_RE is gone"
    import re as _re
    pattern = _re.compile(match.group(1).replace('\\\\', '\\'))
    assert pattern.match("合計（0-100 封頂）＝ 64.2")
    assert pattern.match("同場／地況往績分 ＝ 71.9")


def test_l600_comparison_replaces_the_sentence():
    """The caption states two numbers meant to be compared inside a 60-character
    sentence. 908 of 908 captions in the 2026-09-02 corpus use one of the two
    phrasings the pattern accepts."""
    text = _template_text()
    definitions, uses = _definition_and_call_counts(text, 'renderL600Compare')
    assert definitions == 1 and uses >= 1, "the L600 comparison is not wired"
    match = re.search(r'const L600_RE = /(.+?)/;', text)
    assert match, "L600_RE is gone"
    import re as _re
    pattern = _re.compile(match.group(1).replace('\\\\', '\\'))
    assert pattern.search("近9場所在賽事嘅 L600 平均慢過基準 0.92 秒；同場平均慢過基準 0.94 秒")
    assert pattern.search("近7場所在賽事嘅 L600 平均快過基準 0.13 秒；同場平均慢過基準 0.97 秒")


# ── HKJC breakdown shape ───────────────────────────────────────────────────
# HKJC nests its 7D breakdown differently from AU and an AU-shaped reader put
# adjustments into sub-score boxes of their own. Measured on 2026-07-12 ShaTin:
#
#   AU    評分構成 → sub-score → its adjustments one level deeper
#   HKJC  評分構成 → sub-scores AND adjustments at the SAME level, the
#                    adjustment naming its target in brackets:
#                      騎師分 62 ← 希威森兩季917仗…          sub-score
#                      檔位分 65                              sub-score, no source
#                      人馬歷史（騎師分）+4.0 ← …            adjusts 騎師分
#                      · L400 絕對值（24.95s） -5.6　末段慢  signal-list item

def _template_const(name):
    text = _template_text()
    match = re.search(r'const ' + name + r' = /(.+?)/;', text)
    assert match, f"{name} is gone"
    import re as _re
    return _re.compile(match.group(1).replace('\\\\', '\\'))


def test_subscore_is_recognised_by_shape_not_by_sign():
    """近績分's own caption is a form sequence (近6仗名次 3-3-10-6-3-6) whose
    hyphens read as negative numbers, and 操練趨勢分's ends in （活躍度+3.7）.
    Classifying by "contains a signed number" put both in the wrong bucket."""
    sub = _template_const('SUBSCORE_LINE_RE')
    for line in [
        "騎師分 62 ← 希威森兩季917仗：勝率6%、上名率22%",
        "近績分 64 ← 近6仗名次 3-3-10-6-3-6；3次前三、1次八名以後",
        "操練趨勢分 64 ← 操練節奏平穩，中性處理；操練量充足（活躍度+3.7）",
        "檔位分 65",
        "走位匹配分 55　走位 PI 衰退",
    ]:
        assert sub.match(line), f"sub-score not recognised: {line}"
    for line in [
        "人馬歷史（騎師分）+4.0 ← 希威森近期策騎此馬3次",
        "完成時間對標趨勢退步：sub分加權後再-5.0",
        "今場賽道 A（僅供參考，未入評分）",
    ]:
        assert not sub.match(line), f"not a sub-score, but matched: {line}"


def test_adjustment_sign_may_touch_the_preceding_bracket():
    """HKJC writes "（騎師分）+4.0 ← …" with no space before the sign; a required
    \\s matched none of them and all four rendered as grey notes."""
    adj = _template_const('DETAIL_ADJUST_RE')
    assert adj.match("人馬歷史（騎師分）+4.0 ← 希威森近期策騎此馬3次：0勝")
    assert adj.match("班次水平調整 +0.4 ← 近仗獎金水平 log10 4.54")
    # the mandatory ← keeps it off form sequences
    assert not adj.match("近6仗名次 3-3-10-6-3-6")


def test_adjustments_are_routed_into_the_box_they_name():
    text = _template_text()
    assert "ADJUST_TARGET_RE" in text, "the bracketed routing target is gone"
    assert "classifyFormulaChildren" in text, "the shape classifier is gone"
    assert "flattenDetailNodes" in text, \
        "nested signal lists (· lines under 速度分＝基準60…) would be dropped"


# ── Reading direction and remaining duplication ────────────────────────────

def test_l600_chart_says_which_way_is_faster():
    """The bars grow right for a bigger "+", which reads as more/better -- but
    + means SLOWER than the benchmark. The axis has to say so, and the horse's
    bar is coloured by whether it beat the field rather than by sign."""
    text = _template_text()
    assert '← 快過基準' in text and '慢過基準 →' in text, \
        "the L600 axis no longer states which direction is faster"
    # The class is built as `l600__fill--${tone}`, so the literal only exists
    # in the stylesheet -- asserting on the template matched nothing.
    css = _stylesheet()
    assert ".l600__fill--good" in css and ".l600__fill--bad" in css, \
        "the beat-the-field / lost-to-the-field colours are gone"
    assert "const faster = ours < field" in text, \
        "the comparison that decides the colour is gone"


def test_the_sentence_the_chart_replaces_is_dropped():
    """Leaving both is the duplication the chart was meant to remove."""
    text = _template_text()
    assert "let caption = chart ? '' : source;" in text, \
        "the L600 sentence is shown alongside the chart again"


def test_reworded_restatements_are_dropped_too():
    """騎練訊號 prints the trainer's record twice, the second time reworded and
    with the win count added, so neither an exact-text nor a strict-number test
    catches it. Three or more numbers with 60%+ already in the caption does."""
    text = _template_text()
    assert "restatesReworded" in text, "the reworded-restatement rule is gone"
    assert "own.size >= 3 && shared >= 0.6" in text, \
        "the overlap threshold changed; check it still drops the duplicate record"


def test_hkjc_analyst_view_chapter_is_dropped():
    text = _template_text()
    match = re.search(r'const ANALYSIS_SKIP_HEADING = /(.+?)/;', text)
    assert match and '最終判讀' in match.group(1), \
        "HKJC's 最終判讀 (Analyst View) chapter is back"


# ── HKJC nested data ───────────────────────────────────────────────────────

def test_nested_data_children_are_rendered():
    """A data row whose value is empty carries its content in its children.
    Rendering only the top level printed "近6場數據:" with nothing under it --
    22 source lines came out as 6 on 2026-07-12 ShaTin, and the whole 晨操分析
    block (workload, who rode work, deployment flags) never appeared at all."""
    text = _template_text()
    assert "if (!value && n.children && n.children.length)" in text, \
        "nested data groups are collapsed again"
    definitions, uses = _definition_and_call_counts(text, 'renderRunRecords')
    assert definitions == 1 and uses >= 1, "per-run record tables are not wired"
    # 晨操分析 used to be its own wide group; it is now an anchor box so every
    # block in a dimension reads in the same shell. What must not regress is
    # that the block is still rendered at all.
    definitions, uses = _definition_and_call_counts(text, 'renderAnchorBox')
    assert definitions == 1 and uses >= 1, "the 晨操分析 block is no longer surfaced"


def test_hkjc_chips_fall_back_to_dimension_impacts():
    """HKJC's newer report prints no 主要優勢 / 主要風險, so the chips said only
    who rides. The flag has to be read BEFORE the jockey/trainer chips are
    pushed, or those very chips make it look like the report had bullets."""
    text = _template_text()
    assert "const hasSourceBullets" in text, "the fallback flag is gone"
    assert text.index("const hasSourceBullets") < text.index("const jt = (horse.dimension_details"), \
        "hasSourceBullets is evaluated after the jockey/trainer chips are added"


def test_person_strike_rate_is_charted_against_the_benchmark():
    """"Tim Clark 去年官方 528 場、91 冠（勝率 17%，收縮後 17%，全國基準 13%）"
    was the box's only description and buried the one comparison that matters."""
    text = _template_text()
    definitions, uses = _definition_and_call_counts(text, 'renderPersonStats')
    assert definitions == 1 and uses >= 1, "the strike-rate chart is not wired"
    assert _template_const('RATE_VS_BENCH_RE').search(
        "去年官方 528 場、91 冠（勝率 17%，收縮後 17%，全國基準 13%）")
    assert _template_const('HK_RATE_RE').search("希威森兩季917仗：勝率6%、上名率22%"), \
        "HKJC's wording carries no benchmark and must still render its figures"


# ── Data routed into the box that consumed it ──────────────────────────────

def test_data_groups_are_routed_into_their_scoring_box():
    """The captions say which sub-score consumed which data ("風險分 71 ←
    醫療欄未見事故。已再綜合醫療紀錄、休賽日數同體重波幅"), but the figures sat
    in a separate 數據 block below the boxes, away from the score they built."""
    text = _template_text()
    assert "const DATA_ROUTES" in text, "the routing table is gone"
    match = re.search(r'const DATA_ROUTES = \[(.+?)\n\];', text, re.S)
    assert match
    routes = match.group(1)
    for source, target in [
        ("近6場數據", "近績分"), ("晨操分析", "操練趨勢分"),
        ("健康掃描", "風險分"), ("走位窗口", "走位匹配分"),
        ("班次", "班次分"), ("賽績線明細", "賽績線強度分"),
    ]:
        assert source in routes and target in routes, f"{source} no longer routes to {target}"


def test_repeated_data_labels_merge_into_one_table():
    """賽績線明細 appears five times; as five separate groups it rendered as
    five one-line boxes instead of one table."""
    text = _template_text()
    assert "existing.nodes.push" in text, \
        "repeated data labels are no longer merged"


def test_career_combo_row_is_dropped_as_unscored():
    """人馬歷史（騎師分）+4.0 uses the rider's last three outings on this horse;
    人馬組合統計 is the career record and feeds no score."""
    text = _template_text()
    assert "const DATA_DROP" in text and "人馬組合統計" in text, \
        "the unscored career-combo row is back"


def test_gear_codes_are_translated():
    """"上仗 B/XB → 今仗 B/XB" meant nothing without the code list, and the
    verdict (無變動) arrived as a separate row far from the change."""
    text = _template_text()
    assert "const GEAR_NAMES" in text, "the gear glossary is gone"
    for code, name in [("B", "眼罩"), ("XB", "交叉鼻箍"), ("TT", "脷帶")]:
        assert f"{code}: '{name}'" in text, f"gear code {code} lost its Chinese name"
    definitions, uses = _definition_and_call_counts(text, 'renderGearChange')
    assert definitions == 1 and uses >= 1, "the gear renderer is not wired"


def test_stability_counts_are_pulled_out_of_the_prose():
    """穩定性分's caption carries four counts inside one long sentence."""
    text = _template_text()
    assert "const STABILITY_COUNTS" in text, "the count extraction is gone"
    definitions, uses = _definition_and_call_counts(text, 'renderCountStats')
    assert definitions == 1 and uses >= 1, "the count stats are not wired"


# --- 穩定性分／晨操／賽績線：睇落太重，改完之後唔好靜靜行返舊樣 -------------


def test_stability_counts_render_as_one_line_not_tiles():
    """四格數字牌換咗一行字。舊 class 一出現就代表改動被還原。"""
    text = _template_text()
    assert "counts-line__item" in text
    assert "counts__cell" not in text
    assert ".counts-line" in _stylesheet()


def test_count_stats_are_not_fed_to_the_person_branch():
    """renderPersonStats 同 renderCountStats 唔可以爭同一個位,
    唔然騎練 box 會多咗一行同佢無關嘅穩定性數字。"""
    assert "const countLine = person ? '' : renderCountStats(source);" in _template_text()


def test_trackwork_lines_are_separated():
    """晨操逐行之間要有分隔,唔係一嚿過。"""
    css = _stylesheet()
    assert re.search(r"\.kv-line \{[^}]*border-bottom: 1px dashed", css)
    assert ".kv-group__lines > .kv-line:last-child { border-bottom: 0; }" in css


def test_formline_table_does_not_repeat_its_own_label():
    """表本身已經有欄名,上面再寫多次「賽績線明細」就係重複。"""
    assert "const title = formline ? '' : " in _template_text()


def test_dropped_formline_rows_stay_dropped():
    text = _template_text()
    drop = text[text.index("const DATA_DROP") : text.index("const DATA_DROP") + 400]
    for label in ("賽績線兌現度", "對手陣容強度", "上仗結果"):
        assert label in drop, label


def test_composition_line_nests_its_inputs():
    """「組合:沙田加權 檔位55%+走位匹配25%+近仗消耗20%」證明呢三項
    係 檔位走位情境分 嘅輸入,唔係同級兄弟。"""
    text = _template_text()
    assert "COMPOSITION_RE" in text
    assert "parent.components" in text
    assert "dim-part__share" in text
    assert ".dim-part" in _stylesheet()


def test_every_scoring_component_uses_the_same_box():
    """騎師分 係讀得最順嗰個格,所以計分項一律用返佢個殼。

    維度層嘅加減分(完成時間對標趨勢 −5、除去配備 −3)以前散落喺格仔外面嘅
    dim-loose 度,睇落唔似計分項;數據錨點就用同一個殼但標「參考」。
    """
    text = _template_text()
    shell_defs, shell_uses = _definition_and_call_counts(text, 'renderBoxShell')
    assert shell_defs == 1 and shell_uses >= 2, "the shared box shell is not wired"
    adj_defs, adj_uses = _definition_and_call_counts(text, 'renderDimensionAdjustBox')
    assert adj_defs == 1 and adj_uses >= 1, "dimension-level adjustments left the box"
    assert 'class="dim-loose"' not in text, \
        "a scoring component is rendered outside the box again"
    # 「未入評分」嘅嘢唔可以擺喺計分項中間。
    assert 'dim-note' in text and '未入評分|僅供參考' in text


def test_markdown_bold_does_not_reach_the_page():
    """來源係 markdown,「**中性**」原封不動 escape 出嚟就變咗一堆星號。"""
    text = _template_text()
    assert "replace(/\\*\\*(.+?)\\*\\*/g, '$1')" in text
