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
    <div className="json-upload-row">
      <span>or</span>
      <label className="btn-json">
        <input type="file" accept=".json" onChange={handleFileChange} style={{ display: 'none' }} />
        Load from JSON
      </label>
    </div>
  );
}
