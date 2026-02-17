import { useState } from 'react';

interface FeedbackWidgetProps {
  onFeedback: (correct: boolean) => void;
  isSubmitting: boolean;
}

export default function FeedbackWidget({ onFeedback, isSubmitting }: FeedbackWidgetProps) {
  const [submitted, setSubmitted] = useState(false);

  const handleClick = (correct: boolean) => {
    onFeedback(correct);
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div style={{ padding: '0.75rem', backgroundColor: '#f0fdf4', borderRadius: '4px', textAlign: 'center' }}>
        <p style={{ color: '#22c55e', fontWeight: 500 }}>Thank you for your feedback!</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '0.75rem', backgroundColor: '#f9fafb', borderRadius: '4px' }}>
      <p style={{ fontSize: '0.875rem', marginBottom: '0.5rem', color: '#6b7280' }}>Was the AI analysis correct?</p>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button
          onClick={() => handleClick(true)}
          disabled={isSubmitting}
          style={{
            padding: '0.5rem 1rem',
            border: '1px solid #22c55e',
            borderRadius: '4px',
            backgroundColor: 'white',
            color: '#22c55e',
            cursor: 'pointer',
            flex: 1,
          }}
        >
          AI Correct
        </button>
        <button
          onClick={() => handleClick(false)}
          disabled={isSubmitting}
          style={{
            padding: '0.5rem 1rem',
            border: '1px solid #ef4444',
            borderRadius: '4px',
            backgroundColor: 'white',
            color: '#ef4444',
            cursor: 'pointer',
            flex: 1,
          }}
        >
          AI Incorrect
        </button>
      </div>
    </div>
  );
}
