import { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ErrorBanner from '../components/shared/ErrorBanner';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import StatusBadge from '../components/shared/StatusBadge';
import ConfidenceBar from '../components/shared/ConfidenceBar';
import { useBatchUpload, useBatchStatus } from '../api/verifications';
import { getErrorMessage } from '../api/errors';

interface PdfEntry {
  file: File;
  assignedImageIndices: number[];
}

export default function BatchPage() {
  const navigate = useNavigate();
  const batchMutation = useBatchUpload();

  const [pdfs, setPdfs] = useState<PdfEntry[]>([]);
  const [images, setImages] = useState<File[]>([]);
  const [batchId, setBatchId] = useState<string | undefined>();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const pdfInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const { data: batchData } = useBatchStatus(batchId);

  const handlePdfFiles = useCallback((files: FileList | null) => {
    if (!files) return;
    const newPdfs: PdfEntry[] = Array.from(files).map((f) => ({
      file: f,
      assignedImageIndices: [],
    }));
    setPdfs((prev) => [...prev, ...newPdfs]);
  }, []);

  const handleImageFiles = useCallback((files: FileList | null) => {
    if (!files) return;
    setImages((prev) => [...prev, ...Array.from(files)]);
  }, []);

  const toggleImageAssignment = useCallback(
    (pdfIndex: number, imageIndex: number) => {
      setPdfs((prev) =>
        prev.map((entry, i) => {
          if (i !== pdfIndex) return entry;
          const indices = entry.assignedImageIndices.includes(imageIndex)
            ? entry.assignedImageIndices.filter((idx) => idx !== imageIndex)
            : [...entry.assignedImageIndices, imageIndex];
          return { ...entry, assignedImageIndices: indices };
        })
      );
    },
    []
  );

  const removePdf = useCallback((index: number) => {
    setPdfs((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const removeImage = useCallback((index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
    setPdfs((prev) =>
      prev.map((entry) => ({
        ...entry,
        assignedImageIndices: entry.assignedImageIndices
          .filter((idx) => idx !== index)
          .map((idx) => (idx > index ? idx - 1 : idx)),
      }))
    );
  }, []);

  const handleSubmit = async () => {
    if (pdfs.length === 0) {
      setSubmitError('Please upload at least one application PDF.');
      return;
    }
    if (images.length === 0) {
      setSubmitError('Please upload at least one label image.');
      return;
    }

    const unassigned = pdfs.some((p) => p.assignedImageIndices.length === 0);
    if (unassigned) {
      setSubmitError('Each PDF must have at least one image assigned.');
      return;
    }

    try {
      setSubmitError(null);
      const result = await batchMutation.mutateAsync({
        pdfs: pdfs.map((p) => p.file),
        images,
        imageAssignments: pdfs.map((p) => p.assignedImageIndices),
      });
      setBatchId(result.batch_id);
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
              Upload multiple application PDFs and label images, then assign
              which images belong to each application.
            </p>
          </div>

          {/* PDF upload */}
          <div style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.95rem', marginBottom: '0.5rem' }}>
              Application PDFs
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
              <span className="zone-label">Drop PDFs here or click to browse</span>
            </div>
            {pdfs.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, marginTop: '0.5rem' }}>
                {pdfs.map((entry, i) => (
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
                    <span style={{ fontWeight: 500 }}>{entry.file.name}</span>
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

          {/* Image upload */}
          <div style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.95rem', marginBottom: '0.5rem' }}>
              Label Images
            </h3>
            <div
              className="upload-zone"
              onClick={() => imageInputRef.current?.click()}
              onDrop={(e) => {
                e.preventDefault();
                handleImageFiles(e.dataTransfer.files);
              }}
              onDragOver={(e) => e.preventDefault()}
              style={{ cursor: 'pointer' }}
            >
              <input
                ref={imageInputRef}
                type="file"
                accept="image/jpeg,image/png,image/tiff"
                multiple
                onChange={(e) => handleImageFiles(e.target.files)}
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
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <span className="zone-label">Drop images here or click to browse</span>
            </div>
            {images.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                  marginTop: '0.75rem',
                }}
              >
                {images.map((img, i) => (
                  <div
                    key={i}
                    style={{
                      position: 'relative',
                      width: 80,
                      textAlign: 'center',
                    }}
                  >
                    <img
                      src={URL.createObjectURL(img)}
                      alt={img.name}
                      style={{
                        width: 80,
                        height: 80,
                        objectFit: 'cover',
                        borderRadius: 6,
                        border: '1px solid var(--slate-200)',
                      }}
                    />
                    <div
                      style={{
                        fontSize: '0.7rem',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {img.name}
                    </div>
                    <button
                      onClick={() => removeImage(i)}
                      style={{
                        position: 'absolute',
                        top: -6,
                        right: -6,
                        background: 'var(--red-600)',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '50%',
                        width: 18,
                        height: 18,
                        fontSize: '0.65rem',
                        cursor: 'pointer',
                        lineHeight: '18px',
                      }}
                    >
                      X
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Assignment UI */}
          {pdfs.length > 0 && images.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '0.95rem', marginBottom: '0.5rem' }}>
                Assign Images to PDFs
              </h3>
              <p style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.75rem' }}>
                For each PDF, check which label images belong to it.
              </p>
              <table className="history-table" style={{ fontSize: '0.85rem' }}>
                <thead>
                  <tr>
                    <th>Application PDF</th>
                    {images.map((img, i) => (
                      <th key={i} style={{ textAlign: 'center', maxWidth: 90 }}>
                        <div
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {img.name}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pdfs.map((entry, pdfIdx) => (
                    <tr key={pdfIdx}>
                      <td style={{ fontWeight: 500 }}>{entry.file.name}</td>
                      {images.map((_, imgIdx) => (
                        <td key={imgIdx} style={{ textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={entry.assignedImageIndices.includes(imgIdx)}
                            onChange={() => toggleImageAssignment(pdfIdx, imgIdx)}
                            style={{ width: 18, height: 18, cursor: 'pointer' }}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

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
                  `Start Batch (${pdfs.length} application${pdfs.length !== 1 ? 's' : ''})`
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
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {batchData.items.map((item) => (
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
                    <td style={{ fontSize: '0.8rem' }}>
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {isDone && (
            <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
              <button
                className="btn-verify"
                onClick={() => {
                  setBatchId(undefined);
                  setPdfs([]);
                  setImages([]);
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
