export default function RunnerSilk({ silkUrl, horseName, size = "md" }) {
  if (!silkUrl) return null;

  return (
    <span className={`runner-silk runner-silk--${size}`}>
      <img
        src={silkUrl}
        alt={`${horseName || "馬匹"} 綵衣`}
        width="40"
        height="40"
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={(event) => {
          event.currentTarget.parentElement.hidden = true;
        }}
      />
    </span>
  );
}
