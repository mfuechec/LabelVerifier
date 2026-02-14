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
  return (
    <div className="history-filters">
      <select
        className="filter-select"
        value={status}
        onChange={(e) => onStatusChange(e.target.value)}
      >
        <option value="">All Statuses</option>
        <option value="pass">Pass</option>
        <option value="needs_review">Needs Review</option>
        <option value="fail">Fail</option>
      </select>

      <select
        className="filter-select"
        value={beverageType}
        onChange={(e) => onBeverageTypeChange(e.target.value)}
      >
        <option value="">All Types</option>
        {BEVERAGE_TYPES.map((t) => (
          <option key={t.value} value={t.value}>{t.label}</option>
        ))}
      </select>

      <input
        className="filter-input"
        type="text"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search by brand..."
      />
    </div>
  );
}
