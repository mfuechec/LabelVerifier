import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ImageUploadZone from '../components/upload/ImageUploadZone';
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

  const [images, setImages] = useState<Record<string, File | null>>({
    front: null,
    back: null,
    other: null,
  });
  const [applicationPdf, setApplicationPdf] = useState<File | null>(null);

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

  const handleFileSelect = useCallback((file: File, panel: string) => {
    setImages((prev) => ({ ...prev, [panel]: file }));
  }, []);

  const handlePdfSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setApplicationPdf(file);
  }, []);

  const handlePdfDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) setApplicationPdf(file);
  }, []);

  const handleSubmit = async () => {
    const imageFiles: File[] = [];
    const panels: string[] = [];

    for (const [panel, file] of Object.entries(images)) {
      if (file) {
        imageFiles.push(file);
        panels.push(panel);
      }
    }

    if (imageFiles.length === 0) {
      setSubmitError('Please upload at least one label image.');
      return;
    }
    if (!applicationPdf) {
      setSubmitError('Please upload the application PDF.');
      return;
    }

    try {
      setSubmitError(null);
      const result = await verifyMutation.mutateAsync({
        images: imageFiles,
        panels,
        applicationPdf,
      });
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
          <p>Upload an application PDF and label images to verify TTB compliance.</p>
        </div>

        <div className="upload-grid">
          <div className="images-column">
            <div className="images-column-label">Label Images</div>
            <ImageUploadZone label="Front Label" panelType="front" file={images.front} onFileSelect={handleFileSelect} />
            <ImageUploadZone label="Back Label" panelType="back" file={images.back} onFileSelect={handleFileSelect} />
            <ImageUploadZone label="Other" panelType="other" file={images.other} onFileSelect={handleFileSelect} />
          </div>

          <div>
            <div className="form-card">
              <div className="form-card-label">Application Data</div>
              <label
                className={`upload-zone pdf-zone${applicationPdf ? ' has-file' : ''}`}
                onDrop={handlePdfDrop}
                onDragOver={(e) => e.preventDefault()}
              >
                <input
                  type="file"
                  accept="application/pdf"
                  onChange={handlePdfSelect}
                  style={{ display: 'none' }}
                />
                {applicationPdf ? (
                  <>
                    <svg className="zone-svg-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                    <span className="zone-label">Application PDF</span>
                    <span className="zone-filename">{applicationPdf.name}</span>
                  </>
                ) : (
                  <>
                    <svg className="zone-svg-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                    <span className="zone-label">Application PDF</span>
                    <span className="zone-hint">Drop or click to browse</span>
                  </>
                )}
              </label>
            </div>
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
