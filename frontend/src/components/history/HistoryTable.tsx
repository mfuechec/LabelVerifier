import { useNavigate } from 'react-router-dom';
import StatusBadge from '../shared/StatusBadge';
import ConfidenceBar from '../shared/ConfidenceBar';
import type { HistoryItem } from '../../api/types';

interface HistoryTableProps {
  items: HistoryItem[];
}

const TYPE_LABELS: Record<string, string> = {
  distilled_spirits: 'Spirits',
  wine: 'Wine',
  beer: 'Beer',
};

export default function HistoryTable({ items }: HistoryTableProps) {
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <div className="history-empty">
        <div className="history-empty-icon">&#128269;</div>
        <p>No verification records found.</p>
      </div>
    );
  }

  return (
    <table className="history-table">
      <thead>
        <tr>
          <th>Brand</th>
          <th>Type</th>
          <th>Status</th>
          <th>Confidence</th>
          <th>Decision</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={item.session_id}
            onClick={() => navigate(`/verify/${item.session_id}`)}
          >
            <td className="brand-cell">{item.brand_name || '-'}</td>
            <td className="type-cell">{TYPE_LABELS[item.beverage_type] || item.beverage_type}</td>
            <td>
              <StatusBadge status={item.status} size="sm" />
            </td>
            <td>
              {item.overall_confidence != null ? (
                <ConfidenceBar value={item.overall_confidence} />
              ) : (
                <span style={{ color: 'var(--slate-400)', fontSize: '0.78rem' }}>-</span>
              )}
            </td>
            <td className="decision-cell">{item.agent_decision || '-'}</td>
            <td className="date-cell">{new Date(item.created_at).toLocaleDateString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
