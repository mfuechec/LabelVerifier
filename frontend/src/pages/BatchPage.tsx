export default function BatchPage() {
  return (
    <div>
      <h2>Batch Processing</h2>
      <p style={{ color: '#6b7280', marginBottom: '1.5rem' }}>
        Upload multiple label images and a CSV file with application data for batch verification.
      </p>

      <div
        style={{
          border: '2px dashed #d1d5db',
          borderRadius: '8px',
          padding: '3rem',
          textAlign: 'center',
          backgroundColor: '#fafafa',
        }}
      >
        <p style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Batch Upload</p>
        <p style={{ color: '#9ca3af', fontSize: '0.875rem' }}>
          Drag and drop label images and a CSV mapping file here, or click to browse.
        </p>
        <p style={{ color: '#9ca3af', fontSize: '0.75rem', marginTop: '1rem' }}>
          CSV format: application_id, brand_name, class_type, alcohol_content, net_contents, beverage_type, image_filename
        </p>
      </div>
    </div>
  );
}
