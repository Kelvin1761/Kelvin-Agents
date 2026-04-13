import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import RatingBadge from "../components/RatingBadge";

/**
 * Merge races across analysts into a single deduplicated list.
 * Uses the first analyst's data (Kelvin preferred) for display.
 */
function getMergedRaces(racesData) {
  // Multi-analyst view
  if (racesData.races_by_analyst) {
    const merged = new Map();
    // Prefer Kelvin first, then others
    const analysts = Object.keys(racesData.races_by_analyst);
    const preferred = analysts.includes("Kelvin")
      ? ["Kelvin", ...analysts.filter((a) => a !== "Kelvin")]
      : analysts;

    for (const analyst of preferred) {
      for (const race of racesData.races_by_analyst[analyst] || []) {
        if (!merged.has(race.race_number)) {
          merged.set(race.race_number, race);
        }
      }
    }
    return [...merged.values()].sort((a, b) => a.race_number - b.race_number);
  }
  // Single analyst
  return racesData.races || [];
}
/**
 * DashboardPage — Main dashboard with meeting selector and race board.
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState([]);
  const [selected, setSelected] = useState(null);
  const [races, setRaces] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const lastUpdatedRef = useRef(null);

  // Refresh data helper
  const refreshData = useCallback(() => {
    api
      .getMeetings()
      .then((data) => {
        setMeetings(data.meetings || []);
        if (data.meetings?.length > 0) {
          setSelected((prev) => {
            const match = data.meetings.find(
              (m) => prev && m.date === prev.date && m.venue === prev.venue,
            );
            return match || data.meetings[0];
          });
        }
      })
      .catch(() => {});
  }, []);

  // Load meetings
  useEffect(() => {
    api
      .getMeetings()
      .then((data) => {
        setMeetings(data.meetings || []);
        if (data.meetings?.length > 0) {
          setSelected(data.meetings[0]);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Load races when meeting selected
  useEffect(() => {
    if (!selected) return;
    setRaces(null);
    api
      .getRaces(selected.date, selected.venue)
      .then((data) => setRaces(data))
      .catch((err) => setError(err.message));
  }, [selected]);

  // Poll for changes every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      api
        .getStatus()
        .then((status) => {
          if (
            lastUpdatedRef.current !== null &&
            status.last_updated !== lastUpdatedRef.current
          ) {
            // New analysis detected!
            setToast("🔄 新分析已偵測到，已自動更新");
            refreshData();
            if (selected) {
              api
                .getRaces(selected.date, selected.venue)
                .then((data) => setRaces(data))
                .catch(() => {});
            }
            setTimeout(() => setToast(null), 4000);
          }
          lastUpdatedRef.current = status.last_updated;
        })
        .catch(() => {});
    }, 30000);
    // Initial fetch to set baseline
    api
      .getStatus()
      .then((s) => {
        lastUpdatedRef.current = s.last_updated;
      })
      .catch(() => {});
    return () => clearInterval(interval);
  }, [selected, refreshData]);

  if (loading)
    return (
      <div className="loading">
        <div className="loading__spinner" />
      </div>
    );
  if (error)
    return (
      <div className="empty-state">
        <div className="empty-state__icon">⚠️</div>
        <div className="empty-state__text">{error}</div>
      </div>
    );

  return (
    <div>
      {/* Auto-refresh toast */}
      {toast && (
        <div
          style={{
            position: "fixed",
            top: "70px",
            left: "50%",
            transform: "translateX(-50%)",
            background: "linear-gradient(135deg, #059669, #10B981)",
            color: "#fff",
            padding: "10px 24px",
            borderRadius: "10px",
            fontSize: "0.85rem",
            fontWeight: 600,
            boxShadow: "0 4px 16px rgba(5,150,105,0.3)",
            zIndex: 9999,
            animation: "slideDown 0.3s ease-out",
          }}
        >
          {toast}
        </div>
      )}
      {/* Meeting Selector */}
      <div className="meeting-selector">
        {meetings.map((m, i) => (
          <div
            key={i}
            className={`meeting-card card--clickable ${selected === m ? "selected" : ""}`}
            onClick={() => setSelected(m)}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div className="meeting-card__date">{m.date}</div>
              <span className={`badge badge--region-${m.region}`}>
                {m.region === "hkjc" ? "🇭🇰 HKJC" : "🇦🇺 AU"}
              </span>
            </div>
            <div className="meeting-card__venue">📍 {m.venue}</div>
            <div className="meeting-card__analysts">
              {m.analysts.map((a) => (
                <span key={a} className="badge badge--b">
                  {a}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Race Board — merged R1-R10 (no analyst separation) */}
      {selected && races && (
        <div>
          <h2
            style={{
              margin: "24px 0 8px",
              fontSize: "1.1rem",
              fontWeight: 700,
            }}
          >
            {selected.region === "hkjc" ? "🇭🇰" : "🇦🇺"} {selected.venue} ·{" "}
            {selected.date}
            {selected.analysts?.length > 1 && (
              <span
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 400,
                  color: "#64748B",
                  marginLeft: "8px",
                }}
              >
                ({selected.analysts.join(" + ")} 分析)
              </span>
            )}
          </h2>

          <div className="race-board">
            {getMergedRaces(races).map((race) => (
              <div
                key={race.race_number}
                className="race-tile card--clickable"
                onClick={() =>
                  navigate(
                    `/race/${selected.date}/${selected.venue}/${race.race_number}`,
                  )
                }
              >
                <div className="race-tile__number">R{race.race_number}</div>
                {race.race_name && (
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
                    {race.race_name}
                  </div>
                )}
                <div
                  className="race-tile__info"
                  style={{ marginTop: race.race_name ? "2px" : "4px" }}
                >
                  {race.distance || "—"} {race.race_class || ""}
                </div>
                <div
                  style={{
                    fontSize: "0.7rem",
                    color: "#94A3B8",
                    marginTop: "4px",
                  }}
                >
                  🐴 {race.horses_count} 匹馬
                </div>
                <div
                  style={{
                    marginTop: "8px",
                    fontSize: "0.7rem",
                    color: "#3B82F6",
                    fontWeight: 600,
                  }}
                >
                  查看分析 →
                </div>
              </div>
            ))}
          </div>

          {/* Per-race betting panel */}
          <MeetingBettingPanel
            date={selected.date}
            venue={selected.venue}
            region={selected.region}
            races={getMergedRaces(races)}
          />
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Meeting Betting Panel — Quick bet overview for all races
   ═══════════════════════════════════════════ */

function MeetingBettingPanel({ date, venue, region, races }) {
  const [raceData, setRaceData] = useState({}); // raceNum -> { consensus, bets }
  const [oddsInput, setOddsInput] = useState({});
  const [oddsConfirmed, setOddsConfirmed] = useState({}); // key -> confirmed odds value
  const [scratchedHorses, setScratchedHorses] = useState({}); // key -> true
  const [skippedHorses, setSkippedHorses] = useState([]); // { raceNum, horse_number, horse_name, jockey, trainer, grade, odds }
  const [collapsedRaces, setCollapsedRaces] = useState({}); // tracks which races are collapsed
  const navigate = useNavigate();
  const tGoing = (s) => (s || '').replace(/\s*[（(].*$/, '').trim() || s;

  // Load consensus + bets for all races
  useEffect(() => {
    if (!races?.length) return;
    const newData = {};
    Promise.all(
      races.map((race) =>
        Promise.all([
          api.getConsensus(date, venue, race.race_number).catch(() => null),
          api
            .getBetsByRace(date, venue, race.race_number)
            .catch(() => ({ bets: [] })),
        ]).then(([consensus, betsRes]) => {
          newData[race.race_number] = {
            consensus: consensus?.consensus || null,
            bets: betsRes?.bets || [],
          };
        }),
      ),
    ).then(() => setRaceData({ ...newData }));
  }, [date, venue, races]);

  // Phase 1: Lock in odds
  const handleConfirmOdds = (raceNum, horseNum) => {
    const key = `${raceNum}-${horseNum}`;
    const odds = parseFloat(oddsInput[key]);
    if (!odds || odds <= 0) return alert("請輸入有效賠率");
    setOddsConfirmed((prev) => ({ ...prev, [key]: odds }));
  };

  // Phase 2: Place the bet
  const handlePlaceBet = async (race, candidate) => {
    const raceNum = race.race_number;
    const key = `${raceNum}-${candidate.horse_number}`;
    const odds = oddsConfirmed[key];
    if (!odds) return;

    // Prevent duplicate: check if bet already exists for this horse in this race
    const existingBets = raceData[raceNum]?.bets || [];
    if (existingBets.some(b => b.horse_number === candidate.horse_number)) return;

    // Clear confirmed odds IMMEDIATELY to prevent dual-track double-click
    setOddsConfirmed((prev) => { const n = { ...prev }; delete n[key]; return n; });

    await api.placeBet({
      date, venue, region,
      race_number: raceNum,
      horse_number: candidate.horse_number,
      horse_name: candidate.horse_name,
      bet_type: "place", stake: 1, odds,
      jockey: candidate.jockey, trainer: candidate.trainer,
      consensus_type: candidate.consensus_type,
      kelvin_grade: candidate.kelvin_grade,
      heison_grade: candidate.heison_grade,
      track_type: race.track, going: race.going,
    });

    const betsRes = await api.getBetsByRace(date, venue, raceNum).catch(() => ({ bets: [] }));
    setRaceData((prev) => ({ ...prev, [raceNum]: { ...prev[raceNum], bets: betsRes?.bets || [] } }));
  };

  // Skip bet (dismiss confirmed odds + record as 放棄馬)
  const handleSkipBet = (raceNum, horseNum, candidate) => {
    const key = `${raceNum}-${horseNum}`;
    const odds = oddsConfirmed[key];
    setOddsConfirmed((prev) => { const n = { ...prev }; delete n[key]; return n; });
    if (candidate) {
      setSkippedHorses((prev) => {
        // Avoid duplicates
        if (prev.some(s => s.raceNum === raceNum && s.horse_number === horseNum)) return prev;
        return [...prev, {
          raceNum, horse_number: horseNum, horse_name: candidate.horse_name,
          jockey: candidate.jockey, trainer: candidate.trainer,
          grade: candidate.kelvin_grade || candidate.heison_grade, odds: odds || '',
        }];
      });
    }
  };

  // Edit odds (go back to input)
  const handleEditOdds = (raceNum, horseNum) => {
    const key = `${raceNum}-${horseNum}`;
    setOddsConfirmed((prev) => { const n = { ...prev }; delete n[key]; return n; });
  };

  // Mark horse as scratched
  const handleScratch = (raceNum, horseNum) => {
    const key = `${raceNum}-${horseNum}`;
    setScratchedHorses((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleResult = async (raceNum, betId, position, odds) => {
    const isPlaced = position >= 1 && position <= 3;
    const payout = isPlaced ? 1 * odds : 0;
    await api.updateBetResult(betId, { result_position: position, payout });
    const betsRes = await api
      .getBetsByRace(date, venue, raceNum)
      .catch(() => ({ bets: [] }));
    setRaceData((prev) => ({
      ...prev,
      [raceNum]: { ...prev[raceNum], bets: betsRes?.bets || [] },
    }));
  };

  const handleDelete = async (raceNum, betId) => {
    if (!confirm("確認刪除此投注？")) return;
    await api.deleteBet(betId);
    const betsRes = await api
      .getBetsByRace(date, venue, raceNum)
      .catch(() => ({ bets: [] }));
    setRaceData((prev) => ({
      ...prev,
      [raceNum]: { ...prev[raceNum], bets: betsRes?.bets || [] },
    }));
  };

  // Always show betting panel when we have race data loaded
  const hasRaceData = Object.keys(raceData).length > 0;
  if (!hasRaceData) return null;

  return (
    <div style={{ marginTop: "24px" }}>
      <h3
        style={{
          fontSize: "0.95rem",
          fontWeight: 700,
          marginBottom: "12px",
          color: "#334155",
        }}
      >
        🎯 投注面板{" "}
        <span
          style={{ fontWeight: 500, fontSize: "0.75rem", color: "#92400E" }}
        >
          $1 平注制
        </span>
      </h3>

      {races.map((race) => {
        const rd = raceData[race.race_number];
        if (!rd) return null;

        const consensusHorses = rd.consensus?.consensus_horses || [];

        // Build candidates: AU uses scenario_top_picks (deduped top-2 each), HKJC uses consensus top-2
        let candidates = [];
        if (region === "au") {
          // Dual-track: 2 primary + 2 alternate = 4 candidates
          if (race.is_dual_track && race.alt_top_picks && race.alt_top_picks.length > 0) {
            const primaryLabel = tGoing(race.primary_condition);
            const altLabel = tGoing(race.alt_condition);
            
            (race.top_picks || [])
              .filter((p) => p.rank <= 2)
              .forEach((p) => {
                const kHorse = race.horses?.find(
                  (kh) => kh.horse_number === p.horse_number,
                );
                candidates.push({
                  horse_number: p.horse_number,
                  horse_name: p.horse_name,
                  kelvin_grade: p.grade,
                  heison_grade: null,
                  jockey: kHorse?.jockey || null,
                  trainer: kHorse?.trainer || null,
                  scenario: race.primary_condition,
                  consensus_type: `預期 (${primaryLabel}) Top ${p.rank}`,
                });
              });
            
            (race.alt_top_picks || [])
              .filter((p) => p.rank <= 2)
              .forEach((p) => {
                const kHorse = race.horses?.find(
                  (kh) => kh.horse_number === p.horse_number,
                );
                candidates.push({
                  horse_number: p.horse_number,
                  horse_name: p.horse_name,
                  kelvin_grade: p.grade,
                  heison_grade: null,
                  jockey: kHorse?.jockey || null,
                  trainer: kHorse?.trainer || null,
                  scenario: race.alt_condition,
                  consensus_type: `備選 (${altLabel}) Top ${p.rank}`,
                });
              });
          } else {
            (race.top_picks || [])
              .filter((p) => p.rank <= 2)
              .forEach((p) => {
                const kHorse = race.horses?.find(
                  (kh) => kh.horse_number === p.horse_number,
                );
                candidates.push({
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
          candidates = consensusHorses
            .filter((h) => h.is_top2_consensus)
            .map((h) => {
              let jockey = h.jockey || null,
                trainer = h.trainer || null;
              const kHorse = race.horses?.find(
                (kh) => kh.horse_number === h.horse_number,
              );
              if (kHorse) {
                jockey = kHorse.jockey || jockey;
                trainer = kHorse.trainer || trainer;
              }
              return {
                horse_number: h.horse_number,
                horse_name: h.horse_name,
                kelvin_grade: h.kelvin_grade,
                heison_grade: h.heison_grade,
                jockey,
                trainer,
                scenario: null,
                consensus_type: "Top 2 共識",
              };
            });
        }

        const bets = rd.bets || [];

        if (candidates.length === 0 && bets.length === 0) {
          // Show collapsed row with 0 候選
          return (
            <div
              key={race.race_number}
              className="card"
              style={{
                marginBottom: "4px",
                padding: 0,
                overflow: "hidden",
                opacity: 0.6,
              }}
            >
              <div
                style={{
                  padding: "10px 16px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontFamily: "Inter, sans-serif",
                }}
              >
                <div
                  style={{ display: "flex", alignItems: "center", gap: "10px" }}
                >
                  <span
                    style={{
                      fontWeight: 800,
                      fontSize: "0.95rem",
                      color: "#94A3B8",
                      background: "#F1F5F9",
                      padding: "2px 8px",
                      borderRadius: "6px",
                    }}
                  >
                    R{race.race_number}
                  </span>
                  <span style={{ fontSize: "0.8rem", color: "#94A3B8" }}>
                    {race.distance} {race.race_class}
                  </span>
                  <span style={{ fontSize: "0.7rem", color: "#CBD5E1" }}>
                    0 候選
                  </span>
                </div>
              </div>
            </div>
          );
        }

        const isCollapsed = collapsedRaces[race.race_number] === true;
        const totalProfit = bets.reduce(
          (sum, b) => sum + (b.net_profit || 0),
          0,
        );
        const hasBets = bets.length > 0;

        return (
          <div
            key={race.race_number}
            className="card"
            style={{ marginBottom: "8px", padding: 0, overflow: "hidden" }}
          >
            <button
              onClick={() =>
                setCollapsedRaces(prev => ({...prev, [race.race_number]: !prev[race.race_number]}))
              }
              style={{
                width: "100%",
                padding: "12px 16px",
                background: "none",
                border: "none",
                cursor: "pointer",
                textAlign: "left",
                fontFamily: "Inter, sans-serif",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div
                style={{ display: "flex", alignItems: "center", gap: "10px" }}
              >
                <span
                  style={{
                    fontWeight: 800,
                    fontSize: "0.95rem",
                    color: "#1E40AF",
                    background: "#EFF6FF",
                    padding: "2px 8px",
                    borderRadius: "6px",
                  }}
                >
                  R{race.race_number}
                </span>
                <span style={{ fontSize: "0.8rem", color: "#64748B" }}>
                  {race.distance} {race.race_class}
                </span>
                {candidates.length > 0 && (
                  <span
                    style={{
                      fontSize: "0.7rem",
                      color: "#059669",
                      fontWeight: 600,
                    }}
                  >
                    {candidates.length} 候選
                  </span>
                )}
                {hasBets && (
                  <span
                    style={{
                      fontSize: "0.7rem",
                      color: "#D97706",
                      fontWeight: 600,
                    }}
                  >
                    {bets.length} 注
                  </span>
                )}
              </div>
              <div
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                {hasBets && (
                  <span
                    style={{
                      fontWeight: 700,
                      fontSize: "0.85rem",
                      color: totalProfit >= 0 ? "#059669" : "#DC2626",
                    }}
                  >
                    {totalProfit >= 0 ? "+" : ""}${totalProfit.toFixed(2)}
                  </span>
                )}
                <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>
                  {isCollapsed ? "▼" : "▲"}
                </span>
              </div>
            </button>

            {!isCollapsed && (
              <div
                style={{ borderTop: "1px solid #F1F5F9", padding: "12px 16px" }}
              >
                {/* Candidates — dual column for dual-track */}
                {race.is_dual_track && race.alt_top_picks?.length > 0 ? (() => {
                  const primaryCands = candidates.filter(c => c.scenario === race.primary_condition);
                  const altCands = candidates.filter(c => c.scenario === race.alt_condition);
                  const primaryLabel = tGoing(race.primary_condition);
                  const altLabel = tGoing(race.alt_condition);
                  
                  const renderCandidateCard = (c) => {
                    const bet = bets.find((b) => b.horse_number === c.horse_number);
                    const key = `${race.race_number}-${c.horse_number}`;
                    const isScratched = scratchedHorses[key];
                    const confirmedOdds = oddsConfirmed[key];
                    return (
                      <div key={c.horse_number} style={{
                        background: isScratched ? "#F8FAFC" : "#fff", borderRadius: "10px",
                        padding: "12px 14px", marginBottom: "8px",
                        border: isScratched ? "1px solid #E2E8F0" : "1px solid #DBEAFE",
                        opacity: isScratched ? 0.5 : 1,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <div style={{ width: "32px", height: "32px", background: "#059669", color: "#fff", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: "0.9rem", flexShrink: 0 }}>{c.horse_number}</div>
                            <div>
                              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{c.horse_name}</div>
                              <div style={{ fontSize: "0.7rem", color: "#94A3B8", marginTop: "2px" }}>
                                {c.jockey && <span>🏇 {c.jockey}</span>}
                                {c.trainer && <span> · 🏠 {c.trainer}</span>}
                              </div>
                            </div>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            {c.kelvin_grade && <RatingBadge grade={c.kelvin_grade} />}
                            <button onClick={() => navigate(`/race/${date}/${venue}/${race.race_number}`)}
                              style={{ padding: "3px 8px", background: "#EFF6FF", color: "#1E40AF", border: "1px solid #BFDBFE", borderRadius: "6px", fontSize: "0.65rem", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
                              查看分析→
                            </button>
                          </div>
                        </div>
                        {isScratched ? (
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "0.8rem", color: "#94A3B8", fontWeight: 600 }}>🚫 已退出</span>
                            <button onClick={() => handleScratch(race.race_number, c.horse_number)}
                              style={{ padding: "3px 8px", background: "#F1F5F9", color: "#64748B", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.65rem", cursor: "pointer" }}>
                              撤銷
                            </button>
                          </div>
                        ) : !bet ? (
                          confirmedOdds ? (
                            <div>
                              <div style={{ fontSize: "0.75rem", color: "#334155", marginBottom: "6px" }}>
                                賠率已確認 @{confirmedOdds} — 是否投注？
                              </div>
                              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                <button onClick={() => handlePlaceBet(race, c)}
                                  style={{ padding: "4px 12px", background: "#059669", color: "#fff", border: "none", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  💰 投注
                                </button>
                                <button onClick={() => handleSkipBet(race.race_number, c.horse_number, c)}
                                  style={{ padding: "4px 12px", background: "#F1F5F9", color: "#64748B", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}>
                                  📋 唔投
                                </button>
                                <button onClick={() => handleEditOdds(race.race_number, c.horse_number)}
                                  style={{ padding: "4px 12px", background: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}>
                                  ✏️ 改賠率
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <div style={{ fontSize: "0.7rem", color: "#94A3B8", marginBottom: "4px" }}>⊙ 輸入賠率</div>
                              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                <input type="number" step="0.1" min="1" placeholder="賠率"
                                  value={oddsInput[key] || ""}
                                  onChange={(e) => setOddsInput((prev) => ({ ...prev, [key]: e.target.value }))}
                                  style={{ width: "60px", padding: "4px 6px", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.75rem", textAlign: "center" }}
                                />
                                <button onClick={() => handleConfirmOdds(race.race_number, c.horse_number)}
                                  style={{ padding: "4px 12px", background: "#1E40AF", color: "#fff", border: "none", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  🔒 確認賠率
                                </button>
                              </div>
                            </div>
                          )
                        ) : bet.status === "pending" ? (
                          <div>
                            <div style={{ fontSize: "0.75rem", color: "#334155", marginBottom: "6px" }}>
                              賠率已確認 @{bet.odds} — 等待結果
                            </div>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                              {[1,2,3].map(p => (
                                <button key={p} onClick={() => handleResult(race.race_number, bet.id, p, bet.odds)}
                                  style={{ padding: "4px 12px", background: "#EFF6FF", color: "#1E40AF", border: "1px solid #BFDBFE", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  {p}位
                                </button>
                              ))}
                              <button onClick={() => handleResult(race.race_number, bet.id, 0, bet.odds)}
                                style={{ padding: "4px 12px", background: "#FEF2F2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                ✗
                              </button>
                              <button onClick={() => handleScratch(race.race_number, c.horse_number)}
                                style={{ padding: "4px 12px", background: "#FEE2E2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}>
                                🚫 已退出
                              </button>
                              <button onClick={() => handleDelete(race.race_number, bet.id)}
                                style={{ padding: "4px 12px", background: "#F8FAFC", color: "#94A3B8", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.7rem", cursor: "pointer" }}>
                                🗑️
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", marginBottom: "6px" }}>
                              <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>@{bet.odds}</span>
                              <span style={{
                                padding: "2px 8px", borderRadius: "999px", fontSize: "0.65rem", fontWeight: 700,
                                background: bet.status === "won" ? "#D1FAE5" : "#FEE2E2",
                                color: bet.status === "won" ? "#059669" : "#DC2626",
                              }}>
                                {bet.status === "won" ? `✅ ${bet.result_position}位` : "❌"}
                              </span>
                              <span style={{ fontWeight: 800, fontSize: "0.8rem", color: bet.net_profit > 0 ? "#059669" : "#DC2626" }}>
                                {bet.net_profit > 0 ? "+" : ""}${(bet.net_profit || 0).toFixed(2)}
                              </span>
                            </div>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                              <span style={{ fontSize: "0.65rem", color: "#94A3B8" }}>更正:</span>
                              {[1,2,3].map(p => (
                                <button key={p} onClick={() => handleResult(race.race_number, bet.id, p, bet.odds)}
                                  style={{ padding: "4px 12px", background: bet.result_position === p ? "#DBEAFE" : "#EFF6FF", color: "#1E40AF", border: "1px solid #BFDBFE", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  {p}位
                                </button>
                              ))}
                              <button onClick={() => handleResult(race.race_number, bet.id, 0, bet.odds)}
                                style={{ padding: "4px 12px", background: bet.result_position === 0 ? "#FECACA" : "#FEF2F2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                ✗
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  };
                  
                  return (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "8px" }}>
                      <div style={{ border: "1px solid #D1FAE5", borderRadius: "8px", overflow: "hidden" }}>
                        <div style={{
                          padding: "6px 10px", background: "linear-gradient(135deg, #059669, #10B981)",
                          color: "#fff", fontWeight: 700, fontSize: "0.72rem",
                        }}>
                          預期場地 ({primaryLabel})
                        </div>
                        <div style={{ padding: "6px 10px" }}>
                          {primaryCands.map(renderCandidateCard)}
                        </div>
                      </div>
                      <div style={{ border: "1px solid #FDE68A", borderRadius: "8px", overflow: "hidden" }}>
                        <div style={{
                          padding: "6px 10px", background: "linear-gradient(135deg, #D97706, #F59E0B)",
                          color: "#fff", fontWeight: 700, fontSize: "0.72rem",
                        }}>
                          備選場地 ({altLabel})
                        </div>
                        <div style={{ padding: "6px 10px" }}>
                          {altCands.map(renderCandidateCard)}
                        </div>
                      </div>
                    </div>
                  );
                })() : (
                  /* Non dual-track: same production-style cards */
                  candidates.map((c) => {
                    const bet = bets.find((b) => b.horse_number === c.horse_number);
                    const key = `${race.race_number}-${c.horse_number}`;
                    const isScratched = scratchedHorses[key];
                    const confirmedOdds = oddsConfirmed[key];
                    return (
                      <div key={c.horse_number} style={{
                        background: isScratched ? "#F8FAFC" : "#fff", borderRadius: "10px",
                        padding: "12px 14px", marginBottom: "8px",
                        border: isScratched ? "1px solid #E2E8F0" : "1px solid #DBEAFE",
                        opacity: isScratched ? 0.5 : 1,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <div style={{ width: "32px", height: "32px", background: "#059669", color: "#fff", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: "0.9rem", flexShrink: 0 }}>{c.horse_number}</div>
                            <div>
                              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{c.horse_name}</div>
                              <div style={{ fontSize: "0.7rem", color: "#94A3B8", marginTop: "2px" }}>
                                {c.jockey && <span>🏇 {c.jockey}</span>}
                                {c.trainer && <span> · 🏠 {c.trainer}</span>}
                              </div>
                            </div>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            {c.kelvin_grade && <RatingBadge grade={c.kelvin_grade} />}
                            <button onClick={() => navigate(`/race/${date}/${venue}/${race.race_number}`)}
                              style={{ padding: "3px 8px", background: "#EFF6FF", color: "#1E40AF", border: "1px solid #BFDBFE", borderRadius: "6px", fontSize: "0.65rem", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
                              查看分析→
                            </button>
                          </div>
                        </div>
                        {isScratched ? (
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "0.8rem", color: "#94A3B8", fontWeight: 600 }}>🚫 已退出</span>
                            <button onClick={() => handleScratch(race.race_number, c.horse_number)}
                              style={{ padding: "3px 8px", background: "#F1F5F9", color: "#64748B", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.65rem", cursor: "pointer" }}>
                              撤銷
                            </button>
                          </div>
                        ) : !bet ? (
                          confirmedOdds ? (
                            <div>
                              <div style={{ fontSize: "0.75rem", color: "#334155", marginBottom: "6px" }}>
                                賠率已確認 @{confirmedOdds} — 是否投注？
                              </div>
                              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                <button onClick={() => handlePlaceBet(race, c)}
                                  style={{ padding: "4px 12px", background: "#059669", color: "#fff", border: "none", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  💰 投注
                                </button>
                                <button onClick={() => handleSkipBet(race.race_number, c.horse_number, c)}
                                  style={{ padding: "4px 12px", background: "#F1F5F9", color: "#64748B", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}>
                                  📋 唔投
                                </button>
                                <button onClick={() => handleEditOdds(race.race_number, c.horse_number)}
                                  style={{ padding: "4px 12px", background: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}>
                                  ✏️ 改賠率
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <div style={{ fontSize: "0.7rem", color: "#94A3B8", marginBottom: "4px" }}>⊙ 輸入賠率</div>
                              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                <input type="number" step="0.1" min="1" placeholder="賠率"
                                  value={oddsInput[key] || ""}
                                  onChange={(e) => setOddsInput((prev) => ({ ...prev, [key]: e.target.value }))}
                                  style={{ width: "60px", padding: "4px 6px", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.75rem", textAlign: "center" }}
                                />
                                <button onClick={() => handleConfirmOdds(race.race_number, c.horse_number)}
                                  style={{ padding: "4px 12px", background: "#1E40AF", color: "#fff", border: "none", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  🔒 確認賠率
                                </button>
                              </div>
                            </div>
                          )
                        ) : bet.status === "pending" ? (
                          <div>
                            <div style={{ fontSize: "0.75rem", color: "#334155", marginBottom: "6px" }}>
                              賠率已確認 @{bet.odds} — 等待結果
                            </div>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                              {[1,2,3].map(p => (
                                <button key={p} onClick={() => handleResult(race.race_number, bet.id, p, bet.odds)}
                                  style={{ padding: "4px 12px", background: "#EFF6FF", color: "#1E40AF", border: "1px solid #BFDBFE", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  {p}位
                                </button>
                              ))}
                              <button onClick={() => handleResult(race.race_number, bet.id, 0, bet.odds)}
                                style={{ padding: "4px 12px", background: "#FEF2F2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                ✗
                              </button>
                              <button onClick={() => handleScratch(race.race_number, c.horse_number)}
                                style={{ padding: "4px 12px", background: "#FEE2E2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}>
                                🚫 已退出
                              </button>
                              <button onClick={() => handleDelete(race.race_number, bet.id)}
                                style={{ padding: "4px 12px", background: "#F8FAFC", color: "#94A3B8", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.7rem", cursor: "pointer" }}>
                                🗑️
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", marginBottom: "6px" }}>
                              <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>@{bet.odds}</span>
                              <span style={{
                                padding: "2px 8px", borderRadius: "999px", fontSize: "0.65rem", fontWeight: 700,
                                background: bet.status === "won" ? "#D1FAE5" : "#FEE2E2",
                                color: bet.status === "won" ? "#059669" : "#DC2626",
                              }}>
                                {bet.status === "won" ? `✅ ${bet.result_position}位` : "❌"}
                              </span>
                              <span style={{ fontWeight: 800, fontSize: "0.8rem", color: bet.net_profit > 0 ? "#059669" : "#DC2626" }}>
                                {bet.net_profit > 0 ? "+" : ""}${(bet.net_profit || 0).toFixed(2)}
                              </span>
                            </div>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                              <span style={{ fontSize: "0.65rem", color: "#94A3B8" }}>更正:</span>
                              {[1,2,3].map(p => (
                                <button key={p} onClick={() => handleResult(race.race_number, bet.id, p, bet.odds)}
                                  style={{ padding: "4px 12px", background: bet.result_position === p ? "#DBEAFE" : "#EFF6FF", color: "#1E40AF", border: "1px solid #BFDBFE", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                  {p}位
                                </button>
                              ))}
                              <button onClick={() => handleResult(race.race_number, bet.id, 0, bet.odds)}
                                style={{ padding: "4px 12px", background: bet.result_position === 0 ? "#FECACA" : "#FEF2F2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: "6px", fontSize: "0.7rem", fontWeight: 700, cursor: "pointer" }}>
                                ✗
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}

                {/* Link to full analysis */}
                <div style={{ textAlign: "center", marginTop: "8px" }}>
                  <button
                    onClick={() =>
                      navigate(`/race/${date}/${venue}/${race.race_number}`)
                    }
                    style={{
                      padding: "6px 16px",
                      background: "#EFF6FF",
                      color: "#1E40AF",
                      border: "1px solid #BFDBFE",
                      borderRadius: "8px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    查看完整分析 →
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* ═══ Betting Records & Export ═══ */}
      {(() => {
        const allBets = Object.values(raceData).flatMap(rd => rd?.bets || []);
        const totalBets = allBets.length;
        const totalProfit = allBets.reduce((s, b) => s + (b.net_profit || 0), 0);
        const wins = allBets.filter(b => b.status === "won").length;
        const settled = allBets.filter(b => b.status === "won" || b.status === "lost").length;

        const exportBets = () => {
          const header = "日期,場地,區域,場次,距離,班級,馬號,馬名,騎師,練馬師,評級,賠率,名次,淨利,狀態";
          const rows = allBets.map(b => {
            const r = races.find(rc => rc.race_number === b.race_number);
            return [
              date, venue, region, b.race_number,
              r?.distance || "", r?.race_class || "",
              b.horse_number, b.horse_name,
              b.jockey || "", b.trainer || "",
              b.kelvin_grade || b.heison_grade || "",
              b.odds, b.result_position ?? "", b.net_profit ?? "", b.status
            ].map(v => `"${v}"`).join(",");
          });
          const csv = "\uFEFF" + [header, ...rows].join("\n");
          const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `投注記錄_${venue}_${date}.csv`;
          a.click();
          URL.revokeObjectURL(url);
        };

        const thStyle = { padding: "8px 10px", fontSize: "0.7rem", fontWeight: 700, color: "#64748B", textAlign: "left", borderBottom: "2px solid #E2E8F0" };
        const tdStyle = { padding: "7px 10px", fontSize: "0.75rem", color: "#334155", borderBottom: "1px solid #F1F5F9" };

        return (
          <div style={{ marginTop: "20px" }}>
            {/* Summary bar + export */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "#F8FAFC", borderRadius: "10px 10px 0 0", border: "1px solid #E2E8F0" }}>
              <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "#334155" }}>
                總計 {totalBets} 注 · 淨利{" "}
                <span style={{ color: totalProfit >= 0 ? "#059669" : "#DC2626", fontWeight: 800 }}>
                  {totalProfit >= 0 ? "+" : ""}${totalProfit.toFixed(2)}
                </span>
              </span>
              <button onClick={exportBets}
                style={{ padding: "6px 16px", background: "#1E40AF", color: "#fff", border: "none", borderRadius: "8px", fontSize: "0.75rem", fontWeight: 700, cursor: "pointer" }}>
                💾 匯出投注記錄
              </button>
            </div>

            {/* 📊 投注記錄 table */}
            {totalBets > 0 && (
              <div style={{ border: "1px solid #E2E8F0", borderTop: "none", borderRadius: "0 0 10px 10px", overflow: "hidden" }}>
                <div style={{ padding: "10px 16px", background: "#fff", borderBottom: "1px solid #E2E8F0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "#1E40AF" }}>
                    📊 投注記錄 · {venue} {date}
                  </span>
                  {settled > 0 && (
                    <span style={{ fontSize: "0.7rem", color: "#64748B" }}>
                      {wins}W/{settled - wins}L · ROI {totalBets > 0 ? ((totalProfit / totalBets) * 100).toFixed(1) : 0}%
                    </span>
                  )}
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "600px" }}>
                    <thead>
                      <tr style={{ background: "#F8FAFC" }}>
                        <th style={thStyle}>場次</th>
                        <th style={thStyle}>馬號</th>
                        <th style={thStyle}>馬匹</th>
                        <th style={thStyle}>騎師</th>
                        <th style={thStyle}>練馬師</th>
                        <th style={thStyle}>評級</th>
                        <th style={thStyle}>賠率</th>
                        <th style={thStyle}>名次</th>
                        <th style={thStyle}>淨利</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allBets.map((b, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? "#fff" : "#FAFBFC" }}>
                          <td style={tdStyle}>R{b.race_number}</td>
                          <td style={tdStyle}>#{b.horse_number}</td>
                          <td style={{ ...tdStyle, fontWeight: 600 }}>{b.horse_name}</td>
                          <td style={tdStyle}>{b.jockey || "-"}</td>
                          <td style={tdStyle}>{b.trainer || "-"}</td>
                          <td style={tdStyle}>
                            {b.kelvin_grade && <RatingBadge grade={b.kelvin_grade} />}
                            {b.heison_grade && <span style={{ marginLeft: "4px" }}><RatingBadge grade={b.heison_grade} /></span>}
                          </td>
                          <td style={tdStyle}>@{b.odds}</td>
                          <td style={tdStyle}>
                            {b.status === "pending" ? (
                              <span style={{ color: "#94A3B8" }}>-</span>
                            ) : b.status === "won" ? (
                              <span style={{ color: "#059669", fontWeight: 700 }}>{b.result_position}</span>
                            ) : (
                              <span style={{ color: "#DC2626", fontWeight: 700 }}>X</span>
                            )}
                          </td>
                          <td style={{ ...tdStyle, fontWeight: 700, color: (b.net_profit || 0) > 0 ? "#059669" : (b.net_profit || 0) < 0 ? "#DC2626" : "#94A3B8" }}>
                            {b.status === "pending" ? "-" : `${(b.net_profit || 0) > 0 ? "+" : ""}$${(b.net_profit || 0).toFixed(2)}`}
                          </td>
                        </tr>
                      ))}
                      <tr style={{ background: "#F8FAFC" }}>
                        <td colSpan={6} style={{ ...tdStyle, fontWeight: 700, borderBottom: "none" }}>
                          總計 {totalBets}注
                        </td>
                        <td style={{ ...tdStyle, borderBottom: "none" }}></td>
                        <td style={{ ...tdStyle, fontWeight: 700, borderBottom: "none" }}>
                          {settled > 0 ? `${wins}/${settled}` : "-"}
                        </td>
                        <td style={{ ...tdStyle, fontWeight: 800, borderBottom: "none", color: totalProfit >= 0 ? "#059669" : "#DC2626" }}>
                          {totalProfit >= 0 ? "+" : ""}${totalProfit.toFixed(2)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ❌ 放棄馬 table */}
            {skippedHorses.length > 0 && (
              <div style={{ marginTop: "16px", border: "1px solid #E2E8F0", borderRadius: "10px", overflow: "hidden" }}>
                <div style={{ padding: "10px 16px", background: "#FEF2F2", borderBottom: "1px solid #FECACA" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "#DC2626" }}>
                    ❌ 放棄馬 · {skippedHorses.length} 匹
                  </span>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "500px" }}>
                    <thead>
                      <tr style={{ background: "#FFFBEB" }}>
                        <th style={thStyle}>場次</th>
                        <th style={thStyle}>馬號</th>
                        <th style={thStyle}>馬匹</th>
                        <th style={thStyle}>騎師</th>
                        <th style={thStyle}>練馬師</th>
                        <th style={thStyle}>評級</th>
                        <th style={thStyle}>賠率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {skippedHorses.map((s, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? "#fff" : "#FAFBFC" }}>
                          <td style={tdStyle}>R{s.raceNum}</td>
                          <td style={tdStyle}>#{s.horse_number}</td>
                          <td style={{ ...tdStyle, fontWeight: 600 }}>{s.horse_name}</td>
                          <td style={tdStyle}>{s.jockey || "-"}</td>
                          <td style={tdStyle}>{s.trainer || "-"}</td>
                          <td style={tdStyle}>
                            {s.grade && <RatingBadge grade={s.grade} />}
                          </td>
                          <td style={tdStyle}>@{s.odds}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
