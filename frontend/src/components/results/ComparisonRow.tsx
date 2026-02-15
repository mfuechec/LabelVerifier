import StatusBadge from '../shared/StatusBadge';
import ConfidenceBar from '../shared/ConfidenceBar';
import { FIELD_LABELS } from '../../lib/constants';
import type { FieldComparisonResult } from '../../api/types';

interface ComparisonRowProps {
  field: FieldComparisonResult;
  isHighlighted: boolean;
  onHover: (fieldName: string | null) => void;
  onOverride: (fieldName: string) => void;
}

const statusBorder: Record<string, string> = {
  match: '#22c55e',
  content_mismatch: '#ef4444',
  field_missing: '#ef4444',
  extraction_uncertain: '#eab308',
};

export default function ComparisonRow({ field, isHighlighted, onHover, onOverride }: ComparisonRowProps) {
  return (
    <tr
      onMouseEnter={() => onHover(field.field_name)}
      onMouseLeave={() => onHover(null)}
      className={`comparison-row${isHighlighted ? ' highlighted' : ''}`}
      style={{ borderLeft: `4px solid ${statusBorder[field.status] || '#d1d5db'}` }}
    >
      <td className="comparison-cell-field">
        {FIELD_LABELS[field.field_name] || field.field_name}
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
        <ConfidenceBar value={field.confidence} />
      </td>
      <td className="comparison-cell">
        <button className="btn-override" onClick={() => onOverride(field.field_name)}>
          Override
        </button>
      </td>
    </tr>
  );
}
