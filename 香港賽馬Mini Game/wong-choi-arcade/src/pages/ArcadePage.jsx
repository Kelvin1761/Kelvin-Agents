/**
 * 旺財街機 — 遊戲主頁面
 * 管理遊戲狀態機 + 各階段 UI 渲染
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useMachine } from '@xstate/react';
import { gameMachine } from '../state/gameMachine';
import { generateRace } from '../utils/raceGenerator';
import { buildHorseDatabase } from '../data/horses';
import { RaceEngine } from '../engine/RaceEngine';
import { soundManager } from '../engine/SoundManager';
import seedrandom from 'seedrandom';
import BettingPanel from '../components/Arcade/BettingPanel';
import NewsScroller from '../components/Arcade/NewsScroller';
import RaceResult from '../components/Arcade/RaceResult';
import DaySummary from '../components/Arcade/DaySummary';
import PaddockScene from '../components/Arcade/PaddockScene';
import './ArcadePage.css';

// localStorage persistence
const STORAGE_KEY = 'wongchoi_arcade';
function loadSave() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)); } catch { return null; }
}
function savePersist(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...data, version: '4.0', savedAt: new Date().toISOString() }));
}

export default function ArcadePage() {
  const [state, send] = useMachine(gameMachine);
  const [allHorses, setAllHorses] = useState(null);
  const [save, setSave] = useState(() => loadSave());

  // Auto-generate race when entering raceSetup
  useEffect(() => {
    if (state.matches('raceSetup') && state.context.seed) {
      const rng = seedrandom(state.context.seed);
      if (!allHorses) {
        setAllHorses(buildHorseDatabase(rng));
      }
      const raceData = generateRace(
        state.context.seed,
        state.context.currentRace,
        allHorses || buildHorseDatabase(rng)
      );
      send({ type: 'RACE_GENERATED', raceData });
    }
  }, [state.value, state.context.currentRace, state.context.seed]);

  // Persist on state changes
  useEffect(() => {
    if (state.context.players.length > 0) {
      savePersist({
        highScore: save?.highScore || 0,
        totalRaceDays: save?.totalRaceDays || 0,
        bestOddsHit: save?.bestOddsHit || 0,
        achievements: state.context.achievements,
        lastSession: {
          balance: state.context.players[0]?.balance,
          currentRace: state.context.currentRace,
        },
      });
    }
  }, [state.context]);

  const handleStartSolo = useCallback(() => {
    soundManager.init();
    soundManager.play('confirm');
    send({ type: 'START_SOLO' });
  }, [send]);
  const handlePlayAgain = useCallback(() => {
    soundManager.play('click');
    send({ type: 'PLAY_AGAIN' });
  }, [send]);

  // ═══ 渲染各狀態 ═══
  return (
    <div className="arcade-container">
      <div className="arcade-header">
        <h1 className="arcade-title">🕹️ 旺財街機</h1>
        {state.context.players[0] && (
          <div className="arcade-balance">
            💰 ${state.context.players[0].balance.toLocaleString()}
          </div>
        )}
        {state.context.currentRace > 0 && (
          <div className="arcade-race-num">
            第 {state.context.currentRace + 1} / {state.context.totalRaces} 場
          </div>
        )}
      </div>

      {/* MENU */}
      {state.matches('menu') && (
        <div className="arcade-menu">
          <div className="menu-logo">
            <div className="pixel-horse">🐴</div>
            <h2>旺財街機 Wong Choi Arcade</h2>
            <p className="menu-subtitle">像素賽馬 × 情報分析策略遊戲</p>
          </div>
          <div className="menu-buttons">
            <button className="btn-arcade btn-solo" onClick={handleStartSolo}>
              🎮 單機模式
            </button>
            <button className="btn-arcade btn-multi" disabled>
              👥 多人模式 (Coming Soon)
            </button>
          </div>
          {save && (
            <div className="menu-stats">
              <p>🏆 最高紀錄: ${save.highScore?.toLocaleString() || 0}</p>
              <p>📅 累計賽日: {save.totalRaceDays || 0}</p>
            </div>
          )}
          <div className="menu-tip">
            <p>💡 閱讀旺財晨報，分析 Wong Choi 指標，做出最精準嘅投注決定！</p>
          </div>
        </div>
      )}

      {/* INTEL REVIEW — 賽前情報 + 出馬表 */}
      {state.matches('intelReview') && state.context.raceData && (() => {
        const rd = state.context.raceData;
        const fav = rd.runners[0]; // sorted by odds, first = favourite
        const outsider = rd.runners[rd.runners.length - 1];
        return (
          <div className="arcade-intel">
            {/* 圍場熱身動畫 */}
            <PaddockScene runners={rd.runners} mode="warmup" />

            {/* Race Card Header */}
            <div className="intel-race-card">
              <div className="race-card-title">
                <span className="race-number-big">R{rd.raceNumber}</span>
                <div className="race-card-details">
                  <h2>{rd.venue === '跑馬地' ? '🌙' : '☀️'} {rd.venue} — {rd.raceClass}</h2>
                  <div className="race-card-sub">
                    <span>📏 {rd.distance}m</span>
                    <span>🏟️ {rd.venue === '跑馬地' ? '右轉 C+3 跑道' : '左轉 A 跑道'}</span>
                    <span>🌤️ {rd.trackCondition === 'yielding' ? '好至黏地' : '好地'}</span>
                    {rd.isDirt && <span>🟤 泥地賽</span>}
                  </div>
                </div>
              </div>
            </div>

            {/* 出馬表 Quick View */}
            <div className="intel-runner-table">
              <div className="runner-table-header">
                <span className="th-barrier">檔</span>
                <span className="th-name">馬名</span>
                <span className="th-jockey">騎師</span>
                <span className="th-weight">磅</span>
                <span className="th-form">近績</span>
                <span className="th-odds">賠率</span>
              </div>
              {rd.runners.map((r, i) => {
                const isFav = i === 0;
                const isOutsider = i === rd.runners.length - 1;
                return (
                  <div key={r.horse.id} className={`runner-table-row ${isFav ? 'row-fav' : ''} ${isOutsider ? 'row-outsider' : ''}`}>
                    <span className="td-barrier">{r.barrier}</span>
                    <span className="td-name">
                      <span className="td-silk" style={{
                        background: r.horse.meta.silkColors?.primary || '#888'
                      }} />
                      {r.horse.name}
                      <span className={`tier-mini tier-${r.horse.tier}`}>{r.horse.tier}</span>
                    </span>
                    <span className="td-jockey">{r.jockey.name}</span>
                    <span className="td-weight">{r.weight}</span>
                    <span className="td-form">
                      {r.raceRecord.slice(0, 4).map((rec, j) => (
                        <span key={j} className={rec.position <= 3 ? 'form-top3' : ''}>{rec.position}</span>
                      ))}
                    </span>
                    <span className={`td-odds ${r.odds <= 5 ? 'odds-hot' : r.odds >= 30 ? 'odds-cold' : ''}`}>
                      @{r.odds}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Highlights: Favourite vs Outsider */}
            <div className="intel-highlights">
              <div className="highlight-box highlight-fav">
                <span className="highlight-label">🔥 大熱門</span>
                <span className="highlight-name">{fav.horse.name}</span>
                <span className="highlight-odds">@{fav.odds}</span>
                <span className="highlight-jockey">🏇 {fav.jockey.name}</span>
              </div>
              <div className="highlight-box highlight-outsider">
                <span className="highlight-label">🎲 大冷門</span>
                <span className="highlight-name">{outsider.horse.name}</span>
                <span className="highlight-odds">@{outsider.odds}</span>
                <span className="highlight-jockey">🏇 {outsider.jockey.name}</span>
              </div>
            </div>

            {/* 旺財晨報 */}
            <NewsScroller intel={rd.intel} />

            {/* 棟哥貼士 */}
            <div className="donggo-tip">
              <span className="donggo-avatar">🐕</span>
              <div className="donggo-content">
                <span className="donggo-label">棟哥貼士</span>
                <span>棟哥搖頭指住 <strong>{rd.dongGo.pickName}</strong>，尾巴搖過不停！</span>
                <span className="donggo-disclaimer">（歷史準確率 ≈ 40%，僅供參考）</span>
              </div>
            </div>

            <button
              className="btn-arcade btn-proceed"
              onClick={() => send({ type: 'PROCEED_TO_BETTING' })}
            >
              📊 睇馬落注 →
            </button>
          </div>
        );
      })()}

      {/* BETTING */}
      {state.matches('betting') && state.context.raceData && (
        <div>
          <PaddockScene runners={state.context.raceData.runners} mode="warmup" />
          <BettingPanel
            raceData={state.context.raceData}
            balance={state.context.players[0]?.balance || 0}
            onConfirmBets={(bets) => {
              send({ type: 'PLACE_BET', bets });
              send({ type: 'CONFIRM_BETS' });
            }}
          />
        </div>
      )}

      {/* RACING — 入閘 → PixiJS Canvas */}
      {state.matches('racing') && (
        <RaceView
          raceData={state.context.raceData}
          onFinish={(result) => send({ type: 'RACE_FINISHED', result })}
        />
      )}

      {/* PHOTO FINISH */}
      {state.matches('photoFinish') && (
        <div className="arcade-photo-finish">
          <h2>📸 Photo Finish!</h2>
          <button className="btn-arcade" onClick={() => send({ type: 'PHOTO_DONE' })}>
            繼續 →
          </button>
        </div>
      )}

      {/* RESULT */}
      {state.matches('result') && state.context.raceResult && (
        <RaceResult
          result={state.context.raceResult}
          bets={state.context.bets}
          balance={state.context.players[0]?.balance}
          onNext={() => send({ type: 'NEXT_RACE' })}
        />
      )}

      {/* BANKRUPTCY */}
      {state.matches('bankruptcy') && (
        <div className="arcade-bankruptcy">
          <div className="bankruptcy-dialog">
            <h2>💀 財神財務 (大耳窿)</h2>
            <p>輸清光啦？㩒個掣即批 $500 俾你翻本！</p>
            <div className="bankruptcy-buttons">
              <button className="btn-arcade btn-loan" onClick={() => send({ type: 'ACCEPT_LOAN' })}>
                💰 接受借貸
              </button>
              <button className="btn-arcade btn-reject" onClick={() => send({ type: 'REJECT_LOAN' })}>
                🚪 拒絕 (Game Over)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DAY SUMMARY */}
      {state.matches('daySummary') && (
        <DaySummary
          players={state.context.players}
          raceHistory={state.context.raceHistory}
          loanCount={state.context.loanCount}
          onPlayAgain={handlePlayAgain}
        />
      )}
    </div>
  );
}

// RaceView: 入閘動畫 → PixiJS 引擎
function RaceView({ raceData, onFinish }) {
  const [phase, setPhase] = useState('entering'); // 'entering' → 'ready' → 'racing'
  const containerRef = useRef(null);
  const engineRef = useRef(null);

  // Gate entering → ready → start race
  useEffect(() => {
    if (!raceData) return;

    // Phase 1: entering (horses enter gate one by one)
    const enterTimer = setTimeout(() => {
      setPhase('ready');
    }, raceData.runners.length * 300 + 500); // each horse takes 300ms

    // Phase 2: ready → start race after 2s
    const readyTimer = setTimeout(() => {
      setPhase('racing');
    }, raceData.runners.length * 300 + 2500);

    return () => {
      clearTimeout(enterTimer);
      clearTimeout(readyTimer);
    };
  }, [raceData]);

  // Init PixiJS when phase becomes 'racing'
  useEffect(() => {
    if (phase !== 'racing' || !containerRef.current || !raceData) return;

    const engine = new RaceEngine();
    engineRef.current = engine;

    engine.init(containerRef.current, raceData, (result) => {
      onFinish(result);
    }).then(() => {
      engine.start();
    }).catch(err => {
      console.error('PixiJS init failed, using fallback:', err);
      setTimeout(() => onFinish(simulateFallbackResult(raceData)), 3000);
    });

    return () => {
      engine.destroy();
      engineRef.current = null;
    };
  }, [phase, raceData]);

  if (phase === 'entering' || phase === 'ready') {
    return (
      <div className="arcade-racing">
        <PaddockScene runners={raceData.runners} mode={phase} />
      </div>
    );
  }

  return (
    <div className="arcade-racing">
      <div ref={containerRef} className="race-canvas-container" />
    </div>
  );
}

// Fallback simulation (if PixiJS fails)
function simulateFallbackResult(raceData) {
  const runners = [...raceData.runners];
  const weights = runners.map(r => 1 / r.odds);
  const sorted = [];
  const remaining = runners.map((r, i) => ({ ...r, w: weights[i] }));
  for (let pos = 0; pos < runners.length; pos++) {
    const totalW = remaining.reduce((a, r) => a + r.w, 0);
    let rand = Math.random() * totalW;
    let picked = 0;
    for (let i = 0; i < remaining.length; i++) {
      rand -= remaining[i].w;
      if (rand <= 0) { picked = i; break; }
    }
    sorted.push({ ...remaining[picked], position: pos + 1 });
    remaining.splice(picked, 1);
  }
  return { positions: sorted, stewardsInquiry: Math.random() < 0.05, incidents: [] };
}
