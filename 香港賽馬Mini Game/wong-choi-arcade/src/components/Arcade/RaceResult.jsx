/**
 * 賽後結算組件
 */
export default function RaceResult({ result, bets, balance, onNext }) {
  if (!result) return null;
  const top3 = result.positions.slice(0, 3);
  return (
    <div className="race-result">
      <h2>🏆 賽果</h2>
      <div className="result-board">
        {top3.map((r, i) => (
          <div key={r.horse.id} className={`result-row pos-${i + 1}`}>
            <span className="pos-num">{['🥇','🥈','🥉'][i]}</span>
            <span className="res-name">{r.horse.name}</span>
            <span className="res-odds">@{r.odds}</span>
            <span className="res-jockey">{r.jockey.name}</span>
          </div>
        ))}
      </div>
      {result.stewardsInquiry && (
        <div className="stewards-alert">🚨 研訊燈亮起！</div>
      )}
      <div className="result-balance">
        <span>💰 餘額: ${balance?.toLocaleString()}</span>
      </div>
      <button className="btn-arcade btn-next" onClick={onNext}>
        {result.positions ? '下一場 →' : '結束'}
      </button>
    </div>
  );
}
