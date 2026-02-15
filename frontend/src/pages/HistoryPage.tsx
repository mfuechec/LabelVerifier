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

  const totalPages = data ? Math.ceil(data.total / 20) : 0;

  return (
    <div>
      <section className="section-card animate-in">
        <div className="history-header">
          <h2>Verification History</h2>
          <HistoryFilters
            status={status}
            beverageType={beverageType}
            search={search}
            onStatusChange={setStatus}
            onBeverageTypeChange={setBeverageType}
            onSearchChange={setSearch}
          />
        </div>

        {isLoading ? (
          <LoadingSpinner message="Loading history..." />
        ) : (
          <>
            <HistoryTable items={data?.items || []} />
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  Previous
                </button>
                <span className="page-info">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= totalPages}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
