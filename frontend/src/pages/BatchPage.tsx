import { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ErrorBanner from '../components/shared/ErrorBanner';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import StatusBadge from '../components/shared/StatusBadge';
import ConfidenceBar from '../components/shared/ConfidenceBar';
import { useBatchUpload, useBatchStatus } from '../api/verifications';
import { getErrorMessage } from '../api/errors';

export default function BatchPage() {
  const navigate = useNavigate();
  const batchMutation = useBatchUpload();

  const [colaPdfs, setColaPdfs] = useState<File[]>([]);
  const [batchId, setBatchId] = useState<string | undefined>();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [skippedCount, setSkippedCount] = useState<number>(0);

  const pdfInputRef = useRef<HTMLInputElement>(null);

  const { data: batchData } = useBatchStatus(batchId);

  const handlePdfFiles = useCallback((files: FileList | null) => {
    if (!files) return;
    setColaPdfs((prev) => [...prev, ...Array.from(files)]);
  }, []);

  const removePdf = useCallback((index: number) => {
    setColaPdfs((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSubmit = async () => {
    if (colaPdfs.length === 0) {
      setSubmitError('Please upload at least one COLA PDF.');
      return;
    }

    try {
      setSubmitError(null);
      const result = await batchMutation.mutateAsync({ colaPdfs });
      setBatchId(result.batch_id);
      setSkippedCount(result.skipped_count ?? 0);
    } catch (err) {
      setSubmitError(getErrorMessage(err));
    }
  };

  const isProcessing = !!batchId;
  const isDone =
    batchData?.batch?.status === 'completed' ||
    batchData?.batch?.status === 'failed';
  const progress = batchData
    ? batchData.batch.completed_items + batchData.batch.failed_items
    : 0;
  const total = batchData?.batch?.total_items ?? 0;
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0;

  return (
    <div>
      {/* Upload Section */}
      {!isProcessing && (
        <section className="section-card animate-in">
          <div className="section-header">
            <h2>Batch Verification</h2>
            <p>
              Upload multiple COLA application PDFs for batch TTB compliance verification.
            </p>
          </div>

          {/* COLA PDF upload */}
          <div style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.95rem', marginBottom: '0.5rem' }}>
              COLA PDFs
            </h3>
            <div
              className="upload-zone pdf-zone"
              onClick={() => pdfInputRef.current?.click()}
              onDrop={(e) => {
                e.preventDefault();
                handlePdfFiles(e.dataTransfer.files);
              }}
              onDragOver={(e) => e.preventDefault()}
              style={{ cursor: 'pointer' }}
            >
              <input
                ref={pdfInputRef}
                type="file"
                accept="application/pdf"
                multiple
                onChange={(e) => handlePdfFiles(e.target.files)}
                style={{ display: 'none' }}
              />
              <svg
                className="zone-svg-icon"
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <span className="zone-label">Drop COLA PDFs here or click to browse</span>
            </div>
            {colaPdfs.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, marginTop: '0.5rem' }}>
                {colaPdfs.map((file, i) => (
                  <li
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.35rem 0',
                      fontSize: '0.875rem',
                    }}
                  >
                    <span style={{ fontWeight: 500 }}>{file.name}</span>
                    <button
                      onClick={() => removePdf(i)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--red-600)',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                      }}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div
            style={{
              borderTop: '1px solid var(--slate-200)',
              marginTop: '1.5rem',
              paddingTop: '1.5rem',
            }}
          >
            {submitError && <ErrorBanner message={submitError} />}
            <div className="verify-action">
              <button
                className="btn-verify"
                onClick={handleSubmit}
                disabled={batchMutation.isPending}
              >
                {batchMutation.isPending ? (
                  <>
                    <span className="spinner-sm" />
                    Starting Batch...
                  </>
                ) : (
                  `Start Batch (${colaPdfs.length} PDF${colaPdfs.length !== 1 ? 's' : ''})`
                )}
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Processing / Results Section */}
      {isProcessing && (
        <section className="section-card animate-in">
          <div className="history-header">
            <h2>
              Batch{' '}
              {batchData?.batch?.status === 'completed'
                ? 'Complete'
                : batchData?.batch?.status === 'failed'
                  ? 'Failed'
                  : 'Processing'}
            </h2>
          </div>

          {/* Skipped items warning */}
          {(skippedCount > 0 || (batchData?.skipped_items?.length ?? 0) > 0) && (
            <div
              style={{
                background: '#fffbeb',
                border: '1px solid #f59e0b',
                borderRadius: 8,
                padding: '0.75rem 1rem',
                marginBottom: '1rem',
                fontSize: '0.875rem',
                color: '#92400e',
              }}
            >
              <strong>
                {batchData?.skipped_items?.length ?? skippedCount} PDF{(batchData?.skipped_items?.length ?? skippedCount) !== 1 ? 's' : ''} skipped
              </strong>
              {batchData?.skipped_items && batchData.skipped_items.length > 0 && (
                <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem' }}>
                  {batchData.skipped_items.map((item, i) => (
                    <li key={i}>
                      <strong>{item.filename}</strong>: {item.reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Progress bar */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '0.85rem',
                marginBottom: '0.35rem',
              }}
            >
              <span>
                {progress} of {total} completed
                {batchData && batchData.batch.failed_items > 0 &&
                  ` (${batchData.batch.failed_items} failed)`}
              </span>
              <span>{pct}%</span>
            </div>
            <div
              style={{
                height: 8,
                background: 'var(--slate-200)',
                borderRadius: 4,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${pct}%`,
                  background: isDone ? 'var(--emerald-600)' : 'var(--blue-600)',
                  borderRadius: 4,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            {!isDone && (
              <div style={{ marginTop: '1rem', textAlign: 'center' }}>
                <LoadingSpinner message="Processing labels..." />
              </div>
            )}
          </div>

          {/* Results table */}
          {batchData && batchData.items.length > 0 && (
            <table className="history-table">
              <thead>
                <tr>
                  <th>Brand</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Time</th>
                  <th>Tokens</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {batchData.items.map((item) => {
                  const ps = item.processing_stats;
                  const timeFmt = ps
                    ? `${(ps.total_time_ms / 1000).toFixed(1)}s`
                    : '-';
                  const totalTokens = ps
                    ? ps.total_input_tokens + ps.total_output_tokens
                    : 0;
                  const tokensFmt = ps
                    ? totalTokens >= 1000
                      ? `${(totalTokens / 1000).toFixed(1)}K`
                      : `${totalTokens}`
                    : '-';
                  return (
                    <tr
                      key={item.session_id}
                      onClick={() => navigate(`/verify/${item.session_id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>{item.brand_name || '-'}</td>
                      <td>{item.beverage_type}</td>
                      <td>
                        <StatusBadge status={item.status} size="sm" />
                      </td>
                      <td>
                        {item.overall_confidence != null ? (
                          <ConfidenceBar value={item.overall_confidence} />
                        ) : (
                          '-'
                        )}
                      </td>
                      <td style={{ fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                        {timeFmt}
                      </td>
                      <td style={{ fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                        {tokensFmt}
                      </td>
                      <td style={{ fontSize: '0.8rem' }}>
                        {new Date(item.created_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {isDone && (
            <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
              <button
                className="btn-verify"
                onClick={() => {
                  setBatchId(undefined);
                  setColaPdfs([]);
                  setSkippedCount(0);
                }}
              >
                New Batch
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
