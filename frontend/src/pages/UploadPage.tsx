import { useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import HistoryFilters from '../components/history/HistoryFilters';
import HistoryTable from '../components/history/HistoryTable';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import ErrorBanner from '../components/shared/ErrorBanner';
import { useVerify, useVerifications } from '../api/verifications';
import { getErrorMessage } from '../api/errors';

export default function UploadPage() {
  const navigate = useNavigate();
  const verifyMutation = useVerify();

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [colaPdf, setColaPdf] = useState<File | null>(null);

  // History state
  const [status, setStatus] = useState('');
  const [beverageType, setBeverageType] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const { data: historyData, isLoading: historyLoading } = useVerifications({
    status: status || undefined,
    beverage_type: beverageType || undefined,
    brand: search || undefined,
    page,
    per_page: 10,
  });

  const handlePdfSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setColaPdf(file);
  }, []);

  const handlePdfDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) setColaPdf(file);
  }, []);

  const handleSubmit = async () => {
    if (!colaPdf) {
      setSubmitError('Please upload a COLA PDF.');
      return;
    }

    try {
      setSubmitError(null);
      const result = await verifyMutation.mutateAsync({ colaPdf });
      navigate(`/verify/${result.session_id}`);
    } catch (err) {
      setSubmitError(getErrorMessage(err));
      console.error(err);
    }
  };

  const totalPages = historyData ? Math.ceil(historyData.total / 10) : 0;

  return (
    <div>
      {/* Upload Section */}
      <section className="section-card animate-in">
        <div className="section-header">
          <h2>New Verification</h2>
          <p>Upload a COLA application PDF to verify TTB compliance.</p>
        </div>

        <div>
          <div className="form-card">
            <div className="form-card-label">COLA PDF</div>
            <label
              className={`upload-zone pdf-zone${colaPdf ? ' has-file' : ''}`}
              onDrop={handlePdfDrop}
              onDragOver={(e) => e.preventDefault()}
            >
              <input
                type="file"
                accept="application/pdf"
                onChange={handlePdfSelect}
                style={{ display: 'none' }}
              />
              {colaPdf ? (
                <>
                  <svg className="zone-svg-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  <span className="zone-label">COLA PDF</span>
                  <span className="zone-filename">{colaPdf.name}</span>
                </>
              ) : (
                <>
                  <svg className="zone-svg-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                  <span className="zone-label">COLA PDF</span>
                  <span className="zone-hint">Drop or click to browse</span>
                </>
              )}
            </label>
          </div>
        </div>

        <div style={{ borderTop: '1px solid var(--slate-200)', marginTop: '1.5rem', paddingTop: '1.5rem' }}>
          {submitError && <ErrorBanner message={submitError} />}
          <div className="verify-action">
            <button
              className="btn-verify"
              onClick={handleSubmit}
              disabled={verifyMutation.isPending}
            >
              {verifyMutation.isPending ? (
                <>
                  <span className="spinner-sm" />
                  Analyzing Label...
                </>
              ) : (
                'Verify Label'
              )}
            </button>
          </div>
        </div>
      </section>

      {/* History Section */}
      <section className="section-card animate-in-delay-1">
        <div className="history-header">
          <h2>Recent Verifications</h2>
          <Link to="/history" className="view-all-link">View All &rarr;</Link>
          <HistoryFilters
            status={status}
            beverageType={beverageType}
            search={search}
            onStatusChange={setStatus}
            onBeverageTypeChange={setBeverageType}
            onSearchChange={setSearch}
          />
        </div>

        {historyLoading ? (
          <LoadingSpinner message="Loading history..." />
        ) : (
          <>
            <HistoryTable items={historyData?.items || []} />
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
