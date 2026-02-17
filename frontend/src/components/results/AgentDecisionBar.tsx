import { useState } from 'react';

interface AgentDecisionBarProps {
  onDecision: (decision: 'confirmed' | 'overridden', notes?: string) => void;
  isSubmitting: boolean;
}

export default function AgentDecisionBar({ onDecision, isSubmitting }: AgentDecisionBarProps) {
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState('');

  return (
    <div
      style={{
        padding: '1rem',
        borderTop: '1px solid #e5e7eb',
        marginTop: '1rem',
      }}
    >
      <p style={{ fontWeight: 600, marginBottom: '0.75rem' }}>Agent Decision</p>

      {showNotes && (
        <div style={{ marginBottom: '0.75rem' }}>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Add notes for your override decision..."
            style={{ width: '100%', padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '4px', resize: 'vertical' }}
          />
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <button
          onClick={() => onDecision('confirmed', notes || undefined)}
          disabled={isSubmitting}
          style={{
            padding: '0.75rem 1.5rem',
            fontSize: '1rem',
            fontWeight: 600,
            backgroundColor: '#22c55e',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            flex: 1,
          }}
        >
          Confirm AI Result
        </button>
        <button
          onClick={() => {
            if (!showNotes) {
              setShowNotes(true);
            } else {
              onDecision('overridden', notes || undefined);
            }
          }}
          disabled={isSubmitting}
          style={{
            padding: '0.75rem 1.5rem',
            fontSize: '1rem',
            fontWeight: 600,
            backgroundColor: '#ef4444',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            flex: 1,
          }}
        >
          {showNotes ? 'Submit Override' : 'Override'}
        </button>
      </div>
    </div>
  );
}
