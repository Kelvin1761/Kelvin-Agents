/**
 * 賽日總結組件
 */
const RATINGS = [
  { grade: 'S', label: '傳奇', min: 5000, color: '#FFD700' },
  { grade: 'A', label: '高手', min: 2000, color: '#FF6347' },
  { grade: 'B', label: '穩健', min: 500, color: '#4169E1' },
  { grade: 'C', label: '普通', min: 0, color: '#32CD32' },
  { grade: 'D', label: '輸家', min: -500, color: '#808080' },
  { grade: 'F', label: '破產', min: -Infinity, color: '#8B0000' },
];

export default function DaySummary({ players, raceHistory, loanCount, onPlayAgain }) {
  const player = players[0];
  if (!player) return null;
  const profit = player.balance - 1000;
  const ratingObj = loanCount > 0
    ? RATINGS.find(r => r.grade === 'F')
    : RATINGS.find(r => profit >= r.min);

  return (
    <div className="day-summary">
      <h2>📊 賽日總結</h2>
      <div className="summary-grade" style={{ color: ratingObj.color }}>
        <span className="grade-letter">{ratingObj.grade}</span>
        <span className="grade-label">{ratingObj.label}</span>
      </div>
      <div className="summary-stats">
        <div className="stat-item">
          <span>💰 最終餘額</span>
          <span>${player.balance.toLocaleString()}</span>
        </div>
        <div className="stat-item">
          <span>{profit >= 0 ? '📈' : '📉'} 盈虧</span>
          <span style={{ color: profit >= 0 ? '#32CD32' : '#FF6347' }}>
            {profit >= 0 ? '+' : ''}{profit.toLocaleString()}
          </span>
        </div>
        <div className="stat-item">
          <span>🏇 完成場數</span>
          <span>{raceHistory.length} / 10</span>
        </div>
        {loanCount > 0 && (
          <div className="stat-item loan-warning">
            <span>💀 借貸次數</span>
            <span>{loanCount}</span>
          </div>
        )}
      </div>
      <button className="btn-arcade btn-play-again" onClick={onPlayAgain}>
        🔄 再嚟一日
      </button>
    </div>
  );
}
