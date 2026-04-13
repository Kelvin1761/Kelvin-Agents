/**
 * API client for the Racing Dashboard backend.
 */
const BASE = "/api";

async function fetchJson(url) {
  const res = await fetch(`${BASE}${url}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  getStatus: () => fetchJson("/status"),
  getMeetings: () => fetchJson("/meetings"),
  refreshMeetings: () =>
    fetch(`${BASE}/meetings/refresh`, { method: "POST" }).then((r) => r.json()),
  getRaces: (date, venue, analyst) => {
    const params = analyst ? `?analyst=${analyst}` : "";
    return fetchJson(`/races/${date}/${venue}${params}`);
  },
  getRaceDetail: (date, venue, raceNum, analyst) => {
    const params = analyst ? `?analyst=${analyst}` : "";
    return fetchJson(`/race/${date}/${venue}/${raceNum}${params}`);
  },
  getConsensus: (date, venue, raceNum) =>
    fetchJson(`/consensus/${date}/${venue}/${raceNum}`),
  compareHorses: (date, venue, raceNum, h1, h2, analyst) =>
    fetchJson(
      `/compare/${date}/${venue}/${raceNum}/${h1}/${h2}?analyst=${analyst || "Kelvin"}`,
    ),

  // Bets
  getBetsByRace: (date, venue, raceNum) =>
    fetchJson(
      `/bets/by-race?date=${date}&venue=${venue}&race_number=${raceNum}`,
    ),
  placeBet: (bet) =>
    fetch(`${BASE}/bets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bet),
    }).then((r) => r.json()),
  getBets: (params = "") => fetchJson(`/bets${params}`),
  getROI: (region) =>
    fetchJson(`/bets/roi${region ? `?region=${region}` : ""}`),
  updateBetResult: (betId, result) =>
    fetch(`${BASE}/bets/${betId}/result`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    }).then((r) => r.json()),
  deleteBet: (betId) =>
    fetch(`${BASE}/bets/${betId}`, { method: "DELETE" }).then((r) => r.json()),

  // Summary ROI from .numbers files
  getSummaryROI: (region) =>
    fetchJson(`/summary-roi${region ? `?region=${region}` : ""}`),
};
