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
    <div className="results-overall">
      <div>
        <StatusBadge status={status} size="lg" />
        <span className="results-overall-info">
          {typeLabels[beverageType] || beverageType}
        </span>
      </div>
      <div className="results-confidence">
        <div className="results-confidence-value">{confidence.toFixed(0)}%</div>
        <div className="results-confidence-label">Overall Confidence</div>
      </div>
    </div>
  );
}
