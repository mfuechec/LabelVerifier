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
      <div className="feedback-success">
        <p>Thank you for your feedback!</p>
      </div>
    );
  }

  return (
    <div className="feedback-widget">
      <p>Was the AI analysis correct?</p>
      <div className="feedback-widget-buttons">
        <button
          className="btn-feedback-correct"
          onClick={() => handleClick(true)}
          disabled={isSubmitting}
        >
          AI Correct
        </button>
        <button
          className="btn-feedback-incorrect"
          onClick={() => handleClick(false)}
          disabled={isSubmitting}
        >
          AI Incorrect
        </button>
      </div>
    </div>
  );
}
