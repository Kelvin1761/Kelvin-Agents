import { useState, useEffect, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import HorseCard from "../components/HorseCard";
import RatingBadge from "../components/RatingBadge";
import RunnerSilk from "../components/RunnerSilk";

/** Trim long going strings: 'Soft 6 (天氣極不穩定...)' → 'Soft 6' */
function trimGoing(going) {
  if (!going) return going;
  // Remove parenthesized extra info
  const trimmed = going.replace(/\s*[（(].*$/, '').trim();
  return trimmed || going;
}

function withRunnerMetadata(pick, horses = []) {
  const horse = horses.find(
    (candidate) => candidate.horse_number === pick.horse_number,
  );
  return {
    ...pick,
    horse_name_en: horse?.horse_name_en || pick.horse_name_en || null,
    horse_code: horse?.horse_code || pick.horse_code || null,
    silk_url: horse?.silk_url || pick.silk_url || null,
  };
}

const BATTLEFIELD_REMOVED_RANKING_FIELDS = new Set([
  "資料完整度",
  "風險分",
  "情境標記",
]);

function cleanBattlefieldCell(value) {
  return String(value || "")
    .replace(/\*{1,3}/g, "")
    .replace(/`+/g, "")
    .replace(/^\[|\]$/g, "")
    .replace(/(\d+)mm\b/g, "$1m")
    .trim();
}

function parseBattlefieldTable(tableLines) {
  if (!tableLines?.length) return null;
  const parseLine = (line) => line.split("|").slice(1, -1).map(cleanBattlefieldCell);
  const headers = parseLine(tableLines[0]);
  const start = /^\|[-:\s|]+\|$/.test(tableLines[1]?.trim() || "") ? 2 : 1;
  return {
    headers,
    rows: tableLines.slice(start).map(parseLine).filter((row) => row.some(Boolean)),
  };
}

function parseBattlefieldOverview(text) {
  const sourceLines = String(text || "").split("\n");
  const filteredLines = [];
  let skippingAutoSummary = false;

  sourceLines.forEach((line) => {
    const clean = cleanBattlefieldCell(line).replace(/^#+\s*/, "");
    if (/^📍\s*Auto\s*走位與檔位摘要（不含節奏預測）\s*[:：]?$/.test(clean)) {
      skippingAutoSummary = true;
      return;
    }
    if (skippingAutoSummary && /^📊\s*全場綜合戰力排名/.test(clean)) {
      skippingAutoSummary = false;
      filteredLines.push(line);
      return;
    }
    if (!skippingAutoSummary) filteredLines.push(line);
  });

  const tables = [];
  const notes = [];
  for (let index = 0; index < filteredLines.length;) {
    if (!filteredLines[index].trim().startsWith("|")) {
      notes.push(filteredLines[index]);
      index += 1;
      continue;
    }
    const tableLines = [];
    while (index < filteredLines.length && filteredLines[index].trim().startsWith("|")) {
      tableLines.push(filteredLines[index]);
      index += 1;
    }
    const table = parseBattlefieldTable(tableLines);
    if (table) tables.push(table);
  }

  const factsTable = tables.find((table) => table.headers.includes("項目") && table.headers.includes("內容"));
  const rawRanking = tables.find((table) => table.headers.includes("排名") && table.headers.includes("馬號"));
  let ranking = null;
  if (rawRanking) {
    const keepIndexes = rawRanking.headers
      .map((header, index) => BATTLEFIELD_REMOVED_RANKING_FIELDS.has(header) ? -1 : index)
      .filter((index) => index >= 0);
    ranking = {
      headers: keepIndexes.map((index) => rawRanking.headers[index]),
      rows: rawRanking.rows.map((row) => keepIndexes.map((index) => row[index] || "")),
    };
  }

  const cleanNotes = notes
    .map((line) => line.trim())
    .filter((line) => line && !/^---+$/.test(line))
    .filter((line) => !/(?:\[第一部分\].*)?(?:🗺️\s*)?戰場全景/i.test(cleanBattlefieldCell(line)))
    .filter((line) => !/^📊\s*全場綜合戰力排名/.test(cleanBattlefieldCell(line)))
    .map((line) => cleanBattlefieldCell(line).replace(/^[-_>]+\s*/, ""));

  return {
    facts: factsTable?.rows.map((row) => ({ label: row[0], value: row[1] })) || [],
    ranking,
    notes: cleanNotes,
  };
}

function splitBattlefieldRacePattern(value) {
  return cleanBattlefieldCell(value).split("/").map((part) => part.trim()).filter(Boolean).map((part, index) => {
    if (index === 0) return { label: /^Race\s*\d+/i.test(part) ? "場次" : "班次", value: part };
    if (index === 1 && /\d+\s*m\b/i.test(part)) return { label: "路程", value: part };
    if (/^HKJC$/i.test(part)) return { label: "賽區", value: "香港" };
    if (/^(?:AU|Australia)$/i.test(part)) return { label: "賽區", value: "澳洲" };
    return { label: "賽事條件", value: part };
  });
}

function BattlefieldOverview({ text, horses = [] }) {
  const overview = parseBattlefieldOverview(text);
  const racePattern = splitBattlefieldRacePattern(
    overview.facts.find((fact) => cleanBattlefieldCell(fact.label) === "賽事格局")?.value || "",
  );
  const horseLookup = new Map(horses.map((horse) => [String(horse.horse_number), horse]));

  return (
    <div className="battlefield battlefield--refined">
      <div className="battlefield__header">
        <div>
          <div className="battlefield__eyebrow">賽事快照</div>
          <div className="battlefield__title">🗺️ 戰場全景</div>
        </div>
        <span className="battlefield__header-note">賽事格局 · 綜合戰力</span>
      </div>
      <div className="battlefield__body">
        {racePattern.length > 0 && (
          <section className="battlefield__race-pattern" aria-label="賽事格局">
            {racePattern.map((item, index) => (
              <div className="battlefield__race-segment" key={`${item.label}-${index}`}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                {index < racePattern.length - 1 && <i aria-hidden="true" />}
              </div>
            ))}
          </section>
        )}

        {overview.notes.length > 0 && (
          <div className="battlefield__notes battlefield__notes--refined">
            {overview.notes.map((line, index) => <div key={index}>{line}</div>)}
          </div>
        )}

        {overview.ranking?.rows?.length > 0 && (
          <div className="battlefield-ranking">
            <div className="battlefield-ranking__header">
              <div><span aria-hidden="true">📊</span><strong>全場綜合戰力排名</strong></div>
              <span>{overview.ranking.rows.length} 匹馬</span>
            </div>
            <div className="battlefield-ranking__scroll">
              <table className="battlefield-ranking__table">
                <thead><tr>{overview.ranking.headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
                <tbody>
                  {overview.ranking.rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className={rowIndex < 3 ? "battlefield-ranking__row--top" : ""}>
                      {overview.ranking.headers.map((header, cellIndex) => {
                        const value = row[cellIndex] || "";
                        const numberIndex = overview.ranking.headers.indexOf("馬號");
                        const horse = horseLookup.get(String(row[numberIndex] || ""));
                        if (header === "排名") {
                          const medal = rowIndex === 0 ? "🥇" : rowIndex === 1 ? "🥈" : rowIndex === 2 ? "🥉" : value;
                          return <td key={header}><span className="battlefield-ranking__rank">{medal}</span></td>;
                        }
                        if (header === "馬號") return <td key={header}><span className="battlefield-ranking__horse-number">{value}</span></td>;
                        if (header === "馬名") return (
                          <td key={header}>
                            <div className="battlefield-ranking__runner">
                              <RunnerSilk silkUrl={horse?.silk_url} horseName={value} size="sm" />
                              <div>
                                <strong className="battlefield-ranking__horse-name">{value}</strong>
                                {horse?.horse_name_en && <span>{horse.horse_name_en}</span>}
                              </div>
                            </div>
                          </td>
                        );
                        if (header === "綜合戰力分") {
                          const score = Math.max(0, Math.min(100, Number(value) || 0));
                          return <td key={header}><div className="battlefield-ranking__score"><strong>{value}</strong><span aria-hidden="true"><i style={{ width: `${score}%` }} /></span></div></td>;
                        }
                        if (/^Grade$/i.test(header)) return <td key={header}><RatingBadge grade={value} /></td>;
                        return <td key={header}>{value || "—"}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * RaceDetailPage — Full race analysis with all horses, Top picks,
 * and dual-analyst comparison (HKJC).
 * Defaults to 並排對比 (comparison) mode for HKJC.
 */
export default function RaceDetailPage() {
  const { date, venue, raceNumber } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [consensus, setConsensus] = useState(null);
  const [activeAnalyst, setActiveAnalyst] = useState(null); // null = comparison mode
  const [loading, setLoading] = useState(true);
  const [meetingRaces, setMeetingRaces] = useState([]);

  useEffect(() => {
    setLoading(true);
    api
      .getRaceDetail(date, venue, raceNumber)
      .then((res) => {
        setData(res);
        const analysts = Object.keys(res.analyses || {});
        // Default to comparison mode (null) if dual-analyst, otherwise first analyst
        setActiveAnalyst(analysts.length > 1 ? null : analysts[0] || null);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    // Consensus will be loaded after we know both analysts have data
    setConsensus(null);

    // Fetch all races in this meeting for the race selector
    api
      .getRaces(date, venue)
      .then((res) => {
        // Merge race numbers from all analysts
        const raceNums = new Set();
        const raceInfo = {};
        const rba = res.races_by_analyst || {};
        for (const races of Object.values(rba)) {
          for (const r of races) {
            raceNums.add(r.race_number);
            if (!raceInfo[r.race_number]) raceInfo[r.race_number] = r;
          }
        }
        const sorted = [...raceNums]
          .sort((a, b) => a - b)
          .map((n) => raceInfo[n]);
        setMeetingRaces(sorted);
      })
      .catch(() => {});
  }, [date, venue, raceNumber]);

  if (loading)
    return (
      <div className="loading">
        <div className="loading__spinner" />
      </div>
    );
  if (!data)
    return (
      <div className="empty-state">
        <div className="empty-state__icon">🏇</div>
        <div className="empty-state__text">No data</div>
      </div>
    );

  const analysts = Object.keys(data.analyses || {});
  const analysis = activeAnalyst
    ? data.analyses?.[activeAnalyst]
    : data.analyses?.[analysts[0]];

  // Load consensus only if both analysts have data for THIS race
  if (analysts.length > 1 && !consensus) {
    api
      .getConsensus(date, venue, raceNumber)
      .then(setConsensus)
      .catch(() => {});
  }

  // For AU (single analyst), also load consensus for betting candidates
  if (analysts.length === 1 && !consensus) {
    api
      .getConsensus(date, venue, raceNumber)
      .then(setConsensus)
      .catch(() => {});
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div
        style={{ fontSize: "0.8rem", color: "#64748B", marginBottom: "12px" }}
      >
        <Link to="/">🏠 Dashboard</Link> → {venue} {date} → Race {raceNumber}
      </div>

      {/* Race selector board — matching home page style */}
      {meetingRaces.length > 1 && (
        <div className="race-board" style={{ marginBottom: "24px" }}>
          {meetingRaces.map((r) => {
            const isActive = r.race_number === Number(raceNumber);
            return (
              <div
                key={r.race_number}
                className={`race-tile card--clickable ${isActive ? "selected" : ""}`}
                onClick={() =>
                  navigate(`/race/${date}/${venue}/${r.race_number}`)
                }
              >
                <div className="race-tile__number">R{r.race_number}</div>
                {r.race_name && (
                  <div
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      marginTop: "6px",
                      marginBottom: "2px",
                      color: "#1E293B",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {(r.race_name || '').replace(/\*{1,2}/g, '')}
                  </div>
                )}
                <div
                  className="race-tile__info"
                  style={{ marginTop: r.race_name ? "2px" : "4px" }}
                >
                  {r.distance || "—"} {r.race_class || ""}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Enhanced race header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: "24px",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "1.5rem",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: "4px",
            }}
          >
            🏇 Race {raceNumber}
            {analysis?.race_name && (
              <span
                style={{
                  fontSize: "1rem",
                  fontWeight: 600,
                  color: "#475569",
                  marginLeft: "12px",
                }}
              >
                {analysis.race_name}
              </span>
            )}
          </h1>
          <div
            style={{ fontSize: "0.8rem", color: "#64748B", lineHeight: "1.6" }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span>{[analysis?.distance, analysis?.race_class, analysis?.track || analysis?.venue].filter(Boolean).join(' · ')}</span>
              {analysis?.analysis_type === "auto" && (
                <span
                  style={{
                    background: '#DBEAFE',
                    color: '#1D4ED8',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontWeight: 700,
                    fontSize: '0.7rem',
                  }}
                >
                  Python Auto
                </span>
              )}
              {analysis?.going && (
                <span
                  style={{
                    background: '#FEF3C7',
                    color: '#92400E',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontWeight: 700,
                    fontSize: '0.75rem',
                  }}
                  title={analysis.going}
                >
                  {trimGoing(analysis.going)}
                </span>
              )}
              {analysis?.alt_condition && (
                <span
                  style={{
                    background: '#FFF7ED',
                    color: '#C2410C',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontWeight: 600,
                    fontSize: '0.7rem',
                    border: '1px solid #FDBA74',
                  }}
                >
                  📙 Alternate
                </span>
              )}
            </div>
          </div>
        </div>

        {/* View mode tabs */}
        {analysts.length > 1 && (
          <div
            style={{
              display: "flex",
              gap: "4px",
              background: "#F1F5F9",
              borderRadius: "8px",
              padding: "3px",
            }}
          >
            <button
              className={
                activeAnalyst === null
                  ? "btn btn--primary btn--sm"
                  : "btn btn--ghost btn--sm"
              }
              onClick={() => setActiveAnalyst(null)}
            >
              📊 並排對比
            </button>
            {analysts.map((a) => (
              <button
                key={a}
                className={
                  activeAnalyst === a
                    ? "btn btn--primary btn--sm"
                    : "btn btn--ghost btn--sm"
                }
                onClick={() => setActiveAnalyst(a)}
              >
                {a}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Consensus panel — only when both analysts have data for this race */}
      {consensus &&
        analysts.length > 1 &&
        (() => {
          const top2Horses = (
            consensus.consensus?.consensus_horses || []
          ).filter((h) => h.is_top2_consensus);
          return (
            <div className="consensus-panel">
              <div className="consensus-panel__title">
                🤝 共識馬匹 — Kelvin × Heison
              </div>
              {top2Horses.length === 0 ? (
                <div
                  style={{
                    padding: "12px 16px",
                    textAlign: "center",
                    color: "#94A3B8",
                    fontSize: "0.85rem",
                  }}
                >
                  本場沒有 Top 2 共識馬匹
                </div>
              ) : (
                top2Horses.map((h) => (
                  <div key={h.horse_number} className="consensus-horse">
                    <span
                      style={{
                        background: "#059669",
                        color: "#fff",
                        width: "28px",
                        height: "28px",
                        borderRadius: "6px",
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontWeight: 800,
                        fontSize: "0.8rem",
                        flexShrink: 0,
                      }}
                    >
                      {h.horse_number}
                    </span>
                    <span className="consensus-horse__name">
                      {h.horse_name}
                    </span>
                    <div
                      style={{
                        display: "flex",
                        gap: "6px",
                        alignItems: "center",
                        fontSize: "0.75rem",
                      }}
                    >
                      <span style={{ color: "#1D4ED8" }}>
                        K#{h.kelvin_rank}
                      </span>
                      <RatingBadge grade={h.kelvin_grade} />
                      <span style={{ color: "#64748B" }}>·</span>
                      <span style={{ color: "#DC2626" }}>
                        H#{h.heison_rank}
                      </span>
                      <RatingBadge grade={h.heison_grade} />
                    </div>
                    <span className="badge badge--consensus">Top 2 共識</span>
                  </div>
                ))
              )}
            </div>
          );
        })()}

      {/* Pace prediction */}
      {analysis?.pace_prediction && (
        <div
          className="card"
          style={{ marginBottom: "16px", padding: "12px 16px" }}
        >
          <span
            style={{ fontSize: "0.75rem", fontWeight: 700, color: "#64748B" }}
          >
            🏃 步速預測
          </span>
          <div
            style={{
              fontSize: "0.85rem",
              marginTop: "4px",
              whiteSpace: "pre-wrap",
            }}
          >
            {analysis.pace_prediction}
          </div>
        </div>
      )}

      {/* Battlefield overview / 戰場全景 */}
      {analysis?.battlefield_overview && (
        <BattlefieldOverview text={analysis.battlefield_overview} horses={analysis.horses || []} />
      )}

      {/* ═══════════════════════════════════════════
          VIEW MODES
          ═══════════════════════════════════════════ */}

      {activeAnalyst === null && analysts.length > 1 ? (
        /* ── COMPARISON MODE (default for HKJC) ── */
        <ComparisonView data={data} analysts={analysts} consensus={consensus} />
      ) : (
        /* ── SINGLE ANALYST MODE ── */
        <SingleAnalystView
          analysis={data.analyses?.[activeAnalyst]}
          analystName={activeAnalyst}
        />
      )}

      {/* Blind spots */}
      {analysis?.blind_spots && (
        <div className="card" style={{ marginTop: "24px" }}>
          <h3
            style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "8px" }}
          >
            🔮 盲區分析
          </h3>
          <div
            style={{
              fontSize: "0.85rem",
              color: "#475569",
              lineHeight: "1.7",
              whiteSpace: "pre-wrap",
            }}
          >
            {analysis.blind_spots.replace(/\*\*/g, "").slice(0, 1000)}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════
          BETTING PANEL — placed after analysis
          ═══════════════════════════════════════════ */}
      <BettingPanel
        date={date}
        venue={venue}
        raceNumber={raceNumber}
        region={data.meeting?.region || "hkjc"}
        consensus={consensus}
        analystsData={data.analyses}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════
   Betting Panel — Per-race betting workflow
   ═══════════════════════════════════════════ */

function BettingPanel({
  date,
  venue,
  raceNumber,
  region,
  consensus,
  analystsData,
}) {
  const [candidates, setCandidates] = useState([]);
  const [raceBets, setRaceBets] = useState([]);
  const [oddsInput, setOddsInput] = useState({});
  const [localStates, setLocalStates] = useState({}); // horse_number -> 'pending'|'skipped'
  const currentRaceData =
    analystsData?.Kelvin || Object.values(analystsData || {})[0] || null;

  const loadBets = useCallback(() => {
    api
      .getBetsByRace(date, venue, raceNumber)
      .then((res) => setRaceBets(res.bets || []))
      .catch(() => {});
  }, [date, venue, raceNumber]);

  useEffect(() => {
    let newCandidates = [];
    if (region === "au") {
      // Find the Kelvin analysis
      const kelvinData = analystsData?.Kelvin;
      const tGoing = (s) => (s || '').replace(/\s*[（(].*$/, '').trim() || s;
      
      if (kelvinData?.is_dual_track && kelvinData?.top_picks && kelvinData?.alt_top_picks) {
        // Dual-track: top 2 from primary (top_picks) + top 2 from alternate (alt_top_picks)
        const primaryLabel = tGoing(kelvinData.primary_condition);
        const altLabel = tGoing(kelvinData.alt_condition);
        
        (kelvinData.top_picks || [])
          .filter((p) => p.rank <= 2)
          .forEach((p) => {
            const kHorse = kelvinData.horses?.find(
              (kh) => kh.horse_number === p.horse_number,
            );
            newCandidates.push({
              horse_number: p.horse_number,
              horse_name: p.horse_name,
              kelvin_grade: p.grade,
              heison_grade: null,
              jockey: kHorse?.jockey || null,
              trainer: kHorse?.trainer || null,
              horse_name_en: kHorse?.horse_name_en || null,
              silk_url: kHorse?.silk_url || null,
              scenario: kelvinData.primary_condition,
              consensus_type: `預期 (${primaryLabel}) Top ${p.rank}`,
            });
          });
        
        (kelvinData.alt_top_picks || [])
          .filter((p) => p.rank <= 2)
          .forEach((p) => {
            const kHorse = kelvinData.horses?.find(
              (kh) => kh.horse_number === p.horse_number,
            );
            newCandidates.push({
              horse_number: p.horse_number,
              horse_name: p.horse_name,
              kelvin_grade: p.grade,
              heison_grade: null,
              jockey: kHorse?.jockey || null,
              trainer: kHorse?.trainer || null,
              horse_name_en: kHorse?.horse_name_en || null,
              silk_url: kHorse?.silk_url || null,
              scenario: kelvinData.alt_condition,
              consensus_type: `備選 (${altLabel}) Top ${p.rank}`,
            });
          });
      } else if (kelvinData?.scenario_top_picks) {
        Object.entries(kelvinData.scenario_top_picks).forEach(
          ([label, picks]) => {
            (picks || [])
              .filter((p) => p.rank <= 2)
              .forEach((p) => {
                const kHorse = kelvinData.horses?.find(
                  (kh) => kh.horse_number === p.horse_number,
                );
                const isPrimary = label === kelvinData.primary_condition;
                const isAlt = label === kelvinData.alt_condition;
                const conditionPrefix = isPrimary
                  ? "預期 "
                  : isAlt
                    ? "備選 "
                    : "";
                newCandidates.push({
                  horse_number: p.horse_number,
                  horse_name: p.horse_name,
                  kelvin_grade: p.grade,
                  heison_grade: null,
                  jockey: kHorse?.jockey || null,
                  trainer: kHorse?.trainer || null,
                  horse_name_en: kHorse?.horse_name_en || null,
                  silk_url: kHorse?.silk_url || null,
                  scenario: label,
                  consensus_type: `${conditionPrefix}${tGoing(label)} Top 2`,
                });
              });
          },
        );
      } else if (kelvinData?.top_picks) {
        (kelvinData.top_picks || [])
          .filter((p) => p.rank <= 2)
          .forEach((p) => {
            const kHorse = kelvinData.horses?.find(
              (kh) => kh.horse_number === p.horse_number,
            );
            newCandidates.push({
              horse_number: p.horse_number,
              horse_name: p.horse_name,
              kelvin_grade: p.grade,
              heison_grade: null,
              jockey: kHorse?.jockey || null,
              trainer: kHorse?.trainer || null,
              horse_name_en: kHorse?.horse_name_en || null,
              silk_url: kHorse?.silk_url || null,
              scenario: null,
              consensus_type: "Top 2 精選",
            });
          });
      }
    } else {
      if (consensus?.consensus?.consensus_horses) {
        newCandidates = consensus.consensus.consensus_horses
          .filter((h) => h.is_top2_consensus)
          .map((h) => {
            let jockey = h.jockey || null;
            let trainer = h.trainer || null;
            let horseNameEn = h.horse_name_en || null;
            let silkUrl = h.silk_url || null;

            if (
              analystsData &&
              analystsData.Kelvin &&
              analystsData.Kelvin.horses
            ) {
              const kHorse = analystsData.Kelvin.horses.find(
                (kh) => kh.horse_number === h.horse_number,
              );
              if (kHorse) {
                jockey = kHorse.jockey || jockey;
                trainer = kHorse.trainer || trainer;
                horseNameEn = kHorse.horse_name_en || horseNameEn;
                silkUrl = kHorse.silk_url || silkUrl;
              }
            }

            return {
              horse_number: h.horse_number,
              horse_name: h.horse_name,
              horse_name_en: horseNameEn,
              silk_url: silkUrl,
              kelvin_grade: h.kelvin_grade,
              heison_grade: h.heison_grade,
              jockey: jockey,
              trainer: trainer,
              scenario: null,
              consensus_type: "Top 2 共識",
            };
          });
      }
    }
    setCandidates(newCandidates);
    loadBets();
  }, [consensus, date, venue, raceNumber, region, analystsData, loadBets]);

  const getBetForHorse = (horseNum) =>
    raceBets.find((b) => b.horse_number === horseNum);

  const getStatus = (horseNum) => {
    const bet = getBetForHorse(horseNum);
    if (bet) {
      if (bet.status === "won" || bet.status === "lost") return "settled";
      return "confirmed";
    }
    return localStates[horseNum] || "pending";
  };

  const handleConfirmBet = async (candidate) => {
    const odds = parseFloat(oddsInput[candidate.horse_number]);
    if (!odds || odds <= 0) return alert("請輸入有效賠率");

    await api.placeBet({
      date,
      venue,
      region,
      race_number: parseInt(raceNumber),
      horse_number: candidate.horse_number,
      horse_name: candidate.horse_name,
      bet_type: "place",
      stake: 1,
      odds,
      jockey: candidate.jockey,
      trainer: candidate.trainer,
      consensus_type: candidate.consensus_type,
      kelvin_grade: candidate.kelvin_grade,
      heison_grade: candidate.heison_grade,
      track_type: currentRaceData?.track,
      going: currentRaceData?.going,
    });

    setLocalStates((prev) => ({
      ...prev,
      [candidate.horse_number]: undefined,
    }));
    loadBets();
  };

  const handleSkip = (horseNum) => {
    setLocalStates((prev) => ({ ...prev, [horseNum]: "skipped" }));
  };

  const handleEditSkipped = (horseNum) => {
    setLocalStates((prev) => ({ ...prev, [horseNum]: "pending" }));
  };

  const handleWithdraw = async (horseNum) => {
    const bet = getBetForHorse(horseNum);
    if (!bet) return;
    if (!confirm("確認退出？此投注將被刪除。")) return;
    await api.deleteBet(bet.id);
    loadBets();
  };

  const handleResult = async (horseNum, position) => {
    const bet = getBetForHorse(horseNum);
    if (!bet) return;

    const isPlaced = position >= 1 && position <= 3;
    const payout = isPlaced ? 1 * bet.odds : 0;

    await api.updateBetResult(bet.id, {
      result_position: position,
      payout: payout,
    });
    loadBets();
  };

  if (candidates.length === 0 && raceBets.length === 0) return null;

  return (
    <div className="betting-panel">
      <div className="betting-panel__title">
        🎯 投注候選
        <span
          style={{ fontWeight: 500, fontSize: "0.75rem", color: "#92400E" }}
        >
          $1 平注制
        </span>
      </div>

      {candidates.map((candidate) => {
        const status = getStatus(candidate.horse_number);
        const bet = getBetForHorse(candidate.horse_number);
        const statusClass =
          status === "confirmed"
            ? "bet-candidate--confirmed"
            : status === "skipped"
              ? "bet-candidate--skipped"
              : status === "settled"
                ? "bet-candidate--settled"
                : "";

        return (
          <div
            key={candidate.horse_number}
            className={`bet-candidate ${statusClass}`}
          >
            <div className="bet-candidate__header">
              <div className="bet-candidate__identity">
                <RunnerSilk
                  silkUrl={candidate.silk_url}
                  horseName={candidate.horse_name}
                />
                <div className="bet-candidate__number">
                  <span>馬號</span>
                  <strong>{candidate.horse_number}</strong>
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                    {candidate.horse_name}
                  </div>
                  {candidate.horse_name_en && (
                    <div className="horse-card__name-en">
                      {candidate.horse_name_en}
                    </div>
                  )}
                  <div style={{ fontSize: "0.7rem", color: "#94A3B8" }}>
                    {[candidate.jockey, candidate.trainer]
                      .filter(Boolean)
                      .join(" · ") || ""}
                  </div>
                </div>
              </div>
              <div
                style={{ display: "flex", gap: "6px", alignItems: "center" }}
              >
                {candidate.kelvin_grade && (
                  <RatingBadge grade={candidate.kelvin_grade} />
                )}
                {candidate.heison_grade && (
                  <RatingBadge grade={candidate.heison_grade} />
                )}
                <span
                  className="badge badge--consensus"
                  style={{ fontSize: "0.65rem" }}
                >
                  {candidate.consensus_type}
                </span>
              </div>
            </div>

            {/* ── PENDING: show odds input + confirm/skip ── */}
            {status === "pending" && (
              <div className="bet-candidate__actions">
                <label className="bet-odds-input">
                  <span
                    style={{
                      fontSize: "0.75rem",
                      color: "#64748B",
                      fontWeight: 600,
                    }}
                  >
                    賠率:
                  </span>
                  <input
                    type="number"
                    inputMode="decimal"
                    autoComplete="off"
                    step="0.1"
                    min="1"
                    placeholder="2.50"
                    value={oddsInput[candidate.horse_number] || ""}
                    onChange={(e) =>
                      setOddsInput((prev) => ({
                        ...prev,
                        [candidate.horse_number]: e.target.value,
                      }))
                    }
                  />
                </label>
                <button
                  className="btn btn--primary btn--sm"
                  onClick={() => handleConfirmBet(candidate)}
                >
                  ✅ 確認投注
                </button>
                <button
                  className="btn btn--ghost btn--sm"
                  onClick={() => handleSkip(candidate.horse_number)}
                >
                  ⏭️ 跳過
                </button>
              </div>
            )}

            {/* ── SKIPPED: show edit button ── */}
            {status === "skipped" && (
              <div className="bet-candidate__actions">
                <span className="bet-status-badge bet-status-badge--skipped">
                  ⏭️ 已跳過
                </span>
                <button
                  className="btn btn--secondary btn--sm"
                  onClick={() => handleEditSkipped(candidate.horse_number)}
                >
                  ✏️ 改變主意
                </button>
              </div>
            )}

            {/* ── CONFIRMED: show result buttons + withdraw ── */}
            {status === "confirmed" && bet && (
              <div className="bet-candidate__actions">
                <span className="bet-status-badge bet-status-badge--confirmed">
                  ✅ 已投注 · ${bet.stake} @ {bet.odds}
                </span>
                <div className="bet-result-buttons">
                  <span
                    style={{
                      fontSize: "0.7rem",
                      color: "#64748B",
                      fontWeight: 600,
                      marginRight: "4px",
                    }}
                  >
                    結果:
                  </span>
                  {[1, 2, 3].map((pos) => (
                    <button
                      key={pos}
                      className="btn btn--sm btn--secondary"
                      onClick={() => handleResult(candidate.horse_number, pos)}
                    >
                      {pos === 1 ? "🥇" : pos === 2 ? "🥈" : "🥉"} {pos}
                    </button>
                  ))}
                  <button
                    className="btn btn--sm btn--ghost"
                    style={{ color: "#DC2626" }}
                    onClick={() => handleResult(candidate.horse_number, 99)}
                  >
                    ❌ 未入位
                  </button>
                </div>
                <button
                  className="btn btn--sm btn--ghost"
                  style={{ color: "#94A3B8" }}
                  onClick={() => handleWithdraw(candidate.horse_number)}
                >
                  🔙 退出
                </button>
              </div>
            )}

            {/* ── SETTLED: show result ── */}
            {status === "settled" && bet && (
              <div className="bet-candidate__actions">
                <span
                  className={`bet-status-badge ${bet.status === "won" ? "bet-status-badge--settled-won" : "bet-status-badge--settled-lost"}`}
                >
                  {bet.status === "won" ? "🏇 入位" : "❌ 未入位"}
                  {bet.result_position && bet.result_position <= 3
                    ? ` #${bet.result_position}`
                    : ""}
                </span>
                <span
                  style={{
                    fontSize: "0.8rem",
                    fontWeight: 800,
                    color: bet.net_profit > 0 ? "#059669" : "#DC2626",
                  }}
                >
                  {bet.net_profit > 0 ? "+" : ""}${bet.net_profit}
                </span>
                <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>
                  ($1 × {bet.odds} = ${bet.payout})
                </span>
              </div>
            )}
          </div>
        );
      })}

      {/* Show any extra bets not in candidates (manually added) */}
      {raceBets
        .filter(
          (b) => !candidates.find((c) => c.horse_number === b.horse_number),
        )
        .map((bet) => (
          <div
            key={bet.id}
            className={`bet-candidate ${bet.status === "won" || bet.status === "lost" ? "bet-candidate--settled" : "bet-candidate--confirmed"}`}
          >
            <div className="bet-candidate__header">
              <div className="bet-candidate__identity">
                <div
                  className="bet-candidate__number"
                  style={{ background: "#64748B" }}
                >
                  {bet.horse_number}
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                    {bet.horse_name}
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "#94A3B8" }}>
                    手動投注
                  </div>
                </div>
              </div>
              <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                ${bet.stake} @ {bet.odds || "—"}
              </span>
            </div>
          </div>
        ))}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Comparison View — synchronized horse rows
   ═══════════════════════════════════════════ */

function ComparisonView({ data, analysts }) {
  return (
    <div>
      {/* Full horse cards — paired rows for equal height */}
      <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}>
        📋 全場馬匹分析
      </h2>

      {/* Column headers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr auto 1fr",
          gap: "8px",
          marginBottom: "8px",
        }}
      >
        {analysts.map((analyst) => {
          const isKelvin = analyst.toLowerCase() === "kelvin";
          const horses = data.analyses[analyst]?.horses || [];
          return [
            <div key={`${analyst}-spacer`} style={{ width: "32px" }} />,
            <div
              key={analyst}
              className={`comparison__header comparison__header--${isKelvin ? "kelvin" : "heison"}`}
              style={{ borderRadius: "8px" }}
            >
              {analyst} · {horses.length} 匹馬
            </div>,
          ];
        })}
      </div>

      {/* Paired rows */}
      {(() => {
        // Build sorted lists per analyst
        const sortedLists = analysts.map((analyst) => {
          const horses = data.analyses[analyst]?.horses || [];
          const picks = data.analyses[analyst]?.top_picks || [];
          const sorted = [...horses].sort((a, b) => {
            const aRank = picks.findIndex(
              (p) => p.horse_number === a.horse_number,
            );
            const bRank = picks.findIndex(
              (p) => p.horse_number === b.horse_number,
            );
            if (aRank >= 0 && bRank >= 0) return aRank - bRank;
            if (aRank >= 0) return -1;
            if (bRank >= 0) return 1;
            return sortByGrade(a.final_grade, b.final_grade);
          });
          return { sorted, picks };
        });

        const maxLen = Math.max(...sortedLists.map((s) => s.sorted.length));
        const rows = [];

        for (let i = 0; i < maxLen; i++) {
          rows.push(
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr auto 1fr",
                gap: "8px",
                marginBottom: "8px",
                alignItems: "stretch",
              }}
            >
              {sortedLists.map((list, colIdx) => {
                const horse = list.sorted[i];
                const picks = list.picks;
                if (!horse)
                  return [
                    <div
                      key={`${colIdx}-empty-rank`}
                      style={{ width: "32px" }}
                    />,
                    <div key={`${colIdx}-empty`} />,
                  ];
                return [
                  <div
                    key={`${colIdx}-rank`}
                    style={{
                      width: "32px",
                      minWidth: "32px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 800,
                      fontSize: "0.8rem",
                      color: i < 4 ? "#fff" : "#64748B",
                      background:
                        i === 0
                          ? "#D97706"
                          : i === 1
                            ? "#9CA3AF"
                            : i === 2
                              ? "#B45309"
                              : i === 3
                                ? "#2563EB"
                                : "#F8FAFC",
                      borderRadius: "6px",
                    }}
                  >
                    #{i + 1}
                  </div>,
                  <div key={`${colIdx}-card`} style={{ minWidth: 0 }}>
                    <HorseCard
                      horse={horse}
                      topPickRank={
                        picks.find((p) => p.horse_number === horse.horse_number)
                          ?.rank
                      }
                      primaryCondition={
                        data.analyses[analyst]?.primary_condition
                      }
                    />
                  </div>,
                ];
              })}
            </div>,
          );
        }
        return rows;
      })()}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Single Analyst View — horse grid
   ═══════════════════════════════════════════ */

function SingleAnalystView({ analysis, analystName }) {
  if (!analysis) return null;

  const horses = analysis.horses || [];
  const picks = (analysis.top_picks || []).map((pick) =>
    withRunnerMetadata(pick, horses),
  );
  const isKelvin = (analystName || "").toLowerCase() === "kelvin";

  // Sort by top_pick rank first, then by grade
  const sortedHorses = [...horses].sort((a, b) => {
    const aRank = picks.findIndex((p) => p.horse_number === a.horse_number);
    const bRank = picks.findIndex((p) => p.horse_number === b.horse_number);
    if (aRank >= 0 && bRank >= 0) return aRank - bRank;
    if (aRank >= 0) return -1;
    if (bRank >= 0) return 1;
    return sortByGrade(a.final_grade, b.final_grade);
  });

  return (
    <div>
      {/* Monte Carlo Panel */}
      {analysis.monte_carlo_results && analysis.monte_carlo_results.length > 0 && (
        <MonteCarloPanel results={analysis.monte_carlo_results} analystName={analystName} />
      )}

      {/* Full horse cards — single column in comparison-style card */}
      <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}>
        📋 全場馬匹分析
      </h2>
      <div className="comparison__column">
        <div
          className={`comparison__header comparison__header--${isKelvin ? "kelvin" : "heison"}`}
        >
          {analystName || "Analyst"} · {horses.length} 匹馬
        </div>
        <div className="comparison__body">
          <div className="horse-grid" style={{ gridTemplateColumns: "1fr" }}>
            {sortedHorses.map((horse, idx) => (
              <div
                key={horse.horse_number}
                style={{ display: "flex", gap: "8px", alignItems: "stretch" }}
              >
                <div
                  style={{
                    width: "32px",
                    minWidth: "32px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 800,
                    fontSize: "0.8rem",
                    color: idx < 4 ? "#fff" : "#64748B",
                    background:
                      idx === 0
                        ? "#D97706"
                        : idx === 1
                          ? "#9CA3AF"
                          : idx === 2
                            ? "#B45309"
                            : idx === 3
                              ? "#2563EB"
                              : "#F8FAFC",
                    borderRadius: "6px",
                    flexShrink: 0,
                  }}
                >
                  #{idx + 1}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <HorseCard
                    horse={horse}
                    topPickRank={
                      picks.find((p) => p.horse_number === horse.horse_number)
                        ?.rank
                    }
                    primaryCondition={primaryCond}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   MonteCarloPanel — MC simulation results with ranking comparison
   ═══════════════════════════════════════════ */
function MonteCarloPanel({ results, analystName }) {
  if (!results || results.length === 0) return null;

  const agreementColor = (ag) => {
    if (!ag) return "#94A3B8";
    if (ag.includes("✅")) return "#10B981";
    if (ag.includes("🔄")) return "#3B82F6";
    if (ag.includes("⚠️")) return "#F59E0B";
    if (ag.includes("❌")) return "#EF4444";
    if (ag.includes("🆕")) return "#0D9488";
    return "#94A3B8";
  };

  const maxProb = Math.max(...results.map((r) => r.win_prob || 0));

  return (
    <div className="mc-panel" style={{ marginBottom: "24px" }}>
      <div className="mc-panel__header">
        <span>🎲 Monte Carlo 概率模擬</span>
        <span className="mc-panel__badge">10,000 次模擬</span>
      </div>
      <div className="mc-panel__body">
        <div style={{ overflowX: "auto" }}>
          <table className="mc-panel__table">
            <thead>
              <tr>
                <th>MC排名</th>
                <th>馬號</th>
                <th>馬名</th>
                <th>MC 勝率</th>
                <th>MC獨贏</th>
                <th>入三甲%</th>
                <th>MC位置</th>
                <th>入四甲%</th>
                <th>法證排名</th>
                <th>差異</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => {
                const barWidth = maxProb > 0 ? ((r.win_prob || 0) / maxProb) * 100 : 0;
                const rankIcons = ["🥇", "🥈", "🥉", "🏅"];
                const mcIcon = rankIcons[i] || `#${r.mc_rank || i + 1}`;
                const origIcon = r.original_rank
                  ? rankIcons[r.original_rank - 1] || `#${r.original_rank}`
                  : "—";
                return (
                  <tr key={r.horse_num || i} className={i < 4 ? "mc-panel__row--top" : ""}>
                    <td style={{ fontWeight: 700 }}>{mcIcon}</td>
                    <td style={{ color: "#64748B" }}>{r.horse_num || "—"}</td>
                    <td style={{ fontWeight: 600 }}>{r.name}</td>
                    <td>
                      <div className="mc-panel__bar-wrap">
                        <div
                          className="mc-panel__bar"
                          style={{
                            width: `${barWidth}%`,
                            background: i === 0 ? "linear-gradient(90deg,#D97706,#F59E0B)" :
                                        i === 1 ? "linear-gradient(90deg,#6B7280,#9CA3AF)" :
                                        i === 2 ? "linear-gradient(90deg,#92400E,#B45309)" :
                                        "linear-gradient(90deg,#1D4ED8,#3B82F6)",
                          }}
                        />
                        <span className="mc-panel__prob">{r.win_prob?.toFixed(1)}%</span>
                      </div>
                    </td>
                    <td style={{ fontFamily: "monospace", color: "#0F766E", fontWeight: 600 }}>
                      {r.predicted_odds ? `$${r.predicted_odds.toFixed(1)}` : "—"}
                    </td>
                    <td style={{ color: "#475569" }}>
                      {r.top3_pct != null ? `${r.top3_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: "#0891B2", fontWeight: 600 }}>
                      {r.predicted_place_odds ? `$${r.predicted_place_odds.toFixed(1)}` : "—"}
                    </td>
                    <td style={{ color: "#64748B" }}>
                      {r.top4_pct != null ? `${r.top4_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td>{origIcon}</td>
                    <td>
                      <span
                        className="mc-panel__agreement"
                        style={{ color: agreementColor(r.agreement) }}
                      >
                        {r.agreement || "—"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mc-panel__note">
          🐍 由 Monte Carlo V2 Engine 自動計算 · 偏態分佈 + 近態衰減 + 步速互動
        </p>
      </div>
    </div>
  );
}

const GRADE_ORDER = [
  "S",
  "A+",
  "A",
  "A-",
  "B+",
  "B",
  "B-",
  "C+",
  "C",
  "C-",
  "D+",
  "D",
  "D-",
];
function sortByGrade(a, b) {
  const ai = GRADE_ORDER.indexOf(a);
  const bi = GRADE_ORDER.indexOf(b);
  return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
}
