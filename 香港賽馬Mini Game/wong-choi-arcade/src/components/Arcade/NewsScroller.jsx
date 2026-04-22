/**
 * 旺財晨報 — 賽前情報捲動條
 */
import { useState, useEffect } from 'react';

export default function NewsScroller({ intel }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (!intel || intel.length === 0) return;
    const timer = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % intel.length);
    }, 4000);
    return () => clearInterval(timer);
  }, [intel]);

  if (!intel || intel.length === 0) return null;

  return (
    <div className="news-scroller">
      <div className="news-header">📰 旺財晨報</div>
      <div className="news-ticker">
        <div className="news-item" key={currentIndex}>
          {intel[currentIndex].text}
        </div>
      </div>
      <div className="news-dots">
        {intel.map((_, i) => (
          <span key={i} className={`dot ${i === currentIndex ? 'active' : ''}`} />
        ))}
      </div>
    </div>
  );
}
