import { useCallback, useState, useEffect } from 'react';

interface ImageUploadZoneProps {
  label: string;
  panelType: string;
  file: File | null;
  onFileSelect: (file: File, panel: string) => void;
}

export default function ImageUploadZone({ label, panelType, file, onFileSelect }: ImageUploadZoneProps) {
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) onFileSelect(droppedFile, panelType);
    },
    [onFileSelect, panelType]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (selectedFile) onFileSelect(selectedFile, panelType);
    },
    [onFileSelect, panelType]
  );

  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  useEffect(() => {
    if (file && file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      setThumbUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    setThumbUrl(null);
  }, [file]);

  const zoneClass = `upload-zone${file ? ' has-file' : ''}${dragging ? ' dragging' : ''}`;

  return (
    <label
      className={zoneClass}
      onDrop={handleDrop}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
    >
      <input
        type="file"
        accept="image/jpeg,image/png,image/tiff,application/pdf"
        onChange={handleChange}
        style={{ display: 'none' }}
      />
      {file && thumbUrl ? (
        <>
          <img src={thumbUrl} alt={label} className="zone-thumb" />
          <span className="zone-filename">{file.name}</span>
        </>
      ) : file ? (
        <>
          <svg className="zone-svg-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
          <span className="zone-label">{label}</span>
          <span className="zone-filename">{file.name}</span>
        </>
      ) : (
        <>
          <svg className="zone-svg-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
          <span className="zone-label">{label}</span>
          <span className="zone-hint">Drop or click to browse</span>
        </>
      )}
    </label>
  );
}
