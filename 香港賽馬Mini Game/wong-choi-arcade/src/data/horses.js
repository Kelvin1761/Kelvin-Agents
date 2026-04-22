/**
 * 旺財街機 — 馬匹資料庫 (170+ 匹)
 * 來源：HKJC 2025-2026 馬季現役 + 傳奇殿堂
 * Single Source of Truth: 旺財街機_完整計劃書.txt v4.0
 */

// Horse Entity Schema
// {
//   id: string,           name: string (中文馬名),
//   tier: 'S'|'A'|'B'|'C'|'D',
//   stats: { baseSpeed, stamina, burstChance, burstPower, finalSprint,
//            consistency, gateSpeed, trackPreference, distanceFit, energyLevel,
//            dirtPreference, runningStyle },
//   meta: { setJockey: string|null, personality: string|null,
//           silkColors: { primary, secondary, pattern } }
// }

// Stat generation ranges by tier
const TIER_RANGES = {
  S: { baseSpeed: [3.0,3.5], stamina: [85,100], burstChance: [0.15,0.30], burstPower: [2.2,2.8], finalSprint: [1.4,1.8], consistency: [0.85,0.98], gateSpeed: [1.1,1.5], energyLevel: [85,100] },
  A: { baseSpeed: [2.7,3.3], stamina: [78,95],  burstChance: [0.12,0.25], burstPower: [1.9,2.5], finalSprint: [1.2,1.6], consistency: [0.80,0.95], gateSpeed: [1.0,1.4], energyLevel: [80,95] },
  B: { baseSpeed: [2.2,3.0], stamina: [65,85],  burstChance: [0.08,0.20], burstPower: [1.6,2.2], finalSprint: [0.8,1.3], consistency: [0.65,0.85], gateSpeed: [0.8,1.2], energyLevel: [65,85] },
  C: { baseSpeed: [1.5,2.5], stamina: [50,75],  burstChance: [0.05,0.15], burstPower: [1.4,1.8], finalSprint: [0.5,1.0], consistency: [0.50,0.75], gateSpeed: [0.6,1.0], energyLevel: [55,75] },
  D: { baseSpeed: [1.0,2.0], stamina: [40,65],  burstChance: [0.03,0.12], burstPower: [1.3,1.6], finalSprint: [0.3,0.7], consistency: [0.40,0.65], gateSpeed: [0.5,0.9], energyLevel: [50,70] },
};

const RUNNING_STYLES = ['領放', '居前', '居中', '後上'];
const TRACK_PREFS = ['good', 'yielding', 'soft'];
const DISTANCE_FITS = ['short', 'mid', 'long'];
const PERSONALITIES = ['膽小鬼', '獨行俠', '大舞台', '早鳥', '鐵腳', '雨戰王', '激動型', null];

// ═══════════════════════════════════════════
// 🏆 傳奇殿堂組 (S 級 · @1.5-@3.0) — 12 匹
// ═══════════════════════════════════════════
const LEGEND_HORSES = [
  { id: 'silent_witness',    name: '精英大師', tier: 'S', meta: { setJockey: 'coetzee', silkColors: { primary: '#000000', secondary: '#228B22', pattern: 'cross' } } },
  { id: 'able_friend',       name: '步步友',   tier: 'S', meta: { setJockey: 'moreira', silkColors: { primary: '#000000', secondary: '#FFD700', pattern: 'vee' } } },
  { id: 'ka_ying_rising',    name: '嘉應高昇', tier: 'S', meta: { setJockey: 'purton',  silkColors: { primary: '#ADD8E6', secondary: '#FF6600', pattern: 'sleeves' } } },
  { id: 'viva_pataca',       name: '翠亨賓客', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#800080', secondary: '#FFD700', pattern: 'border' } } },
  { id: 'beauty_generation', name: '美麗傳承', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#000000', secondary: '#FFB6C1', pattern: 'sleeves' } } },
  { id: 'good_ba_ba',        name: '好利高',   tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#FFFFFF', secondary: '#FF0000', pattern: 'cross' } } },
  { id: 'lotus_gem',         name: '蓮華生輝', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#800080', secondary: '#C0C0C0', pattern: 'bow' } } },
  { id: 'bullish_luck',      name: '牛精福星', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#FF0000', secondary: '#FFD700', pattern: 'stars' } } },
  { id: 'e_unicorn',         name: '電子麒麟', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#0000FF', secondary: '#FFFFFF', pattern: 'lightning' } } },
  { id: 'lucky_nine',        name: '靚蝦王',   tier: 'S', meta: { setJockey: 'fradd',   silkColors: { primary: '#FF6600', secondary: '#FFFFFF', pattern: 'stripe' } } },
  { id: 'ambitious_dragon',  name: '針鋒相對', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#006400', secondary: '#FFD700', pattern: 'dragon' } } },
  { id: 'fairy_king_prawn',  name: '祈勝仙子', tier: 'S', meta: { setJockey: null,      silkColors: { primary: '#FF69B4', secondary: '#FFFFFF', pattern: 'fairy' } } },
];

// ═══════════════════════════════════════════
// 🔴 超級熱門組 (A 級 · @2.5-@5.0) — 16 匹
// ═══════════════════════════════════════════
const A_TIER_HORSES = [
  { id: 'romantic_warrior',  name: '浪漫勇士', tier: 'A', meta: { setJockey: 'mcdonald', silkColors: { primary: '#87CEEB', secondary: '#FFFFFF', pattern: 'vee' } } },
  { id: 'golden_sixty',      name: '金槍六十', tier: 'A', meta: { setJockey: 'ho_cy',    silkColors: { primary: '#FFFFFF', secondary: '#FFD700', pattern: 'vee_stars' } } },
  { id: 'california_spangle',name: '加州星球', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#FFD700', secondary: '#FF0000', pattern: 'sleeves' } } },
  { id: 'happy_smiles',      name: '信心歡笑', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#FFB6C1', secondary: '#FFFFFF', pattern: 'hearts' } } },
  { id: 'voyage_bubble',     name: '遙遙領先', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#0000CD', secondary: '#FFFFFF', pattern: 'stripe' } } },
  { id: 'supreme_power',     name: '大至尊',   tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#8B0000', secondary: '#FFD700', pattern: 'crown' } } },
  { id: 'wishes',            name: '祝願',     tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#FF6347', secondary: '#FFFFFF', pattern: 'stars' } } },
  { id: 'star_player',       name: '球星',     tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#1E90FF', secondary: '#FFFFFF', pattern: 'ball' } } },
  { id: 'supreme_king',      name: '大天王',   tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#FFD700', secondary: '#000000', pattern: 'crown' } } },
  { id: 'supreme_treasure',  name: '至尊瑰寶', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#800080', secondary: '#FFD700', pattern: 'gem' } } },
  { id: 'elite_spirit',      name: '精英雄心', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#C0C0C0', secondary: '#0000FF', pattern: 'shield' } } },
  { id: 'summit_glory',      name: '會當凌',   tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#228B22', secondary: '#FFFFFF', pattern: 'mountain' } } },
  { id: '展雄志',            name: '展雄志',   tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#000080', secondary: '#FF0000', pattern: 'stripe' } } },
  { id: 'fairy_land',        name: '蓬萊仙境', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#E6E6FA', secondary: '#FFD700', pattern: 'clouds' } } },
  { id: 'splendid_champion', name: '競駿輝煌', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#FF4500', secondary: '#FFFFFF', pattern: 'diamond' } } },
  { id: 'ka_ying_legacy',    name: '嘉應傳承', tier: 'A', meta: { setJockey: null,       silkColors: { primary: '#ADD8E6', secondary: '#FFFFFF', pattern: 'vee' } } },
];

// ═══════════════════════════════════════════
// 🟠 實力組 (B 級 · @5.0-@12.0) — 40+ 匹
// ═══════════════════════════════════════════
const B_TIER_NAMES = [
  '燈膽將軍','平凡騎士','友愛心得','遨遊武士','春風萬里','晨曦灑人','得道猴王',
  '八駿巨昇','英雄豪傑','銀亮奔騰','超級龍華','威利金箭','巴基之勝','氣勢',
  '翠紅','晒冷','飲杯','天星','快路','和平波','信心星','桃花開','鈦易搵',
  '新意馬','昇瀧駒','喜尊龍','愛馬善','韋金主','仁心星','喜至寶','白鷺金剛',
  '小鳥天堂','錶之銀河','驕陽明駒','禪勝輝煌','超超比','直線力山','多巴先生',
  '神虎龍駒','包裝必勝','幸運有您'
];

// ═══════════════════════════════════════════
// 🟡 中游組 (C 級 · @12.0-@30.0) — 50 匹
// ═══════════════════════════════════════════
const C_TIER_NAMES = [
  '馬力','膨才','米奇','銀進','風將','奔放','泰坦','增強','神鵰','瑪瑙',
  '傲聖','神馳','冷娃','金主','寶進','耀寶','星幻','安都','將睿','泰力',
  '赤海','優才','安帝','凌登','安泰','安路','嵐鑽','將義','乘數表','話你知',
  '一定掂','凱旋升','勁先生','天賜喜','超力量','紅逸舍','俏眼光','友瑩光',
  '香港仔','晉步贏','確好勁','喜豐年','巴閉仔','巨靈神','巨星駒','歡樂至寶',
  '紫荊歡呼','美麗第一','韋小寶','同樣美麗'
];

// ═══════════════════════════════════════════
// 🟢 冷門組 (D 級 · @30.0-@80.0) — 50 匹
// ═══════════════════════════════════════════
const D_TIER_NAMES = [
  '飛雲','勁騷','首駿','本能','迅意','銳一','千杯','焦點','風雲','拚搏',
  '勁爽','爆熱','永福','煌令','銳逸','獵寶勤','辣得金','小皇爺','星之願',
  '魅力星','天比高','型到爆','美神來','熊噹噹','桃花多','贏得爽','戰騎飛',
  '南區旺','劍無情','東昇鉞','駿先生','添喜運','龍又生','金德義','富貴駒',
  '常多笑','江南盛','同宝宝','哥得寶','極歡欣','綠頂峰','銳行星','銀騎士',
  '博士生','大浪園田','特別美麗','鐵甲驕龍','悠悠乾坤','鄉村樂韻','歡樂老鍋'
];

// Utility: generate random stat within range using seeded RNG
function genStat(rng, range) {
  const [min, max] = range;
  return +(min + rng() * (max - min)).toFixed(3);
}

// Generate full horse object from minimal definition
function buildHorse(def, rng) {
  const tier = def.tier;
  const ranges = TIER_RANGES[tier];
  return {
    id: def.id,
    name: def.name,
    tier,
    stats: {
      baseSpeed:       genStat(rng, ranges.baseSpeed),
      stamina:         Math.round(genStat(rng, ranges.stamina)),
      burstChance:     genStat(rng, ranges.burstChance),
      burstPower:      genStat(rng, ranges.burstPower),
      finalSprint:     genStat(rng, ranges.finalSprint),
      consistency:     genStat(rng, ranges.consistency),
      gateSpeed:       genStat(rng, ranges.gateSpeed),
      trackPreference: TRACK_PREFS[Math.floor(rng() * TRACK_PREFS.length)],
      distanceFit:     DISTANCE_FITS[Math.floor(rng() * DISTANCE_FITS.length)],
      energyLevel:     Math.round(genStat(rng, ranges.energyLevel)),
      dirtPreference:  +(0.5 + rng() * 1.0).toFixed(2),
      runningStyle:    RUNNING_STYLES[Math.floor(rng() * RUNNING_STYLES.length)],
    },
    meta: {
      setJockey:   def.meta?.setJockey || null,
      personality: PERSONALITIES[Math.floor(rng() * PERSONALITIES.length)],
      silkColors:  def.meta?.silkColors || { primary: '#888', secondary: '#FFF', pattern: 'plain' },
    },
    raceRecord: [],
  };
}

// Convert name-only lists to minimal definition objects
function nameToId(name) {
  return name.replace(/\s/g, '_').toLowerCase();
}

function namesToDefs(names, tier) {
  return names.map(name => ({
    id: nameToId(name),
    name,
    tier,
    meta: { setJockey: null, silkColors: null },
  }));
}

// Build complete database
export function buildHorseDatabase(rng) {
  const allDefs = [
    ...LEGEND_HORSES,
    ...A_TIER_HORSES,
    ...namesToDefs(B_TIER_NAMES, 'B'),
    ...namesToDefs(C_TIER_NAMES, 'C'),
    ...namesToDefs(D_TIER_NAMES, 'D'),
  ];
  return allDefs.map(def => buildHorse(def, rng));
}

export { TIER_RANGES, RUNNING_STYLES, TRACK_PREFS, DISTANCE_FITS, PERSONALITIES };
