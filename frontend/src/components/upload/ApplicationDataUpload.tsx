import type { ApplicationData } from '../../api/types';

interface ApplicationDataUploadProps {
  onDataLoaded: (data: ApplicationData) => void;
}

export default function ApplicationDataUpload({ onDataLoaded }: ApplicationDataUploadProps) {
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const data = JSON.parse(text) as ApplicationData;
      onDataLoaded(data);
    } catch {
      alert('Invalid JSON file. Please check the format.');
    }
  };

  return (
    <div style={{ marginTop: '0.5rem' }}>
      <label
        style={{
          display: 'inline-block',
          padding: '0.5rem 1rem',
          border: '1px solid #d1d5db',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '0.875rem',
          color: '#4b5563',
        }}
      >
        <input type="file" accept=".json" onChange={handleFileChange} style={{ display: 'none' }} />
        Upload JSON File
      </label>
    </div>
  );
}
