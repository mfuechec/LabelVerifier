import StatusBadge from '../shared/StatusBadge';
import type { FieldComparisonResult, ReviewSummary } from '../../api/types';

interface OverallStatusProps {
  status: string;
  confidence: number;
  beverageType: string;
  fields?: FieldComparisonResult[];
  reviewSummary?: ReviewSummary | null;
}

export default function OverallStatus({ status, confidence, beverageType, fields, reviewSummary }: OverallStatusProps) {
  const typeLabels: Record<string, string> = {
    distilled_spirits: 'Distilled Spirits',
    wine: 'Wine',
    beer: 'Beer',
  };

  // Compute field breakdown
  const matchCount = fields?.filter((f) => f.status === 'match').length || 0;
  const uncertainCount = fields?.filter((f) => f.status === 'extraction_uncertain').length || 0;
  const failCount = fields?.filter((f) => f.status === 'content_mismatch' || f.status === 'field_missing').length || 0;

  return (
    <div className="results-overall">
      <div>
        <StatusBadge status={status} size="lg" />
        <span className="results-overall-info">
          {typeLabels[beverageType] || beverageType}
        </span>

        {fields && fields.length > 0 && (
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
            {matchCount > 0 && (
              <span style={{ fontSize: '0.8rem', padding: '0.15rem 0.5rem', borderRadius: '12px', backgroundColor: 'var(--emerald-100)', color: 'var(--emerald-700)' }}>
                {matchCount} match{matchCount !== 1 ? 'es' : ''}
              </span>
            )}
            {uncertainCount > 0 && (
              <span style={{ fontSize: '0.8rem', padding: '0.15rem 0.5rem', borderRadius: '12px', backgroundColor: 'var(--yellow-100)', color: 'var(--yellow-700)' }}>
                {uncertainCount} need{uncertainCount !== 1 ? '' : 's'} review
              </span>
            )}
            {failCount > 0 && (
              <span style={{ fontSize: '0.8rem', padding: '0.15rem 0.5rem', borderRadius: '12px', backgroundColor: 'var(--red-100)', color: 'var(--red-700)' }}>
                {failCount} failed
              </span>
            )}
          </div>
        )}

        {status === 'needs_review' && reviewSummary && reviewSummary.fields_needing_review > 0 && (
          <div style={{ fontSize: '0.8rem', color: 'var(--yellow-700)', marginTop: '0.3rem' }}>
            {reviewSummary.fields_needing_review} field{reviewSummary.fields_needing_review > 1 ? 's have' : ' has'} uncertain extraction
          </div>
        )}
      </div>
      <div className="results-confidence">
        <div className="results-confidence-value">{confidence.toFixed(0)}%</div>
        <div className="results-confidence-label">Overall Confidence</div>
      </div>
    </div>
  );
}
