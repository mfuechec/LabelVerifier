import { useNavigate } from 'react-router-dom';
import StatusBadge from '../shared/StatusBadge';
import type { HistoryItem } from '../../api/types';

interface HistoryTableProps {
  items: HistoryItem[];
}

export default function HistoryTable({ items }: HistoryTableProps) {
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>
        No verification records found.
      </div>
    );
  }

  const typeLabels: Record<string, string> = {
    distilled_spirits: 'Spirits',
    wine: 'Wine',
    beer: 'Beer',
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
          <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Brand</th>
          <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Type</th>
          <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Status</th>
          <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Confidence</th>
          <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Decision</th>
          <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: '0.75rem', color: '#6b7280' }}>Date</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={item.session_id}
            onClick={() => navigate(`/verify/${item.session_id}`)}
            style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }}
          >
            <td style={{ padding: '0.75rem 0.5rem', fontWeight: 500 }}>{item.brand_name || '-'}</td>
            <td style={{ padding: '0.75rem 0.5rem', fontSize: '0.875rem' }}>
              {typeLabels[item.beverage_type] || item.beverage_type}
            </td>
            <td style={{ padding: '0.75rem 0.5rem' }}>
              <StatusBadge status={item.status} size="sm" />
            </td>
            <td style={{ padding: '0.75rem 0.5rem', fontSize: '0.875rem' }}>
              {item.overall_confidence?.toFixed(0) ?? '-'}%
            </td>
            <td style={{ padding: '0.75rem 0.5rem', fontSize: '0.875rem', color: '#6b7280' }}>
              {item.agent_decision || '-'}
            </td>
            <td style={{ padding: '0.75rem 0.5rem', fontSize: '0.875rem', color: '#9ca3af' }}>
              {new Date(item.created_at).toLocaleDateString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
