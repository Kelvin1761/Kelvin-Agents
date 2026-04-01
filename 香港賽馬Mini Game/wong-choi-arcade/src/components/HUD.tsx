import { useEffect, useState } from 'react';
import type { RunnerState } from '../game/GameEngine';

interface HUDProps {
  runners: RunnerState[];
  distance: number;
}

export default function HUD({ runners, distance }: HUDProps) {
  const [raceTime, setRaceTime] = useState<number>(0);

  // Simple stopwatch
  useEffect(() => {
    let startTime = performance.now();
    let rAF: number;
    const loop = (now: number) => {
       setRaceTime((now - startTime) / 1000);
       rAF = requestAnimationFrame(loop);
    };
    rAF = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rAF);
  }, []);

  // Format time mm:ss.ms
  const formatTime = (seconds: number) => {
      const m = Math.floor(seconds / 60).toString().padStart(2, '0');
      const s = Math.floor(seconds % 60).toString().padStart(2, '0');
      const ms = Math.floor((seconds % 1) * 10).toString();
      return `${m}:${s}.${ms}`;
  };

  const sortedRunners = [...runners].sort((a, b) => b.position.x - a.position.x);
  const top4 = sortedRunners.slice(0, 4);
  const leaderX = sortedRunners[0]?.position.x || 0;
  
  const finishLineRemaining = Math.max(0, distance - leaderX);

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', 
                  fontFamily: '"Courier New", Courier, monospace', padding: '15px', boxSizing: 'border-box' }}>
       
       {/* Top Row: Clock & Distance */}
       <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
           
           {/* Distance Remaining */}
           <div style={{ background: 'rgba(0,0,0,0.7)', border: '2px solid #555', padding: '10px 15px', borderRadius: '8px' }}>
              <div style={{ fontSize: '12px', color: '#AAA', fontWeight: 'bold' }}>REMAINING 剩餘</div>
              <div style={{ fontSize: '24px', color: '#FFF', fontWeight: 'bold' }}>
                  {finishLineRemaining > 0 ? `${finishLineRemaining.toFixed(0)}m` : 'FINISH!'}
              </div>
           </div>
           
           {/* Clock */}
           <div style={{ background: 'rgba(0,0,0,0.7)', border: '2px solid #555', padding: '10px 15px', borderRadius: '8px', minWidth: '100px', textAlign: 'center' }}>
              <div style={{ fontSize: '12px', color: '#AAA', fontWeight: 'bold' }}>TIME 時間</div>
              <div style={{ fontSize: '24px', color: '#0F0', fontWeight: 'bold' }}>
                  {formatTime(raceTime)}
              </div>
           </div>
       </div>

       {/* Top 4 Display Array */}
       <div style={{ position: 'absolute', top: '15px', left: '50%', transform: 'translateX(-50%)', 
                     background: 'rgba(0,0,0,0.7)', padding: '5px 10px', borderRadius: '8px', border: '2px solid #555',
                     display: 'flex', gap: '8px' }}>
           <div style={{ fontSize: '12px', color: '#AAA', writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>LEADER</div>
           {top4.map((r, i) => (
               <div key={`hud-${r.competitor.id}`} 
                    style={{ width: '30px', height: '30px', background: i===0?'#FFD700': i===1?'#C0C0C0': i===2?'#CD7F32':'#333', 
                             color: i < 3 ? '#000' : '#FFF', display: 'flex', alignItems: 'center', justifyContent: 'center', 
                             fontSize: '20px', fontWeight: 'bold', borderRadius: '4px', border: '2px solid #000' }}>
                   {r.competitor.id}
               </div>
           ))}
       </div>

       {/* Scanline CRT overlay effect */}
       <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', 
                     background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06))',
                     backgroundSize: '100% 4px, 6px 100%', pointerEvents: 'none', mixBlendMode: 'overlay', opacity: 0.5 }} />
    </div>
  );
}
