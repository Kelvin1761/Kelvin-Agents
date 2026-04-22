/**
 * 旺財街機 — 賽事生成器
 * 負責：抽馬、配騎師練馬師、生成情報、計算賠率、生成近六場賽績
 */
import seedrandom from 'seedrandom';
import { buildHorseDatabase } from '../data/horses.js';
import { JOCKEYS, getActiveJockeys } from '../data/jockeys.js';
import { TRAINERS } from '../data/trainers.js';

// ═══ 賽日結構常數 ═══
const HV_DISTANCES = [1000, 1200, 1650, 1800, 2200];
const ST_DISTANCES = [1000, 1200, 1400, 1600, 1800, 2000, 2400];

const HV_CLASS_WEIGHTS = [
  { class: '第五班', weight: 30 }, { class: '第四班', weight: 30 },
  { class: '第三班', weight: 25 }, { class: '第二班', weight: 10 },
  { class: '第一班', weight: 5 },
];
const ST_CLASS_WEIGHTS = [
  { class: '第五班', weight: 10 }, { class: '第四班', weight: 15 },
  { class: '第三班', weight: 25 }, { class: '第二班', weight: 25 },
  { class: '第一班', weight: 15 }, { class: '國際賽', weight: 10 },
];

const CLASS_TIER_MAP = {
  '第五班': ['C', 'D'], '第四班': ['B', 'C', 'D'], '第三班': ['B', 'C'],
  '第二班': ['A', 'B'], '第一班': ['S', 'A', 'B'], '國際賽': ['S', 'A'],
};

// ═══ 情報模板 ═══
const INTEL_TEMPLATES = {
  barrier_trial: [
    { text: '🏋 {horse} 近期試閘表現出色，段速驚人！', effect: { stat: 'baseSpeed', mod: 0.12 } },
    { text: '🏋 {horse} 試閘墮後，狀態恐未到位。', effect: { stat: 'baseSpeed', mod: -0.08 } },
  ],
  streak: [
    { text: '🔥 {jockey} 今日狀態火熱！配搭 {trainer} 更是默契十足！', effect: { stat: 'baseSpeed', mod: 0.10 } },
    { text: '❄️ {jockey} 已連續多場食白果，今日能否翻身？', effect: { stat: 'consistency', mod: -0.05 } },
  ],
  sectional: [
    { text: '📊 {horse} 上仗 L600 段速為近期最佳！', effect: { stat: 'finalSprint', mod: 0.15 } },
    { text: '📊 {horse} 近仗末段明顯乏力。', effect: { stat: 'stamina', mod: -0.05 } },
  ],
  energy: [
    { text: '⚡ {horse} 休息充足後復出，體力充沛！', effect: { stat: 'energyLevel', mod: 0.10 } },
    { text: '⚡ {horse} 已連續出戰，能量恐已透支。', effect: { stat: 'stamina', mod: -0.15 } },
  ],
  forgiveness: [
    { text: '📋 {horse} 上仗走位受阻，實力未盡展現。', effect: { stat: 'baseSpeed', mod: 0.08 } },
  ],
  underhorse: [
    { text: '🔍 UNDERHORSE 🟢: {horse} 操練有起色！', effect: { stat: 'burstChance', mod: 0.10 } },
    { text: '🔍 UNDERHORSE 🟡: {horse} 冷門馬信號中度！', effect: { stat: 'burstChance', mod: 0.20 } },
    { text: '🔍 UNDERHORSE 🔴: {horse} 強烈冷門信號！', effect: { stat: 'burstChance', mod: 0.35 } },
  ],
  going: [
    { text: '🌦 今日場地由「好地」轉為「好至黏地」，內欄稍有偏差。', effect: { stat: 'trackGlobal', mod: 'yielding' } },
  ],
  weight: [
    { text: '📈 {horse} 減磅作戰，狀態疑似處於顛峰。', effect: { stat: 'baseSpeed', mod: 0.05 } },
    { text: '📉 {horse} 增磅出戰，體型偏向豐滿。', effect: { stat: 'baseSpeed', mod: -0.03 } },
  ],
};

// ═══ 工具函數 ═══
function weightedPick(rng, items) {
  const total = items.reduce((s, i) => s + i.weight, 0);
  let r = rng() * total;
  for (const item of items) {
    r -= item.weight;
    if (r <= 0) return item;
  }
  return items[items.length - 1];
}

function shuffle(rng, arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function pickN(rng, arr, n) {
  return shuffle(rng, arr).slice(0, n);
}

// ═══ 賠率計算 ═══
function calculateOdds(runners) {
  const scores = runners.map(r => {
    const s = r.horse.stats;
    const jRating = r.jockey.rating;
    const tRating = r.trainer.rating;
    return s.baseSpeed * 25 + s.stamina * 0.15 + s.finalSprint * 15 +
      s.consistency * 10 + s.energyLevel * 0.10 + jRating * 0.15 + tRating * 0.10;
  });
  const totalScore = scores.reduce((a, b) => a + b, 0);
  return scores.map(score => {
    const winProb = score / totalScore;
    let odds = (1 / winProb) * 0.82;
    odds = Math.max(1.5, Math.min(99.0, odds));
    return Math.round(odds * 10) / 10;
  });
}

// ═══ 近六場賽績生成 ═══
function generateRaceRecord(rng, tier) {
  const ranges = { S: [1,4,5,7], A: [1,4,5,7], B: [2,6,1,9], C: [4,9,2,3], D: [7,12,4,6] };
  const [mainMin, mainMax, rareMin, rareMax] = ranges[tier];
  const record = [];
  const venues = ['沙田', '跑馬地'];
  const dists = [1000, 1200, 1400, 1600, 1800, 2000];
  for (let i = 0; i < 6; i++) {
    const isRare = rng() < 0.2;
    const pos = isRare
      ? Math.floor(rng() * (rareMax - rareMin + 1)) + rareMin
      : Math.floor(rng() * (mainMax - mainMin + 1)) + mainMin;
    record.push({
      venue: venues[Math.floor(rng() * venues.length)],
      distance: dists[Math.floor(rng() * dists.length)],
      position: Math.min(12, Math.max(1, pos)),
    });
  }
  return record;
}

// ═══ 情報生成 ═══
function generateIntel(rng, runners) {
  const types = Object.keys(INTEL_TEMPLATES);
  const count = 2 + Math.floor(rng() * 3); // 2-4 條
  const intel = [];
  for (let i = 0; i < count; i++) {
    const type = types[Math.floor(rng() * types.length)];
    const templates = INTEL_TEMPLATES[type];
    const tmpl = templates[Math.floor(rng() * templates.length)];
    const runner = runners[Math.floor(rng() * runners.length)];
    const text = tmpl.text
      .replace('{horse}', runner.horse.name)
      .replace('{jockey}', runner.jockey.name)
      .replace('{trainer}', runner.trainer.name);
    intel.push({ type, text, effect: tmpl.effect, targetHorseId: runner.horse.id });
  }
  return intel;
}

// ═══ 騎師配對 ═══
function assignJockeys(rng, horses) {
  const activeJockeys = getActiveJockeys();
  const available = [...activeJockeys];
  const assignments = [];

  // Step 1: Set jockeys for horses with setJockey
  for (const horse of horses) {
    if (horse.meta.setJockey) {
      const jIdx = available.findIndex(j => j.id === horse.meta.setJockey);
      if (jIdx >= 0) {
        assignments.push({ horse, jockey: available[jIdx] });
        available.splice(jIdx, 1);
      } else {
        // Jockey already taken — assign best remaining
        assignments.push({ horse, jockey: null }); // will fill below
      }
    }
  }

  // Step 2: Remaining horses by rating desc, get best available jockey
  const remaining = horses.filter(h => !assignments.find(a => a.horse.id === h.id && a.jockey));
  const unassigned = assignments.filter(a => !a.jockey);

  const sortedRemaining = [...remaining, ...unassigned.map(a => a.horse)]
    .sort((a, b) => (b.stats?.baseSpeed || 0) - (a.stats?.baseSpeed || 0));

  for (const horse of sortedRemaining) {
    if (available.length === 0) break;
    // Sort available by rating desc
    available.sort((a, b) => b.rating - a.rating);
    const jockey = available.shift();
    const existing = assignments.find(a => a.horse.id === horse.id);
    if (existing) {
      existing.jockey = jockey;
    } else {
      assignments.push({ horse, jockey });
    }
  }

  return assignments;
}

// ═══ 主生成函數 ═══
export function generateRace(globalSeed, raceIndex, allHorses) {
  const raceSeed = `${globalSeed}_race_${raceIndex}`;
  const rng = seedrandom(raceSeed);

  // Determine venue & time
  const hour = new Date().getHours();
  const isNight = hour >= 18 || hour < 6;
  const venue = isNight ? '跑馬地' : '沙田';

  // Determine class
  const classWeights = isNight ? HV_CLASS_WEIGHTS : ST_CLASS_WEIGHTS;
  let raceClass;
  if (raceIndex === 0) {
    raceClass = isNight ? '第五班' : '第四班'; // R1 = lowest
  } else if (raceIndex === 9) {
    raceClass = isNight ? '第一班' : '國際賽'; // R10 = highest
  } else {
    raceClass = weightedPick(rng, classWeights).class;
  }

  // Determine distance
  const distPool = isNight ? HV_DISTANCES : ST_DISTANCES;
  const distance = distPool[Math.floor(rng() * distPool.length)];

  // Pick 12 horses from appropriate tiers
  const allowedTiers = CLASS_TIER_MAP[raceClass];
  const eligible = allHorses.filter(h => allowedTiers.includes(h.tier));
  const selectedHorses = pickN(rng, eligible, 12);

  // Assign barrier draws (1-12)
  selectedHorses.forEach((h, i) => { h.barrierDraw = i + 1; });

  // Assign jockeys
  const jockeyAssignments = assignJockeys(rng, selectedHorses);

  // Assign trainers randomly
  const shuffledTrainers = shuffle(rng, TRAINERS);
  const runners = jockeyAssignments.map((a, i) => ({
    horse: a.horse,
    jockey: a.jockey,
    trainer: shuffledTrainers[i % shuffledTrainers.length],
    barrier: i + 1,
    weight: generateWeight(rng, a.horse.tier),
    raceRecord: generateRaceRecord(rng, a.horse.tier),
    comment: generateComment(rng, a.horse, a.jockey, shuffledTrainers[i % shuffledTrainers.length], distance),
  }));

  // Calculate odds
  const odds = calculateOdds(runners);
  runners.forEach((r, i) => { r.odds = odds[i]; });

  // Sort by odds (favourite first) for display
  runners.sort((a, b) => a.odds - b.odds);

  // Generate intel
  const intel = generateIntel(rng, runners);

  // 棟哥貼士 (accuracy ~40%)
  const dongGoPick = runners[Math.floor(rng() * runners.length)];
  const dongGoCorrect = rng() < 0.40;

  return {
    raceIndex,
    raceNumber: raceIndex + 1,
    venue,
    raceClass,
    distance,
    runners,
    intel,
    dongGo: { pick: dongGoPick.horse.id, pickName: dongGoPick.horse.name },
    seed: raceSeed,
    trackCondition: rng() < 0.05 ? 'yielding' : 'good',
    isDirt: rng() < 0.15,
  };
}

// ═══ 旺財評語生成器 — 連貫數據分析版 ═══
function generateComment(rng, horse, jockey, trainer, raceDistance) {
  const s = horse.stats;
  const parts = [];

  // ── 1. 開場：等級定位 ──
  const tierOpeners = {
    S: `${horse.name} 屬頂級精英馬，綜合能力極強`,
    A: `${horse.name} 實力班底雄厚，穩定輸出型選手`,
    B: `${horse.name} 屬中堅分子，條件配合下有力爭勝`,
    C: `${horse.name} 整體實力一般，需要有利條件先有機會`,
    D: `${horse.name} 實力偏弱，屬於搏冷類型`,
  };
  parts.push(tierOpeners[horse.tier] || `${horse.name} 今場出戰`);

  // ── 2. 核心能力分析（基於實際數值）──
  const speedPct = Math.round(s.baseSpeed / 3.5 * 100);
  const staminaPct = Math.round(s.stamina);
  const sprintPct = Math.round(s.finalSprint / 1.8 * 100);

  if (speedPct >= 80 && sprintPct >= 75) {
    parts.push(`速度（${speedPct}分）同衝刺力（${sprintPct}分）都處於高水平，攻守兼備`);
  } else if (speedPct >= 75) {
    parts.push(`基礎速度達 ${speedPct} 分，在同級中屬前列`);
  } else if (speedPct < 50) {
    parts.push(`速度僅 ${speedPct} 分，需要靠策略同走位彌補`);
  } else {
    parts.push(`速度 ${speedPct} 分屬中游水準`);
  }

  // ── 3. 跑法 × 距離適性 ──
  const distFit = s.distanceFit || 'mid';
  const isShort = raceDistance <= 1200;
  const isMid = raceDistance > 1200 && raceDistance < 1800;
  const isLong = raceDistance >= 1800;
  const distLabel = isShort ? '短途' : isLong ? '長途' : '中距離';

  const styleMap = {
    '領放': '領放型跑法，慣性搶放佔先',
    '居前': '居前跟進，靈活部署',
    '居中': '中段待放型，靠末段突圍',
    '後上': '後上猛追型，依賴末段爆發',
  };
  let styleComment = styleMap[s.runningStyle] || s.runningStyle;

  if ((distFit === 'short' && isShort) || (distFit === 'mid' && isMid) || (distFit === 'long' && isLong)) {
    styleComment += `，今場 ${raceDistance}m ${distLabel}賽正合其路程`;
  } else if ((distFit === 'short' && isLong) || (distFit === 'long' && isShort)) {
    styleComment += `，但今場 ${raceDistance}m 並非其最佳路程，存在隱憂`;
  }
  parts.push(styleComment);

  // ── 4. 體力/耐力狀態 ──
  if (s.stamina > 80 && s.energyLevel > 75) {
    parts.push(`體力（${staminaPct}分）充沛，具備全程保持力`);
  } else if (s.energyLevel < 40) {
    parts.push(`近期能量值偏低（${Math.round(s.energyLevel)}分），體力恐未完全恢復`);
  } else if (s.stamina < 45 && isLong) {
    parts.push(`耐力僅 ${staminaPct} 分，今場長途賽恐尾段乏力`);
  }

  // ── 5. 穩定性評估 ──
  const conPct = Math.round(s.consistency * 100);
  if (s.consistency > 0.85) {
    parts.push(`穩定性高達 ${conPct}%，發揮少有失準`);
  } else if (s.consistency < 0.50) {
    parts.push(`穩定性僅 ${conPct}%，表現飄忽不定，落注需審慎`);
  }

  // ── 6. 騎師配搭分析 ──
  if (jockey.rating >= 85) {
    parts.push(`配搭頂級騎師 ${jockey.name}（評分 ${jockey.rating}），人馬配合有力保證`);
  } else if (jockey.rating >= 70) {
    parts.push(`騎師 ${jockey.name} 經驗充足`);
  } else {
    parts.push(`騎師 ${jockey.name} 經驗尚淺（評分 ${jockey.rating}），臨場發揮待觀察`);
  }
  if (jockey.apprenticeAllowance) {
    parts.push(`見習減 ${jockey.apprenticeAllowance} 磅作戰，負磅優勢明顯`);
  }

  // ── 7. 特殊因素 ──
  const specials = [];
  if (s.finalSprint > 1.5) specials.push(`末段衝刺力 ${sprintPct} 分，壓線能力一流`);
  if (s.burstChance > 0.15) specials.push('具備突然爆發嘅冷門基因');
  if (s.dirtPreference > 1.0) specials.push('泥地賽有額外加成');
  if (s.trackPreference === 'yielding') specials.push('偏好軟身場地');

  const personality = horse.meta?.personality;
  if (personality) {
    const pMap = {
      '穩定': '性格穩定可靠',
      '爆發': '有突然提速嘅能力',
      '懶馬': '有時欠缺鬥心，需要騎師催策',
      '神經質': '容易受環境影響',
      '鬥心強': '鬥志旺盛，越鬥越勇',
      '大將風範': '大賽型選手，壓力下表現更佳',
    };
    if (pMap[personality]) specials.push(pMap[personality]);
  }
  if (specials.length > 0) parts.push(specials.join('，'));

  return parts.join('。') + '。';
}

function generateWeight(rng, tier) {
  const ranges = { S: [128,133], A: [125,131], B: [120,127], C: [115,121], D: [110,116] };
  const [min, max] = ranges[tier];
  return Math.floor(rng() * (max - min + 1)) + min;
}

// Generate full race day (10 races)
export function generateRaceDay(seed) {
  const rng = seedrandom(seed);
  const allHorses = buildHorseDatabase(rng);
  const races = [];
  for (let i = 0; i < 10; i++) {
    races.push(generateRace(seed, i, allHorses));
  }
  return { races, allHorses, seed };
}
