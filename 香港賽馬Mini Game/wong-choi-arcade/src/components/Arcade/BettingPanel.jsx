/**
 * 投注面板 — 12 匹馬 Wong Choi 卡片 + 選馬 + 注碼
 */
import { useState } from 'react';
import { soundManager } from '../../engine/SoundManager';

const BET_TYPES = [
  { id: 'win', label: '🏆 獨贏', picks: 1 },
  { id: 'place', label: '🏅 位置', picks: 1 },
  { id: 'quinella', label: '🔄 連贏', picks: 2 },
  { id: 'wp', label: '🔄 位置Q', picks: 2 },
  { id: 'tierce', label: '🎰 三重彩', picks: 3 },
  { id: 'trio', label: '🎰 三重彩(唔順序)', picks: 3 },
];

export default function BettingPanel({ raceData, balance, onConfirmBets }) {
  const [betType, setBetType] = useState('win');
  const [selectedHorses, setSelectedHorses] = useState([]);
  const [stake, setStake] = useState(100);

  const currentBetType = BET_TYPES.find(b => b.id === betType);
  const maxPicks = currentBetType?.picks || 1;

  const toggleHorse = (horseId) => {
    soundManager.play('click');
    setSelectedHorses(prev => {
      if (prev.includes(horseId)) return prev.filter(id => id !== horseId);
      if (prev.length >= maxPicks) return [...prev.slice(1), horseId];
      return [...prev, horseId];
    });
  };

  const handleConfirm = () => {
    if (selectedHorses.length !== maxPicks) { soundManager.play('error'); return; }
    if (stake < 10 || stake > balance) { soundManager.play('error'); return; }
    soundManager.play('bet');
    onConfirmBets([{
      type: betType,
      horses: selectedHorses,
      stake,
    }]);
  };

  // Progress bar helper
  const StatBar = ({ label, emoji, value, max = 100 }) => (
    <div className="stat-bar">
      <span className="stat-emoji">{emoji}</span>
      <span className="stat-label">{label}</span>
      <div className="stat-track">
        <div className="stat-fill" style={{
          width: `${Math.min(100, (value / max) * 100)}%`,
          background: value > 70 ? '#00ff88' : value > 40 ? '#ffd700' : '#ff4444',
        }} />
      </div>
      <span className="stat-value">{Math.round(Math.min(100, value))}</span>
    </div>
  );

  return (
    <div className="betting-panel">
      <div className="race-info-bar">
        <span>{raceData.venue === '跑馬地' ? '🌙' : '☀️'} {raceData.venue}</span>
        <span>{raceData.raceClass}</span>
        <span>{raceData.distance}m</span>
        {raceData.isDirt && <span>🟤 泥地</span>}
      </div>

      {/* Bet type selector */}
      <div className="bet-type-row">
        {BET_TYPES.map(bt => (
          <button
            key={bt.id}
            className={`btn-bet-type ${betType === bt.id ? 'active' : ''}`}
            onClick={() => { setBetType(bt.id); setSelectedHorses([]); }}
          >
            {bt.label}
          </button>
        ))}
      </div>

      {/* Horse cards grid */}
      <div className="horse-cards-grid">
        {raceData.runners.map((runner, idx) => {
          const isSelected = selectedHorses.includes(runner.horse.id);
          const s = runner.horse.stats;
          const j = runner.jockey;
          const t = runner.trainer;
          const avgRecord = runner.raceRecord.reduce((a, r) => a + r.position, 0) / runner.raceRecord.length;
          return (
            <div
              key={runner.horse.id}
              className={`horse-card ${isSelected ? 'selected' : ''}`}
              onClick={() => toggleHorse(runner.horse.id)}
            >
              {/* Header: Barrier + Name + Odds */}
              <div className="card-header">
                <span className="barrier-num">#{runner.barrier}</span>
                <span className="silk-preview" style={{
                  background: `linear-gradient(135deg, ${runner.horse.meta.silkColors?.primary || '#888'} 50%, ${runner.horse.meta.silkColors?.secondary || '#fff'} 50%)`
                }} />
                <span className="horse-name">{runner.horse.name}</span>
                <span className={`tier-badge tier-${runner.horse.tier}`}>{runner.horse.tier}</span>
                <span className="horse-odds">@{runner.odds}</span>
              </div>

              {/* Jockey + Trainer + Weight */}
              <div className="card-meta">
                <div className="meta-row">
                  <span className="meta-label">🏇 騎師</span>
                  <span className="meta-value">{j.name}</span>
                  <span className="meta-rating">R{j.rating}</span>
                </div>
                <div className="meta-row">
                  <span className="meta-label">🏠 練馬師</span>
                  <span className="meta-value">{t.name}</span>
                  <span className="meta-rating">R{t.rating}</span>
                </div>
                <div className="meta-row">
                  <span className="meta-label">⚖️ 負磅</span>
                  <span className="meta-value">{runner.weight}磅</span>
                  {j.apprenticeAllowance && (
                    <span className="apprentice-tag">減{j.apprenticeAllowance}磅</span>
                  )}
                </div>
              </div>

              {/* Skills */}
              <div className="card-skills">
                <div className="skill-tag jockey-skill">🎯 {j.skill.name}: {j.skill.desc}</div>
                <div className="skill-tag trainer-skill">📋 {t.skill.name}</div>
                {runner.horse.meta.personality && (
                  <div className="skill-tag personality-tag">🧠 {runner.horse.meta.personality}</div>
                )}
              </div>

              {/* Race Record — 最近→最舊 */}
              <div className="card-record">
                <span className="record-label">近績</span>
                <span className="record-timeline">
                  <span className="timeline-arrow">最近</span>
                  {runner.raceRecord.map((r, i) => (
                    <span key={i} className={`record-pos ${r.position <= 3 ? 'top3' : ''}`}>
                      <span className="record-race-num">R{i + 1}</span>
                      {r.position}
                    </span>
                  ))}
                  <span className="timeline-arrow">舊</span>
                </span>
                <span className={`avg-badge ${avgRecord <= 3 ? 'avg-good' : avgRecord <= 6 ? 'avg-mid' : 'avg-poor'}`}>
                  平均 {avgRecord.toFixed(1)}
                </span>
              </div>

              {/* Stats bars */}
              <div className="card-stats">
                <StatBar label="速度" emoji="🏃" value={s.baseSpeed / 3.5 * 100} />
                <StatBar label="體力" emoji="⚡" value={s.energyLevel} />
                <StatBar label="耐力" emoji="💪" value={s.stamina} />
                <StatBar label="穩定" emoji="🎯" value={s.consistency * 100} />
                <StatBar label="衝刺" emoji="🚀" value={s.finalSprint / 1.8 * 100} />
                <StatBar label="爆發" emoji="💥" value={s.burstChance * 500} />
              </div>

              {/* Tags: running style + distance fit + track */}
              <div className="card-tags">
                <span className="tag running">{s.runningStyle}</span>
                <span className="tag distance">{s.distanceFit === 'short' ? '短途' : s.distanceFit === 'mid' ? '中距' : '長途'}</span>
                <span className="tag track">{s.trackPreference === 'good' ? '好地' : s.trackPreference === 'yielding' ? '黏地' : '軟地'}</span>
                {s.dirtPreference > 1.0 && <span className="tag dirt">泥地✓</span>}
              </div>

              {/* 旺財評語 */}
              {runner.comment && (
                <div className="card-comment">
                  <span className="comment-icon">🐕</span>
                  <p className="comment-text">{runner.comment}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Stake input */}
      <div className="stake-row">
        <div className="stake-info">
          <span>選咗 {selectedHorses.length}/{maxPicks} 匹</span>
          <span>餘額: ${balance.toLocaleString()}</span>
        </div>
        <div className="stake-input-group">
          <label>注碼: $</label>
          <input
            type="number"
            min={10}
            max={balance}
            step={10}
            value={stake}
            onChange={e => setStake(Math.max(10, Math.min(balance, parseInt(e.target.value) || 10)))}
          />
          <button className="btn-allin" onClick={() => setStake(balance)}>ALL IN 🔥</button>
        </div>
        <button
          className="btn-arcade btn-confirm-bet"
          disabled={selectedHorses.length !== maxPicks || stake < 10}
          onClick={handleConfirm}
        >
          ✅ 確認落注
        </button>
      </div>
    </div>
  );
}
