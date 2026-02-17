import ComparisonRow from './ComparisonRow';
import type { FieldComparisonResult } from '../../api/types';

interface ComparisonTableProps {
  fields: FieldComparisonResult[];
  highlightedField: string | null;
  onFieldHover: (fieldName: string | null) => void;
  onOverride: (fieldName: string) => void;
}

export default function ComparisonTable({ fields, highlightedField, onFieldHover, onOverride }: ComparisonTableProps) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Field</th>
            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Declared</th>
            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Extracted</th>
            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Status</th>
            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Confidence</th>
            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <ComparisonRow
              key={field.field_name}
              field={field}
              isHighlighted={highlightedField === field.field_name}
              onHover={onFieldHover}
              onOverride={onOverride}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
