import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ImageUploadZone from '../components/upload/ImageUploadZone';
import ApplicationDataForm from '../components/upload/ApplicationDataForm';
import ApplicationDataUpload from '../components/upload/ApplicationDataUpload';
import HistoryFilters from '../components/history/HistoryFilters';
import HistoryTable from '../components/history/HistoryTable';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import { useVerify, useVerifications } from '../api/verifications';
import type { ApplicationData } from '../api/types';

const emptyAppData: ApplicationData = {
  brand_name: '',
  class_type: '',
  alcohol_content: '',
  net_contents: '',
  beverage_type: 'distilled_spirits',
};

export default function UploadPage() {
  const navigate = useNavigate();
  const verifyMutation = useVerify();

  const [images, setImages] = useState<Record<string, File | null>>({
    front: null,
    back: null,
    other: null,
  });
  const [appData, setAppData] = useState<ApplicationData>(emptyAppData);

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
      alert('Please upload at least one label image.');
      return;
    }
    if (!appData.brand_name || !appData.class_type || !appData.alcohol_content || !appData.net_contents) {
      alert('Please fill in all required fields (Brand Name, Class/Type, Alcohol Content, Net Contents).');
      return;
    }

    try {
      const result = await verifyMutation.mutateAsync({
        images: imageFiles,
        panels,
        applicationData: appData,
      });
      navigate(`/verify/${result.session_id}`);
    } catch (err) {
      alert('Verification failed. Please try again.');
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
          <p>Upload label images and enter application data to verify TTB compliance.</p>
        </div>

        <div className="upload-grid">
          <div className="images-column">
            <div className="images-column-label">Label Images</div>
            <ImageUploadZone label="Front Label" panelType="front" file={images.front} onFileSelect={handleFileSelect} />
            <ImageUploadZone label="Back Label" panelType="back" file={images.back} onFileSelect={handleFileSelect} />
            <ImageUploadZone label="Other" panelType="other" file={images.other} onFileSelect={handleFileSelect} />
            <ApplicationDataUpload onDataLoaded={setAppData} />
          </div>

          <div>
            <ApplicationDataForm data={appData} onChange={setAppData} />
          </div>
        </div>

        <div style={{ borderTop: '1px solid var(--slate-200)', marginTop: '1.5rem', paddingTop: '1.5rem' }}>
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
