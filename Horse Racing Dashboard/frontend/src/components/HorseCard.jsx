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

        {/* 3.3a — Rating matrix: table-format display */}
        {horse.rating_matrix && horse.rating_matrix.dimensions?.length > 0 && (
          <div className="horse-card__section">
            <div className="horse-card__section-title">📊 評級矩陣</div>
            <RatingMatrixTable matrix={horse.rating_matrix} />
          </div>
        )}

        {/* Expanded: Show full raw analysis text */}
        {expanded && hasAnalysis && (
          <div style={{ marginTop: "12px" }}>
            {horse.raw_text ? (
              <div className="horse-card__section">
                <div className="horse-card__section-title">📋 完整分析</div>
                <SmartAnalysisRenderer text={horse.raw_text} />
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
                    <FormLineRenderer text={horse.form_line} />
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

/* ═══════════════════════════════════════════════════════════════
   3.3a — RatingMatrixTable: Structured table for 8-dimension matrix
   ═══════════════════════════════════════════════════════════════ */
function RatingMatrixTable({ matrix }) {
  if (!matrix || !matrix.dimensions?.length) return null;

  const categoryStyle = (cat) => {
    const c = (cat || "").toLowerCase();
    if (c.includes("核心") && !c.includes("半")) return { bg: "#EFF6FF", color: "#1E40AF", label: "核心" };
    if (c.includes("半核心") || c.includes("semi")) return { bg: "#FFF7ED", color: "#C2410C", label: "半核心" };
    return { bg: "#F0FDF4", color: "#15803D", label: "輔助" };
  };

  const tickColor = (v) => {
    if (v === "✅") return { bg: "#D1FAE5", color: "#059669" };
    if (v === "❌") return { bg: "#FEE2E2", color: "#DC2626" };
    return { bg: "#F1F5F9", color: "#6B7280" };
  };

  return (
    <div className="rating-matrix">
      <table className="rating-matrix__table">
        <thead>
          <tr>
            <th>維度</th>
            <th>類別</th>
            <th>判定</th>
            <th>理據</th>
          </tr>
        </thead>
        <tbody>
          {matrix.dimensions.map((dim, i) => {
            const cs = categoryStyle(dim.category);
            const tc = tickColor(dim.value);
            return (
              <tr key={i} className={dim.value === "✅" ? "rating-matrix__row--strong" : dim.value === "❌" ? "rating-matrix__row--weak" : ""}>
                <td className="rating-matrix__dim-name">{dim.name}</td>
                <td>
                  <span className="rating-matrix__cat-badge" style={{ background: cs.bg, color: cs.color }}>
                    {cs.label}
                  </span>
                </td>
                <td>
                  <span className="rating-matrix__tick" style={{ background: tc.bg, color: tc.color }}>
                    {dim.value}
                  </span>
                </td>
                <td className="rating-matrix__rationale">{dim.rationale || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {/* Grade summary row */}
      {(matrix.base_grade || matrix.fine_tune || matrix.override) && (
        <div className="rating-matrix__summary">
          {matrix.base_grade && <span>📐 基礎: <strong>{matrix.base_grade}</strong></span>}
          {matrix.fine_tune && <span>🔧 微調: <strong>{matrix.fine_tune}</strong></span>}
          {matrix.override && <span>🔄 覆蓋: <strong>{matrix.override}</strong></span>}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   3.3b — SmartAnalysisRenderer: Detects markdown tables in raw_text
   and renders them as structured HTML tables; renders rest as text
   ═══════════════════════════════════════════════════════════════ */
function SmartAnalysisRenderer({ text }) {
  if (!text) return null;

  // Split text into blocks: markdown tables vs regular text
  const blocks = splitIntoBlocks(text);

  return (
    <div className="smart-analysis">
      {blocks.map((block, i) => {
        if (block.type === "table") {
          return <RaceHistoryTable key={i} rows={block.rows} headers={block.headers} />;
        }
        // Regular text block
        return (
          <div key={i} className="smart-analysis__text" style={{ whiteSpace: "pre-wrap" }}>
            {formatRawAnalysis(block.content)}
          </div>
        );
      })}
    </div>
  );
}

/** Parse markdown text into blocks of {type:'text'|'table', ...} */
function splitIntoBlocks(text) {
  const lines = text.split("\n");
  const blocks = [];
  let currentText = [];
  let tableLines = [];
  let inTable = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isTableLine = /^\s*\|.*\|/.test(line);
    const isSeparator = /^\s*\|[\s-:|]+\|/.test(line);

    if (isTableLine) {
      if (!inTable) {
        // Flush any accumulated text
        if (currentText.length > 0) {
          blocks.push({ type: "text", content: currentText.join("\n") });
          currentText = [];
        }
        inTable = true;
      }
      tableLines.push(line);
    } else {
      if (inTable) {
        // End of table — parse it
        const parsed = parseMarkdownTable(tableLines);
        if (parsed) {
          blocks.push({ type: "table", ...parsed });
        } else {
          // Fallback: treat as text
          blocks.push({ type: "text", content: tableLines.join("\n") });
        }
        tableLines = [];
        inTable = false;
      }
      currentText.push(line);
    }
  }

  // Flush remaining
  if (inTable && tableLines.length > 0) {
    const parsed = parseMarkdownTable(tableLines);
    if (parsed) {
      blocks.push({ type: "table", ...parsed });
    } else {
      blocks.push({ type: "text", content: tableLines.join("\n") });
    }
  }
  if (currentText.length > 0) {
    blocks.push({ type: "text", content: currentText.join("\n") });
  }

  return blocks;
}

/** Parse markdown table lines into {headers, rows} */
function parseMarkdownTable(lines) {
  if (lines.length < 2) return null;

  const parseLine = (line) =>
    line.split("|").map(c => c.trim()).filter((c, i, arr) => i > 0 && i < arr.length);

  // Find header and separator
  let headerIdx = 0;
  let sepIdx = -1;
  for (let i = 0; i < Math.min(lines.length, 3); i++) {
    if (/^\s*\|[\s-:|]+\|/.test(lines[i]) && !/[a-zA-Z\u4e00-\u9fff]/.test(lines[i].replace(/[|:\-\s]/g, ""))) {
      sepIdx = i;
      break;
    }
  }

  if (sepIdx === -1) {
    // No separator found — treat all as data rows
    const allRows = lines.map(parseLine).filter(r => r.length > 0);
    if (allRows.length === 0) return null;
    return { headers: allRows[0], rows: allRows.slice(1) };
  }

  headerIdx = sepIdx > 0 ? sepIdx - 1 : 0;
  const headers = parseLine(lines[headerIdx]);
  const rows = [];
  for (let i = sepIdx + 1; i < lines.length; i++) {
    const row = parseLine(lines[i]);
    if (row.length > 0) rows.push(row);
  }
  return { headers, rows };
}

/** Render a race history / form table as structured HTML */
function RaceHistoryTable({ headers, rows }) {
  if (!headers || !rows || rows.length === 0) return null;

  // Detect finish position column index
  const posIdx = headers.findIndex(h =>
    /名次|Fin|Pos|Result|finish/i.test(h)
  );

  const posColor = (val) => {
    const n = parseInt(val);
    if (n === 1) return { bg: "#FEF3C7", color: "#92400E", fontWeight: 800 };
    if (n === 2) return { bg: "#F1F5F9", color: "#475569", fontWeight: 700 };
    if (n === 3) return { bg: "#FFF7ED", color: "#9A3412", fontWeight: 700 };
    if (n <= 4) return { bg: "#EFF6FF", color: "#1E40AF", fontWeight: 600 };
    return {};
  };

  // Detect forgiveness column
  const forgIdx = headers.findIndex(h =>
    /寬恕|forgiv/i.test(h)
  );

  // Detect going/track column
  const goingIdx = headers.findIndex(h =>
    /場地|going|track.*cond/i.test(h)
  );

  const goingStyle = (val) => {
    const v = (val || "").toLowerCase();
    if (v.includes("heavy") || v.includes("濕")) return { bg: "#FEE2E2", color: "#991B1B" };
    if (v.includes("soft") || v.includes("軟")) return { bg: "#DBEAFE", color: "#1E40AF" };
    if (v.includes("good") || v.includes("firm") || v.includes("快")) return { bg: "#D1FAE5", color: "#065F46" };
    return {};
  };

  return (
    <div className="race-history">
      <div className="race-history__scroll">
        <table className="race-history__table">
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => {
                  let style = {};
                  // Position column color coding
                  if (ci === posIdx && posIdx >= 0) {
                    style = posColor(cell);
                  }
                  // Going/track column styling
                  if (ci === goingIdx && goingIdx >= 0) {
                    const gs = goingStyle(cell);
                    if (gs.bg) style = { ...style, ...gs };
                  }
                  // Forgiveness column badge
                  if (ci === forgIdx && forgIdx >= 0) {
                    const isForgiven = /✅|可作準|Y/i.test(cell);
                    const isNotForgiven = /❌|不可|N/i.test(cell);
                    if (isForgiven) style = { background: "#D1FAE5", color: "#059669", fontWeight: 600 };
                    else if (isNotForgiven) style = { background: "#FEE2E2", color: "#DC2626", fontWeight: 600 };
                  }

                  return (
                    <td
                      key={ci}
                      style={{
                        ...(style.bg ? { background: style.bg } : {}),
                        ...(style.color ? { color: style.color } : {}),
                        ...(style.fontWeight ? { fontWeight: style.fontWeight } : {}),
                      }}
                    >
                      {cell || "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   3.3c — FormLineRenderer: Renders form line as timeline cards
   ═══════════════════════════════════════════════════════════════ */
function FormLineRenderer({ text }) {
  if (!text) return null;

  // Try to detect table format first
  const tableLines = text.split("\n").filter(l => /^\s*\|.*\|/.test(l));
  if (tableLines.length >= 3) {
    const parsed = parseMarkdownTable(tableLines);
    if (parsed && parsed.rows.length > 0) {
      return <FormLineTimeline headers={parsed.headers} rows={parsed.rows} />;
    }
  }

  // Fallback: render as formatted text
  return (
    <div className="horse-card__details" style={{ whiteSpace: "pre-wrap" }}>
      {formatAnalysis(text)}
    </div>
  );
}

/** Render form line data as a visual timeline */
function FormLineTimeline({ headers, rows }) {
  if (!rows || rows.length === 0) return null;

  // Detect key column indices
  const dateIdx = headers.findIndex(h => /日期|date/i.test(h));
  const raceIdx = headers.findIndex(h => /賽事|race|event/i.test(h));
  const opponentIdx = headers.findIndex(h => /對手|opponent|馬名/i.test(h));
  const resultIdx = headers.findIndex(h => /表現|result|perf|名次/i.test(h));
  const strengthIdx = headers.findIndex(h => /強弱|strength|組別|group/i.test(h));

  const strengthStyle = (val) => {
    const v = (val || "").toLowerCase();
    if (v.includes("強") || v.includes("strong")) return { bg: "#D1FAE5", color: "#065F46", label: "強" };
    if (v.includes("弱") || v.includes("weak")) return { bg: "#FEE2E2", color: "#991B1B", label: "弱" };
    return { bg: "#FFF7ED", color: "#9A3412", label: "中" };
  };

  // If we can't detect meaningful columns, fall back to table
  if (dateIdx < 0 && raceIdx < 0 && opponentIdx < 0) {
    return <RaceHistoryTable headers={headers} rows={rows} />;
  }

  return (
    <div className="form-timeline">
      {rows.map((row, i) => {
        const date = dateIdx >= 0 ? row[dateIdx] : "";
        const race = raceIdx >= 0 ? row[raceIdx] : "";
        const opponent = opponentIdx >= 0 ? row[opponentIdx] : "";
        const result = resultIdx >= 0 ? row[resultIdx] : "";
        const strength = strengthIdx >= 0 ? row[strengthIdx] : "";
        const ss = strengthStyle(strength);

        return (
          <div key={i} className="form-timeline__card">
            <div className="form-timeline__marker">
              <div className="form-timeline__dot" style={{ background: ss.color }} />
              {i < rows.length - 1 && <div className="form-timeline__line" />}
            </div>
            <div className="form-timeline__content">
              <div className="form-timeline__header">
                {date && <span className="form-timeline__date">{date}</span>}
                {race && <span className="form-timeline__race">{race}</span>}
                {strength && (
                  <span className="form-timeline__strength" style={{ background: ss.bg, color: ss.color }}>
                    {strength}
                  </span>
                )}
              </div>
              {opponent && (
                <div className="form-timeline__detail">
                  <span className="form-timeline__label">對手:</span> {opponent}
                </div>
              )}
              {result && (
                <div className="form-timeline__detail">
                  <span className="form-timeline__label">表現:</span> {result}
                </div>
              )}
              {/* Show remaining columns as key-value pairs */}
              {row.map((cell, ci) => {
                if ([dateIdx, raceIdx, opponentIdx, resultIdx, strengthIdx].includes(ci)) return null;
                if (!cell || cell === "-" || cell === "—") return null;
                return (
                  <div key={ci} className="form-timeline__detail">
                    <span className="form-timeline__label">{headers[ci]}:</span> {cell}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Utility formatters (preserved from original)
   ═══════════════════════════════════════════════════════════════ */

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
