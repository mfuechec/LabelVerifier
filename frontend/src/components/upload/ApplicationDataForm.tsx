import { BEVERAGE_TYPES } from '../../lib/constants';
import type { ApplicationData } from '../../api/types';

interface ApplicationDataFormProps {
  data: ApplicationData;
  onChange: (data: ApplicationData) => void;
}

export default function ApplicationDataForm({ data, onChange }: ApplicationDataFormProps) {
  const update = (field: keyof ApplicationData, value: string | boolean) => {
    onChange({ ...data, [field]: value });
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '0.5rem',
    border: '1px solid #d1d5db',
    borderRadius: '4px',
    fontSize: '0.875rem',
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    marginBottom: '0.25rem',
    fontWeight: 500,
    fontSize: '0.875rem',
  };

  const fieldGroup: React.CSSProperties = {
    marginBottom: '0.75rem',
  };

  return (
    <div>
      <h3 style={{ marginBottom: '1rem' }}>Application Data</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
        <div style={fieldGroup}>
          <label style={labelStyle}>Brand Name *</label>
          <input style={inputStyle} value={data.brand_name} onChange={(e) => update('brand_name', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Class/Type *</label>
          <input style={inputStyle} value={data.class_type} onChange={(e) => update('class_type', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Alcohol Content *</label>
          <input style={inputStyle} value={data.alcohol_content} onChange={(e) => update('alcohol_content', e.target.value)} placeholder="e.g., 45%" />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Net Contents *</label>
          <input style={inputStyle} value={data.net_contents} onChange={(e) => update('net_contents', e.target.value)} placeholder="e.g., 750 mL" />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Beverage Type *</label>
          <select style={inputStyle} value={data.beverage_type} onChange={(e) => update('beverage_type', e.target.value)}>
            {BEVERAGE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Application ID</label>
          <input style={inputStyle} value={data.application_id || ''} onChange={(e) => update('application_id', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Producer Name</label>
          <input style={inputStyle} value={data.producer_name || ''} onChange={(e) => update('producer_name', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Producer Address</label>
          <input style={inputStyle} value={data.producer_address || ''} onChange={(e) => update('producer_address', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Country of Origin</label>
          <input style={inputStyle} value={data.country_of_origin || ''} onChange={(e) => update('country_of_origin', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Importer Name</label>
          <input style={inputStyle} value={data.importer_name || ''} onChange={(e) => update('importer_name', e.target.value)} />
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>Importer Address</label>
          <input style={inputStyle} value={data.importer_address || ''} onChange={(e) => update('importer_address', e.target.value)} />
        </div>
        <div style={{ ...fieldGroup, display: 'flex', alignItems: 'center', gap: '0.5rem', paddingTop: '1.5rem' }}>
          <input
            type="checkbox"
            checked={data.has_sulfites_declaration || false}
            onChange={(e) => update('has_sulfites_declaration', e.target.checked)}
            id="sulfites"
          />
          <label htmlFor="sulfites" style={{ fontSize: '0.875rem' }}>Contains Sulfites Declaration</label>
        </div>
      </div>
    </div>
  );
}
