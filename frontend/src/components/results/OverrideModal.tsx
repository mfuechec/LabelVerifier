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
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: 'white',
          borderRadius: '12px',
          padding: '2rem',
          width: '400px',
          maxWidth: '90vw',
        }}
      >
        <h3 style={{ marginBottom: '1rem' }}>Override: {FIELD_LABELS[fieldName] || fieldName}</h3>

        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Status</label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as OverrideRequest['override_status'])}
            style={{ width: '100%', padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '4px' }}
          >
            <option value="match">Match</option>
            <option value="content_mismatch">Content Mismatch</option>
            <option value="field_missing">Field Missing</option>
          </select>
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Note (optional)</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            style={{ width: '100%', padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '4px', resize: 'vertical' }}
            placeholder="Explain your override..."
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{ padding: '0.5rem 1rem', border: '1px solid #d1d5db', borderRadius: '4px', backgroundColor: 'white', cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            style={{ padding: '0.5rem 1rem', backgroundColor: '#2563eb', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Save Override
          </button>
        </div>
      </div>
    </div>
  );
}
