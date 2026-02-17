import { useState } from 'react';

interface AgentDecisionBarProps {
  onDecision: (decision: 'confirmed' | 'overridden', notes?: string) => void;
  isSubmitting: boolean;
}

export default function AgentDecisionBar({ onDecision, isSubmitting }: AgentDecisionBarProps) {
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState('');

  return (
    <div className="agent-decision-bar">
      <p>Agent Decision</p>

      {showNotes && (
        <div className="agent-decision-notes">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Add notes for your override decision..."
          />
        </div>
      )}

      <div className="agent-decision-buttons">
        <button
          className="btn-confirm"
          onClick={() => onDecision('confirmed', notes || undefined)}
          disabled={isSubmitting}
        >
          Confirm AI Result
        </button>
        <button
          className="btn-override-decision"
          onClick={() => {
            if (!showNotes) {
              setShowNotes(true);
            } else {
              onDecision('overridden', notes || undefined);
            }
          }}
          disabled={isSubmitting}
        >
          {showNotes ? 'Submit Override' : 'Override'}
        </button>
      </div>
    </div>
  );
}
