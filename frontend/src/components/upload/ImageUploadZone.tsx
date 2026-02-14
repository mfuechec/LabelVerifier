import { useCallback } from 'react';

interface ImageUploadZoneProps {
  label: string;
  panelType: string;
  file: File | null;
  onFileSelect: (file: File, panel: string) => void;
}

export default function ImageUploadZone({ label, panelType, file, onFileSelect }: ImageUploadZoneProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
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

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      style={{
        border: `2px dashed ${file ? '#22c55e' : '#d1d5db'}`,
        borderRadius: '8px',
        padding: '1.5rem',
        textAlign: 'center',
        cursor: 'pointer',
        backgroundColor: file ? '#f0fdf4' : '#fafafa',
        minHeight: '120px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <label style={{ cursor: 'pointer', width: '100%' }}>
        <input
          type="file"
          accept="image/jpeg,image/png,image/tiff,application/pdf"
          onChange={handleChange}
          style={{ display: 'none' }}
        />
        <p style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{label}</p>
        {file ? (
          <p style={{ color: '#22c55e', fontSize: '0.875rem' }}>{file.name}</p>
        ) : (
          <p style={{ color: '#9ca3af', fontSize: '0.875rem' }}>
            Drop image here or click to browse
          </p>
        )}
      </label>
    </div>
  );
}
