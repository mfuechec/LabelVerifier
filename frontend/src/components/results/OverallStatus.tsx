import StatusBadge from '../shared/StatusBadge';

interface OverallStatusProps {
  status: string;
  confidence: number;
  beverageType: string;
}

export default function OverallStatus({ status, confidence, beverageType }: OverallStatusProps) {
  const typeLabels: Record<string, string> = {
    distilled_spirits: 'Distilled Spirits',
    wine: 'Wine',
    beer: 'Beer',
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '1rem',
        borderRadius: '8px',
        backgroundColor: '#f9fafb',
        marginBottom: '1rem',
      }}
    >
      <div>
        <StatusBadge status={status} size="lg" />
        <span style={{ marginLeft: '1rem', color: '#6b7280', fontSize: '0.875rem' }}>
          {typeLabels[beverageType] || beverageType}
        </span>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{confidence.toFixed(0)}%</div>
        <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Overall Confidence</div>
      </div>
    </div>
  );
}
