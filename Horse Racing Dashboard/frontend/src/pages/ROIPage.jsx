import { useState, useEffect } from "react";
import { api } from "../api/client";

/**
 * ROIPage — ROI analytics powered by HK/AU Horse Race Summary .numbers files.
 * Displays stats, P&L chart, side breakdowns, and per-session detail.
 */
export default function ROIPage() {
  const [roi, setRoi] = useState(null);
  const [regionFilter, setRegionFilter] = useState(null);
  const [expandedSession, setExpandedSession] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    setLoading(true);
    api
      .getSummaryROI(regionFilter)
      .then((data) => {
        setRoi(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [regionFilter]);

  if (loading)
    return (
      <div className="loading">
        <div className="loading__spinner" />
      </div>
    );

  return (
    <div>
      {/* Page header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "24px",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <h1
          style={{
            fontSize: "1.5rem",
            fontWeight: 800,
            letterSpacing: "-0.02em",
          }}
        >
          📊 ROI 分析
        </h1>
        <RegionTabs active={regionFilter} onChange={setRegionFilter} />
      </div>

      {/* Stats cards */}
      {roi && <StatsRow roi={roi} />}

      {/* P&L Chart */}
      {roi?.running_profit?.length > 0 && (
        <ProfitChart data={roi.running_profit} />
      )}

      {/* Side ROI Breakdowns */}
      {roi?.side_roi && <SideBreakdowns side={roi.side_roi} />}

      {/* Per-session breakdown — grouped by month */}
      {roi?.daily_breakdown?.length > 0 && (
        <MonthlyBreakdown
          sessions={roi.daily_breakdown}
          bets={roi.bets || []}
          expandedSession={expandedSession}
          setExpandedSession={setExpandedSession}
        />
      )}

      {/* Empty state */}
      {!roi?.total_bets && (
        <div className="empty-state" style={{ marginTop: "40px" }}>
          <div className="empty-state__icon">📊</div>
          <div className="empty-state__text">暫無投注數據</div>
          <div
            style={{ fontSize: "0.8rem", color: "#94A3B8", marginTop: "8px" }}
          >
            在賽事頁面投注後或匯入 Summary 數據後，ROI 數據將會在此顯示
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Sub-components ─── */

function RegionTabs({ active, onChange }) {
  return (
    <div className="roi-tabs">
      <button
        className={`roi-tab ${!active ? "roi-tab--active" : ""}`}
        onClick={() => onChange(null)}
      >
        全部
      </button>
      <button
        className={`roi-tab ${active === "hkjc" ? "roi-tab--active" : ""}`}
        onClick={() => onChange("hkjc")}
      >
        🇭🇰 HKJC
      </button>
      <button
        className={`roi-tab ${active === "au" ? "roi-tab--active" : ""}`}
        onClick={() => onChange("au")}
      >
        🇦🇺 AU
      </button>
    </div>
  );
}

function StatsRow({ roi }) {
  const profit = roi.total_profit || 0;
  const isPositive = profit >= 0;

  return (
    <div className="roi-stats-grid">
      <StatCard label="總投注數" value={roi.total_bets} icon="🎯" />
      <StatCard
        label="總投入"
        value={`$${roi.total_stake}`}
        icon="💵"
        subtext={`$1 × ${roi.total_bets}`}
      />
      <StatCard label="總回報" value={`$${roi.total_payout}`} icon="💰" />
      <StatCard
        label="總淨利"
        value={`${isPositive ? "+" : ""}$${profit}`}
        icon={isPositive ? "📈" : "📉"}
        color={isPositive ? "#059669" : "#DC2626"}
      />
      <StatCard
        label="ROI"
        value={`${roi.roi_pct}%`}
        icon="📊"
        color={roi.roi_pct >= 0 ? "#059669" : "#DC2626"}
        highlight
      />
      <StatCard label="勝率" value={`${roi.win_rate}%`} icon="🏆" />
      <StatCard label="勝/負" value={`${roi.wins}/${roi.losses}`} icon="⚖️" />
    </div>
  );
}

function StatCard({ label, value, icon, color, subtext, highlight }) {
  return (
    <div
      className={`roi-stat-card ${highlight ? "roi-stat-card--highlight" : ""}`}
    >
      <div style={{ fontSize: "1.4rem", marginBottom: "4px" }}>{icon}</div>
      <div
        style={{
          fontSize: highlight ? "1.3rem" : "1.1rem",
          fontWeight: 800,
          color: color || "#0F172A",
          letterSpacing: "-0.01em",
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: "0.7rem", color: "#94A3B8", marginTop: "2px" }}>
        {label}
      </div>
      {subtext && (
        <div
          style={{ fontSize: "0.65rem", color: "#CBD5E1", marginTop: "1px" }}
        >
          {subtext}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    pending: { bg: "#FEF3C7", color: "#D97706", label: "✅" },
    won: { bg: "#D1FAE5", color: "#059669", label: "✅" },
    lost: { bg: "#FEE2E2", color: "#DC2626", label: "❌" },
  };
  const s = styles[status] || styles.pending;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        padding: "1px 6px",
        borderRadius: "999px",
        fontSize: "0.65rem",
        fontWeight: 700,
      }}
    >
      {s.label}
    </span>
  );
}

function SideBreakdowns({ side }) {
  const sections = [
    { key: "by_venue", title: "🏟️ 馬場分析", label: "馬場" },
    { key: "by_distance", title: "📏 路程分析", label: "路程" },
    { key: "by_class", title: "🏆 班次分析", label: "班次" },
  ];

  if (side.by_track?.length > 0) {
    sections.push({ key: "by_track", title: "🛤️ 賽道分析", label: "賽道" });
  }
  if (side.by_jockey?.length > 0) {
    sections.push({ key: "by_jockey", title: "🏇 騎師分析", label: "騎師" });
  }
  if (side.by_trainer?.length > 0) {
    sections.push({
      key: "by_trainer",
      title: "👨‍🏫 練馬師分析",
      label: "練馬師",
    });
  }

  const hasSideData = sections.some((s) => side[s.key]?.length > 0);
  if (!hasSideData) return null;

  return (
    <div className="roi-carousel">
      {sections.map(({ key, title, label }) => {
        let items = side[key] || [];
        if (items.length === 0) return null;

        if (key === "by_venue") {
          const vMap = {};
          items.forEach((it) => {
            let name = String(it.name).trim();
            const lower = name.toLowerCase().replace(/\s/g, "");
            if (lower === "shatin" || lower === "st") name = "Sha Tin";
            if (lower === "happyvalley" || lower === "hv")
              name = "Happy Valley";

            if (!vMap[name]) {
              vMap[name] = {
                ...it,
                name,
                _wins:
                  it.win_rate != null
                    ? (it.win_rate * (it.total_bets || 0)) / 100
                    : 0,
              };
            } else {
              vMap[name].total_bets =
                (vMap[name].total_bets || 0) + (it.total_bets || 0);
              vMap[name].total_profit = Number(
                (
                  (vMap[name].total_profit || 0) + (it.total_profit || 0)
                ).toFixed(2),
              );
              vMap[name]._wins +=
                it.win_rate != null
                  ? (it.win_rate * (it.total_bets || 0)) / 100
                  : 0;
              vMap[name].win_rate =
                vMap[name].total_bets > 0
                  ? Math.round((vMap[name]._wins / vMap[name].total_bets) * 100)
                  : 0;
              vMap[name].roi_pct =
                vMap[name].total_bets > 0
                  ? Math.round(
                      (vMap[name].total_profit / vMap[name].total_bets) * 100,
                    )
                  : 0;
            }
          });
          items = Object.values(vMap);
        }

        // Sort by total_profit descending
        items = [...items].sort(
          (a, b) => (b.total_profit || 0) - (a.total_profit || 0),
        );

        return (
          <div key={key} className="card" style={{ padding: "16px" }}>
            <h3
              style={{
                fontSize: "0.85rem",
                fontWeight: 700,
                marginBottom: "10px",
                color: "#475569",
              }}
            >
              {title}
            </h3>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.75rem",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid #E2E8F0",
                    color: "#94A3B8",
                  }}
                >
                  <th style={{ padding: "4px 6px", textAlign: "left" }}>
                    {label}
                  </th>
                  <th style={{ padding: "4px 6px", textAlign: "right" }}>
                    注數
                  </th>
                  <th style={{ padding: "4px 6px", textAlign: "right" }}>
                    勝率
                  </th>
                  <th style={{ padding: "4px 6px", textAlign: "right" }}>
                    淨利
                  </th>
                  <th style={{ padding: "4px 6px", textAlign: "right" }}>
                    ROI
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const isUp = item.total_profit >= 0;
                  let dName = String(item.name || "");
                  if (key === "by_distance") {
                    dName = dName.replace(/\.0$/, "");
                    if (
                      !dName.toLowerCase().endsWith("m") &&
                      !isNaN(parseFloat(dName))
                    ) {
                      dName += "m";
                    }
                  }
                  return (
                    <tr
                      key={item.name}
                      style={{ borderBottom: "1px solid #F8FAFC" }}
                    >
                      <td style={{ padding: "4px 6px", fontWeight: 600 }}>
                        {dName}
                      </td>
                      <td
                        style={{
                          padding: "4px 6px",
                          textAlign: "right",
                          color: "#64748B",
                        }}
                      >
                        {item.total_bets || "-"}
                      </td>
                      <td
                        style={{
                          padding: "4px 6px",
                          textAlign: "right",
                          color: "#64748B",
                        }}
                      >
                        {item.win_rate != null ? `${item.win_rate}%` : "-"}
                      </td>
                      <td
                        style={{
                          padding: "4px 6px",
                          textAlign: "right",
                          fontWeight: 700,
                          color: isUp ? "#059669" : "#DC2626",
                        }}
                      >
                        {isUp ? "+" : ""}${item.total_profit}
                      </td>
                      <td
                        style={{
                          padding: "4px 6px",
                          textAlign: "right",
                          color: item.roi_pct >= 0 ? "#059669" : "#DC2626",
                        }}
                      >
                        {item.roi_pct}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

function ProfitChart({ data }) {
  if (data.length === 0) return null;

  const values = data.map((d) => d.cumulative);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const width = 800;
  const height = 300;
  const padLeft = 50;
  const padBottom = 30;
  const padTop = 20;
  const padRight = 20;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const zeroY = padTop + chartH - ((0 - min) / range) * chartH;
  const pointCoords = data.map((d, i) => {
    const x = padLeft + (i / (data.length - 1 || 1)) * chartW;
    const y = padTop + chartH - ((d.cumulative - min) / range) * chartH;
    return { x, y, date: d.date };
  });

  const linePoints = pointCoords.map((p) => `${p.x},${p.y}`).join(" ");
  const fillPath =
    `M ${pointCoords[0].x},${zeroY} ` +
    pointCoords.map((p) => `L ${p.x},${p.y}`).join(" ") +
    ` L ${pointCoords[pointCoords.length - 1].x},${zeroY} Z`;

  const lastValue = values[values.length - 1];
  const isUp = lastValue >= 0;
  const gradientId = isUp ? "profitFill" : "lossFill";

  // Build MM/YY x-axis labels from distinct months
  const monthLabels = [];
  const seen = new Set();
  data.forEach((d, i) => {
    const dateStr = d.date || "";
    let monthKey = "";
    let label = "";
    // Handle both "YYYY-MM-DD" and "M.D" formats
    if (dateStr.includes("-") && dateStr.length >= 7) {
      const parts = dateStr.split("-");
      monthKey = `${parts[0]}-${parts[1]}`;
      const m = parseInt(parts[1]);
      const y = parts[0].slice(-2);
      const monthNames = [
        "",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
      ];
      label = `${monthNames[m] || m}/${y}`;
    } else if (dateStr.includes(".")) {
      const m = dateStr.split(".")[0];
      monthKey = m;
      const monthNames = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
      };
      label = `${monthNames[m] || m}/26`;
    }
    if (monthKey && !seen.has(monthKey)) {
      seen.add(monthKey);
      monthLabels.push({ x: pointCoords[i].x, label });
    }
  });

  // Y-axis tick values
  const yTicks = [];
  const step = range / 4;
  for (let i = 0; i <= 4; i++) {
    const val = min + step * i;
    const y = padTop + chartH - ((val - min) / range) * chartH;
    yTicks.push({ y, label: `$${Math.round(val)}` });
  }

  return (
    <div className="card" style={{ marginTop: "16px", padding: "16px" }}>
      <div
        style={{
          fontSize: "0.8rem",
          fontWeight: 700,
          marginBottom: "8px",
          color: "#64748B",
        }}
      >
        📊 累計損益走勢
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: "100%", height: "320px" }}
      >
        <defs>
          <linearGradient id="profitFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#059669" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#059669" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="lossFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#DC2626" stopOpacity="0.02" />
            <stop offset="100%" stopColor="#DC2626" stopOpacity="0.3" />
          </linearGradient>
        </defs>
        {/* Y-axis grid lines + labels */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={padLeft}
              y1={t.y}
              x2={width - padRight}
              y2={t.y}
              stroke="#F1F5F9"
              strokeWidth="1"
            />
            <text
              x={padLeft - 6}
              y={t.y + 3}
              textAnchor="end"
              fontSize="10"
              fill="#94A3B8"
            >
              {t.label}
            </text>
          </g>
        ))}
        {/* Zero line */}
        <line
          x1={padLeft}
          y1={zeroY}
          x2={width - padRight}
          y2={zeroY}
          stroke="#CBD5E1"
          strokeDasharray="4,4"
          strokeWidth="1"
        />
        <text
          x={padLeft - 6}
          y={zeroY + 3}
          textAnchor="end"
          fontSize="10"
          fill="#64748B"
          fontWeight="600"
        >
          $0
        </text>
        {/* Fill area */}
        <path d={fillPath} fill={`url(#${gradientId})`} />
        {/* Dual-color profit line — green above zero, red below */}
        {pointCoords.map((p, i) => {
          if (i === 0) return null;
          const prev = pointCoords[i - 1];
          const segColor =
            values[i] >= 0 && values[i - 1] >= 0 ? "#059669" : "#DC2626";
          return (
            <line
              key={i}
              x1={prev.x}
              y1={prev.y}
              x2={p.x}
              y2={p.y}
              stroke={segColor}
              strokeWidth="2"
              strokeLinecap="round"
            />
          );
        })}
        {/* End dot */}
        {(() => {
          const last = pointCoords[pointCoords.length - 1];
          const endColor = lastValue >= 0 ? "#059669" : "#DC2626";
          return <circle cx={last.x} cy={last.y} r="4" fill={endColor} />;
        })()}
        {/* End label */}
        <text
          x={pointCoords[pointCoords.length - 1].x}
          y={pointCoords[pointCoords.length - 1].y - 10}
          textAnchor="end"
          fontSize="12"
          fontWeight="700"
          fill={lastValue >= 0 ? "#059669" : "#DC2626"}
        >
          {lastValue >= 0 ? "+" : ""}${lastValue}
        </text>
        {/* MM/YY x-axis labels — with minimum spacing */}
        {monthLabels
          .filter((ml, i) => {
            if (i === 0) return true;
            return ml.x - monthLabels[i - 1].x > 60;
          })
          .map((ml, i) => (
            <g key={i}>
              <line
                x1={ml.x}
                y1={padTop}
                x2={ml.x}
                y2={padTop + chartH}
                stroke="#F1F5F9"
                strokeDasharray="2,4"
                strokeWidth="1"
              />
              <text
                x={ml.x}
                y={height - 6}
                textAnchor="middle"
                fontSize="10"
                fill="#64748B"
                fontWeight="600"
              >
                {ml.label}
              </text>
            </g>
          ))}
      </svg>
    </div>
  );
}

/* Monthly breakdown component */
function MonthlyBreakdown({
  sessions,
  bets,
  expandedSession,
  setExpandedSession,
}) {
  // Sort sessions descending (newest first)
  const sorted = [...sessions].sort((a, b) => {
    // Compare dates — handle both "YYYY-MM-DD" and "M.D" formats
    const dateA = normalizeDate(a.date);
    const dateB = normalizeDate(b.date);
    return dateB.localeCompare(dateA);
  });

  // Group by month
  const monthGroups = [];
  let currentMonth = "";
  let currentGroup = null;

  for (const session of sorted) {
    const safeDate = cleanDateStr(session.date);
    const monthKey = getMonthKey(safeDate);
    const monthLabel = getMonthLabel(safeDate);
    if (monthKey !== currentMonth) {
      currentMonth = monthKey;
      currentGroup = {
        key: monthKey,
        label: monthLabel,
        sessions: [],
        totalProfit: 0,
        totalBets: 0,
      };
      monthGroups.push(currentGroup);
    }
    currentGroup.sessions.push(session);
    currentGroup.totalProfit += session.profit || 0;
    currentGroup.totalBets += session.bets || 0;
  }

  return (
    <div style={{ marginTop: "20px" }}>
      <h3
        style={{
          fontSize: "0.9rem",
          fontWeight: 700,
          marginBottom: "12px",
          color: "#475569",
        }}
      >
        📅 每日投注明細
      </h3>
      {monthGroups.map((group) => {
        const isUp = group.totalProfit >= 0;
        return (
          <div key={group.key} style={{ marginBottom: "16px" }}>
            {/* Month header */}
            <div className="roi-month-header">
              <div
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <span
                  style={{
                    fontSize: "0.85rem",
                    fontWeight: 800,
                    color: "#334155",
                  }}
                >
                  📆 {group.label}
                </span>
                <span
                  style={{
                    fontSize: "0.7rem",
                    color: "#64748B",
                    fontWeight: 500,
                  }}
                >
                  {group.totalBets} 注
                </span>
              </div>
              <span
                className={
                  isUp ? "text-gradient-emerald" : "text-gradient-rose"
                }
                style={{ fontWeight: 800, fontSize: "0.9rem" }}
              >
                {isUp ? "+" : ""}${group.totalProfit.toFixed(2)}
              </span>
            </div>
            {/* Sessions in this month */}
            {group.sessions.map((session) => {
              const key = `${session.date}-${session.venue}`;
              const isExpanded = expandedSession === key;
              const sessionBets = bets.filter(
                (b) => b.date === session.date && b.venue === session.venue,
              );
              const profit = session.profit || 0;
              return (
                <div
                  key={key}
                  className="card"
                  style={{
                    marginBottom: "4px",
                    padding: "0",
                    overflow: "hidden",
                  }}
                >
                  <button
                    onClick={() => setExpandedSession(isExpanded ? null : key)}
                    className={`roi-session-btn ${isExpanded ? "roi-session-btn--expanded" : ""}`}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: "0.8rem",
                          color: "#334155",
                          minWidth: "80px",
                        }}
                      >
                        {cleanDateStr(session.date)}
                      </span>
                      <span className={`badge badge--region-${session.region}`}>
                        {session.region === "hkjc"
                          ? "🇭🇰 "
                          : session.region === "au"
                            ? "🇦🇺 "
                            : ""}
                        {session.venue}
                      </span>
                      <span
                        style={{
                          color: "#94A3B8",
                          fontSize: "0.7rem",
                          fontWeight: 500,
                        }}
                      >
                        {session.bets} 注
                      </span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <span
                        className={`roi-session-profit-badge ${profit >= 0 ? "roi-session-profit-badge--up" : "roi-session-profit-badge--down"}`}
                      >
                        {profit >= 0 ? "+" : ""}${profit.toFixed(2)}
                      </span>
                      <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </div>
                  </button>
                  {isExpanded && sessionBets.length > 0 && (
                    <div
                      style={{
                        borderTop: "1px solid #F1F5F9",
                        padding: "16px 12px",
                        background: "#FAFAF9",
                      }}
                    >
                      {/* Summary Row */}
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: "12px",
                          padding: "0 4px",
                        }}
                      >
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            color: "#64748B",
                          }}
                        >
                          共 {sessionBets.length} 注 ·{" "}
                          {sessionBets.filter((b) => b.net_profit > 0).length}{" "}
                          贏
                        </span>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            color: "#64748B",
                          }}
                        >
                          總回報: {profit >= 0 ? "+" : ""}${profit.toFixed(2)}
                        </span>
                      </div>

                      {/* Reverted Compact Table Layout */}
                      <div style={{ overflowX: "auto" }}>
                        <table
                          style={{
                            width: "100%",
                            borderCollapse: "collapse",
                            fontSize: "0.75rem",
                          }}
                        >
                          <thead>
                            <tr
                              style={{
                                borderBottom: "1px solid #E2E8F0",
                                color: "#94A3B8",
                              }}
                            >
                              <th
                                style={{
                                  padding: "4px 8px",
                                  textAlign: "left",
                                }}
                              >
                                場次
                              </th>
                              <th
                                style={{
                                  padding: "4px 8px",
                                  textAlign: "left",
                                }}
                              >
                                馬匹
                              </th>
                              <th
                                style={{
                                  padding: "4px 8px",
                                  textAlign: "left",
                                }}
                              >
                                賠率
                              </th>
                              <th
                                style={{
                                  padding: "4px 8px",
                                  textAlign: "left",
                                }}
                              >
                                名次
                              </th>
                              <th
                                style={{
                                  padding: "4px 8px",
                                  textAlign: "left",
                                }}
                              >
                                狀態
                              </th>
                              <th
                                style={{
                                  padding: "4px 8px",
                                  textAlign: "right",
                                }}
                              >
                                淨利
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {sessionBets.map((b, idx) => {
                              const bc =
                                b.net_profit > 0
                                  ? "#059669"
                                  : b.net_profit < 0
                                    ? "#DC2626"
                                    : "#94A3B8";
                              const stBg =
                                b.status === "won"
                                  ? "#D1FAE5"
                                  : b.status === "lost"
                                    ? "#FEE2E2"
                                    : "#FEF3C7";
                              const stCol =
                                b.status === "won"
                                  ? "#059669"
                                  : b.status === "lost"
                                    ? "#DC2626"
                                    : "#D97706";
                              const stLabel =
                                b.status === "won"
                                  ? "✅"
                                  : b.status === "lost"
                                    ? "❌"
                                    : "✅";

                              return (
                                <tr
                                  key={idx}
                                  style={{ borderBottom: "1px solid #F8FAFC" }}
                                >
                                  <td style={{ padding: "4px 8px" }}>
                                    R{b.race_number}
                                  </td>
                                  <td style={{ padding: "4px 8px" }}>
                                    <strong>#{b.horse_number}</strong>{" "}
                                    {b.horse_name}
                                  </td>
                                  <td style={{ padding: "4px 8px" }}>
                                    {b.odds || "—"}
                                  </td>
                                  <td style={{ padding: "4px 8px" }}>
                                    {b.result_position || "—"}
                                  </td>
                                  <td style={{ padding: "4px 8px" }}>
                                    <span
                                      style={{
                                        background: stBg,
                                        color: stCol,
                                        padding: "1px 6px",
                                        borderRadius: "999px",
                                        fontSize: "0.65rem",
                                        fontWeight: 700,
                                      }}
                                    >
                                      {stLabel}
                                    </span>
                                  </td>
                                  <td
                                    style={{
                                      padding: "4px 8px",
                                      textAlign: "right",
                                      fontWeight: 700,
                                      color: bc,
                                    }}
                                  >
                                    {b.net_profit != null
                                      ? `${b.net_profit > 0 ? "+" : ""}$${b.net_profit.toFixed(2)}`
                                      : "—"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

/* Date helper functions */
function cleanDateStr(val) {
  if (val == null) return "";
  let str = String(val);
  // Fix JSON float parsing precision errors like `3.6999999999999997` -> `3.7`
  if (/^\d+\.\d{5,}$/.test(str)) {
    str = String(Math.round(parseFloat(str) * 100) / 100);
  }
  return str;
}

function normalizeDate(dateRaw) {
  const dateStr = cleanDateStr(dateRaw);
  if (!dateStr) return "";
  // Already "YYYY-MM-DD" format
  if (dateStr.includes("-") && dateStr.length >= 8) return dateStr;
  // "M.D" format from HK summary → assume 2026 year
  if (dateStr.includes(".")) {
    const [m, d] = dateStr.split(".");
    return `2026-${m.padStart(2, "0")}-${(d || "01").padStart(2, "0")}`;
  }
  return dateStr;
}

function getMonthKey(dateRaw) {
  const dateStr = cleanDateStr(dateRaw);
  if (!dateStr) return "unknown";
  if (dateStr.includes("-") && dateStr.length >= 7) {
    return dateStr.substring(0, 7); // "YYYY-MM"
  }
  if (dateStr.includes(".")) {
    const m = dateStr.split(".")[0];
    return `2026-${m.padStart(2, "0")}`;
  }
  return "unknown";
}

function getMonthLabel(dateStr) {
  const monthNames = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    10: "October",
    11: "November",
    12: "December",
    1: "January",
    2: "February",
    3: "March",
    4: "April",
  };
  const safeDateStr = cleanDateStr(dateStr);
  if (!safeDateStr) return "Unknown";
  let month = "";
  let year = "";
  if (safeDateStr.includes("-") && safeDateStr.length >= 7) {
    const parts = safeDateStr.split("-");
    month = parts[1];
    year = parts[0].slice(-2);
  } else if (safeDateStr.includes(".")) {
    month = safeDateStr.split(".")[0];
    year = "26";
  }
  return `${monthNames[month] || month} '${year}`;
}
