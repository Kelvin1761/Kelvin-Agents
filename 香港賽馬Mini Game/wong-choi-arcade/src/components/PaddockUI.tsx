import { useState } from 'react';
import type { Competitor } from '../game/RaceGenerator';

export type Bet = {
  horseId: number;
  type: 'WIN' | 'PLACE';
  amount: number;
};

interface PaddockUIProps {
  competitors: Competitor[];
  wallet: number;
  jackpot: number;
  bets: Bet[];
  trioBet: number[] | null;
  onPlaceBet: (horseId: number, type: 'WIN' | 'PLACE', amount: number) => void;
  onPlaceTrio: (horses: number[]) => void;
  onStartRace: () => void;
}

export default function PaddockUI({ competitors, wallet, jackpot, bets, trioBet, onPlaceBet, onPlaceTrio, onStartRace }: PaddockUIProps) {
  
  const [trioPicks, setTrioPicks] = useState<number[]>([]);
  
  const getHorseBets = (id: number) => bets.filter(b => b.horseId === id);

  const handleToggleTrio = (id: number) => {
      if (trioBet) return; // already bet
      if (trioPicks.includes(id)) {
          setTrioPicks(trioPicks.filter(i => i !== id));
      } else if (trioPicks.length < 3) {
          setTrioPicks([...trioPicks, id]);
      }
  };

  return (
    <div style={{ padding: '20px', fontFamily: '"Courier New", Courier, monospace', color: '#FFF', background: '#222', 
                  border: '4px solid #444', borderRadius: 8, width: 800, height: 400, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #555', paddingBottom: '10px', marginBottom: '10px' }}>
         <h2 style={{ margin: 0, color: '#FFD700' }}>沙圈與投注 (PADDOCK)</h2>
         <div style={{ display: 'flex', gap: '20px' }}>
             <h2 style={{ margin: 0, color: '#FAA' }}>三T JACKPOT: <span style={{ color: '#FFD700' }}>${jackpot.toLocaleString()}</span></h2>
             <h2 style={{ margin: 0, color: '#00FF00' }}>WALLET: ${wallet.toLocaleString()}</h2>
         </div>
      </div>

      {/* Trio Betting Panel */}
      <div style={{ background: '#300', border: '2px solid #F00', padding: '10px', marginBottom: '10px', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
              <div style={{ color: '#FFD700', fontWeight: 'bold' }}>單T特獎 (TRIO JACKPOT) - 買中前三名即可帶走大獎！</div>
              <div style={{ fontSize: '12px' }}>Pick exactly 3 horses. Cost: $50</div>
              <div style={{ display: 'flex', gap: '5px', marginTop: '5px' }}>
                  {trioBet ? (
                      <span style={{ color: '#0F0' }}>已下注單T: {trioBet.join(', ')}</span>
                  ) : (
                      <span style={{ color: '#AAA' }}>已選: {trioPicks.length === 0 ? '無' : trioPicks.join(', ')}</span>
                  )}
              </div>
          </div>
          <button 
             disabled={trioBet !== null || trioPicks.length !== 3 || wallet < 50}
             onClick={() => onPlaceTrio(trioPicks)}
             style={{ background: trioPicks.length === 3 ? '#FFD700' : '#555', color: '#000', fontWeight: 'bold', padding: '10px 20px', borderRadius: '4px', border: 'none', cursor: trioPicks.length === 3 ? 'pointer' : 'not-allowed' }}>
             BET TRIO ($50)
          </button>
      </div>

      {/* Horse List */}
      <div style={{ flex: 1, overflowY: 'auto', paddingRight: '10px' }}>
         {competitors.map(c => {
             const horseBets = getHorseBets(c.id);
             const winBet = horseBets.find(b => b.type === 'WIN')?.amount || 0;
             const plaBet = horseBets.find(b => b.type === 'PLACE')?.amount || 0;

             return (
               <div key={c.id} style={{ display: 'flex', alignItems: 'center', background: '#333', marginBottom: '5px', padding: '8px', borderRadius: '4px' }}>
                  <div style={{ width: '30px', fontWeight: 'bold', fontSize: '18px', color: '#FAA' }}>{c.id}.</div>
                  <div style={{ width: '150px' }}>
                     <div style={{ fontWeight: 'bold' }}>{c.horse.name.zh}</div>
                     <div style={{ fontSize: '12px', color: '#AAA' }}>騎: {c.jockey.name.zh} | 練: {c.trainer.name.zh}</div>
                  </div>
                  
                  <div style={{ width: '120px', textAlign: 'center' }}>
                     <div style={{ color: '#FFD700', fontSize: '18px', fontWeight: 'bold' }}>{c.odds.toFixed(1)}</div>
                     <div style={{ fontSize: '10px', color: '#888' }}>WIN ODDS</div>
                  </div>

                  {/* Betting Controls */}
                  <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '15px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#FAA' }}>
                          <input type="checkbox" checked={trioBet ? trioBet.includes(c.id) : trioPicks.includes(c.id)} 
                                 disabled={trioBet !== null || (!trioPicks.includes(c.id) && trioPicks.length >= 3)}
                                 onChange={() => handleToggleTrio(c.id)} />
                          選Trio
                      </label>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                          <span style={{ fontSize: '12px', color: '#FFF' }}>WIN: ${winBet}</span>
                          <button onClick={() => onPlaceBet(c.id, 'WIN', 10)} disabled={wallet < 10}
                                  style={{ background: '#550000', color: '#FFF', border: '1px solid #F00', padding: '2px 8px', cursor: wallet >= 10 ? 'pointer' : 'not-allowed' }}>
                             +$10
                          </button>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                          <span style={{ fontSize: '12px', color: '#FFF' }}>PLA: ${plaBet}</span>
                          <button onClick={() => onPlaceBet(c.id, 'PLACE', 10)} disabled={wallet < 10}
                                  style={{ background: '#000055', color: '#FFF', border: '1px solid #00F', padding: '2px 8px', cursor: wallet >= 10 ? 'pointer' : 'not-allowed' }}>
                             +$10
                          </button>
                      </div>
                  </div>
               </div>
             );
         })}
      </div>

      {/* Footer / Start Button */}
      <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '2px solid #555', display: 'flex', justifyContent: 'flex-end' }}>
         <button onClick={onStartRace} 
                 style={{ background: '#FF4500', color: '#FFF', fontSize: '20px', fontWeight: 'bold', padding: '10px 30px', 
                          border: '2px solid #FFF', borderRadius: '8px', cursor: 'pointer', boxShadow: '0 4px 0 #900' }}>
            入閘 START RACE!
         </button>
      </div>
    </div>
  );
}
