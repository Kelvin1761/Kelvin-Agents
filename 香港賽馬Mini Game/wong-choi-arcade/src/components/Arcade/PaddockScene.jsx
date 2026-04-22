/**
 * 旺財街機 — 閘前場景
 * 用 AI 生成嘅像素畫做背景
 * mode: warmup / entering / ready
 */
import { useState, useEffect } from 'react';
import './PaddockScene.css';

export default function PaddockScene({ runners = [], mode = 'warmup' }) {
  const [gateProgress, setGateProgress] = useState(0);

  useEffect(() => {
    if (mode !== 'entering') {
      setGateProgress(0);
      return;
    }
    let count = 0;
    const timer = setInterval(() => {
      count++;
      setGateProgress(count);
      if (count >= runners.length) clearInterval(timer);
    }, 400);
    return () => clearInterval(timer);
  }, [mode, runners.length]);

  return (
    <div className={`paddock-scene paddock-${mode}`}>
      {/* Background image */}
      <div className="ps-bg" />
      
      {/* Overlay effects per mode */}
      {mode === 'warmup' && (
        <div className="ps-overlay ps-warmup-overlay">
          <div className="ps-scan-line" />
        </div>
      )}

      {mode === 'entering' && (
        <div className="ps-overlay ps-entering-overlay">
          <div className="ps-gate-progress">
            <div className="ps-gate-bar" style={{ width: `${(gateProgress / runners.length) * 100}%` }} />
          </div>
        </div>
      )}

      {mode === 'ready' && (
        <div className="ps-overlay ps-ready-overlay" />
      )}

      {/* Label */}
      <div className="ps-label">
        {mode === 'warmup' && '🏇 閘前熱身中...'}
        {mode === 'entering' && `🚪 入閘中... (${Math.min(gateProgress, runners.length)}/${runners.length})`}
        {mode === 'ready' && '✅ 全部入閘！即將開跑...'}
      </div>
    </div>
  );
}
