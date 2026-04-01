import type { RunnerState } from '../game/GameEngine';

interface ResultBoardProps {
  results: RunnerState[];
  totalPayout: number;
  trioWin: boolean;
  jackpotWin: number;
  onNextRace: () => void;
}

export default function ResultBoard({ results, totalPayout, trioWin, jackpotWin, onNextRace }: ResultBoardProps) {
  
  const top4 = results.slice(0, 4);

  return (
    <div style={{ padding: '20px', fontFamily: '"Courier New", Courier, monospace', color: '#FFF', background: 'rgba(0, 0, 0, 0.85)', 
                  border: '4px solid #FFD700', borderRadius: 8, width: 800, height: 400, position: 'absolute', top: 0, left: 0, 
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      
      <h1 style={{ color: '#FFD700', marginBottom: '10px', textShadow: '2px 2px 0 #F00' }}>賽果公佈 OFFICIAL RESULT</h1>

      {/* Top 4 Display */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '30px' }}>
          {top4.map((r, i) => (
             <div key={r.competitor.id} style={{ background: '#333', border: `2px solid ${i===0?'#FFD700': i===1?'#C0C0C0': i===2?'#CD7F32':'#555'}`, padding: '15px', textAlign: 'center', borderRadius: '8px', minWidth: '100px' }}>
                 <div style={{ fontSize: '24px', fontWeight: 'bold', color: i===0?'#FFD700': i===1?'#C0C0C0': i===2?'#CD7F32':'#FFF' }}>第 {i+1} 名</div>
                 <div style={{ fontSize: '32px', fontWeight: 'bold', margin: '10px 0', color: '#FAA' }}>{r.competitor.id}</div>
                 <div style={{ fontSize: '14px' }}>{r.competitor.horse.name.zh}</div>
             </div>
          ))}
      </div>

      {/* Payout Display */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '30px', width: '100%', justifyContent: 'center' }}>
          <div style={{ background: totalPayout > 0 ? '#005500' : '#550000', padding: '15px 40px', borderRadius: '8px', border: `2px solid ${totalPayout > 0 ? '#0F0' : '#F00'}`, textAlign: 'center', flex: 1, maxWidth: '300px' }}>
              <div style={{ fontSize: '18px', color: '#AAA' }}>普通派彩 PAYOUT</div>
              <div style={{ fontSize: '36px', fontWeight: 'bold', color: totalPayout > 0 ? '#0F0' : '#F00' }}>
                  {totalPayout > 0 ? `+ $${totalPayout.toFixed(1)}` : '$0.0'}
              </div>
          </div>
          
          <div style={{ background: trioWin ? '#FFD700' : '#333', padding: '15px 40px', borderRadius: '8px', border: `2px solid ${trioWin ? '#FFF' : '#555'}`, textAlign: 'center', flex: 1, maxWidth: '300px' }}>
              <div style={{ fontSize: '18px', color: trioWin ? '#000' : '#AAA' }}>單T特獎 (JACKPOT)</div>
              <div style={{ fontSize: '36px', fontWeight: 'bold', color: trioWin ? '#F00' : '#555' }}>
                  {trioWin ? `+ $${jackpotWin.toLocaleString()}` : 'FAILED'}
              </div>
          </div>
      </div>

      <button onClick={onNextRace} 
              style={{ background: '#222', color: '#FFF', fontSize: '18px', padding: '10px 30px', 
                       border: '2px solid #FFF', borderRadius: '8px', cursor: 'pointer' }}>
         下一場比賽 NEXT RACE
      </button>

    </div>
  );
}
