import { useState } from "react";
import RatingBadge from "./RatingBadge";

/**
 * HorseCard — Expandable horse analysis card showing full raw analysis.
 * Displays the complete analysis text when expanded, preserving all information.
 */
export default function HorseCard({ horse, topPickRank, primaryCondition }) {
  const [expanded, setExpanded] = useState(false);

  // Card is expandable if there's any detailed analysis content
  const hasAnalysis =
    horse.raw_text ||
    horse.speed_forensics ||
    horse.eem_energy ||
    horse.forgiveness_file ||
    horse.form_line ||
    horse.horse_profile ||
    horse.core_analysis ||
    horse.conclusion;

  return (
    <div
      className={`horse-card ${topPickRank ? `horse-card--top-pick rank-${topPickRank}` : ""}`}
    >
      <div className="horse-card__header">
        <div className="horse-card__identity">
          {/* Ranking indicator (if top pick) */}
          {topPickRank && (
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
                background:
                  topPickRank === 1
                    ? "#FEF3C7"
                    : topPickRank === 2
                      ? "#F1F5F9"
                      : topPickRank === 3
                        ? "#FFF7ED"
                        : "#EFF6FF",
                color:
                  topPickRank === 1
                    ? "#D97706"
                    : topPickRank === 2
                      ? "#6B7280"
                      : topPickRank === 3
                        ? "#B45309"
                        : "#2563EB",
              }}
            >
              {topPickRank === 1
                ? "🥇"
                : topPickRank === 2
                  ? "🥈"
                  : topPickRank === 3
                    ? "🥉"
                    : `#${topPickRank}`}
            </div>
          )}
          {/* Horse number badge */}
          <div className="horse-card__number" title="馬號">
            <span
              style={{
                fontSize: "0.55rem",
                color: "#94A3B8",
                lineHeight: 1,
                fontWeight: 600,
              }}
            >
              馬號
            </span>
            <span>{horse.horse_number}</span>
          </div>
          <div>
            <div className="horse-card__name">{horse.horse_name}</div>
            <div className="horse-card__meta">
              {horse.jockey && <span>🏇 {horse.jockey}</span>}
              {horse.trainer && <span> · 🏠 {horse.trainer}</span>}
              {horse.weight && (
                <span title="負磅/排位體重">
                  {" "}
                  · ⚖️ 負磅:{" "}
                  {horse.weight.includes("磅")
                    ? horse.weight
                    : `${horse.weight}磅`}
                </span>
              )}
              {horse.barrier && <span> · 檔{horse.barrier}</span>}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {horse.engine_type &&
            (() => {
              const typeColors = {
                "Type A": { bg: "#DBEAFE", color: "#1D4ED8", icon: "🏎️" },
                "Type B": { bg: "#FFF7ED", color: "#C2410C", icon: "⚡" },
                "Type C": { bg: "#D1FAE5", color: "#047857", icon: "🔄" },
                "Type A/B": { bg: "#E0F2FE", color: "#0E7490", icon: "🔀" },
                "Type A/C": { bg: "#E0F2FE", color: "#0E7490", icon: "🔀" },
                "Type B/C": { bg: "#E0F2FE", color: "#0E7490", icon: "🔀" },
              };
              const style =
                typeColors[horse.engine_type] || typeColors["Type A/B"];
              return (
                <span
                  title={
                    horse.engine_distance_summary ||
                    `${horse.engine_type} (${horse.engine_type_label})`
                  }
                  style={{
                    fontSize: "0.65rem",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "6px",
                    background: style.bg,
                    color: style.color,
                    whiteSpace: "nowrap",
                    letterSpacing: "0.02em",
                  }}
                >
                  {style.icon} {horse.engine_type}
                  {horse.engine_type_label
                    ? ` (${horse.engine_type_label})`
                    : ""}
                </span>
              );
            })()}
          {/* Grades displaying logic */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              {primaryCondition && horse.alt_grade && (
                <span
                  style={{
                    fontSize: "0.55rem",
                    color: "#94A3B8",
                    fontWeight: 700,
                    marginBottom: "2px",
                    letterSpacing: "0.02em",
                  }}
                >
                  預期 ({(() => { const t = (primaryCondition || '').replace(/\s*[（(].*$/, '').trim(); return t || primaryCondition; })()})
                </span>
              )}
              <RatingBadge grade={horse.final_grade} size="lg" />
            </div>

            {horse.alt_grade && horse.alt_condition && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  paddingLeft: "8px",
                  borderLeft: "1px dashed #CBD5E1",
                  opacity: 0.95,
                }}
              >
                <span
                  style={{
                    fontSize: "0.55rem",
                    color: "#94A3B8",
                    fontWeight: 700,
                    marginBottom: "2px",
                    letterSpacing: "0.02em",
                  }}
                >
                  備選 ({(() => { const t = (horse.alt_condition || '').replace(/\s*[（(].*$/, '').trim(); return t || horse.alt_condition; })()})
                </span>
                <div
                  style={{ display: "flex", alignItems: "center", gap: "4px" }}
                  title={horse.grade_shift_reason}
                >
                  <span
                    style={{
                      fontSize: "0.65rem",
                      fontWeight: 800,
                      color: horse.grade_shift?.includes("↑")
                        ? "#059669"
                        : horse.grade_shift?.includes("↓")
                          ? "#DC2626"
                          : "#94A3B8",
                    }}
                  >
                    {horse.grade_shift?.charAt(0)}
                  </span>
                  <RatingBadge grade={horse.alt_grade} size="md" />
                </div>
              </div>
            )}
          </div>

          {horse.underhorse_triggered && (
            <span
              className="badge badge--consensus"
              title="冷門馬訊號"
              style={{ marginLeft: "auto" }}
            >
              🐴⚡
            </span>
          )}
        </div>
      </div>

      <div className="horse-card__body">
        {/* Key info summary (always visible) */}
        <div className="horse-card__details">
          {horse.situation_tag && <div>📌 {horse.situation_tag}</div>}
          {(horse.recent_form || horse.form_cycle) && (
            <div>
              📊{" "}
              {horse.recent_form && (
                <>
                  近六場: <strong>{horse.recent_form}</strong>
                </>
              )}
              {horse.recent_form && horse.form_cycle && " | "}
              {horse.form_cycle && <>狀態週期: {horse.form_cycle}</>}
            </div>
          )}
          {/* Engine distance summary */}
          {horse.engine_distance_summary && (
            <div
              style={{
                marginTop: "4px",
                fontSize: "0.75rem",
                color: "#475569",
              }}
            >
              🏎️ <strong>引擎距離:</strong>{" "}
              {horse.engine_distance_summary.length > 120
                ? horse.engine_distance_summary.substring(0, 120) + "..."
                : horse.engine_distance_summary}
            </div>
          )}
          {horse.advantage && (
            <div style={{ marginTop: "8px" }}>
              ✅ <strong>優勢:</strong> {horse.advantage}
            </div>
          )}
          {horse.risk && (
            <div>
              ⚠️ <strong>風險:</strong> {horse.risk}
            </div>
          )}
          {/* Core logic from conclusion */}
          {(horse.core_logic || horse.conclusion) &&
            (() => {
              const logic =
                horse.core_logic ||
                (() => {
                  // Strip blockquote markers before matching
                  const cleaned = (horse.conclusion || "")
                    .replace(/^>\s*-?\s*/gm, "")
                    .replace(/\*{1,2}/g, "");
                  const m = cleaned.match(
                    /核心邏輯[：:]\s*(.+?)(?=最大競爭優勢|最大失敗|$)/s,
                  );
                  return m ? m[1].trim() : null;
                })();
              if (!logic) return null;
              // Split on sentence endings and numbered points for separate lines
              const sentences = logic
                .replace(/。/g, '。\n')
                .replace(/[、，]?\s*(?=\(\d+\)|（\d+）|[①②③④⑤⑥⑦⑧⑨⑩])/g, '\n')
                .split('\n')
                .map(s => s.trim())
                .filter(s => s.length > 0);

              return (
                <div
                  style={{
                    marginTop: "8px",
                    padding: "8px 12px",
                    background: "#F0F9FF",
                    borderLeft: "3px solid #3B82F6",
                    borderRadius: "4px",
                    fontSize: "0.78rem",
                    lineHeight: "1.8",
                  }}
                >
                  💡 <strong>核心邏輯:</strong>
                  <br />
                  {sentences.map((line, i) => {
                    const isBullet = line.match(/^(\(\d+\)|（\d+）|[①-⑩])/);
                    return (
                      <div
                        key={i}
                        style={{
                          paddingLeft: isBullet ? "18px" : "0",
                          textIndent: isBullet ? "-18px" : "0",
                          marginTop: isBullet ? "2px" : "0",
                        }}
                      >
                        {line.trim()}
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          {/* Underhorse signal */}
          {horse.underhorse_triggered && (
            <div
              style={{
                marginTop: "8px",
                padding: "8px 12px",
                background: "#FFF7ED",
                borderLeft: "3px solid #F59E0B",
                borderRadius: "4px",
                fontSize: "0.78rem",
                lineHeight: "1.8",
              }}
            >
              🐴⚡ <strong>冷門馬訊號: 觸發!</strong>
              {horse.underhorse_condition && (
                <>
                  <br />🎯 <strong>受惠條件:</strong>{" "}
                  {horse.underhorse_condition}
                </>
              )}
              {horse.underhorse_reason && (
                <>
                  <br />📝 <strong>理由:</strong> {horse.underhorse_reason}
                </>
              )}
            </div>
          )}
        </div>

        {/* Rating matrix summary */}
        {horse.rating_matrix && horse.rating_matrix.dimensions?.length > 0 && (
          <div className="horse-card__section">
            <div className="horse-card__section-title">📊 評級矩陣</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
              {horse.rating_matrix.dimensions.map((dim, i) => (
                <span
                  key={i}
                  title={`${dim.name}: ${dim.rationale}`}
                  style={{
                    fontSize: "0.7rem",
                    padding: "2px 6px",
                    borderRadius: "4px",
                    background:
                      dim.value === "✅"
                        ? "#D1FAE5"
                        : dim.value === "❌"
                          ? "#FEE2E2"
                          : "#F1F5F9",
                    color:
                      dim.value === "✅"
                        ? "#059669"
                        : dim.value === "❌"
                          ? "#DC2626"
                          : "#6B7280",
                  }}
                >
                  {dim.value} {dim.name}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Expanded: Show full raw analysis text */}
        {expanded && hasAnalysis && (
          <div style={{ marginTop: "12px" }}>
            {horse.raw_text ? (
              <div className="horse-card__section">
                <div className="horse-card__section-title">📋 完整分析</div>
                <div
                  className="horse-card__raw-analysis"
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: "0.78rem",
                    lineHeight: "1.7",
                    color: "#334155",
                    padding: "12px",
                    background: "#F8FAFC",
                    borderRadius: "8px",
                    maxHeight: "600px",
                    overflowY: "auto",
                  }}
                >
                  {formatRawAnalysis(horse.raw_text)}
                </div>
              </div>
            ) : (
              /* Fallback: show individual sections if no raw_text */
              <>
                {horse.speed_forensics && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">🔬 段速法醫</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.speed_forensics)}
                    </div>
                  </div>
                )}
                {horse.eem_energy && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">⚡ EEM 能量</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.eem_energy)}
                    </div>
                  </div>
                )}
                {horse.forgiveness_file && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">📋 寬恕檔案</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.forgiveness_file)}
                    </div>
                  </div>
                )}
                {horse.form_line && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">🔗 賽績線</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.form_line)}
                    </div>
                  </div>
                )}
                {horse.horse_profile && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">🐴 馬匹剖析</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.horse_profile)}
                    </div>
                  </div>
                )}
                {horse.core_analysis && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">🧠 核心分析</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.core_analysis)}
                    </div>
                  </div>
                )}
                {horse.conclusion && (
                  <div className="horse-card__section">
                    <div className="horse-card__section-title">💡 結論</div>
                    <div
                      className="horse-card__details"
                      style={{ whiteSpace: "pre-wrap" }}
                    >
                      {formatAnalysis(horse.conclusion)}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {hasAnalysis && (
        <button
          className="horse-card__expand-btn"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "收起詳情 ▲" : "展開詳情 ▼"}
        </button>
      )}
    </div>
  );
}

/**
 * Format raw analysis text for clean display.
 * Preserves structure: headings, bullets, sections, emojis.
 * Strips markdown artifacts while keeping readability.
 */
function formatRawAnalysis(text) {
  if (!text) return "";
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, "$1") // Remove bold-italic markdown
    .replace(/\*\*(.+?)\*\*/g, "$1") // Remove bold markdown
    .replace(/\*(.+?)\*/g, "$1") // Remove italic markdown
    .replace(/^[=]{3,}$/gm, "─".repeat(40)) // Replace === dividers with clean lines
    .replace(/^[-]{3,}$/gm, "─".repeat(30)) // Replace --- dividers
    .replace(/^[#]+\s*/gm, "") // Remove heading markers
    .replace(/\n{4,}/g, "\n\n") // Collapse excess blank lines
    .trim();
}

function formatAnalysis(text) {
  if (!text) return "";
  return text
    .replace(/\*\*/g, "") // Remove bold markdown
    .replace(/^[#]+\s*/gm, "") // Remove heading markers
    .replace(/^[-*]\s+/gm, "• ") // Convert bullet markers to •
    .replace(/;\s*\[/g, ";\n[") // Line break before each [N] race entry
    .replace(/\|\s*修正/g, "\n修正") // Line break before 修正因素/修正判斷
    .replace(/\|\s*段速/g, "\n段速") // Line break before 段速
    .replace(/\|\s*結論/g, "\n結論") // Line break before 結論
    .replace(/\n{3,}/g, "\n\n") // Collapse excess blank lines
    .trim();
}
