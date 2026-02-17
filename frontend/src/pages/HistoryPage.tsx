import { useState } from 'react';
import HistoryFilters from '../components/history/HistoryFilters';
import HistoryTable from '../components/history/HistoryTable';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import { useVerifications } from '../api/verifications';

export default function HistoryPage() {
  const [status, setStatus] = useState('');
  const [beverageType, setBeverageType] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useVerifications({
    status: status || undefined,
    beverage_type: beverageType || undefined,
    brand: search || undefined,
    page,
    per_page: 20,
  });

  return (
    <div>
      <h2>Verification History</h2>

      <HistoryFilters
        status={status}
        beverageType={beverageType}
        search={search}
        onStatusChange={setStatus}
        onBeverageTypeChange={setBeverageType}
        onSearchChange={setSearch}
      />

      {isLoading ? (
        <LoadingSpinner message="Loading history..." />
      ) : (
        <>
          <HistoryTable items={data?.items || []} />
          {data && data.total > 20 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                style={{ padding: '0.5rem 1rem', border: '1px solid #d1d5db', borderRadius: '4px', cursor: 'pointer' }}
              >
                Previous
              </button>
              <span style={{ padding: '0.5rem', color: '#6b7280' }}>
                Page {page} of {Math.ceil(data.total / 20)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(data.total / 20)}
                style={{ padding: '0.5rem 1rem', border: '1px solid #d1d5db', borderRadius: '4px', cursor: 'pointer' }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
