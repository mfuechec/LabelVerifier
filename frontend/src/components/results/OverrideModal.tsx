import { useState } from 'react';
import { FIELD_LABELS } from '../../lib/constants';
import type { OverrideRequest } from '../../api/types';

interface OverrideModalProps {
  fieldName: string;
  onSubmit: (request: OverrideRequest) => void;
  onClose: () => void;
}

export default function OverrideModal({ fieldName, onSubmit, onClose }: OverrideModalProps) {
  const [status, setStatus] = useState<OverrideRequest['override_status']>('match');
  const [note, setNote] = useState('');

  const handleSubmit = () => {
    onSubmit({ override_status: status, note: note || undefined });
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="override-modal-title">
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 id="override-modal-title">Override: {FIELD_LABELS[fieldName] || fieldName}</h3>

        <div className="modal-field">
          <label>Status</label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as OverrideRequest['override_status'])}
          >
            <option value="match">Match</option>
            <option value="content_mismatch">Content Mismatch</option>
            <option value="field_missing">Field Missing</option>
          </select>
        </div>

        <div className="modal-field modal-field-note">
          <label>Note (optional)</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            placeholder="Explain your override..."
          />
        </div>

        <div className="modal-actions">
          <button className="btn-modal-cancel" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-modal-save" onClick={handleSubmit}>
            Save Override
          </button>
        </div>
      </div>
    </div>
  );
}
