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

export default function ComparisonRow({ field, isHighlighted, onHover, onOverride }: ComparisonRowProps) {
  const statusBorder: Record<string, string> = {
    match: '#22c55e',
    content_mismatch: '#ef4444',
    field_missing: '#ef4444',
    extraction_uncertain: '#eab308',
  };

  return (
    <tr
      onMouseEnter={() => onHover(field.field_name)}
      onMouseLeave={() => onHover(null)}
      style={{
        borderLeft: `4px solid ${statusBorder[field.status] || '#d1d5db'}`,
        backgroundColor: isHighlighted ? '#eff6ff' : 'transparent',
        cursor: 'pointer',
      }}
    >
      <td style={{ padding: '0.75rem 0.5rem', fontWeight: 500 }}>
        {FIELD_LABELS[field.field_name] || field.field_name}
      </td>
      <td style={{ padding: '0.75rem 0.5rem', fontSize: '0.875rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {field.declared_value || '-'}
      </td>
      <td style={{ padding: '0.75rem 0.5rem', fontSize: '0.875rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {field.extracted_value || '-'}
      </td>
      <td style={{ padding: '0.75rem 0.5rem' }}>
        <StatusBadge status={field.status} size="sm" />
      </td>
      <td style={{ padding: '0.75rem 0.5rem' }}>
        <ConfidenceBar value={field.confidence} />
      </td>
      <td style={{ padding: '0.75rem 0.5rem' }}>
        <button
          onClick={() => onOverride(field.field_name)}
          style={{
            padding: '4px 8px',
            fontSize: '0.75rem',
            border: '1px solid #d1d5db',
            borderRadius: '4px',
            backgroundColor: 'white',
            cursor: 'pointer',
          }}
        >
          Override
        </button>
      </td>
    </tr>
  );
}
