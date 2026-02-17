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
    <div className="comparison-table-wrap">
      <table className="comparison-table">
        <thead>
          <tr>
            <th className="comparison-th">Field</th>
            <th className="comparison-th">Declared</th>
            <th className="comparison-th">Extracted</th>
            <th className="comparison-th">Status</th>
            <th className="comparison-th">Confidence</th>
            <th className="comparison-th">Action</th>
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
