import StatusBadge from '../shared/StatusBadge';
import ConfidenceBar from '../shared/ConfidenceBar';
import ExtractionQualityBadge from '../shared/ExtractionQualityBadge';
import { FIELD_LABELS } from '../../lib/constants';
import type { FieldComparisonResult } from '../../api/types';

interface ComparisonRowProps {
  field: FieldComparisonResult;
  isHighlighted: boolean;
  onHover: (fieldName: string | null) => void;
  onOverride: (fieldName: string) => void;
  onConfirmReview?: (fieldName: string) => void;
}

const statusBorder: Record<string, string> = {
  match: '#22c55e',
  content_mismatch: '#ef4444',
  field_missing: '#ef4444',
  extraction_uncertain: '#eab308',
};

export default function ComparisonRow({ field, isHighlighted, onHover, onOverride, onConfirmReview }: ComparisonRowProps) {
  const needsReview = field.status === 'extraction_uncertain' && !field.reviewed;

  return (
    <tr
      onMouseEnter={() => onHover(field.field_name)}
      onMouseLeave={() => onHover(null)}
      className={`comparison-row${isHighlighted ? ' highlighted' : ''}`}
      style={{ borderLeft: `4px solid ${statusBorder[field.status] || '#d1d5db'}` }}
    >
      <td className="comparison-cell-field">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          {/* Review status icon */}
          {field.status === 'extraction_uncertain' && (
            <span
              title={field.reviewed ? 'Reviewed' : 'Needs review'}
              style={{ fontSize: '0.9rem', lineHeight: 1 }}
            >
              {field.reviewed ? '\u2705' : '\u26A0\uFE0F'}
            </span>
          )}
          {FIELD_LABELS[field.field_name] || field.field_name}
          <ExtractionQualityBadge quality={field.extraction_confidence} />
        </div>
      </td>
      <td className="comparison-cell-value">
        {field.declared_value || '-'}
      </td>
      <td className="comparison-cell-value">
        {field.extracted_value || '-'}
      </td>
      <td className="comparison-cell">
        <StatusBadge status={field.status} size="sm" />
      </td>
      <td className="comparison-cell">
        <div title={field.confidence_reason || undefined}>
          <ConfidenceBar value={field.confidence} />
        </div>
      </td>
      <td className="comparison-cell">
        <div style={{ display: 'flex', gap: '0.3rem' }}>
          {needsReview && onConfirmReview && (
            <button
              className="btn-override"
              style={{ backgroundColor: 'var(--emerald-50)', borderColor: 'var(--emerald-300)', color: 'var(--emerald-700)', fontSize: '0.75rem' }}
              onClick={() => onConfirmReview(field.field_name)}
            >
              Confirm
            </button>
          )}
          <button className="btn-override" onClick={() => onOverride(field.field_name)}>
            Override
          </button>
        </div>
      </td>
    </tr>
  );
}
