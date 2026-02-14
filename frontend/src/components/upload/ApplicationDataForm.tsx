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

  return (
    <div className="form-card">
      <div className="form-card-label">Application Data</div>
      <div className="form-grid">
        <div className="form-field">
          <label>Brand Name <span className="required">*</span></label>
          <input value={data.brand_name} onChange={(e) => update('brand_name', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Class / Type <span className="required">*</span></label>
          <input value={data.class_type} onChange={(e) => update('class_type', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Alcohol Content <span className="required">*</span></label>
          <input
            value={data.alcohol_content}
            onChange={(e) => update('alcohol_content', e.target.value)}
            placeholder="e.g., 45%"
          />
        </div>
        <div className="form-field">
          <label>Net Contents <span className="required">*</span></label>
          <input
            value={data.net_contents}
            onChange={(e) => update('net_contents', e.target.value)}
            placeholder="e.g., 750 mL"
          />
        </div>
        <div className="form-field">
          <label>Beverage Type <span className="required">*</span></label>
          <select value={data.beverage_type} onChange={(e) => update('beverage_type', e.target.value)}>
            {BEVERAGE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label>Application ID</label>
          <input value={data.application_id || ''} onChange={(e) => update('application_id', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Producer Name</label>
          <input value={data.producer_name || ''} onChange={(e) => update('producer_name', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Producer Address</label>
          <input value={data.producer_address || ''} onChange={(e) => update('producer_address', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Country of Origin</label>
          <input value={data.country_of_origin || ''} onChange={(e) => update('country_of_origin', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Importer Name</label>
          <input value={data.importer_name || ''} onChange={(e) => update('importer_name', e.target.value)} />
        </div>
        <div className="form-field">
          <label>Importer Address</label>
          <input value={data.importer_address || ''} onChange={(e) => update('importer_address', e.target.value)} />
        </div>
        <div className="form-checkbox">
          <input
            type="checkbox"
            checked={data.has_sulfites_declaration || false}
            onChange={(e) => update('has_sulfites_declaration', e.target.checked)}
            id="sulfites"
          />
          <label htmlFor="sulfites">Contains Sulfites Declaration</label>
        </div>
      </div>
    </div>
  );
}
