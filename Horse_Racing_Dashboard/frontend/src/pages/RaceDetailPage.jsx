import { useState, useEffect, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import HorseCard from "../components/HorseCard";

/** Trim long going strings: 'Soft 6 (天氣極不穩定...)' → 'Soft 6' */
function trimGoing(going) {
  if (!going) return going;
  // Remove parenthesized extra info
  const trimmed = going.replace(/\s*[（(].*$/, '').trim();
  return trimmed || going;
}
import RatingBadge from "../components/RatingBadge";

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
      {analysis?.battlefield_overview && (() => {
        const raw = analysis.battlefield_overview
          .replace(/^[#]+\s*/gm, "")
          .replace(/^\[第一部分\]\s*/gm, "")
          .replace(/^(?:🗺️|🌍)?\s*戰場全景(?:\s*\(Course & Environment\))?\s*/gm, "")
          .replace(/^(?:🗺️|🌍)?\s*賽事環境與 Speed Map 預判\s*/gm, "")
          .replace(/`/g, "")
          .replace(/^\s+/g, "")
          .trim();
        
        const lines = raw.split("\n");
        const infoChips = [];
        const speedMapGroups = {};
        const otherLines = [];
        let inSpeedMap = false;
        
        // Known chip field icons
        const chipIcons = {
          "場地": "🏟️", "賽道": "🏟️", "track": "🏟️", "venue": "🏟️",
          "距離": "📏", "distance": "📏",
          "場地狀況": "🌧️", "going": "🌧️", "場地評分": "🌧️",
          "班次": "🏷️", "class": "🏷️", "race_class": "🏷️",
          "彎道": "🔄", "rail": "🔄", "欄位": "🔄",
          "天氣": "☁️", "weather": "☁️",
          "起步位": "🚦", "barrier": "🚦",
          "跑道": "🛤️", "surface": "🛤️",
        };
        
        // Group classification for speed map
        const groupClassMap = {
          "領放": "lead", "前列": "lead", "帶": "lead",
          "前中": "mid-front", "緊跟": "mid-front",
          "中後": "mid-back", "中段": "mid-back",
          "後上": "back", "後段": "back", "包尾": "back",
        };
        
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || /^\|[-:\s|]+\|$/.test(trimmed)) continue;
          
          if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
            const cells = trimmed.split("|").filter(Boolean).map(c => c.replace(/\*{1,2}/g, "").trim());
            if (cells.length >= 2) {
              infoChips.push({ label: cells[0], value: cells.slice(1).join(" · ") });
            }
          } else if (/Speed Map|速度地圖|預判走位/.test(trimmed)) {
            inSpeedMap = true;
          } else if (inSpeedMap && trimmed.startsWith("-")) {
            const content = trimmed.replace(/^-\s*/, "").replace(/\*{1,2}/g, "");
            // Detect which group this belongs to
            const groupKey = Object.keys(groupClassMap).find(g => content.includes(g));
            const groupClass = groupKey ? groupClassMap[groupKey] : "mid-back";
            const groupLabel = groupKey || "中段";
            
            if (!speedMapGroups[groupClass]) {
              speedMapGroups[groupClass] = { label: groupLabel, horses: [] };
            }
            // Extract horse names/numbers from the line
            const afterColon = content.includes("：") ? content.split("：").slice(1).join("：") :
                               content.includes(":") ? content.split(":").slice(1).join(":") : content;
            const horseNames = afterColon.split(/[、,，]/).map(h => h.trim()).filter(h => h.length > 0);
            speedMapGroups[groupClass].horses.push(...horseNames);
          } else if (trimmed === "---") {
            continue;
          } else {
            if (inSpeedMap && !trimmed.startsWith("-")) inSpeedMap = false;
            otherLines.push(trimmed.replace(/\*{1,2}/g, ""));
          }
        }

        // Order for speed map lanes
        const laneOrder = ["lead", "mid-front", "mid-back", "back"];
        const laneLabels = { "lead": "領放", "mid-front": "前中", "mid-back": "中後", "back": "後上" };

        return (
          <div className="battlefield">
            <div className="battlefield__header">
              🗺️ 戰場全景
            </div>
            <div className="battlefield__body">
              {/* Info chips */}
              {infoChips.length > 0 && (
                <div className="battlefield__chips">
                  {infoChips.map((chip, i) => {
                    const iconKey = Object.keys(chipIcons).find(k => chip.label.toLowerCase().includes(k));
                    return (
                      <div key={i} className="battlefield__chip">
                        <span className="battlefield__chip-icon">
                          {iconKey ? chipIcons[iconKey] : "📋"}
                        </span>
                        <span className="battlefield__chip-label">{chip.label}</span>
                        <span className="battlefield__chip-value">{chip.value}</span>
                      </div>
                    );
                  })}
                </div>
              )}
              {/* Speed Map visual */}
              {Object.keys(speedMapGroups).length > 0 && (
                <div className="battlefield__speedmap">
                  <div className="battlefield__speedmap-title">
                    📍 Speed Map 預判走位
                  </div>
                  {laneOrder.map(laneKey => {
                    const group = speedMapGroups[laneKey];
                    if (!group || group.horses.length === 0) return null;
                    return (
                      <div key={laneKey} className={`battlefield__lane battlefield__lane--${laneKey}`}>
                        <span className="battlefield__lane-label">
                          {laneLabels[laneKey]}
                        </span>
                        <div className="battlefield__lane-horses">
                          {group.horses.map((horse, i) => (
                            <span key={i} className="battlefield__horse-pill">{horse}</span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {/* Other notes */}
              {otherLines.length > 0 && (
                <div className="battlefield__notes">
                  {otherLines.map((l, i) => <div key={i}>{l}</div>)}
                </div>
              )}
            </div>
          </div>
        );
      })()}

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
              }
            }

            return {
              horse_number: h.horse_number,
              horse_name: h.horse_name,
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
  }, [consensus, date, venue, raceNumber, region, loadBets]);

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
      track_type: raceData?.track,
      going: raceData?.going,
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
                <div className="bet-candidate__number">
                  {candidate.horse_number}
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                    {candidate.horse_name}
                  </div>
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
                <div className="bet-odds-input">
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
                </div>
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
   Comparison View — Vertical top picks per analyst + synchronized horse rows
   ═══════════════════════════════════════════ */

function ComparisonView({ data, analysts }) {
  return (
    <div>
      {/* Vertical Top Picks — side by side with ranking */}
      <div style={{ marginBottom: "24px" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}>
          🏆 Top Picks 對比
        </h2>
        <div className="comparison">
          {analysts.map((analyst) => {
            const analysis = data.analyses[analyst];
            if (!analysis) return null;
            const picks = analysis.top_picks || [];
            const altPicks = analysis.alt_top_picks || [];
            const isDualTrack = analysis.is_dual_track;
            const primaryCond = analysis.primary_condition || "預期場地";
            const altCond = analysis.alt_condition || "備選場地";
            const isKelvin = analyst.toLowerCase() === "kelvin";
            return (
              <div key={analyst} className="comparison__column">
                <div
                  className={`comparison__header comparison__header--${isKelvin ? "kelvin" : "heison"}`}
                >
                  {analyst}
                  {isDualTrack && (
                    <div
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: "normal",
                        opacity: 0.9,
                      }}
                    >
                      預期: {primaryCond} | 備選: {altCond}
                    </div>
                  )}
                </div>
                <div className="comparison__body" style={{ padding: 0 }}>
                  {picks.length === 0 ? (
                    <div
                      style={{
                        padding: "16px",
                        textAlign: "center",
                        color: "#94A3B8",
                        fontSize: "0.8rem",
                      }}
                    >
                      暫無 Top Picks 數據
                    </div>
                  ) : (
                    picks.map((pick, i) => (
                      <div
                        key={pick.rank}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "12px",
                          padding: "12px 16px",
                          borderBottom:
                            i < picks.length - 1 ? "1px solid #F1F5F9" : "none",
                        }}
                      >
                        {/* Rank medal */}
                        <div
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "8px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontWeight: 800,
                            fontSize: "0.9rem",
                            flexShrink: 0,
                            background:
                              i === 0
                                ? "#FEF3C7"
                                : i === 1
                                  ? "#F1F5F9"
                                  : i === 2
                                    ? "#FFF7ED"
                                    : "#EFF6FF",
                            color:
                              i === 0
                                ? "#D97706"
                                : i === 1
                                  ? "#6B7280"
                                  : i === 2
                                    ? "#B45309"
                                    : "#2563EB",
                          }}
                        >
                          {pick.rank}
                        </div>
                        {/* Horse info */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>
                            {pick.horse_name}
                          </div>
                          <div style={{ fontSize: "0.7rem", color: "#94A3B8" }}>
                            馬號 #{pick.horse_number}
                          </div>
                        </div>
                        {/* Grade */}
                        <RatingBadge grade={pick.grade} size="lg" />
                      </div>
                    ))
                  )}

                  {/* Alternate Top Picks for Dual Track */}
                  {isDualTrack && altPicks.length > 0 && (
                    <>
                      <div
                        style={{
                          padding: "8px 16px",
                          background: "#F8FAFC",
                          borderBottom: "1px solid #E2E8F0",
                          fontSize: "0.8rem",
                          fontWeight: 700,
                          color: "#475569",
                          textAlign: "center",
                        }}
                      >
                        🔄 備選場地 Top Picks ({altCond})
                      </div>
                      {altPicks.map((pick, i) => (
                        <div
                          key={`alt-${pick.rank}`}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "12px",
                            padding: "10px 16px",
                            borderBottom:
                              i < altPicks.length - 1
                                ? "1px solid #F1F5F9"
                                : "none",
                            background: "#FAFAF9",
                            opacity: 0.9,
                          }}
                        >
                          <div
                            style={{
                              width: "28px",
                              height: "28px",
                              borderRadius: "6px",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontWeight: 800,
                              fontSize: "0.8rem",
                              flexShrink: 0,
                              background: "#F1F5F9",
                              color: "#64748B",
                            }}
                          >
                            {pick.rank}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                fontWeight: 700,
                                fontSize: "0.85rem",
                                color: "#475569",
                              }}
                            >
                              {pick.horse_name}
                            </div>
                            <div
                              style={{ fontSize: "0.65rem", color: "#94A3B8" }}
                            >
                              馬號 #{pick.horse_number}
                            </div>
                          </div>
                          <RatingBadge grade={pick.grade} size="md" />
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

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
   Single Analyst View — Vertical top picks + horse grid
   ═══════════════════════════════════════════ */

function SingleAnalystView({ analysis, analystName }) {
  if (!analysis) return null;

  const picks = analysis.top_picks || [];
  const horses = analysis.horses || [];
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

  const altPicks = analysis.alt_top_picks || [];
  const isDualTrack = analysis.is_dual_track;
  const primaryCond = analysis.primary_condition || "預期場地";
  const altCond = analysis.alt_condition || "備選場地";

  return (
    <div>
      {/* Top Picks — side-by-side for dual track */}
      {(picks.length > 0 || altPicks.length > 0) && (
        <div style={{ marginBottom: "24px" }}>
          <h2
            style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}
          >
            🏆 Top Picks
            {isDualTrack && (
              <span style={{ fontSize: "0.75rem", fontWeight: 500, color: "#64748B", marginLeft: "8px" }}>
                (雙軌制：{trimGoing(primaryCond)} / {trimGoing(altCond)})
              </span>
            )}
          </h2>

          {isDualTrack && altPicks.length > 0 ? (
            /* ── Side-by-side dual-track layout (stacks on mobile) ── */
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px" }}>
              {/* Primary / 預期場地 */}
              <div className="comparison__column">
                <div
                  style={{
                    padding: "8px 16px",
                    background: "linear-gradient(135deg, #059669, #10B981)",
                    color: "#fff",
                    fontWeight: 700,
                    fontSize: "0.8rem",
                    borderRadius: "8px 8px 0 0",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  預期場地
                  <span style={{ fontWeight: 500, fontSize: "0.7rem", opacity: 0.9 }}>({trimGoing(primaryCond)})</span>
                </div>
                <div className="comparison__body" style={{ padding: 0 }}>
                  {picks.map((pick, i) => (
                    <PickRow key={pick.rank} pick={pick} index={i} isLast={i === picks.length - 1} />
                  ))}
                </div>
              </div>
              {/* Alternate / 備選場地 */}
              <div className="comparison__column">
                <div
                  style={{
                    padding: "8px 16px",
                    background: "linear-gradient(135deg, #D97706, #F59E0B)",
                    color: "#fff",
                    fontWeight: 700,
                    fontSize: "0.8rem",
                    borderRadius: "8px 8px 0 0",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  備選場地
                  <span style={{ fontWeight: 500, fontSize: "0.7rem", opacity: 0.9 }}>({trimGoing(altCond)})</span>
                </div>
                <div className="comparison__body" style={{ padding: 0 }}>
                  {altPicks.map((pick, i) => (
                    <PickRow key={`alt-${pick.rank}`} pick={pick} index={i} isLast={i === altPicks.length - 1} />
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* ── Single column (non dual-track) ── */
            <div className="comparison__column" style={{ maxWidth: "600px" }}>
              <div
                className={`comparison__header comparison__header--${isKelvin ? "kelvin" : "heison"}`}
              >
                {analystName || "Analyst"}
              </div>
              <div className="comparison__body" style={{ padding: 0 }}>
                {picks.map((pick, i) => (
                  <PickRow key={pick.rank} pick={pick} index={i} isLast={i === picks.length - 1} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

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
    if (ag.includes("🆕")) return "#8B5CF6";
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

/* ═══════════════════════════════════════════
   PickRow — Reusable Top Pick display row
   ═══════════════════════════════════════════ */
function PickRow({ pick, index, isLast }) {
  const medals = ["🥇", "🥈", "🥉", "🏅"];
  const bgColors = ["#FEF3C7", "#F1F5F9", "#FFF7ED", "#EFF6FF"];
  const fgColors = ["#D97706", "#6B7280", "#B45309", "#2563EB"];
  const i = index;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "10px 14px",
        borderBottom: isLast ? "none" : "1px solid #F1F5F9",
      }}
    >
      <div
        style={{
          width: "28px",
          height: "28px",
          borderRadius: "6px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 800,
          fontSize: "0.85rem",
          flexShrink: 0,
          background: bgColors[i] || "#EFF6FF",
          color: fgColors[i] || "#2563EB",
        }}
      >
        {pick.rank}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>
          {pick.horse_name}
        </div>
        <div style={{ fontSize: "0.65rem", color: "#94A3B8" }}>
          馬號 #{pick.horse_number}
        </div>
      </div>
      <span style={{ fontSize: "1rem" }}>
        {medals[i] || "🏅"}
      </span>
      <RatingBadge grade={pick.grade} size="md" />
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
