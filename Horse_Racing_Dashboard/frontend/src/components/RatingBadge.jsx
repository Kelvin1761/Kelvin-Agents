/**
 * RatingBadge — Displays a color-coded rating badge.
 */
export default function RatingBadge({ grade, size = "md" }) {
  if (!grade) return null;

  const classMap = {
    S: "badge--s",
    "A+": "badge--a-plus",
    A: "badge--a",
    "A-": "badge--a-minus",
    "B+": "badge--b-plus",
    B: "badge--b",
    "B-": "badge--b-minus",
    "C+": "badge--c-plus",
    C: "badge--c",
    "C-": "badge--c-minus",
    "D+": "badge--d-plus",
    D: "badge--d",
    "D-": "badge--d-minus",
  };

  const cls = classMap[grade] || "badge--b";
  const sizeClass = size === "lg" ? " badge--lg" : "";

  return <span className={`badge ${cls}${sizeClass}`}>{grade}</span>;
}
