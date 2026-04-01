import { useEffect, useRef, useState } from 'react';
import { GameEngine } from './game/GameEngine';
import type { RunnerState, RacePhase } from './game/GameEngine';
import { RaceGenerator } from './game/RaceGenerator';
import type { Competitor } from './game/RaceGenerator';
import { setSeed } from './utils/rng';
import PixiApp from './components/PixiApp';
import PaddockUI from './components/PaddockUI';
import type { Bet } from './components/PaddockUI';
import ResultBoard from './components/ResultBoard';
import HUD from './components/HUD';

type AppState = 'PADDOCK' | 'RACING' | 'RESULT';

export default function App() {
  const [appState, setAppState] = useState<AppState>('PADDOCK');
  const [wallet, setWallet] = useState<number>(() => parseInt(localStorage.getItem('wongChoiWallet') || '1000'));
  const [jackpot, setJackpot] = useState<number>(() => parseInt(localStorage.getItem('wongChoiJackpot') || '50000'));
  const [bets, setBets] = useState<Bet[]>([]);
  const [trioBet, setTrioBet] = useState<number[] | null>(null);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  
  const engineRef = useRef<GameEngine | null>(null);
  const [phase, setPhase] = useState<RacePhase>('GATE');
  const [runners, setRunners] = useState<RunnerState[]>([]);
  const [finalResults, setFinalResults] = useState<RunnerState[]>([]);
  
  // Environment State
  const [environment, setEnvironment] = useState<{venue: 'shatin'|'happy_valley', surface: 'turf'|'dirt'}>({
      venue: 'shatin', surface: 'turf'
  });
  
  // Results payout state
  const [currentPayout, setCurrentPayout] = useState<number>(0);
  const [trioWinStatus, setTrioWinStatus] = useState<boolean>(false);
  const [jackpotWinAmount, setJackpotWinAmount] = useState<number>(0);
  
  const RACE_DISTANCE = 2000;
  const SEED_PREFIX = useRef(Date.now()); // Unique seed per session/race

  const loadNewRace = () => {
    SEED_PREFIX.current += 1;
    setSeed(`wong-choi-${SEED_PREFIX.current}`);
    const newCompetitors = RaceGenerator.generateRace('dummy');
    setCompetitors(newCompetitors);
    setBets([]);
    setTrioBet(null);
    setRunners([]);
    setFinalResults([]);
    setCurrentPayout(0);
    setTrioWinStatus(false);
    setJackpotWinAmount(0);
    // Randomize environment for visual variety
    const isHV = Math.random() > 0.5;
    const isDirt = Math.random() > 0.8;
    setEnvironment({
        venue: isHV ? 'happy_valley' : 'shatin',
        surface: isDirt ? 'dirt' : 'turf'
    });

    setPhase('GATE');
    setAppState('PADDOCK');
  };

  useEffect(() => {
    loadNewRace();
  }, []);

  useEffect(() => {
    localStorage.setItem('wongChoiWallet', wallet.toString());
  }, [wallet]);

  useEffect(() => {
    localStorage.setItem('wongChoiJackpot', jackpot.toString());
  }, [jackpot]);

  const handlePlaceBet = (horseId: number, type: 'WIN' | 'PLACE', amount: number) => {
    if (wallet < amount) return;
    setWallet(prev => prev - amount);
    setBets(prev => {
        const existing = prev.find(b => b.horseId === horseId && b.type === type);
        if (existing) {
            return prev.map(b => b === existing ? { ...b, amount: b.amount + amount } : b);
        }
        return [...prev, { horseId, type, amount }];
    });
  };

  const handlePlaceTrio = (horses: number[]) => {
    if (wallet < 50) return;
    setWallet(prev => prev - 50);
    setTrioBet(horses);
    setJackpot(prev => prev + 50); // pool injection
  };

  const processFinish = (results: RunnerState[]) => {
      let payout = 0;
      const first = results[0].competitor;
      const top3 = results.slice(0, 3).map(r => r.competitor.id);

      bets.forEach(b => {
          if (b.type === 'WIN' && b.horseId === first.id) {
              payout += b.amount * first.odds;
          } else if (b.type === 'PLACE' && top3.includes(b.horseId)) {
              const placeOdds = Math.max(1.1, first.odds / 3); 
              payout += b.amount * placeOdds;
          }
      });
      
      let isTrioWin = false;
      let wonJackpotPool = 0;
      if (trioBet) {
          const allInTop3 = trioBet.every(id => top3.includes(id));
          if (allInTop3) {
              isTrioWin = true;
              wonJackpotPool = jackpot;
              payout += wonJackpotPool;
              setJackpot(50000); // reset pool
          } else {
              setJackpot(prev => prev + 500); // add to pool on loss
          }
      }

      setTrioWinStatus(isTrioWin);
      setJackpotWinAmount(wonJackpotPool);
      setCurrentPayout(payout);
      setWallet(prev => prev + payout);
  };

  const handleStartRace = () => {
    engineRef.current = new GameEngine(competitors, RACE_DISTANCE);
    
    let lastRender = 0;
    engineRef.current.onTick = (currentRunners, currentPhase) => {
      const now = performance.now();
      if (now - lastRender > 33) { 
        lastRender = now;
        setRunners([...currentRunners].map(r => ({...r, position: {...r.position}})));
        setPhase(currentPhase);
      }
    };

    engineRef.current.onFinish = (finalRunners) => {
      setFinalResults([...finalRunners]);
      setPhase('FINISH');
      
      processFinish(finalRunners);
      
      setTimeout(() => {
          setAppState('RESULT');
      }, 2000);
    };

    setAppState('RACING');
    engineRef.current.start();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', backgroundColor: '#111', minHeight: '100vh', padding: '20px' }}>
      
      {appState === 'PADDOCK' && (
         <PaddockUI 
             competitors={competitors} 
             wallet={wallet} 
             jackpot={jackpot}
             bets={bets} 
             trioBet={trioBet}
             onPlaceBet={handlePlaceBet} 
             onPlaceTrio={handlePlaceTrio}
             onStartRace={handleStartRace} 
         />
      )}

      {appState === 'RACING' && (
         <div style={{ position: 'relative', width: 800, height: 400, overflow: 'hidden', border: '4px solid #333', borderRadius: 8 }}>
             <PixiApp runners={runners} phase={phase} distance={RACE_DISTANCE} environment={environment} />
             <HUD runners={runners} distance={RACE_DISTANCE} />
         </div>
      )}

      {appState === 'RESULT' && (
         <div style={{ position: 'relative', width: 800, height: 400, overflow: 'hidden', border: '4px solid #333', borderRadius: 8 }}>
             <PixiApp runners={finalResults} phase={phase} distance={RACE_DISTANCE} environment={environment} />
             <HUD runners={finalResults} distance={RACE_DISTANCE} />
             <ResultBoard 
                 results={finalResults} 
                 totalPayout={currentPayout} 
                 trioWin={trioWinStatus}
                 jackpotWin={jackpotWinAmount}
                 onNextRace={loadNewRace} 
             />
         </div>
      )}

    </div>
  );
}
