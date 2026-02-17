import { useState } from 'react';

interface AgentDecisionBarProps {
  onDecision: (decision: 'confirmed' | 'overridden', notes?: string) => void;
  onFeedback: (correct: boolean) => void;
  isSubmitting: boolean;
}

export default function AgentDecisionBar({ onDecision, onFeedback, isSubmitting }: AgentDecisionBarProps) {
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleConfirm = () => {
    onDecision('confirmed', notes || undefined);
    onFeedback(true);
    setSubmitted(true);
  };

  const handleOverride = () => {
    if (!showNotes) {
      setShowNotes(true);
    } else {
      onDecision('overridden', notes || undefined);
      onFeedback(false);
      setSubmitted(true);
    }
  };

  if (submitted) {
    return (
      <div className="agent-decision-bar">
        <div className="agent-decision-success">
          <p>Decision recorded. Thank you for your feedback!</p>
        </div>
      </div>
    );
  }

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
          onClick={handleConfirm}
          disabled={isSubmitting}
        >
          Confirm AI Result
        </button>
        <button
          className="btn-override-decision"
          onClick={handleOverride}
          disabled={isSubmitting}
        >
          {showNotes ? 'Submit Override' : 'Override'}
        </button>
      </div>
    </div>
  );
}
