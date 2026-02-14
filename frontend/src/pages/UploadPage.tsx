import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ImageUploadZone from '../components/upload/ImageUploadZone';
import ApplicationDataForm from '../components/upload/ApplicationDataForm';
import ApplicationDataUpload from '../components/upload/ApplicationDataUpload';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import { useVerify } from '../api/verifications';
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

  if (verifyMutation.isPending) {
    return <LoadingSpinner message="Analyzing label... This usually takes 3-5 seconds." />;
  }

  return (
    <div>
      <h2>Label Verification</h2>
      <p style={{ color: '#6b7280', marginBottom: '1.5rem' }}>
        Upload label images and enter application data to begin verification.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
        <div>
          <h3 style={{ marginBottom: '1rem' }}>Label Images</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <ImageUploadZone label="Front Label" panelType="front" file={images.front} onFileSelect={handleFileSelect} />
            <ImageUploadZone label="Back Label" panelType="back" file={images.back} onFileSelect={handleFileSelect} />
            <ImageUploadZone label="Other" panelType="other" file={images.other} onFileSelect={handleFileSelect} />
          </div>

          <div style={{ marginTop: '1rem' }}>
            <p style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>
              Or load application data from a JSON file:
            </p>
            <ApplicationDataUpload onDataLoaded={setAppData} />
          </div>
        </div>

        <div>
          <ApplicationDataForm data={appData} onChange={setAppData} />
        </div>
      </div>

      <div style={{ marginTop: '2rem', textAlign: 'center' }}>
        <button
          onClick={handleSubmit}
          disabled={verifyMutation.isPending}
          style={{
            padding: '0.75rem 3rem',
            fontSize: '1.1rem',
            fontWeight: 600,
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
          }}
        >
          Verify Label
        </button>
      </div>
    </div>
  );
}
