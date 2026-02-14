interface ConfidenceBarProps {
  value: number;
}

export default function ConfidenceBar({ value }: ConfidenceBarProps) {
  const color =
    value >= 90 ? 'var(--emerald-600)' :
    value >= 70 ? 'var(--yellow-500)' :
    'var(--red-600)';

  return (
    <div className="confidence-bar-container">
      <div className="confidence-bar-track">
        <div
          className="confidence-bar-fill"
          style={{ width: `${Math.min(100, value)}%`, backgroundColor: color }}
        />
      </div>
      <span className="confidence-bar-label">{value.toFixed(0)}%</span>
    </div>
  );
}
