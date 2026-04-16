import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import RatingBadge from "../components/RatingBadge";

/**
 * BetPage — Betting records, ROI tracking, and consensus suggestions.
 */
export default function BetPage() {
  const [bets, setBets] = useState([]);
  const [roi, setRoi] = useState(null);
  const [regionFilter, setRegionFilter] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [resultForm, setResultForm] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    setLoading(true);
    const params = regionFilter ? `?region=${regionFilter}` : "";
    Promise.all([api.getBets(params), api.getROI(regionFilter)])
      .then(([betData, roiData]) => {
        setBets(betData.bets || []);
        setRoi(roiData);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [regionFilter]);

  const handlePlaceBet = async (betData) => {
    await api.placeBet(betData);
    setShowForm(false);
    loadData();
  };

  const handleResult = async (betId, position, payout) => {
    await api.updateBetResult(betId, { result_position: position, payout });
    setResultForm(null);
    loadData();
  };

  const handleDelete = async (betId) => {
    if (!confirm("確認刪除此投注記錄？")) return;
    await api.deleteBet(betId);
    loadData();
  };

  if (loading)
    return (
      <div className="loading">
        <div className="loading__spinner" />
      </div>
    );

  return (
    <div>
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
          💰 投注記錄 & ROI
        </h1>
        <div style={{ display: "flex", gap: "8px" }}>
          <RegionFilter active={regionFilter} onChange={setRegionFilter} />
          <button
            className="btn btn--primary"
            onClick={() => setShowForm(true)}
          >
            + 新增投注
          </button>
        </div>
      </div>

      {/* ROI Summary Cards */}
      {roi && <ROISummary roi={roi} />}

      {/* ROI Chart */}
      {roi?.running_profit?.length > 0 && (
        <ProfitChart data={roi.running_profit} />
      )}

      {/* Bet Form Modal */}
      {showForm && (
        <BetFormModal
          onSubmit={handlePlaceBet}
          onClose={() => setShowForm(false)}
        />
      )}

      {/* Bet Records */}
      <div style={{ marginTop: "24px" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}>
          📋 投注記錄 ({bets.length})
        </h2>
        {bets.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">🎯</div>
            <div className="empty-state__text">暫無投注記錄</div>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.8rem",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "2px solid #E2E8F0",
                    textAlign: "left",
                  }}
                >
                  <th style={{ padding: "8px" }}>日期</th>
                  <th style={{ padding: "8px" }}>馬場</th>
                  <th style={{ padding: "8px" }}>場次</th>
                  <th style={{ padding: "8px" }}>馬匹</th>
                  <th style={{ padding: "8px" }}>類型</th>
                  <th style={{ padding: "8px" }}>本金</th>
                  <th style={{ padding: "8px" }}>賠率</th>
                  <th style={{ padding: "8px" }}>狀態</th>
                  <th style={{ padding: "8px" }}>跑道</th>
                  <th style={{ padding: "8px" }}>場地</th>
                  <th style={{ padding: "8px" }}>派彩</th>
                  <th style={{ padding: "8px" }}>淨利</th>
                  <th style={{ padding: "8px" }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {bets.map((bet) => (
                  <tr
                    key={bet.id}
                    style={{ borderBottom: "1px solid #F1F5F9" }}
                  >
                    <td style={{ padding: "8px" }}>{bet.date}</td>
                    <td style={{ padding: "8px" }}>
                      <span className={`badge badge--region-${bet.region}`}>
                        {bet.venue}
                      </span>
                    </td>
                    <td style={{ padding: "8px" }}>R{bet.race_number}</td>
                    <td style={{ padding: "8px" }}>
                      <strong>#{bet.horse_number}</strong> {bet.horse_name}
                      {bet.consensus_type && (
                        <span
                          className="badge badge--consensus"
                          style={{ marginLeft: "4px" }}
                        >
                          {bet.consensus_type}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "8px" }}>
                      {bet.bet_type === "place" ? "位置" : bet.bet_type}
                    </td>
                    <td style={{ padding: "8px" }}>${bet.stake}</td>
                    <td style={{ padding: "8px" }}>{bet.odds || "—"}</td>
                    <td style={{ padding: "8px" }}>
                      <StatusBadge status={bet.status} />
                    </td>
                    <td style={{ padding: "8px", color: "#64748B" }}>
                      {bet.track_type || "—"}
                    </td>
                    <td style={{ padding: "8px", color: "#64748B" }}>
                      {bet.going || "—"}
                    </td>
                    <td style={{ padding: "8px" }}>
                      {bet.payout != null ? `$${bet.payout}` : "—"}
                    </td>
                    <td
                      style={{
                        padding: "8px",
                        color:
                          bet.net_profit > 0
                            ? "#059669"
                            : bet.net_profit < 0
                              ? "#DC2626"
                              : "#64748B",
                      }}
                    >
                      {bet.net_profit != null
                        ? `${bet.net_profit > 0 ? "+" : ""}$${bet.net_profit}`
                        : "—"}
                    </td>
                    <td style={{ padding: "8px" }}>
                      {bet.status === "pending" && (
                        <div style={{ display: "flex", gap: "4px" }}>
                          <button
                            className="btn btn--sm btn--secondary"
                            onClick={() => setResultForm(bet)}
                          >
                            📝 結果
                          </button>
                          <button
                            className="btn btn--sm btn--ghost"
                            onClick={() => handleDelete(bet.id)}
                          >
                            🗑
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Result form modal */}
      {resultForm && (
        <ResultFormModal
          bet={resultForm}
          onSubmit={(pos, payout) => handleResult(resultForm.id, pos, payout)}
          onClose={() => setResultForm(null)}
        />
      )}
    </div>
  );
}

/* ─── Sub-components ─── */

function RegionFilter({ active, onChange }) {
  return (
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
          !active ? "btn btn--primary btn--sm" : "btn btn--ghost btn--sm"
        }
        onClick={() => onChange(null)}
      >
        全部
      </button>
      <button
        className={
          active === "hkjc"
            ? "btn btn--primary btn--sm"
            : "btn btn--ghost btn--sm"
        }
        onClick={() => onChange("hkjc")}
      >
        🇭🇰 HKJC
      </button>
      <button
        className={
          active === "au"
            ? "btn btn--primary btn--sm"
            : "btn btn--ghost btn--sm"
        }
        onClick={() => onChange("au")}
      >
        🇦🇺 AU
      </button>
    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    pending: { bg: "#FEF3C7", color: "#D97706", label: "✅ 待開" },
    won: { bg: "#D1FAE5", color: "#059669", label: "✅ 贏" },
    lost: { bg: "#FEE2E2", color: "#DC2626", label: "❌ 輸" },
  };
  const s = styles[status] || styles.pending;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.7rem",
        fontWeight: 700,
      }}
    >
      {s.label}
    </span>
  );
}

function ROISummary({ roi }) {
  const profit = roi.total_profit || 0;
  const isPositive = profit >= 0;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
        gap: "12px",
      }}
    >
      <StatCard label="總投注" value={roi.total_bets} icon="🎯" />
      <StatCard label="總本金" value={`$${roi.total_stake}`} icon="💵" />
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
      />
      <StatCard label="勝率" value={`${roi.win_rate}%`} icon="🏆" />
      <StatCard
        label="勝/負/待"
        value={`${roi.wins}/${roi.losses}/${roi.pending}`}
        icon="⚖️"
      />
    </div>
  );
}

function StatCard({ label, value, icon, color }) {
  return (
    <div className="card" style={{ padding: "16px", textAlign: "center" }}>
      <div style={{ fontSize: "1.5rem", marginBottom: "4px" }}>{icon}</div>
      <div
        style={{
          fontSize: "1.1rem",
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
    </div>
  );
}

function ProfitChart({ data }) {
  if (data.length === 0) return null;

  const values = data.map((d) => d.cumulative);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const width = 100;
  const height = 120;

  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1 || 1)) * width;
      const y = height - ((d.cumulative - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  const lastValue = values[values.length - 1];
  const isUp = lastValue >= 0;

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
        viewBox={`-5 -10 ${width + 10} ${height + 20}`}
        style={{ width: "100%", height: "150px" }}
      >
        {/* Zero line */}
        <line
          x1="0"
          y1={height - ((0 - min) / range) * height}
          x2={width}
          y2={height - ((0 - min) / range) * height}
          stroke="#E2E8F0"
          strokeDasharray="4,4"
        />
        {/* Profit line */}
        <polyline
          points={points}
          fill="none"
          stroke={isUp ? "#059669" : "#DC2626"}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* End dot */}
        {data.length > 0 &&
          (() => {
            const lastX = width;
            const lastY = height - ((lastValue - min) / range) * height;
            return (
              <circle
                cx={lastX}
                cy={lastY}
                r="3"
                fill={isUp ? "#059669" : "#DC2626"}
              />
            );
          })()}
        {/* End label */}
        <text
          x={width}
          y={height - ((lastValue - min) / range) * height - 8}
          textAnchor="end"
          fontSize="6"
          fontWeight="700"
          fill={isUp ? "#059669" : "#DC2626"}
        >
          {isUp ? "+" : ""}
          {lastValue}
        </text>
      </svg>
    </div>
  );
}

function BetFormModal({ onSubmit, onClose }) {
  const [form, setForm] = useState({
    date: new Date().toISOString().split("T")[0],
    venue: "",
    region: "hkjc",
    race_number: 1,
    horse_number: 1,
    horse_name: "",
    bet_type: "place",
    stake: 1,
    odds: "",
    consensus_type: "",
    notes: "",
    track_type: "",
    going: "",
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      ...form,
      odds: form.odds ? parseFloat(form.odds) : null,
      consensus_type: form.consensus_type || null,
    });
  };

  const inputStyle = {
    width: "100%",
    padding: "8px 10px",
    border: "1px solid #E2E8F0",
    borderRadius: "6px",
    fontSize: "0.85rem",
    fontFamily: "Inter, sans-serif",
  };
  const labelStyle = {
    fontSize: "0.75rem",
    fontWeight: 600,
    color: "#64748B",
    display: "block",
    marginBottom: "4px",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
      }}
    >
      <div
        className="card"
        style={{
          width: "90%",
          maxWidth: "480px",
          maxHeight: "90vh",
          overflow: "auto",
        }}
      >
        <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "16px" }}>
          📝 新增投注
        </h3>
        <form onSubmit={handleSubmit}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "12px",
            }}
          >
            <div>
              <label style={labelStyle}>日期</label>
              <input
                type="date"
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
                style={inputStyle}
                required
              />
            </div>
            <div>
              <label style={labelStyle}>地區</label>
              <select
                value={form.region}
                onChange={(e) => setForm({ ...form, region: e.target.value })}
                style={inputStyle}
              >
                <option value="hkjc">🇭🇰 HKJC</option>
                <option value="au">🇦🇺 AU</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>馬場</label>
              <input
                value={form.venue}
                onChange={(e) => setForm({ ...form, venue: e.target.value })}
                style={inputStyle}
                placeholder="ShaTin"
                required
              />
            </div>
            <div>
              <label style={labelStyle}>場次</label>
              <input
                type="number"
                min="1"
                value={form.race_number}
                onChange={(e) =>
                  setForm({ ...form, race_number: parseInt(e.target.value) })
                }
                style={inputStyle}
                required
              />
            </div>
            <div>
              <label style={labelStyle}>馬號</label>
              <input
                type="number"
                min="1"
                value={form.horse_number}
                onChange={(e) =>
                  setForm({ ...form, horse_number: parseInt(e.target.value) })
                }
                style={inputStyle}
                required
              />
            </div>
            <div>
              <label style={labelStyle}>馬名</label>
              <input
                value={form.horse_name}
                onChange={(e) =>
                  setForm({ ...form, horse_name: e.target.value })
                }
                style={inputStyle}
                placeholder="機械之星"
                required
              />
            </div>
            <div>
              <label style={labelStyle}>本金 ($)</label>
              <input
                type="number"
                min="1"
                value={form.stake}
                onChange={(e) =>
                  setForm({ ...form, stake: parseFloat(e.target.value) })
                }
                style={inputStyle}
                required
              />
            </div>
            <div>
              <label style={labelStyle}>位置賠率</label>
              <input
                type="number"
                step="0.01"
                value={form.odds}
                onChange={(e) => setForm({ ...form, odds: e.target.value })}
                style={inputStyle}
                placeholder="2.50"
              />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label style={labelStyle}>共識類型</label>
              <select
                value={form.consensus_type}
                onChange={(e) =>
                  setForm({ ...form, consensus_type: e.target.value })
                }
                style={inputStyle}
              >
                <option value="">無</option>
                <option value="Top 2 共識">Top 2 共識</option>
                <option value="Top 4 重疊">Top 4 重疊</option>
                <option value="單一分析師">單一分析師</option>
              </select>
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label style={labelStyle}>備註</label>
              <input
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                style={inputStyle}
                placeholder="（選填）"
              />
            </div>
            <div>
              <label style={labelStyle}>跑道 (Track)</label>
              <input
                value={form.track_type}
                onChange={(e) =>
                  setForm({ ...form, track_type: e.target.value })
                }
                style={inputStyle}
                placeholder="例如: 草地, AWT"
              />
            </div>
            <div>
              <label style={labelStyle}>場地 (Going)</label>
              <input
                value={form.going}
                onChange={(e) => setForm({ ...form, going: e.target.value })}
                style={inputStyle}
                placeholder="例如: Good, Soft"
              />
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: "8px",
              marginTop: "16px",
              justifyContent: "flex-end",
            }}
          >
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onClose}
            >
              取消
            </button>
            <button type="submit" className="btn btn--primary">
              確認投注
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ResultFormModal({ bet, onSubmit, onClose }) {
  const [position, setPosition] = useState("");
  const [payout, setPayout] = useState("");

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
      }}
    >
      <div className="card" style={{ width: "90%", maxWidth: "360px" }}>
        <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}>
          📝 輸入結果 — #{bet.horse_number} {bet.horse_name}
        </h3>
        <div style={{ marginBottom: "12px" }}>
          <label
            style={{ fontSize: "0.75rem", fontWeight: 600, color: "#64748B" }}
          >
            完成名次
          </label>
          <input
            type="number"
            min="1"
            value={position}
            onChange={(e) => setPosition(e.target.value)}
            style={{
              width: "100%",
              padding: "8px",
              border: "1px solid #E2E8F0",
              borderRadius: "6px",
              marginTop: "4px",
            }}
            placeholder="例: 2"
          />
        </div>
        <div style={{ marginBottom: "16px" }}>
          <label
            style={{ fontSize: "0.75rem", fontWeight: 600, color: "#64748B" }}
          >
            派彩金額 ($)
          </label>
          <input
            type="number"
            step="0.01"
            value={payout}
            onChange={(e) => setPayout(e.target.value)}
            style={{
              width: "100%",
              padding: "8px",
              border: "1px solid #E2E8F0",
              borderRadius: "6px",
              marginTop: "4px",
            }}
            placeholder="0 = 輸, 250 = 贏"
          />
        </div>
        <div
          style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}
        >
          <button className="btn btn--secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn--primary"
            onClick={() =>
              onSubmit(parseInt(position), parseFloat(payout || "0"))
            }
            disabled={!position}
          >
            確認
          </button>
        </div>
      </div>
    </div>
  );
}
