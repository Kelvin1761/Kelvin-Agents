"""
Patch script to add full interactive betting system back to static_template.html.
Reads the clean git version, surgically inserts betting code, writes back.
"""
import re

TEMPLATE = 'static_template.html'

with open(TEMPLATE, 'r', encoding='utf-8') as f:
    html = f.read()

# ── 1. Add expandedBetRaces state variable ──
html = html.replace(
    "let expandedSession = null;",
    "let expandedSession = null;\nlet expandedBetRaces = new Set();"
)

# ── 2. Add Betting State system (after Data helpers, before Dashboard View) ──
BETTING_STATE_CODE = r'''
// ═══════════════════════════════════════════════
// Betting State (localStorage-persisted)
// ═══════════════════════════════════════════════
function betKey(date, venue, race, horse) { return `bet|${date}|${venue}|${race}|${horse}`; }
let bettingState = {};

function loadBettingState() {
  if (!selectedMeeting) return;
  const k = `bets_${selectedMeeting.date}_${selectedMeeting.venue}`;
  try { bettingState = JSON.parse(localStorage.getItem(k) || '{}'); } catch(e) { bettingState = {}; }
}

function saveBettingState() {
  if (!selectedMeeting) return;
  const k = `bets_${selectedMeeting.date}_${selectedMeeting.venue}`;
  try { localStorage.setItem(k, JSON.stringify(bettingState)); } catch(e) {}
}

function getBetState(date, venue, race, horse) {
  return bettingState[betKey(date,venue,race,horse)] || { odds: null, oddsConfirmed: false, confirmed: false, skipped: false, scratched: false, result: null };
}

function setBetState(date, venue, race, horse, patch) {
  const k = betKey(date,venue,race,horse);
  bettingState[k] = { ...getBetState(date,venue,race,horse), ...patch };
  saveBettingState();
  render();
}

function calcProfit(s) {
  if (!s.confirmed || s.scratched || s.result === null) return null;
  if (s.result === 1) return (s.odds || 0) - 1;
  return -1;
}

// Betting action functions
function setOddsValue(date, venue, race, horse, val) {
  const k = betKey(date,venue,race,horse);
  bettingState[k] = { ...getBetState(date,venue,race,horse), odds: parseFloat(val) || null };
  saveBettingState();
}

function lockOdds(date, venue, race, horse) {
  const s = getBetState(date,venue,race,horse);
  if (!s.odds || s.odds < 1) { alert('請輸入有效賠率'); return; }
  setBetState(date,venue,race,horse, { oddsConfirmed: true });
}

function unlockOdds(date, venue, race, horse) {
  setBetState(date,venue,race,horse, { oddsConfirmed: false, confirmed: false });
}

function placeBet(date, venue, race, horse) {
  setBetState(date,venue,race,horse, { confirmed: true, skipped: false });
}

function skipBet(date, venue, race, horse) {
  setBetState(date,venue,race,horse, { skipped: true, confirmed: false });
}

function reopenBet(date, venue, race, horse) {
  setBetState(date,venue,race,horse, { skipped: false, confirmed: false, oddsConfirmed: false });
}

function setResult(date, venue, race, horse, result) {
  setBetState(date,venue,race,horse, { result: result });
}

function scratchHorse(date, venue, race, horse) {
  setBetState(date,venue,race,horse, { scratched: true });
}

function unscratchHorse(date, venue, race, horse) {
  setBetState(date,venue,race,horse, { scratched: false });
}

function toggleBetRace(rn) {
  if (expandedBetRaces.has(rn)) expandedBetRaces.delete(rn);
  else expandedBetRaces.add(rn);
  render();
}

function exportBetsJSON() {
  const m = selectedMeeting;
  if (!m) return;
  const racesData = getRacesData(m);
  if (!racesData) return;
  const merged = getMergedRaces(racesData);
  const isDualAnalyst = (m.analysts?.length > 1);
  const betsToExport = [];
  merged.forEach(race => {
    const cands = getRaceBettingCandidates(m, race.race_number, isDualAnalyst);
    cands.forEach(c => {
      const s = getBetState(m.date, m.venue, race.race_number, c.horse_number);
      if (s.confirmed || s.skipped) {
        betsToExport.push({
          date: m.date, venue: m.venue, region: m.region,
          race_number: race.race_number, horse_number: c.horse_number,
          horse_name: c.horse_name, jockey: c.jockey, trainer: c.trainer,
          kelvin_grade: c.kelvin_grade, heison_grade: c.heison_grade,
          odds: s.odds, status: s.scratched ? 'scratched' : s.confirmed ? (s.result === 1 ? 'won' : s.result === 0 ? 'lost' : 'pending') : 'skipped',
          result_position: s.result, net_profit: calcProfit(s),
          stake: s.confirmed && !s.scratched ? 1 : 0,
          payout: s.confirmed && !s.scratched && s.result === 1 ? s.odds : 0,
        });
      }
    });
  });
  if (betsToExport.length === 0) { alert('沒有投注記錄可匯出'); return; }

  // Dual mode: try API first, fallback to JSON download
  (async () => {
    try {
      const res = await fetch('http://localhost:8000/api/bets/batch', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(betsToExport), signal: AbortSignal.timeout(3000)
      });
      if (res.ok) { alert('\u2705 成功寫入 Database (' + betsToExport.length + ' 筆)'); return; }
      throw new Error('API returned ' + res.status);
    } catch(e) {
      // Fallback: download JSON file
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
      const a = document.createElement('a');
      a.setAttribute("href", dataStr);
      const datePrefix = new Date().toISOString().slice(0, 10);
      a.setAttribute("download", 'betting_records_' + datePrefix + '.json');
      document.body.appendChild(a);
      a.click();
      a.remove();
      alert('\u2705 已下載 ' + betsToExport.length + ' 筆投注記錄 (JSON)');
    }
  })();
}

'''

html = html.replace(
    "// ═══════════════════════════════════════════════\n// Dashboard View",
    BETTING_STATE_CODE + "// ═══════════════════════════════════════════════\n// Dashboard View"
)

# ── 3. Add renderDashboardBettingPanel call to renderDashboard ──
html = html.replace(
    "      html += '</div>';",
    "      html += '</div>';\n\n      // Betting panel — consolidated list below all race tiles\n      html += renderDashboardBettingPanel(selectedMeeting, merged, isDualAnalyst);",
    1  # only first occurrence
)

# Also need to add isDualAnalyst variable in renderDashboard
html = html.replace(
    "      const analystNote = (selectedMeeting.analysts?.length > 1)",
    "      const isDualAnalyst = (selectedMeeting.analysts?.length > 1);\n      const analystNote = isDualAnalyst"
)

# ── 4. Update selectMeeting to load betting state and expand races ──
html = html.replace(
    """function selectMeeting(index) {
  selectedMeeting = DASHBOARD_DATA.meetings[index];
  render();
}""",
    """function selectMeeting(index) {
  selectedMeeting = DASHBOARD_DATA.meetings[index];
  loadBettingState();
  expandedBetRaces.clear();
  const racesData = getRacesData(selectedMeeting);
  if (racesData) {
    getMergedRaces(racesData).forEach(r => expandedBetRaces.add(r.race_number));
  }
  render();
}"""
)

# ── 5. Replace old renderBettingPanel and add new betting functions before setAnalyst ──
BETTING_RENDER_CODE = r'''function renderBetCard(c, m, raceNum) {
  const s = getBetState(m.date, m.venue, raceNum, c.horse_number);
  const A = `'${m.date}','${m.venue}',${raceNum},${c.horse_number}`;
  const cls = s.scratched ? 'bh bh--scratch' : s.confirmed ? 'bh bh--bet' : s.skipped ? 'bh bh--skip' : 'bh';
  let h = `<div class="${cls}">`;

  // Top row: horse info + grades + profit
  h += `<div class="bh-top"><div class="bh-info">`;
  h += `<div class="bh-num">${c.horse_number}</div><div>`;
  h += `<div class="bh-name">${esc(c.horse_name)}</div>`;
  h += `<div class="bh-meta">${[c.jockey ? '\ud83c\udfc7 '+esc(c.jockey) : '', c.trainer ? '\ud83c\udfe0 '+esc(c.trainer) : ''].filter(Boolean).join(' \u00b7 ')}</div>`;
  h += `</div></div>`;
  h += `<div class="bh-grades">${ratingBadge(String(c.kelvin_grade||c.grade||''))}${c.heison_grade?' '+ratingBadge(String(c.heison_grade)):''}`;
  h += `<button class="bh-analysis" onclick="showRace(${raceNum})">查看分析\u2192</button>`;
  const profit = calcProfit(s);
  if (profit !== null) {
    h += `<span class="bh-profit ${profit >= 0 ? 'bh-profit--win' : 'bh-profit--loss'}">${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}</span>`;
  }
  h += `</div></div>`;

  if (s.scratched) {
    h += `<div class="bh-step"><div class="bh-step-row">`;
    h += `<span style="font-size:0.75rem;color:#64748B">\ud83d\udeab \u5df2\u9000\u51fa (Scratched)</span>`;
    h += `<button class="bb bb-restore" onclick="unscratchHorse(${A})">\u21a9\ufe0f \u5fa9\u539f</button>`;
    h += `</div></div>`;
  } else if (s.skipped) {
    h += `<div class="bh-step"><div class="bh-step-row">`;
    h += `<span style="font-size:0.75rem;color:#64748B">\u23ed\ufe0f \u5df2\u653e\u68c4\u6b64\u99ac${s.odds ? ' \u00b7 \u8cde\u7387 @'+s.odds : ''}</span>`;
    h += `<button class="bb bb-reopen" onclick="reopenBet(${A})">\ud83d\udd04 \u91cd\u65b0\u8003\u616e</button>`;
    h += `</div></div>`;
  } else if (s.confirmed) {
    h += `<div class="bh-step">`;
    h += `<div class="bh-step-label">\ud83d\udcb0 \u5df2\u6295\u6ce8 \u00b7 \u8cde\u7387 @${s.odds}</div>`;
    h += `<div class="bh-step-row">`;
    h += `<span style="font-size:0.72rem;color:#94A3B8;margin-right:4px">\u540d\u6b21:</span>`;
    h += `<div class="br-group">`;
    ;[1,2,3].forEach(p => {
      h += `<button class="br${s.result===p?' br--on':''}" onclick="setResult(${A},${p})">${p}</button>`;
    });
    h += `<button class="br br--x${s.result===0?' br--x-on':''}" onclick="setResult(${A},0)">X</button>`;
    h += `</div>`;
    h += `<button class="bb bb-scratch" onclick="scratchHorse(${A})" style="margin-left:8px">\ud83d\udeab \u5df2\u9000\u51fa</button>`;
    h += `<button class="bb bb-edit" onclick="unlockOdds(${A})" style="margin-left:4px">\u270f\ufe0f \u6539\u8cde\u7387</button>`;
    h += `</div></div>`;
  } else if (s.oddsConfirmed) {
    h += `<div class="bh-step">`;
    h += `<div class="bh-step-label">\u8cde\u7387\u5df2\u78ba\u8a8d @${s.odds} \u2014 \u662f\u5426\u6295\u6ce8\uff1f</div>`;
    h += `<div class="bh-step-row">`;
    h += `<button class="bb bb-bet" onclick="placeBet(${A})">\ud83d\udcb0 \u6295\u6ce8</button>`;
    h += `<button class="bb bb-skip" onclick="skipBet(${A})">\u23ed\ufe0f \u5514\u6295</button>`;
    h += `<button class="bb bb-edit" onclick="unlockOdds(${A})" style="margin-left:4px">\u270f\ufe0f \u6539\u8cde\u7387</button>`;
    h += `</div></div>`;
  } else {
    h += `<div class="bh-step">`;
    h += `<div class="bh-step-label">\u2460 \u8f38\u5165\u8cde\u7387</div>`;
    h += `<div class="bh-step-row">`;
    h += `<input class="bh-odds-input" type="number" step="0.1" min="1" placeholder="\u8cde\u7387" value="${s.odds||''}" onchange="setOddsValue(${A},this.value)" oninput="setOddsValue(${A},this.value)">`;
    h += `<button class="bb bb-lock" onclick="lockOdds(${A})">\ud83d\udd12 \u78ba\u8a8d\u8cde\u7387</button>`;
    h += `</div></div>`;
  }

  h += '</div>';
  return h;
}

function renderDashboardBettingPanel(meeting, races, isDualAnalyst) {
  const m = meeting;
  const allRC = [];
  races.forEach(race => {
    allRC.push({ rn: race.race_number, cands: getRaceBettingCandidates(m, race.race_number, isDualAnalyst), race });
  });

  let totalBets = 0, totalProfit = 0;
  allRC.forEach(({rn, cands}) => cands.forEach(c => {
    const s = getBetState(m.date, m.venue, rn, c.horse_number);
    if (s.confirmed && !s.scratched) { totalBets++; const p = calcProfit(s); if (p !== null) totalProfit += p; }
  }));

  let html = `<div class="bp">
    <div class="bp-hdr"><div class="bp-title">\ud83c\udfaf \u6295\u6ce8\u9762\u677f</div>
    <span class="bp-sub">${isDualAnalyst ? 'Top 2 \u5171\u8b58\u99ac' : 'Top 2 \u7cbe\u9078'} \u00b7 $1 \u5e73\u6ce8\u5236</span></div>`;

  allRC.forEach(({rn, cands, race}) => {
    let rBets=0, rProfit=0;
    cands.forEach(c => {
      const s = getBetState(m.date, m.venue, rn, c.horse_number);
      if (s.confirmed && !s.scratched) { rBets++; const p=calcProfit(s); if(p!==null) rProfit+=p; }
    });

    const isExp = expandedBetRaces.has(rn);
    const profitStr = rBets > 0 ? `${rProfit >= 0 ? '+' : ''}$${rProfit.toFixed(2)}` : '';
    const profitCls = rProfit >= 0 ? 'bh-profit--win' : 'bh-profit--loss';

    html += `<div class="bp-race"><div class="bp-race-hdr" onclick="toggleBetRace(${rn})">`;
    html += `<div><span class="bp-race-lbl">R${rn}</span><span class="bp-race-meta">${esc(race.distance||'')} ${esc(race.race_class||'')}</span>`;
    html += ` <span class="bp-race-stat">${cands.length} \u5019\u9078</span></div>`;
    html += `<div style="display:flex;align-items:center;gap:8px">`;
    if (rBets>0) html += `<span style="font-size:0.75rem;color:#94A3B8">${rBets}\u6ce8</span>`;
    if (profitStr) html += `<span class="bh-profit ${profitCls}" style="font-size:0.78rem">${profitStr}</span>`;
    html += `<span style="font-size:0.6rem;color:#475569">${isExp?'\u25b2':'\u25bc'}</span></div></div>`;

    if (isExp) {
      html += `<div class="bp-race-body">`;
      if (cands.length === 0) {
        html += `<div style="text-align:center;padding:16px;color:#475569;font-size:0.8rem">\u672c\u5834\u6c92\u6709\u5019\u9078\u99ac</div>`;
      } else {
        cands.forEach(c => { html += renderBetCard(c, m, rn); });
      }
      if (rBets > 0) {
        html += `<div class="bp-race-sum"><span class="bp-race-sum-lbl">\u5834\u6b21\u5c0f\u7d50 \u00b7 ${rBets}\u6ce8</span>`;
        html += `<span class="bh-profit ${profitCls}">${profitStr}</span></div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
  });

  // Bottom bar
  html += `<div class="bp-bar">`;
  html += `<div class="bp-bar-info">\u7e3d\u8a08 ${totalBets} \u6ce8${totalBets > 0 ? ` \u00b7 \u6de8\u5229 <span class="bh-profit ${totalProfit >= 0 ? 'bh-profit--win' : 'bh-profit--loss'}">${totalProfit >= 0 ? '+' : ''}$${totalProfit.toFixed(2)}</span>` : ''}</div>`;
  html += `<button class="bp-bar-btn" onclick="exportBetsJSON()" ${totalBets===0?'disabled':''}>\ud83d\udcbe \u532f\u51fa\u6295\u6ce8\u8a18\u9304</button>`;
  html += `</div>`;

  // ROI Summary Table
  const allConfirmed = [];
  const allSkipped = [];
  allRC.forEach(({rn, cands}) => {
    cands.forEach(c => {
      const s = getBetState(m.date, m.venue, rn, c.horse_number);
      if (s.confirmed && !s.scratched) {
        const p = calcProfit(s);
        allConfirmed.push({race:rn, num:c.horse_number, name:c.horse_name, jockey:c.jockey, trainer:c.trainer, odds:s.odds, result:s.result, profit:p, grade:c.kelvin_grade||c.grade, heison:c.heison_grade});
      } else if (s.skipped) {
        allSkipped.push({race:rn, num:c.horse_number, name:c.horse_name, jockey:c.jockey, trainer:c.trainer, odds:s.odds, grade:c.kelvin_grade||c.grade, heison:c.heison_grade});
      }
    });
  });
  if (allConfirmed.length > 0) {
    const totalStake = allConfirmed.length;
    const totalPnl = allConfirmed.reduce((a,b) => a + (b.profit||0), 0);
    const wins = allConfirmed.filter(b => b.profit !== null && b.profit > 0).length;
    const roi = totalStake > 0 ? (totalPnl / totalStake * 100) : 0;
    html += `<div class="roi-sum">`;
    html += `<div class="roi-sum-hdr"><span>\ud83d\udcca \u6295\u6ce8\u8a18\u9304 \u00b7 ${m.venue} ${m.date}</span><span style="font-size:0.72rem;color:#6B7280;font-weight:500">${wins}W/${allConfirmed.length-wins}L \u00b7 ROI ${roi>=0?'+':''}${roi.toFixed(1)}%</span></div>`;
    html += `<table><thead><tr><th>\u5834\u6b21</th><th>\u99ac\u865f</th><th>\u99ac\u5339</th><th>\u9a0e\u5e2b</th><th>\u7df4\u99ac\u5e2b</th><th>\u8a55\u7d1a</th><th>\u8cde\u7387</th><th>\u540d\u6b21</th><th>\u6de8\u5229</th></tr></thead><tbody>`;
    allConfirmed.forEach(b => {
      const rStr = b.result === null ? '\u2014' : b.result === 0 ? 'X' : b.result;
      const pStr = b.profit !== null ? `<span style="color:${b.profit>=0?'#059669':'#DC2626'};font-weight:700">${b.profit>=0?'+':''}$${b.profit.toFixed(2)}</span>` : '<span style="color:#9CA3AF">\u2014</span>';
      const gStr = ratingBadge(String(b.grade||'')) + (b.heison ? ' '+ratingBadge(String(b.heison)) : '');
      html += `<tr><td>R${b.race}</td><td>#${b.num}</td><td>${esc(b.name)}</td><td style="font-size:0.68rem;color:#6B7280">${esc(b.jockey||'')}</td><td style="font-size:0.68rem;color:#6B7280">${esc(b.trainer||'')}</td><td>${gStr}</td><td>@${b.odds}</td><td style="font-weight:700">${rStr}</td><td>${pStr}</td></tr>`;
    });
    html += `<tr class="roi-sum-total"><td colspan="6" style="text-align:right">\u7e3d\u8a08 ${totalStake}\u6ce8</td><td></td><td>${wins}/${allConfirmed.length}</td><td><span style="color:${totalPnl>=0?'#059669':'#DC2626'}">${totalPnl>=0?'+':''}$${totalPnl.toFixed(2)}</span></td></tr>`;
    html += `</tbody></table></div>`;
  }
  if (allSkipped.length > 0) {
    html += `<div class="roi-sum" style="margin-top:10px;opacity:0.7">`;
    html += `<div class="roi-sum-hdr" style="background:linear-gradient(135deg,#F9FAFB,#F3F4F6)"><span style="color:#6B7280">\u274c \u653e\u68c4\u99ac \u00b7 ${allSkipped.length} \u5339</span></div>`;
    html += `<table><thead><tr><th>\u5834\u6b21</th><th>\u99ac\u865f</th><th>\u99ac\u5339</th><th>\u9a0e\u5e2b</th><th>\u7df4\u99ac\u5e2b</th><th>\u8a55\u7d1a</th><th>\u8cde\u7387</th></tr></thead><tbody>`;
    allSkipped.forEach(b => {
      const gStr = ratingBadge(String(b.grade||'')) + (b.heison ? ' '+ratingBadge(String(b.heison)) : '');
      html += `<tr style="color:#9CA3AF"><td>R${b.race}</td><td>#${b.num}</td><td>${esc(b.name)}</td><td style="font-size:0.68rem">${esc(b.jockey||'')}</td><td style="font-size:0.68rem">${esc(b.trainer||'')}</td><td>${gStr}</td><td>@${b.odds||'\u2014'}</td></tr>`;
    });
    html += `</tbody></table></div>`;
  }

  html += `</div>`;
  return html;
}

function getRaceBettingCandidates(meeting, raceNum, isDualAnalyst) {
  const candidates = [];
  if (isDualAnalyst) {
    const consensus = getConsensus(meeting, raceNum);
    if (consensus) {
      const consensusHorses = consensus.consensus?.consensus_horses || [];
      consensusHorses.filter(h => h.is_top2_consensus).forEach(h => {
        let jockey = h.jockey || null;
        let trainer = h.trainer || null;
        const racesData = getRacesData(meeting);
        if (racesData && racesData.races_by_analyst && racesData.races_by_analyst['Kelvin']) {
           const kRace = racesData.races_by_analyst['Kelvin'].find(r => r.race_number === raceNum);
           if (kRace && kRace.horses) {
               const kHorse = kRace.horses.find(kh => kh.horse_number === h.horse_number);
               if (kHorse) {
                   jockey = kHorse.jockey || jockey;
                   trainer = kHorse.trainer || trainer;
               }
           }
        }
        candidates.push({
          horse_number: h.horse_number, horse_name: h.horse_name,
          jockey: jockey, trainer: trainer,
          kelvin_grade: h.kelvin_grade, heison_grade: h.heison_grade,
          grade: h.kelvin_grade || h.heison_grade, consensus_type: 'Top 2 \u5171\u8b58',
        });
      });
    }
  } else {
    const racesData = getRacesData(meeting);
    if (racesData) {
      const analysts = Object.keys(racesData.races_by_analyst);
      const race = racesData.races_by_analyst[analysts[0]]?.find(r => r.race_number === raceNum);
      if (race?.top_picks) {
        race.top_picks.slice(0, 2).forEach(p => {
          const horseData = race.horses?.find(h => h.horse_number === p.horse_number);
          candidates.push({
            horse_number: p.horse_number, horse_name: p.horse_name,
            jockey: horseData?.jockey || null, trainer: horseData?.trainer || null,
            grade: p.grade, kelvin_grade: p.grade, heison_grade: null,
            consensus_type: 'Top 2 \u7cbe\u9078',
          });
        });
      }
    }
  }
  return candidates;
}

'''

NEW_RD_BETTING_PANEL = r'''function renderBettingPanel(meeting, raceNum, isDualAnalyst, consensus) {
  const candidates = getRaceBettingCandidates(meeting, raceNum, isDualAnalyst);
  const m = meeting;

  let html = `<div class="bp" style="margin-top:24px">
    <div class="bp-hdr"><div class="bp-title">\ud83c\udfaf R${raceNum} \u6295\u6ce8\u9762\u677f</div>
    <span class="bp-sub">$1 \u5e73\u6ce8\u5236</span></div>`;

  if (candidates.length === 0) {
    html += `<div style="text-align:center;padding:20px;color:#475569;font-size:0.85rem">
      <div style="font-size:1.5rem;margin-bottom:6px">\ud83d\udccb</div>
      <div style="font-weight:700;color:#94A3B8">0 \u5019\u9078</div>
      <div style="font-size:0.72rem;color:#64748B;margin-top:4px">\u672c\u5834\u6c92\u6709\u5019\u9078\u99ac</div>
    </div>`;
  } else {
    candidates.forEach(c => { html += renderBetCard(c, m, raceNum); });
  }

  html += '</div>';
  return html;
}
'''

# Find and replace old renderBettingPanel (from "function renderBettingPanel" to "function setAnalyst")
old_bp_start = html.find("function renderBettingPanel(meeting, raceNum, isDualAnalyst, consensus) {")
old_bp_end = html.find("function setAnalyst(a)")
if old_bp_start > 0 and old_bp_end > old_bp_start:
    html = html[:old_bp_start] + BETTING_RENDER_CODE + NEW_RD_BETTING_PANEL + "\n" + html[old_bp_end:]
    print("[OK] Replaced old renderBettingPanel with full betting system")
else:
    print("[FAIL] Could not find renderBettingPanel boundaries")

# ── 6. Wrap renderRaceDetail's betting panel call with try/catch ──
html = html.replace(
    "  // Betting panel\n  html += renderBettingPanel(m, raceNum, raceAnalysts.length > 1, consensus);",
    """  // Betting panel
  try {
    html += renderBettingPanel(m, raceNum, raceAnalysts.length > 1, consensus);
  } catch (e) {
    html += `<div class="card" style="margin-top:24px"><h3 style="color:red">\u26a0\ufe0f \u6295\u6ce8\u5340\u57df\u532f\u5165\u5931\u6557</h3><pre style="font-size:0.75rem">${e.message}</pre></div>`;
    console.error('BettingPanel error:', e);
  }"""
)

# ── 7. Add loadBettingState to DOMContentLoaded init ──
html = html.replace(
    "  if (DASHBOARD_DATA.meetings.length) {\n    selectedMeeting = DASHBOARD_DATA.meetings[0];\n  }\n  showDashboard();",
    "  if (DASHBOARD_DATA.meetings.length) {\n    selectedMeeting = DASHBOARD_DATA.meetings[0];\n    loadBettingState();\n    const rd = getRacesData(selectedMeeting);\n    if (rd) getMergedRaces(rd).forEach(r => expandedBetRaces.add(r.race_number));\n  }\n  showDashboard();"
)

# ── 8. Add betting panel CSS ──
BETTING_CSS = """
    /* Betting Panel */
    .bp { background: #fff; border-radius: 12px; border: 1px solid #E2E8F0; margin-top: 24px; overflow: hidden; }
    .bp-hdr { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: linear-gradient(135deg,#F0F9FF,#EFF6FF); border-bottom: 1px solid #E2E8F0; }
    .bp-title { font-size: 0.9rem; font-weight: 800; color: #1E40AF; }
    .bp-sub { font-size: 0.72rem; color: #64748B; font-weight: 500; }
    .bp-race { border-bottom: 1px solid #F1F5F9; }
    .bp-race-hdr { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; cursor: pointer; }
    .bp-race-hdr:hover { background: #F8FAFC; }
    .bp-race-lbl { font-weight: 800; font-size: 0.85rem; color: #1E40AF; margin-right: 8px; }
    .bp-race-meta { font-size: 0.72rem; color: #94A3B8; }
    .bp-race-stat { font-size: 0.68rem; color: #64748B; margin-left: 8px; }
    .bp-race-body { padding: 0 16px 12px; }
    .bp-race-sum { display: flex; justify-content: space-between; padding: 8px 12px; background: #F8FAFC; border-radius: 6px; margin-top: 8px; font-size: 0.75rem; }
    .bp-race-sum-lbl { color: #64748B; font-weight: 600; }
    .bp-bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: linear-gradient(135deg,#F0F9FF,#EFF6FF); border-top: 1px solid #E2E8F0; }
    .bp-bar-info { font-size: 0.8rem; font-weight: 600; color: #334155; }
    .bp-bar-btn { padding: 6px 16px; background: #1D4ED8; color: #fff; border: none; border-radius: 6px; font-size: 0.78rem; font-weight: 700; cursor: pointer; }
    .bp-bar-btn:hover { background: #1E40AF; }
    .bp-bar-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    /* Bet Horse Card */
    .bh { background: #fff; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px; margin-bottom: 8px; transition: all 0.2s; }
    .bh--bet { border-color: #059669; background: linear-gradient(135deg,#F0FDF4,#ECFDF5); }
    .bh--skip { border-color: #94A3B8; opacity: 0.6; }
    .bh--scratch { border-color: #DC2626; opacity: 0.5; background: #FEF2F2; }
    .bh-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
    .bh-info { display: flex; align-items: center; gap: 10px; }
    .bh-num { width: 32px; height: 32px; background: #1E40AF; color: #fff; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.9rem; flex-shrink: 0; }
    .bh-name { font-weight: 700; font-size: 0.88rem; }
    .bh-meta { font-size: 0.68rem; color: #94A3B8; margin-top: 2px; }
    .bh-grades { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .bh-analysis { font-size: 0.65rem; color: #3B82F6; background: none; border: 1px solid #BFDBFE; border-radius: 4px; padding: 1px 6px; cursor: pointer; margin-left: 4px; }
    .bh-profit { font-size: 0.78rem; font-weight: 800; }
    .bh-profit--win { color: #059669; }
    .bh-profit--loss { color: #DC2626; }
    .bh-step { margin-top: 4px; }
    .bh-step-label { font-size: 0.72rem; color: #64748B; font-weight: 600; margin-bottom: 4px; }
    .bh-step-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .bh-odds-input { width: 70px; padding: 4px 8px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 0.8rem; text-align: center; }
    .bb { padding: 4px 10px; border-radius: 6px; font-size: 0.72rem; font-weight: 700; border: 1px solid; cursor: pointer; }
    .bb-lock { background: #1D4ED8; color: #fff; border-color: #1D4ED8; }
    .bb-bet { background: #059669; color: #fff; border-color: #059669; }
    .bb-skip { background: #F1F5F9; color: #64748B; border-color: #E2E8F0; }
    .bb-edit { background: #FEF3C7; color: #92400E; border-color: #FDE68A; }
    .bb-scratch { background: #FEE2E2; color: #DC2626; border-color: #FECACA; }
    .bb-restore { background: #EFF6FF; color: #1D4ED8; border-color: #BFDBFE; }
    .bb-reopen { background: #F0F9FF; color: #0369A1; border-color: #BAE6FD; }
    .br-group { display: flex; gap: 2px; }
    .br { width: 28px; height: 28px; border-radius: 6px; border: 1px solid #E2E8F0; background: #F8FAFC; color: #64748B; font-weight: 700; font-size: 0.75rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }
    .br--on { background: #059669; color: #fff; border-color: #059669; }
    .br--x { border-color: #FECACA; color: #DC2626; }
    .br--x-on { background: #DC2626; color: #fff; border-color: #DC2626; }
    /* ROI Summary in Betting Panel */
    .roi-sum { margin-top: 12px; border-radius: 8px; overflow: hidden; border: 1px solid #E2E8F0; }
    .roi-sum-hdr { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; background: linear-gradient(135deg,#F8FAFC,#F1F5F9); font-size: 0.8rem; font-weight: 700; color: #334155; }
    .roi-sum table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
    .roi-sum th { padding: 6px 10px; text-align: left; color: #94A3B8; border-bottom: 1px solid #E2E8F0; font-weight: 600; }
    .roi-sum td { padding: 6px 10px; border-bottom: 1px solid #F8FAFC; }
    .roi-sum-total td { font-weight: 700; background: #F8FAFC; border-top: 2px solid #E2E8F0; }
"""

html = html.replace(
    "  </style>",
    BETTING_CSS + "  </style>"
)

# ── 9. Add weight label fix in horse card ──
html = html.replace(
    "  if (horse.weight) html += `<span> · ${esc(horse.weight)}</span>`;",
    '  if (horse.weight) { const w = esc(horse.weight); html += `<span title="負磅/排位體重"> · ⚖️ 負磅: ${w.includes(\'磅\') ? w : w + \'磅\'}</span>`; }'
)

# ── 10. Add core_logic display in horse card ──
OLD_UNDERHORSE = "  // Underhorse signal"
CORE_LOGIC_CODE = """  // Extract 核心邏輯 from conclusion for preview
  const logicText = horse.core_logic || (horse.conclusion ? (horse.conclusion.match(/核心邏輯[：:]\\s*\\*{0,2}\\s*(.+?)(?:\\n|$)/) || [])[1] : null);
  if (logicText) {
    let formattedLogic = logicText.trim()
      .replace(/[、，]?\\s*(?=\\(\\d+\\)|（\\d+）|[①②③④⑤⑥⑦⑧⑨⑩])/g, '\\n')
      .replace(/。/g, '。\\n');
    const lines = formattedLogic.split('\\n').filter(s => s.trim());
    const renderedLines = lines.map(line => {
      const isBullet = line.match(/^(\\(\\d+\\)|（\\d+）|[①-⑩])/);
      const style = isBullet ? 'padding-left:18px;text-indent:-18px;margin-top:2px;display:block;' : 'display:block;';
      return `<div style="${style}">${esc(line.trim())}</div>`;
    });
    html += `<div style="margin-top:8px;padding:8px 12px;background:#F0F9FF;border-left:3px solid #3B82F6;border-radius:4px;font-size:0.78rem;line-height:1.8">💡 <strong>核心邏輯:</strong><br>${renderedLines.join('')}</div>`;
  }
  // Underhorse signal"""

html = html.replace(OLD_UNDERHORSE, CORE_LOGIC_CODE)

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from backend.utils.safe_writer import safe_write

# Fix target path since script might be run from root or inside dashboard dir
target_html_path = os.path.join(os.path.dirname(__file__), TEMPLATE)
safe_write(target_html_path, html, mode="w")

print(f"[OK] Patch complete! Template is now {len(html)} bytes, {html.count(chr(10))+1} lines")
