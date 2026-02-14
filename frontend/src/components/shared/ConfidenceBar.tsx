interface ConfidenceBarProps {
  value: number;
}

export default function ConfidenceBar({ value }: ConfidenceBarProps) {
  const color = value >= 90 ? '#22c55e' : value >= 70 ? '#eab308' : '#ef4444';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div
        style={{
          width: '60px',
          height: '8px',
          backgroundColor: '#e5e7eb',
          borderRadius: '4px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${Math.min(100, value)}%`,
            height: '100%',
            backgroundColor: color,
            borderRadius: '4px',
          }}
        />
      </div>
      <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>{value.toFixed(0)}%</span>
    </div>
  );
}
