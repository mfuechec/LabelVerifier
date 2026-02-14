import { BEVERAGE_TYPES } from '../../lib/constants';

interface HistoryFiltersProps {
  status: string;
  beverageType: string;
  search: string;
  onStatusChange: (status: string) => void;
  onBeverageTypeChange: (type: string) => void;
  onSearchChange: (search: string) => void;
}

export default function HistoryFilters({
  status,
  beverageType,
  search,
  onStatusChange,
  onBeverageTypeChange,
  onSearchChange,
}: HistoryFiltersProps) {
  const selectStyle: React.CSSProperties = {
    padding: '0.5rem',
    border: '1px solid #d1d5db',
    borderRadius: '4px',
    fontSize: '0.875rem',
  };

  return (
    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
      <select value={status} onChange={(e) => onStatusChange(e.target.value)} style={selectStyle}>
        <option value="">All Statuses</option>
        <option value="pass">Pass</option>
        <option value="needs_review">Needs Review</option>
        <option value="fail">Fail</option>
      </select>

      <select value={beverageType} onChange={(e) => onBeverageTypeChange(e.target.value)} style={selectStyle}>
        <option value="">All Types</option>
        {BEVERAGE_TYPES.map((t) => (
          <option key={t.value} value={t.value}>{t.label}</option>
        ))}
      </select>

      <input
        type="text"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search by brand..."
        style={{ ...selectStyle, flex: 1, minWidth: '200px' }}
      />
    </div>
  );
}
